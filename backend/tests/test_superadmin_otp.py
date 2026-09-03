"""Signing in to the operator account with a code sent to its own address.

A password was the only way in, so losing it locked the operator out of their
own platform.

This is a login path, so the tests are mostly about what it must refuse. Six
digits is a million guesses, which is nothing to a script - so a code dies
after five wrong tries and after ten minutes, and trying is rate limited. And
the code must never appear in a response body: an endpoint that hands back the
code it just sent is not a second factor at all.
"""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
import models

OPERATOR = "hello@keyroutes.co"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield
    main.rate_limiter._hits.clear()


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    """A working transport, with nothing actually leaving the machine.

    The readiness check is deliberately not stubbed - it looks at what is
    configured, and a code that cannot be sent must be refused rather than
    silently lost. So a transport is configured for real and only the sending
    is captured.
    """
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    was = _set_transport("smtp")

    sent = []

    def fake_send(to_email, subject, body, from_email, *a, **kw):
        sent.append({"to": to_email, "subject": subject, "body": body})
        return True, "captured"

    monkeypatch.setattr(main, "send_email_background", fake_send)
    main._test_sent = sent
    yield sent
    _set_transport(was or "gmail")


def _set_transport(value):
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = value
        else:
            db.add(models.DBSettings(key="email.transport", client_id=None,
                                     value=value))
        db.commit()
        return was


def request_code(client, identifier=OPERATOR):
    res = client.post("/api/superadmin/request-otp", json={"identifier": identifier})
    assert res.status_code == 200, res.text
    return res


def latest_code():
    """The code as the operator would read it out of their inbox."""
    import re
    for message in reversed(main._test_sent):
        found = re.search(r"\b(\d{6})\b", message["subject"] + " " + message["body"])
        if found:
            return found.group(1)
    return None


def stored(db=None):
    with main.SessionLocal() as own:
        return own.query(models.DBSuperAdminOtp).order_by(
            models.DBSuperAdminOtp.id.desc()).first()


# --- asking for a code ------------------------------------------------------------
def test_a_code_is_sent_to_the_address_on_the_account(client):
    request_code(client)
    assert main._test_sent, "nothing was sent"
    assert main._test_sent[-1]["to"] == OPERATOR


def test_the_code_is_never_in_the_answer(client):
    """An endpoint that hands back the code it just sent is not a second
    factor - anyone who can reach it can sign in."""
    res = request_code(client)
    code = latest_code()
    assert code, "no code was generated"
    assert code not in res.text, res.text


def test_it_is_never_sent_to_an_address_in_the_request(client):
    """Otherwise anybody could have the operator's code posted to themselves."""
    res = client.post("/api/superadmin/request-otp",
                      json={"identifier": OPERATOR, "email_to": "thief@evil.test"})
    assert res.status_code == 200
    assert main._test_sent[-1]["to"] == OPERATOR


def test_an_unknown_address_gets_the_same_answer(client):
    """Saying "no such operator" would say who the operator is."""
    known = request_code(client)
    main._test_sent.clear()
    unknown = client.post("/api/superadmin/request-otp",
                          json={"identifier": "nobody@nowhere.test"})
    assert unknown.status_code == 200
    assert unknown.json() == known.json()
    assert main._test_sent == [], "an email went to a stranger"


def test_the_code_is_not_stored_as_typed(client):
    """Anybody who can read this table must not be able to sign in with what
    they find."""
    request_code(client)
    code = latest_code()
    row = stored()
    assert row.code_hash != code
    assert code not in row.code_hash


def test_asking_again_retires_the_previous_code(client):
    """Several live codes for one account is several chances to guess."""
    request_code(client)
    first = latest_code()
    request_code(client)

    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": first})
    assert res.status_code == 401, "the old code still worked"


def test_asking_over_and_over_is_refused(client):
    for _ in range(3):
        client.post("/api/superadmin/request-otp", json={"identifier": OPERATOR})
    res = client.post("/api/superadmin/request-otp", json={"identifier": OPERATOR})
    assert res.status_code == 429


# --- using it ----------------------------------------------------------------------
def test_the_right_code_signs_you_in(client):
    request_code(client)
    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": latest_code()})
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True
    # A real session, not just a cheerful answer.
    assert client.get("/api/superadmin/landing-items").status_code == 200


def test_a_wrong_code_is_refused(client):
    request_code(client)
    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": "000000"})
    assert res.status_code == 401


def test_a_code_works_once(client):
    request_code(client)
    code = latest_code()
    assert client.post("/api/superadmin/verify-otp",
                       json={"identifier": OPERATOR, "code": code}).status_code == 200
    with TestClient(main.app) as second:
        again = second.post("/api/superadmin/verify-otp",
                            json={"identifier": OPERATOR, "code": code})
        assert again.status_code == 401, "the code was reusable"


