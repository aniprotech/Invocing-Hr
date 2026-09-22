"""Chasing: the reminder sequence a business sets, and the late fee at the
end of it.

A business sets its own steps - a nudge before the due date, a firmer word
after, a final notice - each in its own tone and with its own sentence if
it wants one. Each step goes out once. A customer can be left out; an
invoice can be paused while something is sorted out. After the grace days
a late fee goes on the invoice as its own line, once or monthly, the
customer is told, and it can be let off - by the button or by taking the
line off the invoice. Nothing crosses a business.
"""
import uuid
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    clear_runs()
    yield


def clear_runs():
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, *a, **kw: (sent.append({"to": to, "subject": subject, "body": body, "html": html_body}), (True, ""))[1])
    return sent


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def uniq(stem):
    return f"{stem}-{uuid.uuid4().hex[:6]}@example.com"


def inv_due(tenant, days_ago, contact="Late Payer", email=None, total=100.0):
    """An invoice whose due date was `days_ago` days ago (negative: ahead)."""
    return make_invoice(tenant, status="Awaiting Payment", contact=contact, email=email or uniq("payer"),
                        issue_date=d(-days_ago - 14), due_date=d(-days_ago), tax_type="none",
                        line_items=[{"description": "Work", "qty": 1, "price": float(total), "tax_rate": "No Tax"}])


def chase_all():
    main.run_due_jobs(only="overdue_reminders")
    clear_runs()


def fee_all():
    main.run_due_jobs(only="late_fees")
    clear_runs()


def mine(outbox, email):
    return [m for m in outbox if m["to"] == email]


def set_policy(tenant, **body):
    res = tenant.put("/api/dunning", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def move_due(inv, days_ago):
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == inv["tracking_id"]).first()
        row.due_date = d(-days_ago)
        db.commit()


# --- the policy ---------------------------------------------------------------

def test_the_default_sequence_is_the_old_ladder(tenant):
    p = tenant.get("/api/dunning").json()
    assert p["enabled"] is True
    assert [s["days"] for s in p["steps"]] == [1, 7, 14, 30]
    assert [s["tone"] for s in p["steps"]] == ["gentle", "firm", "firm", "final"]
    assert p["late_fee"]["enabled"] is False
    assert [s["subject"] for s in p["samples"]][0].startswith("Reminder: invoice INV-0042 is 1 day overdue")
    assert "Final notice" in p["samples"][-1]["subject"]


def test_a_business_sets_its_own_steps_and_bad_ones_are_refused(tenant):
    p = set_policy(tenant, steps=[{"days": 7, "tone": "firm"}, {"days": -3, "tone": "gentle", "message": "Thank you for your custom."}, {"days": 0}],
                   late_fee={"enabled": True, "kind": "percent", "value": 2, "after_days": 14, "repeat": "monthly"})
    assert [s["days"] for s in p["steps"]] == [-3, 0, 7]
    assert p["steps"][0]["message"] == "Thank you for your custom."
    assert p["steps"][1]["tone"] == "gentle"
    assert p["late_fee"] == {"enabled": True, "kind": "percent", "value": 2.0, "after_days": 14, "repeat": "monthly"}
    assert "3 days before due" in p["samples"][0]["label"] and "due in 3 days" in p["samples"][0]["opening"]
    assert "applies to invoices more than 14 days overdue" in p["samples"][0]["opening"] or any(
        "more than 14 days overdue" in s["opening"] for s in p["samples"])
    # It sticks.
    assert [s["days"] for s in tenant.get("/api/dunning").json()["steps"]] == [-3, 0, 7]

    bad = [
        ({"steps": [{"days": 7}, {"days": 7}]}, "Two steps"),
        ({"steps": [{"days": 400}]}, "between"),
        ({"steps": [{"days": 7, "tone": "angry"}]}, "Tone"),
        ({"steps": [{"days": n} for n in range(9)]}, "At most"),
        ({"steps": []}, "at least one step"),
        ({"steps": [{"days": "soon"}]}, "whole number"),
        ({"late_fee": {"enabled": True, "value": 0}}, "Set the fee"),
        ({"late_fee": {"enabled": True, "kind": "percent", "value": 40}}, "between 0 and 25"),
        ({"late_fee": {"kind": "tip", "value": 1}}, "percent"),
        ({"late_fee": {"value": 1, "repeat": "hourly"}}, "once, or monthly"),
        ({"late_fee": {"value": 1, "after_days": -1}}, "Grace days"),
    ]
    for body, why in bad:
        res = tenant.put("/api/dunning", json=body)
        assert res.status_code == 400, (body, res.text)
        assert why in res.json()["detail"], (body, res.text)


