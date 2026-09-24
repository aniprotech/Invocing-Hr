"""What needs you today.

The dashboard could say what a business had done and nothing about what it
still had to do. Every one of these counts already existed on its own
screen; a person had to go looking for each. This panel gathers them worst
first, each with the screen it is fixed on, and leaves out anything that is
zero - a list of zeroes is noise.
"""
from datetime import date, datetime, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def panel(tenant):
    res = tenant.get("/api/dashboard/attention")
    assert res.status_code == 200, res.text
    return res.json()


def keys(tenant):
    return [i["key"] for i in panel(tenant)["items"]]


def item(tenant, key):
    return next((i for i in panel(tenant)["items"] if i["key"] == key), None)


def an_invoice(tenant, **kw):
    fields = dict(status="Awaiting Payment", contact="Acme Ltd", email="acme@x.test",
                  issue_date=d(-30), due_date=d(-10), tax_type="none",
                  line_items=[{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    fields.update(kw)
    return make_invoice(tenant, **fields)


# --- nothing to do -----------------------------------------------------------
def test_a_quiet_business_is_told_nothing(tenant):
    """The panel is worth a click only if everything on it is."""
    assert panel(tenant)["items"] == []


def test_a_zero_is_left_out_not_shown_as_zero(tenant):
    an_invoice(tenant)
    ks = keys(tenant)
    assert "overdue" in ks and "drafts" not in ks and "leave_pending" not in ks


# --- money owed to the business ----------------------------------------------
def test_an_overdue_invoice_leads_the_panel_with_what_is_owed(tenant):
    an_invoice(tenant)
    row = item(tenant, "overdue")
    assert row and row["count"] == 1 and row["amount"] == 100.0 and row["tone"] == "bad"
    assert row["view"] == "invoices-view" and row["filter"] == "overdue"


def test_an_invoice_falling_due_this_week_is_a_nudge_not_an_alarm(tenant):
    an_invoice(tenant, issue_date=d(-1), due_date=d(3))
    row = item(tenant, "due_soon")
    assert row and row["count"] == 1 and row["tone"] == "info"


def test_one_due_next_month_is_not_hurried(tenant):
    an_invoice(tenant, issue_date=d(-1), due_date=d(40))
    assert keys(tenant) == []


def test_a_draft_is_money_never_asked_for(tenant):
    an_invoice(tenant, status="Draft", issue_date=d(0), due_date=d(20))
    row = item(tenant, "drafts")
    assert row and row["count"] == 1 and row["filter"] == "draft"


def test_a_paid_invoice_asks_for_nothing(tenant):
    inv = an_invoice(tenant)
    tenant.post(f"/api/invoices/{inv['number']}/payments",
                json={"amount": 100.0, "date": d(0), "method": "Bank"})
    assert keys(tenant) == []


# --- the bank ----------------------------------------------------------------
def test_the_bank_lines_with_no_home_are_listed(tenant, account):
    acc = tenant.post("/api/accounts", json={"name": "Current", "kind": "bank"}).json()
    tenant.post("/api/bank/import", json={
        "text": f"Date,Description,Amount\n{d(-2)},SOMEONE PAID US,250.00\n{d(-1)},RENT,-900.00\n",
        "filename": "s.csv", "account_id": acc["id"]})
    match = item(tenant, "bank_to_match")
    code = item(tenant, "bank_to_code")
    assert match and match["count"] == 1 and match["amount"] == 250.0
    assert match["view"] == "bank-view" and match["filter"] == "unmatched"
    assert code and code["count"] == 1 and code["filter"] == "out"


def test_a_coded_line_stops_asking(tenant, account):
    acc = tenant.post("/api/accounts", json={"name": "Current", "kind": "bank"}).json()
    tenant.post("/api/bank/import", json={
        "text": f"Date,Description,Amount\n{d(-1)},RENT,-900.00\n", "filename": "s.csv", "account_id": acc["id"]})
    line = tenant.get("/api/bank/lines?status=out").json()["lines"][0]
    tenant.post("/api/bank/lines/code", json={"ids": [line["id"]], "category": "rent"})
    assert "bank_to_code" not in keys(tenant)


# --- money the business owes --------------------------------------------------
def test_a_bill_past_due_outranks_one_merely_coming(tenant):
    tenant.post("/api/bills", json={"number": "B-LATE", "vendor_name": "Late Co", "issue_date": d(-40), "due_date": d(-5),
                                    "amount": 200.0, "tax_amount": 0.0, "total": 200.0, "status": "Awaiting Payment"})
    tenant.post("/api/bills", json={"number": "B-SOON", "vendor_name": "Soon Co", "issue_date": d(-5), "due_date": d(3),
                                    "amount": 50.0, "tax_amount": 0.0, "total": 50.0, "status": "Awaiting Payment"})
    ks = keys(tenant)
    assert ks.index("bills_overdue") < ks.index("bills_due")
    assert item(tenant, "bills_overdue")["amount"] == 200.0


def test_a_bill_already_paid_is_not_chased(tenant):
    b = tenant.post("/api/bills", json={"number": "B-PAID", "vendor_name": "Paid Co", "issue_date": d(-40), "due_date": d(-5),
                                        "amount": 200.0, "tax_amount": 0.0, "total": 200.0, "status": "Paid"}).json()
    assert tenant.get(f"/api/bills/{b['id']}").json()["status"] == "Paid"
    assert "bills_overdue" not in keys(tenant)


# --- work that has stalled ----------------------------------------------------
def test_a_quote_nobody_answered_is_on_the_list(tenant):
    q = tenant.post("/api/quotes", json={"contact": "Acme", "email": "a@x.test", "issue_date": d(-10),
                                         "expiry_date": d(20), "status": "Sent", "tax_type": "none",
                                         "line_items": [{"description": "Job", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}]})
    assert q.status_code == 200, q.text
    row = item(tenant, "quotes_open")
    assert row and row["count"] == 1 and row["view"] == "quotes-view"


def test_leave_waiting_on_a_manager_is_on_the_list(tenant):
    from conftest import make_employee
    emp = make_employee(tenant)
    with main.SessionLocal() as db:
        db.add(models.DBLeaveRequest(client_id=_client_id(db), employee_id=emp["id"], leave_type="Holiday",
                                     start_date=d(5), end_date=d(7), days=3.0, status="pending"))
        db.commit()
    row = item(tenant, "leave_pending")
    assert row and row["count"] == 1 and row["view"] == "leave-view"


def _client_id(db):
    return db.query(models.DBClient).order_by(models.DBClient.id.desc()).first().id


# --- things that quietly went wrong -------------------------------------------
def test_the_accounts_own_verification_mail_is_not_the_businesss_problem(tenant):
    """It has its own bar and its own Resend. A brand new account must not
    open on a warning about itself."""
    with main.SessionLocal() as db:
        db.add(models.DBEmailDelivery(client_id=_client_id(db), kind="verification", reference="",
                                      to_email="owner@x.test", status="failed",
                                      created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    assert "email_failed" not in keys(tenant)


def test_a_send_that_failed_today_is_surfaced(tenant):
    with main.SessionLocal() as db:
        cid = _client_id(db)
        db.add(models.DBEmailDelivery(client_id=cid, kind="invoice", reference="INV-0001",
                                      to_email="acme@x.test", status="failed",
                                      created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    row = item(tenant, "email_failed")
    assert row and row["count"] == 1 and row["tone"] == "bad"


def test_a_send_that_failed_last_week_is_not_todays_problem(tenant):
    with main.SessionLocal() as db:
        cid = _client_id(db)
        db.add(models.DBEmailDelivery(client_id=cid, kind="invoice", reference="INV-0001",
                                      to_email="acme@x.test", status="failed",
                                      created_at=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    assert "email_failed" not in keys(tenant)


def test_a_bank_connection_near_its_ninety_days_says_so(tenant):
    with main.SessionLocal() as db:
        cid = _client_id(db)
        db.add(models.DBBankFeed(client_id=cid, provider="gocardless", institution_name="TSB",
                                 reference=f"ref-{cid}-near", status="linked", consent_expires_on=d(5)))
        db.commit()
    row = item(tenant, "feed_ending")
    assert row and row["count"] == 1 and row["view"] == "bank-view"


def test_a_connection_with_months_left_is_left_alone(tenant):
    with main.SessionLocal() as db:
        cid = _client_id(db)
        db.add(models.DBBankFeed(client_id=cid, provider="gocardless", institution_name="TSB",
                                 reference=f"ref-{cid}-far", status="linked", consent_expires_on=d(80)))
        db.commit()
    assert "feed_ending" not in keys(tenant)


# --- the shape of the panel ----------------------------------------------------
def test_the_worst_comes_first_and_the_panel_stays_short(tenant, account):
    an_invoice(tenant)                                                    # bad
    an_invoice(tenant, issue_date=d(-1), due_date=d(3))                   # info
    acc = tenant.post("/api/accounts", json={"name": "Current", "kind": "bank"}).json()
    tenant.post("/api/bank/import", json={
        "text": f"Date,Description,Amount\n{d(-2)},IN,250.00\n{d(-1)},OUT,-900.00\n",
        "filename": "s.csv", "account_id": acc["id"]})                    # warn, warn
    tones = [i["tone"] for i in panel(tenant)["items"]]
    assert tones == sorted(tones, key=lambda t: {"bad": 0, "warn": 1, "info": 2}[t]), tones
    assert len(tones) <= main.ATTENTION_LIMIT


def test_a_business_behind_on_everything_still_gets_a_readable_panel(tenant, account):
    """Ten things can be waiting. A list of ten is a second inbox, so the
    panel stops at the limit and the worst are the ones that survive."""
    from conftest import make_employee
    an_invoice(tenant)                                                    # overdue
    an_invoice(tenant, issue_date=d(-1), due_date=d(3))                   # due_soon
    an_invoice(tenant, status="Draft", issue_date=d(0), due_date=d(20))   # drafts
    acc = tenant.post("/api/accounts", json={"name": "Current", "kind": "bank"}).json()
    tenant.post("/api/bank/import", json={                                # to match, to code
        "text": f"Date,Description,Amount\n{d(-2)},IN,250.00\n{d(-1)},OUT,-900.00\n",
        "filename": "s.csv", "account_id": acc["id"]})
    tenant.post("/api/bills", json={"number": "B1", "vendor_name": "Late", "issue_date": d(-40),
                                    "due_date": d(-5), "amount": 200.0, "tax_amount": 0.0,
                                    "total": 200.0, "status": "Awaiting Payment"})
    tenant.post("/api/bills", json={"number": "B2", "vendor_name": "Soon", "issue_date": d(-5),
                                    "due_date": d(3), "amount": 50.0, "tax_amount": 0.0,
                                    "total": 50.0, "status": "Awaiting Payment"})
    tenant.post("/api/quotes", json={"contact": "Acme", "email": "a@x.test", "issue_date": d(-10),
                                     "expiry_date": d(20), "status": "Sent", "tax_type": "none",
                                     "line_items": [{"description": "Job", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}]})
    emp = make_employee(tenant)
    with main.SessionLocal() as db:
        cid = _client_id(db)
        db.add(models.DBLeaveRequest(client_id=cid, employee_id=emp["id"], leave_type="Holiday",
                                     start_date=d(5), end_date=d(7), days=3.0, status="pending"))
        db.add(models.DBEmailDelivery(client_id=cid, kind="invoice", reference="INV-0001",
                                      to_email="acme@x.test", status="failed",
                                      created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    items = panel(tenant)["items"]
    assert len(items) == main.ATTENTION_LIMIT, [i["key"] for i in items]
    # The three that cost the most are the three that survive being cut.
    assert {"overdue", "bills_overdue", "email_failed"} <= {i["key"] for i in items}
    # And what was cut was the least urgent and the smallest, not something
    # in the middle: the two lowest-value of the merely-informative rows.
    assert {"drafts", "bills_due"}.isdisjoint({i["key"] for i in items})
    assert items[-1]["tone"] == "info"


def test_every_item_names_a_screen_the_router_knows(tenant, account):
    an_invoice(tenant)
    acc = tenant.post("/api/accounts", json={"name": "Current", "kind": "bank"}).json()
    tenant.post("/api/bank/import", json={
        "text": f"Date,Description,Amount\n{d(-1)},OUT,-900.00\n", "filename": "s.csv", "account_id": acc["id"]})
    for i in panel(tenant)["items"]:
        assert i["view"].endswith("-view"), i
        assert i["label"] and i["hint"], i


def test_another_business_is_not_on_this_panel(tenant, client, account):
    an_invoice(tenant)
    other = f"other-{account['email']}"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/dashboard/attention").json()["items"] == []


def test_signed_out_it_answers_nothing(client):
    client.post("/api/client/logout")
    assert client.get("/api/dashboard/attention").status_code == 401


# --- the wallet ----------------------------------------------------------------
def test_a_brand_new_account_is_not_warned_about_a_wallet_it_never_set_up(tenant):
    """A zero balance on day one is not a problem, it is a business that has
    not needed the wallet yet."""
    with main.SessionLocal() as db:
        cid = _client_id(db)
        db.add(models.DBWallet(client_id=cid, balance_minor=0, low_balance_minor=500,
                               currency="GBP", lifetime_topped_up_minor=0))
        db.commit()
    assert "wallet_low" not in keys(tenant)


def test_a_wallet_that_has_been_used_and_run_down_does_warn(tenant):
    with main.SessionLocal() as db:
        cid = _client_id(db)
        db.add(models.DBWallet(client_id=cid, balance_minor=120, low_balance_minor=500,
                               currency="GBP", lifetime_topped_up_minor=5000))
        db.commit()
    row = item(tenant, "wallet_low")
    assert row and row["tone"] == "bad" and row["amount"] == 1.2 and row["view"] == "wallet-view"
