"""An address is the same address however it was typed.

Reported as "I changed my password and it still says invalid credentials",
and that is exactly what it looked like from the outside.

Registering stored the address exactly as typed and signing in matched it
exactly, while the reset flow matched without regard to case. So somebody who
signed up as Uday@Gmail.com and asked to reset as uday@gmail.com had the
password changed on an account the sign-in could not find. The reset worked.
The login could never work.

Existing accounts were stored as typed, so matching has to be
case-insensitive rather than relying on what is in the column.
"""
import uuid

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield
    main.rate_limiter._hits.clear()


def register(client, email, password="OldPassw0rd"):
    return client.post("/api/client/register", json={
        "email": email, "password": password, "company_name": "Case Ltd"})


def login(client, email, password="OldPassw0rd"):
    main.rate_limiter._hits.clear()
    return client.post("/api/client/login", json={"email": email, "password": password})


def test_capitals_do_not_make_a_different_account(client):
    mixed = f"Probe-{uuid.uuid4().hex[:8]}@Example.COM"
    assert register(client, mixed).status_code == 200
    assert login(client, mixed.lower()).status_code == 200, "lowercase was refused"
    assert login(client, mixed.upper()).status_code == 200, "uppercase was refused"


def test_a_stray_space_does_not_either(client):
    """Autofill and copy-paste add them, and nobody can see one."""
    email = f"probe-{uuid.uuid4().hex[:8]}@example.com"
    register(client, email)
    assert login(client, f"  {email} ").status_code == 200


def test_an_account_stored_with_capitals_still_signs_in(client):
    """Every account that existed before this was stored exactly as typed, so
    the fix has to work on what is already in the column."""
    email = f"Legacy-{uuid.uuid4().hex[:8]}@Example.COM"
    register(client, email)
    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(
            main.sqlfunc.lower(models.DBClient.email) == email.lower()).first()
        row.email = email          # put the capitals back, as a legacy row
        db.commit()

    assert login(client, email.lower()).status_code == 200


def test_you_cannot_register_the_same_address_twice_in_different_capitals(client):
    """Two accounts differing only in capitals is one person locked out of
    whichever one they did not mean."""
    email = f"twice-{uuid.uuid4().hex[:8]}@example.com"
    assert register(client, email).status_code == 200
    again = register(client, email.upper())
    assert again.status_code == 400, again.text
    assert "already registered" in again.json()["detail"]


def test_a_reset_and_a_sign_in_find_the_same_account(client, monkeypatch):
    """The whole bug in one test: the reset matched case-insensitively and
    the login did not, so a password could be changed on an account nobody
    could then sign in to."""
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = "smtp"
        else:
            db.add(models.DBSettings(key="email.transport", client_id=None, value="smtp"))
        db.commit()

    sent = {}

    def capture(to_email, subject, body, from_email, *a, **kw):
        sent["body"] = body
        return True, "captured"

    monkeypatch.setattr(main, "send_email_background", capture)

    mixed = f"Both-{uuid.uuid4().hex[:8]}@Example.COM"
    register(client, mixed)
    try:
        main.rate_limiter._hits.clear()
        asked = client.post("/api/client/forgot-password", json={"email": mixed.lower()})
        assert asked.status_code == 200, asked.text

        import re
        token = re.search(r"token=([A-Za-z0-9_\-]+)", sent.get("body") or "")
        assert token, "no reset link was sent"

        done = client.post("/api/client/reset-password",
                           json={"token": token.group(1), "password": "NewPassw0rd1"})
        assert done.status_code == 200, done.text

        # The point: the address that got the reset can sign in with it.
        assert login(client, mixed.lower(), "NewPassw0rd1").status_code == 200
    finally:
        with main.SessionLocal() as db:
            row = db.query(models.DBSettings).filter(
                models.DBSettings.key == "email.transport",
                models.DBSettings.client_id == None,    # noqa: E711
            ).first()
            if row:
                row.value = was or "gmail"
                db.commit()