# --- the sequence -------------------------------------------------------------

def test_a_nudge_goes_before_the_due_date_in_a_gentle_voice(tenant, outbox):
    set_policy(tenant, steps=[{"days": -3, "tone": "gentle"}, {"days": 0, "tone": "gentle"}, {"days": 7, "tone": "firm"}])
    soon = inv_due(tenant, -3, email=uniq("soon"))
    later = inv_due(tenant, -10, email=uniq("later"))
    chase_all()
    got = mine(outbox, soon["email"])
    assert len(got) == 1
    assert got[0]["subject"] == f"Invoice {soon['number']} is due on {d(3)}"
    assert "is due in 3 days" in got[0]["body"] and "If you have already paid" in got[0]["body"]
    assert mine(outbox, later["email"]) == []
    log = tenant.get(f"/api/invoices/{soon['number']}/reminders").json()
    assert log[0]["stage_days"] == -3 and log[0]["label"] == "3 days before due"


def test_each_step_goes_once_and_the_tone_hardens(tenant, outbox):
    inv = inv_due(tenant, 8, email=uniq("late"))
    chase_all()
    got = mine(outbox, inv["email"])
    assert len(got) == 1 and got[0]["subject"].startswith("Overdue: invoice") and "still unpaid 8 days later" in got[0]["body"]
    chase_all()
    assert len(mine(outbox, inv["email"])) == 1, "the same step never goes twice"
    move_due(inv, 31)
    chase_all()
    got = mine(outbox, inv["email"])
    assert len(got) == 2 and got[1]["subject"] == f"Final notice: invoice {inv['number']}"
    assert "further steps" in got[1]["body"] and "already paid" not in got[1]["body"]
    assert "Final notice" in got[1]["html"]
    assert [r["stage_days"] for r in tenant.get(f"/api/invoices/{inv['number']}/reminders").json()] == [7, 30]


