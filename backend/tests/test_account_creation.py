"""Making an account, and the three things that were missing from it.

An address was never checked on the way in. The form carries type="email",
which is a convenience rather than a rule - anything posting straight at the
endpoint skipped it. The account was made, the code was sent nowhere, and
because an unconfirmed account is not allowed to send, that account could
never work and its owner had no way to find out why.

Signing in added to whatever session was already there instead of starting a
fresh one, which every other way in does.

And the verification code was the one message in the product that could fail
in silence.
"""
import uuid

import pytest

import main
import models


def address():
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


def register(client, email, password="Passw0rdTest", **extra):
    body = {"email": email, "password": password, "company_name": "Acme Ltd"}
    body.update(extra)
    return client.post("/api/client/register", json=body)


def accounts_matching(email):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            main.sqlfunc.lower(models.DBClient.email) == (email or "").strip().lower()
        ).count()


def deliveries_for(client_id, kind=None):
    with main.SessionLocal() as db:
        q = db.query(models.DBEmailDelivery).filter(
            models.DBEmailDelivery.client_id == client_id)
        if kind:
            q = q.filter(models.DBEmailDelivery.kind == kind)
        return [{"kind": r.kind, "status": r.status, "to": r.to_email,
                 "error": r.error} for r in q.all()]


# --- an address has to be one -----------------------------------------------------

@pytest.mark.parametrize("bad", [
    "nobody",                      # no @ at all
    "@example.com",                # nothing in front
    "someone@",                    # nothing behind
    "someone@localhost",           # no dot, so nothing to deliver to
    "two@@example.com",
    "spaced out@example.com",
    "",
])
def test_an_address_that_is_not_an_address_is_refused(client, bad):
    res = register(client, bad)
    assert res.status_code == 400, f"{bad!r} was accepted: {res.text}"
    assert "valid email" in res.json()["detail"].lower(), res.text


def test_and_no_account_is_left_behind_when_it_is_refused(client):
    bad = "definitely-not-an-address"
    register(client, bad)
    assert accounts_matching(bad) == 0


def test_ordinary_addresses_still_get_through(client):
    for good in (f"first.last+tag-{uuid.uuid4().hex[:6]}@sub.example.co.uk",
                 f"num123-{uuid.uuid4().hex[:6]}@example.io"):
        assert register(client, good).status_code == 200, good


def test_capitals_and_spaces_are_the_same_address(client):
    email = address()
    assert register(client, "  " + email.upper() + " ").status_code == 200
    # The one that reads as "I reset it and it still says invalid credentials".
    assert client.post("/api/client/login",
                       json={"email": email, "password": "Passw0rdTest"}
                       ).status_code == 200


def test_the_same_address_cannot_be_taken_twice(client):
    email = address()
    assert register(client, email).status_code == 200
    again = register(client, email.upper())
    assert again.status_code == 400
    assert "already" in again.json()["detail"].lower()


def test_a_password_that_is_too_weak_is_still_refused(client):
    assert register(client, address(), password="short").status_code == 400


# --- signing in starts a session rather than adopting one ---------------------------

def test_signing_in_does_not_inherit_an_earlier_session(client, monkeypatch):
    """A session left from a Google sign-in kept its 'user'. The header then
    went on naming whoever that was, while every action ran as this account -
    two different people on one screen."""
    stranger = f"someone.else-{uuid.uuid4().hex[:6]}@gmail.com"

    async def fake_token(request):
        return {"userinfo": {"email": stranger, "name": "Someone Else"},
                "access_token": "tok"}

    monkeypatch.setattr(main.oauth.google, "authorize_access_token", fake_token)
    client.get("/api/auth/callback", follow_redirects=False)
    assert client.get("/api/auth/me").json()["user"]["email"] == stranger

    mine = address()
    assert register(client, mine).status_code == 200
    assert client.post("/api/client/login",
                       json={"email": mine, "password": "Passw0rdTest"}
                       ).status_code == 200

    who = client.get("/api/auth/me").json()
    assert who["user"]["email"] == mine, "the old sign-in was still on the session"


def test_a_stale_google_token_does_not_follow_you_into_the_new_account(
        client, monkeypatch):
    async def fake_token(request):
        return {"userinfo": {"email": f"g-{uuid.uuid4().hex[:6]}@gmail.com"},
                "access_token": "tok", "refresh_token": "left-behind"}

    monkeypatch.setattr(main.oauth.google, "authorize_access_token", fake_token)
    client.get("/api/auth/callback", follow_redirects=False)

    mine = address()
    register(client, mine)
    client.post("/api/client/login", json={"email": mine, "password": "Passw0rdTest"})

    # Nothing of the previous sign-in should still be usable.
    assert client.get("/api/client/me").json()["email"] == mine


# --- the code that has to arrive ----------------------------------------------------

def test_the_verification_code_is_written_down_like_any_other_send(
        client, monkeypatch):
    """It used to be fired off and forgotten. A code that never left looked
    exactly like a code somebody had not read yet.

    The send is stubbed to succeed because the suite's mail server is not a
    real one - what is being checked is that the outcome gets written down,
    not what this machine's network can reach."""
    monkeypatch.setattr(main, "send_email_background", lambda *a, **k: (True, "sent"))
    email = address()
    res = register(client, email)
    assert res.json()["verification_sent"] is True

    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(
            main.sqlfunc.lower(models.DBClient.email) == email).first()
    rows = deliveries_for(row.id, "verification")
    assert len(rows) == 1, rows
    assert rows[0]["to"] == email
    # The outcome, not just the attempt. A row that stays "pending" forever
    # says only that we meant to send something.
    assert rows[0]["status"] == "sent", rows


def test_a_code_that_never_left_is_recorded_as_failed(client, monkeypatch):
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **k: (False, "mailbox unavailable"))
    email = address()
    register(client, email)

    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(
            main.sqlfunc.lower(models.DBClient.email) == email).first()
    rows = deliveries_for(row.id, "verification")
    assert rows and rows[0]["status"] == "failed", rows
    assert "mailbox unavailable" in rows[0]["error"]


def test_and_the_owner_can_see_it_on_the_failures_list(client, monkeypatch):
    """Otherwise the only person who can find out is whoever reads the logs."""
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **k: (False, "mailbox unavailable"))
    email = address()
    register(client, email)
    assert client.post("/api/client/login",
                       json={"email": email, "password": "Passw0rdTest"}
                       ).status_code == 200

    listed = client.get("/api/deliveries?status=failed")
    assert listed.status_code == 200, listed.text
    kinds = [d["kind"] for d in listed.json()["deliveries"]]
    assert "verification" in kinds, listed.json()


def test_a_signup_is_not_lost_when_the_server_cannot_send_at_all(
        client, monkeypatch):
    """The account is still made; the code can be asked for again. Refusing
    the signup would lose somebody over an outage that is ours, not theirs."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None).first()   # noqa: E711
        if row:
            row.value = "smtp"
            db.commit()

    email = address()
    res = register(client, email)
    assert res.status_code == 200, res.text
    assert res.json()["verification_sent"] is False
    assert accounts_matching(email) == 1
