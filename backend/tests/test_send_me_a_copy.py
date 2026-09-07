"""The "send myself a copy" tickbox, which appeared to do nothing.

Reported as not working. It was working, in the sense that the second message
was queued - but it was queued straight to send_email_background, which never
raises and returns (False, reason) on every failure, and BackgroundTasks
discards a return value. So a copy that did not arrive was indistinguishable
from one that did: no delivery row, nothing in the failed-deliveries banner,
no error anywhere, and no way for anybody to find out why.

The other half is worse, because it happens before anything is even
attempted. If the business has no address of its own set, or is itself the
recipient, the copy was skipped in silence. The box stayed ticked, the send
succeeded, and no copy ever came - which is exactly what "it doesn't work"
looks like from the outside.

So the copy is now a tracked delivery like the invoice, and a copy that cannot
be sent says so in the response instead of disappearing.
"""
import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture
def outbox(monkeypatch):
    """Record what is handed to the transport, and let the test decide whether
    it worked."""
    box = {"sent": [], "fail": False}

    def transport(to_email, subject, *a, **k):
        box["sent"].append({"to": to_email, "subject": subject})
        if box["fail"]:
            return False, "mailbox unavailable"
        return True, "sent"

    monkeypatch.setattr(main, "send_email_background", transport)
    return box


def send(tenant, number, **extra):
    body = {"to": "customer@example.com", "subject": "Invoice", "body": "Hello"}
    body.update(extra)
    return tenant.post(f"/api/invoices/{number}/send", json=body)


def deliveries(tenant, status="all"):
    return tenant.get(f"/api/deliveries?status={status}&limit=50").json()["deliveries"]


def my_email(tenant):
    return tenant.get("/api/client/me").json()["email"]


# --- the copy is actually sent -------------------------------------------------

def test_a_copy_goes_to_the_business_itself(client, tenant, outbox):
    inv = make_invoice(tenant, email="customer@example.com")
    res = send(tenant, inv["number"], send_copy=True)
    assert res.status_code == 200, res.text

    copies = [m for m in outbox["sent"] if m["subject"].startswith("[Copy]")]
    assert len(copies) == 1, outbox["sent"]
    assert copies[0]["to"] == my_email(tenant)


def test_no_copy_is_sent_when_the_box_is_not_ticked(client, tenant, outbox):
    inv = make_invoice(tenant, email="customer@example.com")
    send(tenant, inv["number"], send_copy=False)
    assert not [m for m in outbox["sent"] if m["subject"].startswith("[Copy]")]


# --- and it is now possible to find out whether it arrived -------------------------

def test_the_copy_is_written_down_like_the_invoice(client, tenant, outbox):
    """The whole finding. Without a delivery row there is no way to tell a
    copy that failed from one that was never attempted."""
    inv = make_invoice(tenant, email="customer@example.com")
    send(tenant, inv["number"], send_copy=True)

    rows = [d for d in deliveries(tenant) if d["kind"] == "invoice_copy"]
    assert len(rows) == 1, [d["kind"] for d in deliveries(tenant)]
    assert rows[0]["to_email"] == my_email(tenant)
    assert rows[0]["status"] == "sent", rows[0]


def test_a_copy_that_fails_says_so_where_the_others_do(client, tenant, outbox):
    """It used to fail into nothing. Now it lands in the same list the failed
    invoice deliveries land in, carrying the provider's own words."""
    outbox["fail"] = True
    inv = make_invoice(tenant, email="customer@example.com")
    send(tenant, inv["number"], send_copy=True)

    failed = [d for d in deliveries(tenant, "failed") if d["kind"] == "invoice_copy"]
    assert len(failed) == 1, deliveries(tenant, "failed")
    assert "mailbox unavailable" in failed[0]["error"], failed[0]


def test_a_failed_copy_does_not_refund_the_send(client, tenant, outbox):
    """The send was charged once, for the invoice. The copy is not a second
    chargeable thing and must not hand money back when it fails."""
    outbox["fail"] = True
    inv = make_invoice(tenant, email="customer@example.com")
    send(tenant, inv["number"], send_copy=True)

    copy_row = [d for d in deliveries(tenant, "failed") if d["kind"] == "invoice_copy"][0]
    assert copy_row["refunded"] is False, copy_row


def test_a_failed_copy_does_not_hold_back_the_invoice(client, tenant, outbox):
    """Whether the seller got their own copy says nothing about whether the
    customer got theirs, so the copy must not be what moves the invoice."""
    inv = make_invoice(tenant, email="customer@example.com")
    send(tenant, inv["number"], send_copy=True)

    with main.SessionLocal() as db:
        mine = tenant.get("/api/client/me").json()["id"]
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.client_id == mine,
            models.DBInvoice.number == inv["number"]).first()
        assert row.status == "Sent", row.status


