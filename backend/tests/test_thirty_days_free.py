"""The first thirty days, which cost nothing and need no card.

A new account can use everything - invoices, payroll, attendance, the AI - with
no wallet, no credit and no payment method on file. After that the wallet is
how it is paid for, exactly as it was before. There is still no subscription
and no plan to choose.

Two things are worth being strict about, and most of this file is them.

Nothing may be refused for want of credit while the trial is running. A trial
that stops working on day three because a wallet nobody was asked to fill is
empty is not a trial, and the person hits it in the middle of doing something
real rather than while looking around.

And nothing may be charged during it either. The opposite failure is quieter
and worse: money taken from somebody who was told the month was free.
"""
from datetime import datetime, timedelta

import pytest

import main
import models
from conftest import make_invoice


@pytest.fixture
def superadmin():
    """The operator on a session of their own - a tenant signing in on the same
    cookie starts a fresh session and would evict this one."""
    from fastapi.testclient import TestClient
    main.rate_limiter._hits.clear()
    with TestClient(main.app) as op:
        res = op.post("/api/superadmin/login", json={
            "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
        assert res.status_code == 200, res.text
        yield op


def set_trial(tenant, ends_at):
    """Move where this account's free month ends."""
    mine = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(models.DBClient.id == mine).first()
        row.trial_ends_at = ends_at
        db.commit()
    return mine


def days_from_now(days):
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def wallet(tenant):
    return tenant.get("/api/wallet").json()


def empty_the_wallet(client_id):
    with main.SessionLocal() as db:
        w = db.query(models.DBWallet).filter(
            models.DBWallet.client_id == client_id).first()
        if w:
            w.balance_minor = 0
            db.commit()


def priced_action(db):
    """An action that genuinely costs something, with no free allowance left,
    so a charge would have to come out of the wallet."""
    rule = db.query(models.DBPricingRule).filter(
        models.DBPricingRule.action_key == "invoice_send").first()
    rule.is_active = True
    rule.unit_price_minor = 500
    rule.free_allowance = 0
    db.commit()


@pytest.fixture(autouse=True)
def _a_real_price():
    with main.SessionLocal() as db:
        rule = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_send").first()
        if not rule:
            yield
            return
        was = (rule.is_active, rule.unit_price_minor, rule.free_allowance)
        priced_action(db)
    yield
    with main.SessionLocal() as db:
        rule = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_send").first()
        rule.is_active, rule.unit_price_minor, rule.free_allowance = was
        db.commit()


# --- while it is running ----------------------------------------------------------

def test_a_new_account_is_in_a_trial(client, tenant):
    said = wallet(tenant)["trial"]
    assert said["active"] is True, said
    assert said["days_total"] == main.TRIAL_DAYS
    assert said["days_left"] > 0


def test_an_empty_wallet_does_not_stop_anything(client, tenant):
    """The whole point. During the trial there is no wallet to fill and no card
    on file, so refusing for want of credit would refuse everything."""
    mine = set_trial(tenant, days_from_now(20))
    empty_the_wallet(mine)

    with main.SessionLocal() as db:
        charged = main.charge_wallet(db, mine, "invoice_send", 1, "INV-1")
    assert charged is None, "the trial was charged for"


def test_and_nothing_is_taken_from_the_wallet_either(client, tenant):
    """The quieter failure: money out of an account that was told the month was
    free. Credit put there early must still be there at the end of it."""
    mine = set_trial(tenant, days_from_now(20))
    with main.SessionLocal() as db:
        # get_wallet, not a query: the row is made on first use, so a new
        # account has no wallet at all until something reaches for one.
        w = main.get_wallet(db, mine)
        w.balance_minor = 5000
        db.commit()

        main.charge_wallet(db, mine, "invoice_send", 1, "INV-1")
        db.commit()

        after = db.query(models.DBWallet).filter(
            models.DBWallet.client_id == mine).first().balance_minor
    assert after == 5000, f"the trial spent {5000 - after} of their credit"


def test_no_ledger_entry_is_written_for_a_free_action(client, tenant):
    mine = set_trial(tenant, days_from_now(20))
    with main.SessionLocal() as db:
        before = db.query(models.DBWalletTransaction).filter(
            models.DBWalletTransaction.client_id == mine).count()
        main.charge_wallet(db, mine, "invoice_send", 1, "INV-1")
        db.commit()
        after = db.query(models.DBWalletTransaction).filter(
            models.DBWalletTransaction.client_id == mine).count()
    assert after == before


def test_sending_an_invoice_is_not_refused_during_the_trial(client, tenant, monkeypatch):
    """End to end, through the endpoint somebody would actually press."""
    mine = set_trial(tenant, days_from_now(20))
    empty_the_wallet(mine)
    monkeypatch.setattr(main, "send_email_background", lambda *a, **k: (True, "sent"))

    inv = make_invoice(tenant, email="customer@example.com")
    res = tenant.post(f"/api/invoices/{inv['number']}/send",
                      json={"to": "customer@example.com",
                            "subject": "Invoice", "body": "Hello"})
    assert res.status_code == 200, res.text


# --- when it ends ---------------------------------------------------------------------

def test_the_wallet_starts_paying_once_it_is_over(client, tenant):
    mine = set_trial(tenant, days_from_now(-1))
    with main.SessionLocal() as db:
        # get_wallet, not a query: the row is made on first use, so a new
        # account has no wallet at all until something reaches for one.
        w = main.get_wallet(db, mine)
        w.balance_minor = 5000
        db.commit()

        main.charge_wallet(db, mine, "invoice_send", 1, "INV-1")
        db.commit()
        after = db.query(models.DBWallet).filter(
            models.DBWallet.client_id == mine).first().balance_minor
    assert after == 4500, after


def test_and_an_empty_wallet_is_refused_once_it_is_over(client, tenant):
    """Which is the point of the trial ending. The refusal is the existing 402
    that offers a top-up."""
    mine = set_trial(tenant, days_from_now(-1))
    empty_the_wallet(mine)
    with main.SessionLocal() as db:
        with pytest.raises(main.InsufficientCredit):
            main.charge_wallet(db, mine, "invoice_send", 1, "INV-1")


def test_the_last_day_still_counts_as_free(client, tenant):
    """Hours left is not none left, and the account is demonstrably working."""
    set_trial(tenant, (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"))
    said = wallet(tenant)["trial"]
    assert said["active"] is True
    assert said["days_left"] == 1, f"{said} read as no days left while still running"


# --- what the screens are told --------------------------------------------------------------

def test_the_app_is_told_without_asking_for_it(client, tenant):
    """Every screen already loads verification-status, so a trial about to end
    can be said everywhere rather than only on the money screen."""
    said = tenant.get("/api/client/verification-status").json()["trial"]
    assert said["active"] is True
    assert "ends_at" in said


def test_it_says_when_the_end_is_close(client, tenant):
    set_trial(tenant, days_from_now(3))
    said = wallet(tenant)["trial"]
    assert said["ending_soon"] is True, said


def test_and_does_not_nag_on_day_one(client, tenant):
    set_trial(tenant, days_from_now(25))
    assert wallet(tenant)["trial"]["ending_soon"] is False


def test_a_finished_trial_reads_as_finished(client, tenant):
    set_trial(tenant, days_from_now(-1))
    said = wallet(tenant)["trial"]
    assert said["active"] is False
    assert said["days_left"] == 0


# --- accounts that were here before trials were ------------------------------------------------

def test_an_older_account_gets_its_thirty_days_from_when_it_signed_up(client, tenant):
    """Not from the day this shipped, which would hand somebody who has been
    here six months a fresh free month."""
    mine = set_trial(tenant, "")
    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(models.DBClient.id == mine).first()
        row.created_at = (datetime.now() - timedelta(days=200)
                          ).strftime("%Y-%m-%d %H:%M:%S")
        db.commit()

    assert wallet(tenant)["trial"]["active"] is False


def test_and_one_that_signed_up_yesterday_is_still_in_it(client, tenant):
    mine = set_trial(tenant, "")
    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(models.DBClient.id == mine).first()
        row.created_at = (datetime.now() - timedelta(days=1)
                          ).strftime("%Y-%m-%d %H:%M:%S")
        db.commit()

    said = wallet(tenant)["trial"]
    assert said["active"] is True
    assert said["days_left"] == main.TRIAL_DAYS - 1, said


def test_an_unreadable_date_ends_the_trial_rather_than_extending_it(client, tenant):
    """The safe way round. The other would hand out unlimited free use of the
    platform on the strength of a malformed string, and nothing would say so."""
    set_trial(tenant, "not a date")
    assert wallet(tenant)["trial"]["active"] is False


def test_signing_up_stamps_the_end_date(client):
    """Stamped once, so extending somebody's trial is changing a date rather
    than an exception in the billing code."""
    import uuid
    email = f"trial-{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/client/register",
                      json={"email": email, "password": "GoodPassword1",
                            "company_name": "Trial Co", "contact_name": "Sam"})
    assert res.status_code == 200, res.text

    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(
            main.sqlfunc.lower(models.DBClient.email) == email).first()
    assert row is not None
    assert row.trial_ends_at, "signing up did not stamp a trial"
    ends = datetime.strptime(row.trial_ends_at, "%Y-%m-%d %H:%M:%S")
    assert timedelta(days=main.TRIAL_DAYS - 1) < (ends - datetime.now()) \
        <= timedelta(days=main.TRIAL_DAYS)


def test_the_other_charging_path_is_free_too(client, tenant):
    """The AI endpoints bill through charge_after_success rather than
    require_credit, because they charge once the model has actually answered.
    A trial that covered one path and not the other would be free for invoices
    and billed for the assistant, which nobody would think to check."""
    mine = set_trial(tenant, days_from_now(20))
    with main.SessionLocal() as db:
        w = main.get_wallet(db, mine)
        w.balance_minor = 5000
        db.commit()

        main.charge_after_success(db, mine, "invoice_send", 1, "INV-1")

        after = db.query(models.DBWallet).filter(
            models.DBWallet.client_id == mine).first().balance_minor
    assert after == 5000, f"the trial was billed {5000 - after} through the other path"


def test_an_operator_adjustment_is_not_a_trial_matter(client, tenant, superadmin):
    """Deliberately outside it. An operator correcting a balance by hand, with
    a reason that lands on the statement, is not a metered action - and being
    unable to correct a balance during somebody's first month would be its own
    kind of stuck."""
    mine = set_trial(tenant, days_from_now(20))
    with main.SessionLocal() as db:
        w = main.get_wallet(db, mine)
        w.balance_minor = 5000
        db.commit()

    res = superadmin.post(f"/api/superadmin/wallets/{mine}/adjust",
                          json={"amount": -10, "reason": "Correcting a duplicate top-up"})
    assert res.status_code == 200, res.text

    with main.SessionLocal() as db:
        after = db.query(models.DBWallet).filter(
            models.DBWallet.client_id == mine).first().balance_minor
    assert after == 4000, after