def test_the_business_own_sentence_and_the_pay_link_go_in(tenant, outbox, monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://bills.example.test")
    set_policy(tenant, steps=[{"days": 1, "tone": "gentle", "message": "Our bank details are on the invoice; card is quickest."}])
    inv = inv_due(tenant, 2, email=uniq("link"))
    chase_all()
    body = mine(outbox, inv["email"])[0]["body"]
    assert "card is quickest." in body
    assert f"https://bills.example.test/invoice.html?id={inv['tracking_id']}" in body
    assert "Review and pay" in mine(outbox, inv["email"])[0]["html"]


def test_a_customer_left_out_is_not_chased(tenant, outbox):
    contact = tenant.post("/api/contacts", json={"name": "Old Friend", "email": uniq("friend")}).json()
    assert contact["chase"] is True and contact["late_fees"] is True
    res = tenant.put(f"/api/contacts/{contact['id']}", json={"chase": False})
    assert res.json()["chase"] is False and res.json()["late_fees"] is True
    inv = inv_due(tenant, 8, contact="Old Friend", email=contact["email"])
    other = inv_due(tenant, 8, contact="Stranger", email=uniq("stranger"))
    chase_all()
    assert mine(outbox, contact["email"]) == []
    assert len(mine(outbox, other["email"])) == 1
    chasing = tenant.get(f"/api/invoices/{inv['number']}").json()["chasing"]
    assert chasing["chased"] is False and chasing["why_not"] == "customer not chased" and chasing["next"] is None
    assert chasing["customer_id"] == contact["id"]


def test_a_paused_invoice_is_left_alone_until_resumed(tenant, outbox):
    inv = inv_due(tenant, 8, email=uniq("paused"))
    res = tenant.post(f"/api/invoices/{inv['number']}/chase/pause", json={"paused": True})
    assert res.status_code == 200 and res.json()["chasing"]["paused"] is True
    chase_all()
    assert mine(outbox, inv["email"]) == []
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["chasing"]["why_not"] == "paused"
    tenant.post(f"/api/invoices/{inv['number']}/chase/pause", json={"paused": False})
    chase_all()
    assert len(mine(outbox, inv["email"])) == 1


def test_chasing_switched_off_sends_nothing(tenant, outbox):
    set_policy(tenant, enabled=False)
    inv = inv_due(tenant, 8, email=uniq("off"))
    chase_all()
    assert mine(outbox, inv["email"]) == []
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["chasing"]["next"] is None


def test_the_invoice_page_says_what_went_and_what_is_next(tenant, outbox):
    inv = inv_due(tenant, 2, email=uniq("next"))
    chasing = tenant.get(f"/api/invoices/{inv['number']}").json()["chasing"]
    assert chasing["next"] == {"days": 1, "tone": "gentle", "on": d(0), "label": "1 day overdue (gentle)"}
    chase_all()
    chasing = tenant.get(f"/api/invoices/{inv['number']}").json()["chasing"]
    assert [r["stage_days"] for r in chasing["reminders"]] == [1]
    assert chasing["next"]["days"] == 7 and chasing["next"]["on"] == d(5)


def test_a_reminder_can_be_sent_now_but_not_twice_a_day(tenant, outbox):
    inv = inv_due(tenant, 3, email=uniq("now"))
    res = tenant.post(f"/api/invoices/{inv['number']}/chase", json={"tone": "final", "message": "Call me on 0123."})
    assert res.status_code == 200, res.text
    got = mine(outbox, inv["email"])
    assert len(got) == 1 and got[0]["subject"].startswith("Final notice") and "Call me on 0123." in got[0]["body"]
    assert res.json()["chasing"]["reminders"][0]["stage_days"] == 3
    assert tenant.post(f"/api/invoices/{inv['number']}/chase", json={}).status_code == 409
    assert tenant.post(f"/api/invoices/{inv['number']}/chase", json={"tone": "rude"}).status_code == 400
    chase_all()
    assert len(mine(outbox, inv["email"])) == 1, "the schedule's 1-day step is behind the one just sent"

    paid = inv_due(tenant, 3, email=uniq("paid"))
    tenant.post(f"/api/invoices/{paid['number']}/payments", json={"amount": 100, "paid_on": d(0), "method": "cash"})
    assert tenant.post(f"/api/invoices/{paid['number']}/chase", json={}).status_code == 400
    no_mail = make_invoice(tenant, status="Awaiting Payment", contact="Nobody", email="", issue_date=d(-20), due_date=d(-3))
    assert tenant.post(f"/api/invoices/{no_mail['number']}/chase", json={}).status_code == 400


# --- late fees ----------------------------------------------------------------

def test_a_late_fee_goes_on_after_the_grace_days_once(tenant, outbox):
    set_policy(tenant, late_fee={"enabled": True, "kind": "percent", "value": 2, "after_days": 14})
    early = inv_due(tenant, 10, email=uniq("early"))
    late = inv_due(tenant, 20, email=uniq("fee"))
    fee_all()
    assert tenant.get(f"/api/invoices/{early['number']}").json()["due"] == 100.0
    got = tenant.get(f"/api/invoices/{late['number']}").json()
    assert got["due"] == 102.0 and got["total"] == 102.0
    fee_line = [li for li in got["line_items"] if li["name"] == "Late payment fee"]
    assert len(fee_line) == 1 and fee_line[0]["price"] == 2.0 and fee_line[0]["tax_amount"] == 0 and "20 days overdue" in fee_line[0]["description"]
    assert got["chasing"]["late_fee_total"] == 2.0
    fee = got["chasing"]["late_fees"][0]
    assert fee["basis"] == "2% of 100.00" and fee["days_overdue"] == 20 and fee["applied_by"] == "policy" and fee["waived_on"] == ""
    note = mine(outbox, late["email"])
    assert len(note) == 1 and "late payment fee" in note[0]["subject"] and "£2.00" in note[0]["body"] and "now due is £102.00" in note[0]["body"]
    # The customer's own page shows the line and the new total.
    public = tenant.get(f"/api/public/invoices/{late['tracking_id']}").json()
    assert public["total"] == 102.0 and any(li.get("name") == "Late payment fee" or "Late payment fee" in str(li) for li in public["line_items"])
    # Once means once.
    fee_all()
    assert tenant.get(f"/api/invoices/{late['number']}").json()["due"] == 102.0
    assert len(mine(outbox, late["email"])) == 1
    # And the next reminder says the amount includes it.
    chase_all()
    body = [m for m in mine(outbox, late["email"]) if "Overdue" in m["subject"]][0]["body"]
    assert "includes a late payment fee of £2.00" in body


def test_a_reminder_warns_of_the_fee_before_it_lands(tenant, outbox):
    set_policy(tenant, late_fee={"enabled": True, "kind": "flat", "value": 25, "after_days": 14})
    inv = inv_due(tenant, 2, email=uniq("warn"))
    chase_all()
    body = mine(outbox, inv["email"])[0]["body"]
    assert "A late payment fee of £25.00 applies to invoices more than 14 days overdue." in body


def test_a_monthly_fee_comes_again_while_unpaid(tenant, outbox):
    set_policy(tenant, late_fee={"enabled": True, "kind": "percent", "value": 2, "after_days": 14, "repeat": "monthly"})
    inv = inv_due(tenant, 20, email=uniq("monthly"))
    fee_all()
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["due"] == 102.0
    move_due(inv, 40)
    fee_all()
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["due"] == 102.0, "the second month is not up yet"
    move_due(inv, 45)
    fee_all()
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["due"] == 104.04 and [f["basis"] for f in got["chasing"]["late_fees"]] == ["2% of 100.00", "2% of 102.00"]
    assert got["chasing"]["late_fee_next"] == d(-45 + 14 + 60)


def test_the_customer_let_off_fees_is_still_reminded(tenant, outbox):
    set_policy(tenant, late_fee={"enabled": True, "kind": "flat", "value": 25, "after_days": 7})
    contact = tenant.post("/api/contacts", json={"name": "Council", "email": uniq("council"), "late_fees": False}).json()
    assert contact["late_fees"] is False and contact["chase"] is True
    inv = inv_due(tenant, 20, contact="Council", email=contact["email"])
    other = inv_due(tenant, 20, contact="Shop", email=uniq("shop"))
    fee_all()
    chase_all()
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["due"] == 100.0
    assert tenant.get(f"/api/invoices/{other['number']}").json()["due"] == 125.0
    assert [m["subject"][:8] for m in mine(outbox, contact["email"])] == ["Overdue:"]
    chasing = tenant.get(f"/api/invoices/{inv['number']}").json()["chasing"]
    assert chasing["fees_allowed"] is False and chasing["fee_why_not"] == "no late fees for this customer" and chasing["late_fee_next"] is None


def test_a_paused_invoice_gets_no_fee_either(tenant, outbox):
    set_policy(tenant, late_fee={"enabled": True, "kind": "flat", "value": 25, "after_days": 7})
    inv = inv_due(tenant, 20, email=uniq("held"))
    tenant.post(f"/api/invoices/{inv['number']}/chase/pause", json={"paused": True})
    fee_all()
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["due"] == 100.0


def test_a_fee_can_be_added_by_hand_and_let_off(tenant, outbox):
    inv = inv_due(tenant, 20, email=uniq("hand"))
    res = tenant.post(f"/api/invoices/{inv['number']}/late-fee", json={})
    assert res.status_code == 400 and "Settings" in res.json()["detail"]
    res = tenant.post(f"/api/invoices/{inv['number']}/late-fee", json={"amount": 15, "tell_customer": False})
    assert res.status_code == 200, res.text
    assert res.json()["invoice"]["due"] == 115.0 and res.json()["fee"]["basis"] == "typed"
    assert mine(outbox, inv["email"]) == [], "told not to"
    fee_id = res.json()["fee"]["id"]
    res = tenant.post(f"/api/invoices/{inv['number']}/late-fees/{fee_id}/waive", json={"reason": "Goodwill"})
    assert res.status_code == 200, res.text
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    assert got["due"] == 100.0 and got["total"] == 100.0
    assert not [li for li in got["line_items"] if li["name"] == "Late payment fee"]
    fee = got["chasing"]["late_fees"][0]
    assert fee["waived_on"] == d(0) and fee["waived_why"] == "Goodwill" and got["chasing"]["late_fee_total"] == 0
    assert tenant.post(f"/api/invoices/{inv['number']}/late-fees/{fee_id}/waive", json={}).status_code == 400

    # A fee on an invoice the customer had otherwise paid: letting it off settles it.
    set_policy(tenant, late_fee={"enabled": True, "kind": "flat", "value": 10, "after_days": 7})
    settled = inv_due(tenant, 20, email=uniq("settled"))
    res = tenant.post(f"/api/invoices/{settled['number']}/late-fee", json={"tell_customer": False})
    assert res.status_code == 200 and res.json()["invoice"]["due"] == 110.0
    tenant.post(f"/api/invoices/{settled['number']}/payments", json={"amount": 100, "paid_on": d(0), "method": "cash"})
    assert tenant.get(f"/api/invoices/{settled['number']}").json()["status"] == "Partially Paid"
    tenant.post(f"/api/invoices/{settled['number']}/late-fees/{res.json()['fee']['id']}/waive", json={})
    got = tenant.get(f"/api/invoices/{settled['number']}").json()
    assert got["status"] == "Paid" and got["due"] == 0
    assert tenant.post(f"/api/invoices/{settled['number']}/late-fee", json={"amount": 5}).status_code == 400

    fresh = inv_due(tenant, -5, email=uniq("fresh"))
    assert tenant.post(f"/api/invoices/{fresh['number']}/late-fee", json={"amount": 5}).status_code == 400


def test_taking_the_fee_line_off_the_invoice_lets_it_off(tenant, outbox):
    inv = inv_due(tenant, 20, email=uniq("edit"))
    res = tenant.post(f"/api/invoices/{inv['number']}/late-fee", json={"amount": 15, "tell_customer": False})
    fee_id = res.json()["fee"]["id"]
    got = tenant.get(f"/api/invoices/{inv['number']}").json()
    edit = {"contact": got["to"], "email": got["email"], "issue_date": got["date"], "due_date": got["due_date"], "tax_type": "none",
            "line_items": [{"name": li["name"], "description": li["description"], "qty": li["qty"], "price": li["price"], "tax_rate": li["tax_rate"]} for li in got["line_items"]]}
    # Keeping the line keeps the fee.
    res = tenant.put(f"/api/invoices/{inv['number']}", json=edit)
    assert res.status_code == 200, res.text
    assert res.json()["due"] == 115.0 and res.json()["chasing"]["late_fees"][0]["waived_on"] == ""
    # Taking it off is letting it off.
    edit["line_items"] = [li for li in edit["line_items"] if li["name"] != "Late payment fee"]
    res = tenant.put(f"/api/invoices/{inv['number']}", json=edit)
    assert res.json()["due"] == 100.0
    fee = res.json()["chasing"]["late_fees"][0]
    assert fee["id"] == fee_id and fee["waived_on"] == d(0) and "edited" in fee["waived_why"]
    assert res.json()["chasing"]["late_fee_total"] == 0


def test_the_chasing_page_lists_what_is_being_chased(tenant, outbox):
    set_policy(tenant, late_fee={"enabled": True, "kind": "flat", "value": 10, "after_days": 7})
    a = inv_due(tenant, 20, contact="Alpha", email=uniq("a"))
    b = inv_due(tenant, 3, contact="Beta", email=uniq("b"))
    inv_due(tenant, -20, contact="Gamma", email=uniq("c"))
    tenant.post(f"/api/invoices/{b['number']}/chase/pause", json={"paused": True})
    chase_all()
    fee_all()
    page = tenant.get("/api/chasing").json()
    assert [r["number"] for r in page["rows"]] == [a["number"], b["number"]]
    assert page["overdue"] == 2 and page["paused"] == 1 and page["owed"] == 210.0
    assert page["rows"][0]["reminders"] == 1 and page["rows"][0]["last_label"] == "14 days overdue" and page["rows"][0]["late_fees"] == 10.0
    assert page["rows"][1]["paused"] is True and page["rows"][1]["reminders"] == 0
    assert page["late_fee"]["value"] == 10.0


def test_nothing_crosses_a_business(client, account, outbox):
    tenant = account["client"]
    set_policy(tenant, late_fee={"enabled": True, "kind": "flat", "value": 10, "after_days": 7})
    inv = inv_due(tenant, 20, email=uniq("mine"))
    fee_id = tenant.post(f"/api/invoices/{inv['number']}/late-fee", json={"amount": 5, "tell_customer": False}).json()["fee"]["id"]
    other_email = f"other-{account['email']}"
    client.post("/api/client/register", json={"email": other_email, "password": "Passw0rdTest", "company_name": "Other Co"})
    client.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    assert client.get("/api/dunning").json()["late_fee"]["enabled"] is False
    assert client.post(f"/api/invoices/{inv['number']}/chase", json={}).status_code == 404
    assert client.post(f"/api/invoices/{inv['number']}/chase/pause", json={}).status_code == 404
    assert client.post(f"/api/invoices/{inv['number']}/late-fee", json={"amount": 1}).status_code == 404
    assert client.post(f"/api/invoices/{inv['number']}/late-fees/{fee_id}/waive", json={}).status_code == 404
    # Its own invoice carries the same number; the fee is still not its to let off.
    twin = make_invoice(client, status="Awaiting Payment", issue_date=d(-30), due_date=d(-20))
    assert twin["number"] == inv["number"]
    assert client.post(f"/api/invoices/{twin['number']}/late-fees/{fee_id}/waive", json={}).status_code == 404
    with main.SessionLocal() as db:
        assert db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == inv["tracking_id"]).first().due == 105.0
    assert [r["number"] for r in client.get("/api/chasing").json()["rows"]] == [twin["number"]]
    assert main.app  # the anonymous can do none of it
    client.cookies.clear()
    assert client.get("/api/dunning").status_code == 401
    assert client.get("/api/chasing").status_code == 401