# --- and when it cannot be sent at all, it says why -------------------------------------

def set_company_email(tenant, value):
    """What the business typed into its own profile, typos and all."""
    with main.SessionLocal() as db:
        mine = tenant.get("/api/client/me").json()["id"]
        row = db.query(models.DBSettings).filter(
            models.DBSettings.client_id == mine,
            models.DBSettings.key == "email").first()
        if not row:
            row = models.DBSettings(client_id=mine, key="email", value="")
            db.add(row)
        row.value = value
        db.commit()


@pytest.mark.parametrize("typed,why", [
    ("info@aniprotech", "no domain ending"),
    ("Ani Protech", "a name rather than an address"),
    ("", "left blank"),
    ("   ", "only spaces"),
])
def test_a_bad_address_in_the_profile_does_not_take_the_copy_with_it(
        client, tenant, outbox, typed, why):
    """The reason a copy could silently never arrive. The address was taken
    from the company profile if anything at all was in it - so one with a typo
    stopped the copy dead, while the account's own address, which is valid
    because it is how they sign in, sat unused one line away."""
    set_company_email(tenant, typed)
    inv = make_invoice(tenant, email="customer@example.com")
    res = send(tenant, inv["number"], send_copy=True)

    assert res.json()["copy_to"] == my_email(tenant), \
        f"profile holding {why} lost the copy: {res.json()}"
    assert [m for m in outbox["sent"] if m["subject"].startswith("[Copy]")]


def test_a_good_address_in_the_profile_is_preferred(client, tenant, outbox):
    """It is still the one they chose to be contacted on."""
    set_company_email(tenant, "billing@theirdomain.test")
    inv = make_invoice(tenant, email="customer@example.com")
    res = send(tenant, inv["number"], send_copy=True)
    assert res.json()["copy_to"] == "billing@theirdomain.test", res.json()


def test_a_stray_space_does_not_reach_the_transport(client, tenant, outbox):
    """It passed validation, which strips before matching, and was then handed
    to the mail server with the space still on it."""
    set_company_email(tenant, "  spaced@theirdomain.test  ")
    inv = make_invoice(tenant, email="customer@example.com")
    res = send(tenant, inv["number"], send_copy=True)

    assert res.json()["copy_to"] == "spaced@theirdomain.test", res.json()
    copies = [m for m in outbox["sent"] if m["subject"].startswith("[Copy]")]
    assert copies and copies[0]["to"] == "spaced@theirdomain.test", copies


def test_being_your_own_customer_is_explained(client, tenant, outbox):
    """Copying yourself on a message already addressed to you is the same
    message twice. Skipping it is right; skipping it in silence is not."""
    inv = make_invoice(tenant, email=my_email(tenant))
    res = send(tenant, inv["number"], to=my_email(tenant), send_copy=True)

    assert res.status_code == 200, res.text
    assert res.json()["copy_skipped"], res.json()
    assert "recipient" in res.json()["copy_skipped"]
    assert not [m for m in outbox["sent"] if m["subject"].startswith("[Copy]")]


def test_the_same_address_in_different_case_is_still_you(client, tenant, outbox):
    """Mailboxes are not case sensitive in practice. Comparing the two exactly
    means Billing@x.test and billing@x.test read as two different people, and
    the same message is sent to the same inbox twice."""
    set_company_email(tenant, "Billing@Theirdomain.test")
    inv = make_invoice(tenant, email="billing@theirdomain.test")
    res = send(tenant, inv["number"], to="billing@theirdomain.test", send_copy=True)

    assert res.json()["copy_skipped"], res.json()
    assert not [m for m in outbox["sent"] if m["subject"].startswith("[Copy]")], \
        "the same inbox got the message twice"


def test_a_successful_copy_names_where_it_went(client, tenant, outbox):
    inv = make_invoice(tenant, email="customer@example.com")
    res = send(tenant, inv["number"], send_copy=True)
    assert res.json()["copy_to"] == my_email(tenant), res.json()
    assert res.json()["copy_skipped"] == ""


def test_nothing_is_said_when_no_copy_was_asked_for(client, tenant, outbox):
    inv = make_invoice(tenant, email="customer@example.com")
    res = send(tenant, inv["number"], send_copy=False)
    assert res.json()["copy_to"] == ""
    assert res.json()["copy_skipped"] == ""
