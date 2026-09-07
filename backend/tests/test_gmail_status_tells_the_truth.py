"""Whether the settings screen agrees with what sending actually does.

The screen said Gmail was connected and ready while every message failed.

gmail_ready was bool(refresh_token) - true the moment a token had ever been
stored, and true forever after. Google revoking that token changed nothing on
the screen. So the account holder saw a working connection, had no reason to
reconnect, and the invoices kept not arriving: the app reporting healthy and
the mail not turning up, with nothing to join the two together.

Readiness now asks whether the token can still be exchanged, which is the same
question sending asks. If it cannot, the screen says so and says what to do.

The address is read from what was stored when the account was connected, not
from users.getProfile. This app holds only gmail.send, and getProfile needs
gmail.readonly or gmail.metadata, so that call was always a 403 - the address
came back blank for healthy accounts exactly as it did for broken ones.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _no_tokens():
    def clear():
        with main.SessionLocal() as db:
            db.query(models.DBSettings).filter(models.DBSettings.key.in_(
                ("GOOGLE_REFRESH_TOKEN", "GOOGLE_SENDER_EMAIL"))).delete(
                    synchronize_session=False)
            db.commit()
    clear()
    yield
    clear()


@pytest.fixture
def google(monkeypatch):
    """Whether Google will still exchange the token we hold."""
    state = {"alive": True}

    class Creds:
        valid = True

    monkeypatch.setattr(main, "get_gmail_credentials",
                        lambda **kw: Creds() if state["alive"] else None)
    return state


def give_token(client_id, value="a-token"):
    with main.SessionLocal() as db:
        db.add(models.DBSettings(key="GOOGLE_REFRESH_TOKEN", value=value,
                                 client_id=client_id))
        db.commit()


def status(tenant):
    res = tenant.get("/api/gmail/status")
    assert res.status_code == 200, res.text
    return res.json()


def mine(tenant):
    return tenant.get("/api/client/me").json()["id"]


# --- the screen that lied ---------------------------------------------------------

def test_a_revoked_token_does_not_read_as_ready(client, tenant, google):
    """The whole finding. A stored token that Google will not exchange is not
    a working connection, and saying it is leaves somebody with no reason to
    fix the thing that is broken."""
    give_token(mine(tenant))
    google["alive"] = False

    assert status(tenant)["gmail_ready"] is False, status(tenant)


def test_and_says_it_needs_connecting_again(client, tenant, google):
    give_token(mine(tenant))
    google["alive"] = False

    said = status(tenant)["gmail_problem"]
    assert "no longer authorised" in said, said
    assert "connecting again" in said, said


def test_a_dead_token_is_distinguishable_from_no_token(client, tenant, google):
    """Two different situations needing two different things done about them:
    one is 'connect an account', the other is 'that account stopped working'."""
    give_token(mine(tenant))
    google["alive"] = False
    dead = status(tenant)
    assert dead["refresh_token_stored"] is True
    assert dead["gmail_broken"] is True

    with main.SessionLocal() as db:
        db.query(models.DBSettings).filter(
            models.DBSettings.key == "GOOGLE_REFRESH_TOKEN").delete()
        db.commit()

    none_at_all = status(tenant)
    assert none_at_all["refresh_token_stored"] is False
    assert none_at_all["gmail_broken"] is False
    assert "no Google account is connected" in none_at_all["gmail_problem"]


# --- and when it is genuinely fine ------------------------------------------------------

def test_a_live_token_reads_as_ready(client, tenant, google):
    give_token(mine(tenant))
    ready = status(tenant)
    assert ready["gmail_ready"] is True
    assert ready["gmail_broken"] is False
    assert ready["gmail_problem"] == ""


def test_no_token_is_not_ready_either(client, tenant, google):
    assert status(tenant)["gmail_ready"] is False


# --- which account it is ----------------------------------------------------------------

def test_the_connected_address_is_shown(client, tenant, google):
    """So somebody who connected the wrong Google account can see that they
    did. getProfile cannot answer this - the app only holds gmail.send."""
    who = mine(tenant)
    give_token(who)
    with main.SessionLocal() as db:
        db.add(models.DBSettings(key="GOOGLE_SENDER_EMAIL",
                                 value="billing@theirs.test", client_id=who))
        db.commit()

    assert status(tenant)["gmail_authorized_email"] == "billing@theirs.test"


def test_a_business_without_one_falls_back_to_the_platform_address(client, tenant, google):
    """It is the platform's account doing the sending in that case, so it is
    the platform's address that is true."""
    give_token(None)                       # platform token, no tenant token
    with main.SessionLocal() as db:
        db.add(models.DBSettings(key="GOOGLE_SENDER_EMAIL",
                                 value="ours@platform.test", client_id=None))
        db.commit()

    assert status(tenant)["gmail_authorized_email"] == "ours@platform.test"
