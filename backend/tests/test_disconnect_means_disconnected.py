"""Whose Google account an email actually leaves through.

Two faults, found because somebody disconnected Gmail and the app still said
the email was sent.

The first is what they saw. A business that had chosen to send through its own
Google account and then pressed Disconnect kept sending - through the
platform's account, silently, from an address nobody had picked. The SMTP path
already refuses to fall back for exactly this reason; the Gmail path did not.

The second is worse and nobody would have seen it. The lookup ended with a
bare "take any row in the table", reachable whenever there was no platform
token - which is the normal state of a fresh install. One business's invoices
would then leave through another business's Gmail account, with nothing
visible from either side.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _no_tokens():
    """Start with none, leave none."""
    def clear():
        with main.SessionLocal() as db:
            db.query(models.DBSettings).filter(
                models.DBSettings.key == "GOOGLE_REFRESH_TOKEN").delete()
            db.commit()
    clear()
    yield
    clear()


def give_token(client_id, value):
    with main.SessionLocal() as db:
        db.add(models.DBSettings(key="GOOGLE_REFRESH_TOKEN", value=value,
                                 client_id=client_id))
        db.commit()


def chose_gmail(client_id):
    with main.SessionLocal() as db:
        row = db.query(models.DBClientEmailSettings).filter(
            models.DBClientEmailSettings.client_id == client_id).first()
        if not row:
            row = models.DBClientEmailSettings(client_id=client_id)
            db.add(row)
        row.transport = "gmail"
        db.commit()


def token_for(client_id, own_only=False):
    with main.SessionLocal() as db:
        return main.get_stored_refresh_token(db, client_id=client_id,
                                             own_only=own_only)


# --- the leak nobody would have seen ------------------------------------------

def test_one_business_never_gets_another_business_token(client, tenant):
    """The lookup used to end with "any row in the table". With no platform
    token - the normal state of a fresh install - that is another tenant's
    Google account, and their invoices leave through it."""
    mine = tenant.get("/api/client/me").json()["id"]
    give_token(mine + 1000, "somebody-elses-token")

    assert token_for(mine) is None, \
        "it handed over a token belonging to a different business"


def test_and_not_even_when_asked_without_own_only(client, tenant):
    """The guard cannot depend on the caller remembering a flag."""
    mine = tenant.get("/api/client/me").json()["id"]
    give_token(mine + 1000, "somebody-elses-token")
    assert token_for(mine, own_only=False) is None


# --- disconnect has to mean disconnected -----------------------------------------

def test_a_business_that_chose_gmail_and_disconnected_cannot_send(client, tenant):
    """What was reported: Disconnect, and it still said the email was sent."""
    mine = tenant.get("/api/client/me").json()["id"]
    chose_gmail(mine)
    give_token(None, "the-platform-token")

    # Connected: their own account is there.
    give_token(mine, "their-own-token")
    assert token_for(mine, own_only=True) == "their-own-token"

    # Disconnected: theirs is gone, and ours is not a substitute.
    with main.SessionLocal() as db:
        db.query(models.DBSettings).filter(
            models.DBSettings.key == "GOOGLE_REFRESH_TOKEN",
            models.DBSettings.client_id == mine).delete()
        db.commit()

    assert token_for(mine, own_only=True) is None, \
        "it fell back to the platform account after a disconnect"


def test_and_the_screen_says_so_rather_than_claiming_it_can_send(client, tenant):
    """The readiness check has to ask the same question, or the app reports a
    business as able to send when nothing of theirs is connected."""
    mine = tenant.get("/api/client/me").json()["id"]
    chose_gmail(mine)
    give_token(None, "the-platform-token")

    with main.SessionLocal() as db:
        ready, why = main.email_delivery_ready(db, mine)
    assert ready is False, "it said they could send using our account"
    assert "no Google account is connected" in why, why


def test_sending_refuses_rather_than_using_our_account(client, tenant, monkeypatch):
    """End to end: the send itself must not go out through the platform."""
    mine = tenant.get("/api/client/me").json()["id"]
    chose_gmail(mine)
    give_token(None, "the-platform-token")

    sent = []
    monkeypatch.setattr(main, "build",
                        lambda *a, **k: sent.append("went out") or object())

    ok, detail = main.send_email_background(
        "customer@example.com", "Invoice", "body", "Acme <a@b.com>",
        client_id=mine)

    assert ok is False, detail
    assert "No Google account is connected" in detail, detail
    assert not sent, "it sent through the platform's account anyway"


# --- what should still work ----------------------------------------------------------

def test_a_business_that_chose_nothing_still_uses_the_platform(client, tenant):
    """The fallback is right for somebody who never picked a transport - it is
    only wrong once they have chosen their own and lost it."""
    mine = tenant.get("/api/client/me").json()["id"]
    give_token(None, "the-platform-token")
    assert token_for(mine) == "the-platform-token"


def test_a_connected_business_uses_its_own(client, tenant):
    mine = tenant.get("/api/client/me").json()["id"]
    give_token(None, "the-platform-token")
    give_token(mine, "their-own-token")
    assert token_for(mine) == "their-own-token"
    assert token_for(mine, own_only=True) == "their-own-token"


def test_the_platform_itself_still_finds_its_own(client):
    give_token(None, "the-platform-token")
    with main.SessionLocal() as db:
        assert main.get_stored_refresh_token(db, client_id=None) == "the-platform-token"


def test_the_platform_does_not_borrow_a_tenant_token_either(client, tenant):
    """The same leak in the other direction: our own codes must not go out
    through a customer's Gmail account."""
    mine = tenant.get("/api/client/me").json()["id"]
    give_token(mine, "their-own-token")
    with main.SessionLocal() as db:
        assert main.get_stored_refresh_token(db, client_id=None) is None
