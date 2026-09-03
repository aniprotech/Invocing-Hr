"""The way back in for a locked-out account owner.

A reset flow is a way to take over an account if it is wrong, so most of this
is about what must *not* work: guessing, reusing, enumerating, or resetting
somebody else's password.
"""
import uuid
from datetime import datetime, timedelta

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _email_can_send(monkeypatch):
    """A transport that exists, so the readiness check is exercised rather
    than stubbed.

    A reset link nobody can send now says so instead of claiming to be on its
    way - which is how a real "I reset it and it still says invalid" turned
    out to be an email that never left.
    """
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
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
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        if row:
            row.value = was or "gmail"
            db.commit()


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def owner(client):
    email = f"owner-{uuid.uuid4().hex[:10]}@example.com"
    res = client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Locked Out Ltd",
    })
    assert res.status_code == 200, res.text
    return {"email": email, "password": "Passw0rdTest"}


def token_for(email):
    """Read the token the way only the mailbox owner could.

    Only its hash is stored, so the test generates a matching pair directly.
    """
    with main.SessionLocal() as db:
        c = db.query(models.DBClient).filter(models.DBClient.email == email).first()
        row = db.query(models.DBPasswordReset).filter(
            models.DBPasswordReset.client_id == c.id,
            models.DBPasswordReset.used_at == "",
        ).order_by(models.DBPasswordReset.id.desc()).first()
        return row, c.id


