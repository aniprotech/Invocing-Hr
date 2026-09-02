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
    """Nothing leaves the machine; the code is captured instead."""
    sent = []

    def fake_send(to_email, subject, body, from_email, *a, **kw):
        sent.append({"to": to_email, "subject": subject, "body": body})
        return True, "captured"

    monkeypatch.setattr(main, "send_email_background", fake_send)
    main._test_sent = sent
    yield sent


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