def test_five_wrong_guesses_kill_the_code(client):
    """Six digits is a million guesses, which is nothing to a script."""
    request_code(client)
    real = latest_code()
    for _ in range(main.OTP_MAX_ATTEMPTS):
        client.post("/api/superadmin/verify-otp",
                    json={"identifier": OPERATOR, "code": "000000"})

    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": real})
    assert res.status_code == 401, "the right code still worked after five wrong ones"


def test_an_expired_code_is_refused(client):
    request_code(client)
    code = latest_code()
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdminOtp).order_by(
            models.DBSuperAdminOtp.id.desc()).first()
        row.expires_at = (datetime.now() - timedelta(minutes=1)
                          ).strftime("%Y-%m-%d %H:%M:%S")
        db.commit()

    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": code})
    assert res.status_code == 401


def test_a_code_for_one_account_is_not_a_code_for_another(client):
    request_code(client)
    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": "nobody@nowhere.test", "code": latest_code()})
    assert res.status_code == 401


def test_no_code_at_all_is_refused(client):
    request_code(client)
    assert client.post("/api/superadmin/verify-otp",
                       json={"identifier": OPERATOR, "code": ""}).status_code == 401
    assert client.post("/api/superadmin/verify-otp",
                       json={"identifier": OPERATOR}).status_code == 401


def test_guessing_over_and_over_is_refused(client):
    request_code(client)
    codes = [f"{n:06d}" for n in range(11)]
    last = None
    for code in codes:
        last = client.post("/api/superadmin/verify-otp",
                           json={"identifier": OPERATOR, "code": code})
    assert last.status_code == 429, last.status_code


def test_signing_in_this_way_is_written_down(client):
    """A sign-in nobody can see afterwards is a sign-in nobody can question."""
    request_code(client)
    client.post("/api/superadmin/verify-otp",
                json={"identifier": OPERATOR, "code": latest_code()})
    logs = client.get("/api/superadmin/login-logs").json()
    rows = logs if isinstance(logs, list) else logs.get("logs", [])
    assert any(r.get("login_type") == "otp" and r.get("status") == "success" for r in rows), \
        rows[:3]


def test_a_refused_code_is_written_down_too(client):
    request_code(client)
    client.post("/api/superadmin/verify-otp",
                json={"identifier": OPERATOR, "code": "000000"})
    client.post("/api/superadmin/verify-otp",
                json={"identifier": OPERATOR, "code": latest_code()})
    logs = client.get("/api/superadmin/login-logs").json()
    rows = logs if isinstance(logs, list) else logs.get("logs", [])
    assert any(r.get("login_type") == "otp" and r.get("status") == "failed" for r in rows), \
        rows[:3]


# --- hardening --------------------------------------------------------------------
def _sign_in_as_a_tenant(client):
    """Any other identity, so there is something in the session to survive."""
    import uuid
    email = f"tenant-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Tenant Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
    assert client.get("/api/client/me").status_code == 200, "the tenant is not signed in"


def test_signing_in_with_a_code_starts_a_fresh_session(client):
    """Every sign-in route used to set the operator id onto whatever session
    the browser already had, keeping everything that was already in it. So a
    session somebody else knows, or a lower-privileged one, carried straight
    on into an operator session."""
    _sign_in_as_a_tenant(client)
    request_code(client)
    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": latest_code()})
    assert res.status_code == 200, res.text

    assert client.get("/api/superadmin/landing-items").status_code == 200
    assert client.get("/api/client/me").status_code in (401, 403),         "the old identity was still in the session"