def issue_token(email, minutes=60):
    """Put a known token on the account, as forgot-password would."""
    raw = uuid.uuid4().hex
    with main.SessionLocal() as db:
        c = db.query(models.DBClient).filter(models.DBClient.email == email).first()
        db.add(models.DBPasswordReset(
            client_id=c.id, token_hash=main.hash_reset_token(raw),
            expires_at=(datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        db.commit()
    return raw


# --- requesting ---------------------------------------------------------------

def test_requesting_a_reset_is_accepted(client, owner):
    res = client.post("/api/client/forgot-password", json={"email": owner["email"]})
    assert res.status_code == 200
    row, _ = token_for(owner["email"])
    assert row is not None, "a reset should have been recorded"


def test_an_unknown_address_gets_the_same_answer(client, owner):
    """Otherwise this endpoint tells you who has an account here."""
    known = client.post("/api/client/forgot-password", json={"email": owner["email"]})
    unknown = client.post("/api/client/forgot-password",
                          json={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


def test_the_raw_token_is_never_stored(client, owner):
    client.post("/api/client/forgot-password", json={"email": owner["email"]})
    row, _ = token_for(owner["email"])
    assert len(row.token_hash) == 64          # sha256 hex
    assert row.token_hash.islower()


def test_asking_again_kills_the_previous_link(client, owner):
    first = issue_token(owner["email"])
    client.post("/api/client/forgot-password", json={"email": owner["email"]})
    res = client.post("/api/client/reset-password",
                      json={"token": first, "password": "BrandNew123"})
    assert res.status_code == 400


def test_requesting_is_rate_limited(client, owner):
    for _ in range(5):
        client.post("/api/client/forgot-password", json={"email": owner["email"]})
    res = client.post("/api/client/forgot-password", json={"email": owner["email"]})
    assert res.status_code == 429


# --- resetting ----------------------------------------------------------------

def test_a_valid_token_changes_the_password(client, owner):
    raw = issue_token(owner["email"])
    res = client.post("/api/client/reset-password",
                      json={"token": raw, "password": "BrandNew123"})
    assert res.status_code == 200, res.text

    assert client.post("/api/client/login", json={
        "email": owner["email"], "password": "BrandNew123"}).status_code == 200
    assert client.post("/api/client/login", json={
        "email": owner["email"], "password": owner["password"]}).status_code == 401


def test_a_token_works_only_once(client, owner):
    raw = issue_token(owner["email"])
    assert client.post("/api/client/reset-password",
                       json={"token": raw, "password": "BrandNew123"}).status_code == 200
    again = client.post("/api/client/reset-password",
                        json={"token": raw, "password": "Different456"})
    assert again.status_code == 400


def test_an_expired_token_is_refused(client, owner):
    raw = issue_token(owner["email"], minutes=-1)
    res = client.post("/api/client/reset-password",
                      json={"token": raw, "password": "BrandNew123"})
    assert res.status_code == 400
    assert client.post("/api/client/login", json={
        "email": owner["email"], "password": owner["password"]}).status_code == 200


@pytest.mark.parametrize("token", ["", "nonsense", "a" * 64])
def test_a_made_up_token_is_refused(client, owner, token):
    res = client.post("/api/client/reset-password",
                      json={"token": token, "password": "BrandNew123"})
    assert res.status_code == 400


def test_the_new_password_must_meet_the_same_rules_as_signing_up(client, owner):
    for weak in ("short1A", "alllowercase1", "NODIGITSHERE"):
        raw = issue_token(owner["email"])
        res = client.post("/api/client/reset-password",
                          json={"token": raw, "password": weak})
        assert res.status_code == 400, weak
        # A refused attempt must not burn the link.
        assert client.post("/api/client/reset-password",
                           json={"token": raw, "password": "GoodPass123"}).status_code == 200


def test_a_token_cannot_reset_a_different_account(client, owner):
    other_email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other_email, "password": "Passw0rdTest", "company_name": "Other Ltd"})

    raw = issue_token(owner["email"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "BrandNew123"})

    # The other account is untouched.
    assert client.post("/api/client/login", json={
        "email": other_email, "password": "Passw0rdTest"}).status_code == 200


# --- checking a link before using it -------------------------------------------

def test_the_page_can_ask_whether_a_link_is_still_good(client, owner):
    raw = issue_token(owner["email"])
    assert client.get(f"/api/client/reset-password?token={raw}").json()["valid"] is True

    client.post("/api/client/reset-password", json={"token": raw, "password": "BrandNew123"})
    assert client.get(f"/api/client/reset-password?token={raw}").json()["valid"] is False


def test_checking_a_missing_token_says_no(client):
    assert client.get("/api/client/reset-password?token=").json()["valid"] is False


# --- staff, who are the ones actually signing in with a password ---------------

def issue_employee_token(emp_id, minutes=60):
    raw = uuid.uuid4().hex
    with main.SessionLocal() as db:
        db.add(models.DBPasswordReset(
            user_type="employee", employee_id=emp_id,
            token_hash=main.hash_reset_token(raw),
            expires_at=(datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"),
        ))
        db.commit()
    return raw


@pytest.fixture
def staffer(tenant):
    from conftest import make_employee
    return make_employee(tenant, password="EmpPass123")


def test_an_employee_can_reset_their_own_password(client, staffer):
    raw = issue_employee_token(staffer["id"])
    res = client.post("/api/client/reset-password",
                      json={"token": raw, "password": "NewStaff123"})
    assert res.status_code == 200, res.text

    assert client.post("/api/employee/auth/login", json={
        "email": staffer["email"], "password": "NewStaff123"}).status_code == 200
    assert client.post("/api/employee/auth/login", json={
        "email": staffer["email"], "password": "EmpPass123"}).status_code == 401


def test_requesting_a_staff_reset_is_accepted(client, staffer):
    res = client.post("/api/employee/forgot-password", json={"email": staffer["email"]})
    assert res.status_code == 200
    with main.SessionLocal() as db:
        row = db.query(models.DBPasswordReset).filter(
            models.DBPasswordReset.employee_id == staffer["id"]).first()
    assert row is not None
    assert row.user_type == "employee"


def test_an_unknown_staff_address_gets_the_same_answer(client, staffer):
    known = client.post("/api/employee/forgot-password", json={"email": staffer["email"]})
    unknown = client.post("/api/employee/forgot-password", json={"email": "ghost@example.com"})
    assert known.json() == unknown.json()


def test_a_staff_token_does_not_touch_the_owner_account(client, owner, staffer):
    raw = issue_employee_token(staffer["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "NewStaff123"})
    assert client.post("/api/client/login", json={
        "email": owner["email"], "password": owner["password"]}).status_code == 200


def test_an_expired_staff_token_is_refused(client, staffer):
    raw = issue_employee_token(staffer["id"], minutes=-1)
    assert client.post("/api/client/reset-password",
                       json={"token": raw, "password": "NewStaff123"}).status_code == 400


def test_a_reset_nobody_can_send_says_so(client, monkeypatch):
    """Reported from production: "I reset it and it still says invalid".

    The link was never sent - the server had no mail transport - but the page
    said one was on its way, so the password was never actually changed and
    the old one kept failing. Refusing here gives nothing away, because it is
    checked before the address is looked at.
    """
    monkeypatch.delenv("SMTP_HOST", raising=False)
    import uuid as _uuid
    email = f"nomail-{_uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "OldPassw0rd", "company_name": "No Mail Ltd"})

    main.rate_limiter._hits.clear()
    res = client.post("/api/client/forgot-password", json={"email": email})
    assert res.status_code == 503, res.text
    assert "cannot send email" in res.json()["detail"]


def test_that_refusal_is_the_same_for_a_stranger(client, monkeypatch):
    """It must not become a way of finding out which addresses have accounts."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    main.rate_limiter._hits.clear()
    known = client.post("/api/client/forgot-password",
                        json={"email": "anybody@example.com"})
    main.rate_limiter._hits.clear()
    stranger = client.post("/api/client/forgot-password",
                           json={"email": "nobody-at-all@example.com"})
    assert known.status_code == stranger.status_code == 503
    assert known.json() == stranger.json()
