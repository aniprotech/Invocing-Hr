"""The two ways a code is asked for, and the two ways it went missing.

Neither OTP flow was broken in its own logic. Both depended on the server
being able to send at all, and both handled not being able to badly.

Registering makes no code when mail is down - correctly, since a code nobody
can send is worse than none. But the screen then asked somebody to type in a
code that was never made, and the only way to learn otherwise was to press
resend and read the error.

The operator's own sign-in code went further: the lookup lowercases what was
typed and compares it exactly against the column, so an address stored with a
capital in it matched nothing - and because the answer is deliberately the
same either way, it replied "if that account exists, a code has been sent"
and sent nothing. Silent by design, for a case that was never meant to be
silent.
"""
import uuid

import pytest

import main
import models


@pytest.fixture
def mail_is_down(monkeypatch):
    """A server with no way to send anything."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None).first()          # noqa: E711
        before = row.value if row else None
        if row:
            row.value = "smtp"
        else:
            db.add(models.DBSettings(key="email.transport", client_id=None,
                                     value="smtp"))
        db.commit()
    yield
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None).first()          # noqa: E711
        if row:
            row.value = before or "gmail"
            db.commit()


def signed_up(client):
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    assert client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest",
        "company_name": "Acme Ltd"}).status_code == 200
    assert client.post("/api/client/login", json={
        "email": email, "password": "Passw0rdTest"}).status_code == 200
    return email


# --- the signup code -----------------------------------------------------------

def test_the_screen_says_when_no_code_could_be_sent(client, mail_is_down):
    """Otherwise it asks for a code that was never made, and the person
    concludes the code is wrong rather than that none arrived."""
    signed_up(client)
    status = client.get("/api/client/verification-status").json()

    assert status["verified"] is False
    assert status["can_send"] is False
    assert status["blocked_reason"], status
    assert "smtp" in status["blocked_reason"].lower(), status["blocked_reason"]


def test_and_says_nothing_of_the_sort_when_it_can(client):
    signed_up(client)
    status = client.get("/api/client/verification-status").json()
    assert status["can_send"] is True
    assert status["blocked_reason"] == ""


def test_asking_again_when_it_cannot_send_says_why(client, mail_is_down):
    signed_up(client)
    res = client.post("/api/client/resend-verification")
    assert res.status_code == 503, res.text
    assert "cannot send" in res.json()["detail"].lower()


def test_a_code_still_works_once_it_can_be_sent(client):
    """All the way through, so the parts are known to fit together.

    The code is only ever stored hashed, which is the point of it - so rather
    than read one back, this puts a known hash in place and proves the compare
    accepts exactly that and nothing else.
    """
    signed_up(client)
    cid = client.get("/api/client/me").json()["id"]

    with main.SessionLocal() as db:
        row = db.query(models.DBEmailVerification).filter(
            models.DBEmailVerification.client_id == cid,
            models.DBEmailVerification.used_at == "").order_by(
                models.DBEmailVerification.id.desc()).first()
        assert row is not None, "registering sent no code"
        row.code_hash = main._hash_otp("424242")
        db.commit()

    assert client.post("/api/client/verify-email",
                       json={"code": "424241"}).status_code == 400
    ok = client.post("/api/client/verify-email", json={"code": "424242"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["verified"] is True

    after = client.get("/api/client/verification-status").json()
    assert after["verified"] is True


def test_a_code_cannot_be_spent_twice(client):
    signed_up(client)
    cid = client.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        row = db.query(models.DBEmailVerification).filter(
            models.DBEmailVerification.client_id == cid).order_by(
                models.DBEmailVerification.id.desc()).first()
        row.code_hash = main._hash_otp("515151")
        db.commit()

    assert client.post("/api/client/verify-email",
                       json={"code": "515151"}).status_code == 200
    # Already verified, so the second one is a no-op rather than an error.
    again = client.post("/api/client/verify-email", json={"code": "515151"})
    assert again.json()["verified"] is True


# --- the operator's own code ------------------------------------------------------

def operator_stored_as(email, username="superadmin"):
    """Put the operator's address in the database exactly as given."""
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).first()
        was = (row.email, row.username)
        row.email, row.username = email, username
        db.commit()
    return was


def restore_operator(was):
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).first()
        row.email, row.username = was
        db.commit()


def codes_for_operator():
    """Every code ever made for this operator.

    Counting only the live ones would say nothing: asking for a code retires
    whatever was outstanding first, so the number of unused codes is 1 before
    and 1 after, whether or not anything happened.
    """
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).first()
        return db.query(models.DBSuperAdminOtp).filter(
            models.DBSuperAdminOtp.super_admin_id == row.id).count()


@pytest.mark.parametrize("typed", [
    "Hello@KeyRoutes.co",       # as somebody's phone would capitalise it
    "HELLO@KEYROUTES.CO",
    "  hello@keyroutes.co  ",
])
def test_the_operator_gets_a_code_whatever_case_it_is_typed_in(client, typed):
    was = operator_stored_as("hello@keyroutes.co")
    try:
        before = codes_for_operator()
        res = client.post("/api/superadmin/request-otp", json={"identifier": typed})
        assert res.status_code == 200, res.text
        assert codes_for_operator() == before + 1, \
            f"{typed!r} produced no code, and said it had"
    finally:
        restore_operator(was)


def test_and_when_the_address_is_stored_with_capitals(client):
    """The stored side matters as much as the typed side."""
    was = operator_stored_as("Hello@KeyRoutes.co")
    try:
        before = codes_for_operator()
        res = client.post("/api/superadmin/request-otp",
                          json={"identifier": "hello@keyroutes.co"})
        assert res.status_code == 200, res.text
        assert codes_for_operator() == before + 1
    finally:
        restore_operator(was)


def test_the_username_is_matched_the_same_way(client):
    was = operator_stored_as("hello@keyroutes.co", username="SuperAdmin")
    try:
        before = codes_for_operator()
        assert client.post("/api/superadmin/request-otp",
                           json={"identifier": "superadmin"}).status_code == 200
        assert codes_for_operator() == before + 1
    finally:
        restore_operator(was)


def test_an_address_nobody_has_still_gives_nothing_away(client):
    """The reply has to stay the same, or this becomes a way of finding out
    which address runs the platform."""
    known = client.post("/api/superadmin/request-otp",
                        json={"identifier": "hello@keyroutes.co"})
    main.rate_limiter._hits.clear()
    unknown = client.post("/api/superadmin/request-otp",
                          json={"identifier": "nobody@example.com"})
    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()


def test_the_operator_cannot_be_asked_for_a_code_when_mail_is_down(
        client, mail_is_down):
    """Said out loud rather than answered with a promise, because a code that
    silently never arrives is the worse of the two."""
    res = client.post("/api/superadmin/request-otp",
                      json={"identifier": "hello@keyroutes.co"})
    assert res.status_code == 503, res.text
    assert "cannot send" in res.json()["detail"].lower()