def test_the_password_route_starts_a_fresh_session_too(client):
    """The same hole was in the password sign-in, and fixing one is not
    fixing it."""
    _sign_in_as_a_tenant(client)
    res = client.post("/api/superadmin/login", json={
        "identifier": OPERATOR, "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    assert client.get("/api/client/me").status_code in (401, 403),         "the old identity was still in the session"


def test_guessing_is_counted_against_the_account_not_only_the_address(client):
    """The per-address limit hands an attacker with a pool of addresses a
    fresh allowance from every one of them, so the account being attacked has
    to be counted too.

    The test client always reports the same address, so this checks the
    counter itself rather than pretending to move: after a few attempts there
    must be a tally keyed on the account.
    """
    request_code(client)
    main.rate_limiter._hits.clear()

    client.post("/api/superadmin/verify-otp",
                json={"identifier": OPERATOR, "code": "000000"})

    keys = list(main.rate_limiter._hits.keys())
    account_keys = [k for k in keys if OPERATOR in k]
    assert account_keys, keys


def test_asking_for_codes_is_counted_against_the_account_too(client):
    """Otherwise a pool of addresses floods one operator's inbox."""
    main.rate_limiter._hits.clear()
    client.post("/api/superadmin/request-otp", json={"identifier": OPERATOR})

    keys = list(main.rate_limiter._hits.keys())
    assert [k for k in keys if OPERATOR in k], keys


def test_a_used_code_tells_the_operator(client):
    """Somebody signing in with a code is the thing an operator most needs to
    hear about if it was not them."""
    request_code(client)
    code = latest_code()
    main._test_sent.clear()
    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": code})
    assert res.status_code == 200, res.text
    assert main._test_sent, "nothing was sent"
    told = main._test_sent[-1]
    assert told["to"] == OPERATOR
    assert "signed in" in told["subject"].lower(), told["subject"]


def test_that_warning_does_not_carry_a_code(client):
    """It is sent to an address that may already be in the wrong hands."""
    request_code(client)
    code = latest_code()
    main._test_sent.clear()
    client.post("/api/superadmin/verify-otp",
                json={"identifier": OPERATOR, "code": code})
    told = main._test_sent[-1]
    assert code not in told["subject"] + told["body"]


def test_a_server_that_cannot_send_email_says_so(client, monkeypatch):
    """Reported from production: the code never arrived and nothing said why.

    Refusing here gives nothing away, because it is checked before the account
    is looked at - the answer is the same whoever asks. Staying quiet only
    means somebody sits waiting for an email that was never going to come.
    """
    monkeypatch.delenv("SMTP_HOST", raising=False)
    was = _set_transport("smtp")
    try:
        res = client.post("/api/superadmin/request-otp",
                          json={"identifier": OPERATOR})
        assert res.status_code == 503, res.text
        assert "SMTP_HOST" in res.json()["detail"], res.json()
        assert main._test_sent == [], "it tried to send anyway"
    finally:
        _set_transport(was or "gmail")


def test_that_refusal_says_nothing_about_the_account(client, monkeypatch):
    """It must be the same answer for a stranger, or it becomes a way of
    finding out who the operator is."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    was = _set_transport("smtp")
    try:
        known = client.post("/api/superadmin/request-otp",
                            json={"identifier": OPERATOR})
        main.rate_limiter._hits.clear()
        stranger = client.post("/api/superadmin/request-otp",
                               json={"identifier": "nobody@nowhere.test"})
        assert known.status_code == stranger.status_code == 503
        assert known.json() == stranger.json()
    finally:
        _set_transport(was or "gmail")


# --- setting a new password ---------------------------------------------------------
# These change a real credential in a database that outlives the run. Restoring
# it inline does not survive a failure half way through - the first version of
# this left the operator locked out of the dev database - so it is a fixture,
# which runs whatever happens.
@pytest.fixture
def password_restored():
    def snapshot():
        with main.SessionLocal() as db:
            row = db.query(models.DBSuperAdmin).filter(
                models.DBSuperAdmin.email == OPERATOR).first()
            return row.password_hash if row else ""

    was = snapshot()
    yield
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.email == OPERATOR).first()
        if row:
            row.password_hash = was
            db.commit()


def sign_in_with_code(client):
    request_code(client)
    res = client.post("/api/superadmin/verify-otp",
                      json={"identifier": OPERATOR, "code": latest_code()})
    assert res.status_code == 200, res.text


def sign_in_with_password(client, password="TestSuper123"):
    res = client.post("/api/superadmin/login",
                      json={"identifier": OPERATOR, "password": password})
    assert res.status_code == 200, res.text


def test_a_code_lets_you_set_a_new_password_without_the_old_one(client, password_restored):
    """The whole point of having codes: somebody who has forgotten the
    password can still get back in, and only from the inbox on the account."""
    sign_in_with_code(client)
    res = client.post("/api/superadmin/change-password",
                      json={"new_password": "BrandNewPass1"})
    assert res.status_code == 200, res.text
    assert res.json()["by_code"] is True

    main.rate_limiter._hits.clear()
    with TestClient(main.app) as fresh:
        assert fresh.post("/api/superadmin/login", json={
            "identifier": OPERATOR, "password": "BrandNewPass1"}).status_code == 200


def test_a_password_session_still_needs_the_current_password(client, password_restored):
    """This asked for nothing at all, so anybody who got hold of an operator
    session could lock the real operator out for good."""
    sign_in_with_password(client)
    res = client.post("/api/superadmin/change-password",
                      json={"new_password": "SomethingElse1"})
    assert res.status_code == 400, res.text
    assert "current password" in res.json()["detail"]


def test_the_wrong_current_password_is_refused(client, password_restored):
    sign_in_with_password(client)
    # There has to be a hash for the current-password rule to apply at all.
    client_code_reset(client)
    res = client.post("/api/superadmin/change-password",
                      json={"current_password": "not-it",
                            "new_password": "SomethingElse1"})
    assert res.status_code == 401, res.text


def client_code_reset(client):
    """Give the account a real password hash, the supported way."""
    sign_in_with_code(client)
    assert client.post("/api/superadmin/change-password",
                       json={"new_password": "KnownPass123"}).status_code == 200
    main.rate_limiter._hits.clear()
    client.post("/api/superadmin/login",
                json={"identifier": OPERATOR, "password": "KnownPass123"})


def test_the_right_current_password_is_accepted(client, password_restored):
    client_code_reset(client)
    res = client.post("/api/superadmin/change-password",
                      json={"current_password": "KnownPass123",
                            "new_password": "AnotherPass1"})
    assert res.status_code == 200, res.text
    assert res.json()["by_code"] is False


def test_one_code_sets_one_password(client, password_restored):
    """Otherwise the code stays a reset token for the rest of the session, and
    a machine left open is a way in for as long as the tab is."""
    sign_in_with_code(client)
    first = client.post("/api/superadmin/change-password",
                        json={"new_password": "FirstChange1"})
    assert first.status_code == 200, first.text

    again = client.post("/api/superadmin/change-password",
                        json={"new_password": "SecondChange1"})
    assert again.status_code == 400, "the code was still good for another go"


def test_a_code_that_has_gone_stale_is_not_a_reset(client, password_restored):
    """A session left open on a borrowed machine must not still be a reset
    token tomorrow. The window is checked against the stamp, so a stamp older
    than the window is the thing to test."""
    stale = (datetime.now() - timedelta(minutes=main.OTP_RESET_MINUTES + 5)
             ).strftime("%Y-%m-%d %H:%M:%S")

    class Stamped:
        def __init__(self, value):
            self.session = {"superadmin_otp_at": value}

    assert main.signed_in_with_a_recent_code(Stamped(stale)) is False
    fresh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assert main.signed_in_with_a_recent_code(Stamped(fresh)) is True
    assert main.signed_in_with_a_recent_code(Stamped("")) is False
    assert main.signed_in_with_a_recent_code(Stamped("not a date")) is False


def test_a_short_password_is_refused(client, password_restored):
    sign_in_with_code(client)
    res = client.post("/api/superadmin/change-password",
                      json={"new_password": "short1"})
    assert res.status_code == 400
    assert "8 characters" in res.json()["detail"]


def test_the_form_is_told_whether_it_must_ask(client, password_restored):
    sign_in_with_code(client)
    got = client.get("/api/superadmin/password-status").json()
    assert got["can_reset_with_code"] is True

    main.rate_limiter._hits.clear()
    with TestClient(main.app) as other:
        other.post("/api/superadmin/login",
                   json={"identifier": OPERATOR, "password": "TestSuper123"})
        assert other.get("/api/superadmin/password-status"
                         ).json()["can_reset_with_code"] is False


def test_changing_it_is_written_down(client, password_restored):
    sign_in_with_code(client)
    client.post("/api/superadmin/change-password", json={"new_password": "LoggedChange1"})
    logs = client.get("/api/superadmin/login-logs").json()
    rows = logs if isinstance(logs, list) else logs.get("logs", [])
    assert any(r.get("login_type") == "password_change" and r.get("status") == "success"
               for r in rows), rows[:3]


def test_a_password_you_chose_survives_a_restart(client, password_restored):
    """SUPERADMIN_PASSWORD used to be reapplied on every startup, so a
    password set in the app was silently back to the environment value after
    the next deploy and nobody was told why."""
    sign_in_with_code(client)
    assert client.post("/api/superadmin/change-password",
                       json={"new_password": "ChosenPass123"}).status_code == 200

    main.ensure_super_admin()          # what a restart does

    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.email == OPERATOR).first()
        assert main.verify_password("ChosenPass123", row.password_hash), \
            "the restart wiped the password that was chosen"


def test_the_environment_password_still_sets_up_a_fresh_install(password_restored):
    """It is for the first run, when there is nothing to keep."""
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.email == OPERATOR).first()
        row.password_hash = ""
        db.commit()

    main.ensure_super_admin()

    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.email == OPERATOR).first()
        assert row.password_hash, "a fresh install got no password at all"


def test_it_can_still_be_forced_back_for_a_locked_out_operator(password_restored,
                                                               monkeypatch):
    """Losing the password and the inbox has to be recoverable somehow."""
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.email == OPERATOR).first()
        row.password_hash = main.hash_password("SomethingElse123")
        db.commit()

    monkeypatch.setenv("SUPERADMIN_PASSWORD_FORCE", "true")
    main.ensure_super_admin()

    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.email == OPERATOR).first()
        assert main.verify_password("TestSuper123", row.password_hash)
