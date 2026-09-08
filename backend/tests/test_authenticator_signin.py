"""Signing in with an authenticator app, which needs nothing delivered.

The emailed code is only ever as good as the mailbox it goes to. A domain with
no MX record has no mailbox, so the code is accepted by Google, bounces
somewhere else, and the operator waits for something that was never going to
arrive. That is how the operator of this platform came to be locked out of it,
and nothing in the sending path can see it happen.

A time-based code has nothing to deliver. The phone and the server hold the
same secret and both compute the same number from the clock.

The implementation is written out rather than pulled in, which is only
defensible because the construction is published with test vectors - RFC 6238,
Appendix B. The first test here checks against those rather than against my own
arithmetic, so a wrong implementation cannot agree with it by accident. Every
authenticator app computes the same numbers from the same secret, so agreeing
with the RFC is the same as agreeing with the phone.
"""
import base64
import time

import pytest

import main
import models


# RFC 6238, Appendix B - the SHA-1 rows. Secret is the ASCII "12345678901234567890".
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
RFC_VECTORS = [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
    (20000000000, "353130"),
]


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


@pytest.fixture
def operator(superadmin):
    """The signed-in operator, and their row."""
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            main.sqlfunc.lower(models.DBSuperAdmin.email) == "hello@keyroutes.co").first()
        ident = row.email or row.username
        rid = row.id
    yield {"client": superadmin, "id": rid, "identifier": ident}
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(models.DBSuperAdmin.id == rid).first()
        if row:
            row.totp_secret = ""
            row.totp_confirmed_at = ""
            row.totp_recovery = ""
            row.totp_last_step = 0
            db.commit()


def set_up(operator):
    res = operator["client"].post("/api/superadmin/totp/setup")
    assert res.status_code == 200, res.text
    return res.json()


def enable(operator):
    """Set up and confirm, as somebody scanning the QR would.

    Confirmed with the step before this one - still inside the drift window, so
    an app would be accepted with it - which leaves the current step unused for
    a test that then signs in. Confirming genuinely spends a code, so in real
    life the thirty seconds between scanning and signing in do this instead.
    """
    started = set_up(operator)
    code = main.totp_at(started["secret"], main.totp_step_now() - 1)
    res = operator["client"].post("/api/superadmin/totp/confirm", json={"code": code})
    assert res.status_code == 200, res.text
    return started["secret"], res.json()["recovery_codes"]


def sign_in(client, identifier, code):
    return client.post("/api/superadmin/login-with-app",
                       json={"identifier": identifier, "code": code})


# --- the construction itself ------------------------------------------------------

@pytest.mark.parametrize("at,expected", RFC_VECTORS)
def test_it_agrees_with_the_published_test_vectors(at, expected):
    """The whole reason writing this out is defensible. Every authenticator app
    computes these same numbers, so agreeing with the RFC is agreeing with the
    phone."""
    assert main.totp_at(RFC_SECRET, at // main.TOTP_STEP_SECONDS) == expected


def test_a_secret_is_the_base32_an_app_can_read():
    secret = main.totp_secret_new()
    base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    assert secret == secret.upper().rstrip("=")


def test_two_secrets_are_never_the_same():
    assert len({main.totp_secret_new() for _ in range(50)}) == 50


def test_the_setup_uri_is_what_an_app_expects():
    uri = main.totp_setup_uri("ABC234", "ops@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "secret=ABC234" in uri
    assert "period=30" in uri and "digits=6" in uri
    assert "ops%40example.com" in uri, uri


# --- the window, which is what "45 seconds" means ------------------------------------

def test_the_code_showing_on_the_phone_is_accepted():
    secret = main.totp_secret_new()
    now = time.time()
    assert main.totp_check(secret, main.totp_at(secret, main.totp_step_now(now)), at=now)[0]


def test_a_code_read_just_before_it_rolled_over_still_works():
    """Somebody typing six digits can cross a boundary while doing it."""
    secret = main.totp_secret_new()
    now = time.time()
    previous = main.totp_at(secret, main.totp_step_now(now) - 1)
    assert main.totp_check(secret, previous, at=now)[0]


def test_a_phone_running_slightly_fast_still_works():
    secret = main.totp_secret_new()
    now = time.time()
    ahead = main.totp_at(secret, main.totp_step_now(now) + 1)
    assert main.totp_check(secret, ahead, at=now)[0]


def test_a_code_from_two_minutes_ago_does_not():
    secret = main.totp_secret_new()
    now = time.time()
    old = main.totp_at(secret, main.totp_step_now(now) - 4)
    assert not main.totp_check(secret, old, at=now)[0]


def test_every_digit_has_to_match():
    """A comparison that stops early, or matches a prefix, would accept a code
    that is nearly right - and "nearly right" is what a guesser produces."""
    secret = main.totp_secret_new()
    now = time.time()
    right = main.totp_at(secret, main.totp_step_now(now))

    for i in range(len(right)):
        wrong = list(right)
        wrong[i] = "0" if right[i] != "0" else "1"
        near = "".join(wrong)
        assert not main.totp_check(secret, near, at=now)[0],             f"a code differing only at position {i} was accepted ({near} for {right})"


@pytest.mark.parametrize("junk", ["", "abcdef", "12345", "1234567", "  ", None])
def test_nonsense_is_refused_rather_than_raising(junk):
    assert main.totp_check(main.totp_secret_new(), junk)[0] is False


# --- setting it up -----------------------------------------------------------------------

def test_a_stranger_cannot_start_a_setup(client):
    assert client.post("/api/superadmin/totp/setup").status_code in (401, 403)
    assert client.get("/api/superadmin/totp/status").status_code in (401, 403)


def test_setup_hands_back_something_an_app_can_scan(operator):
    started = set_up(operator)
    assert started["secret"]
    assert started["uri"].startswith("otpauth://totp/")


def test_it_is_not_on_until_a_code_is_confirmed(operator):
    """A mistyped scan would otherwise lock the operator out of the very thing
    meant to let them in."""
    set_up(operator)
    assert operator["client"].get("/api/superadmin/totp/status").json()["enabled"] is False


def test_a_wrong_code_does_not_enable_it(operator):
    set_up(operator)
    res = operator["client"].post("/api/superadmin/totp/confirm", json={"code": "000000"})
    assert res.status_code == 400, res.text
    assert operator["client"].get("/api/superadmin/totp/status").json()["enabled"] is False


def test_confirming_turns_it_on_and_hands_over_recovery_codes(operator):
    _secret, codes = enable(operator)
    assert len(codes) == main.TOTP_RECOVERY_CODES
    assert len(set(codes)) == len(codes)
    status = operator["client"].get("/api/superadmin/totp/status").json()
    assert status["enabled"] is True
    assert status["recovery_codes_left"] == main.TOTP_RECOVERY_CODES


def test_the_secret_is_never_handed_out_again(operator):
    """It is enough to mint codes, so after setup it is a password."""
    enable(operator)
    body = operator["client"].get("/api/superadmin/totp/status").text
    assert "secret" not in body.lower(), body
    again = operator["client"].post("/api/superadmin/totp/setup")
    assert again.status_code == 409, again.text


def test_recovery_codes_are_not_stored_as_written(operator):
    """Anybody reading the table would otherwise hold eight ways in."""
    _secret, codes = enable(operator)
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.id == operator["id"]).first()
        stored = row.totp_recovery or ""
    for code in codes:
        assert code not in stored


# --- signing in with it ---------------------------------------------------------------------

def test_signing_in_with_the_app_works(client, operator):
    secret, _ = enable(operator)
    res = sign_in(client, operator["identifier"], main.totp_at(secret, main.totp_step_now()))
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True


def test_and_the_session_it_gives_reaches_operator_pages(client, operator):
    secret, _ = enable(operator)
    sign_in(client, operator["identifier"], main.totp_at(secret, main.totp_step_now()))
    assert client.get("/api/superadmin/me").status_code == 200


def test_a_wrong_code_is_refused(client, operator):
    enable(operator)
    assert sign_in(client, operator["identifier"], "000000").status_code == 401


def test_the_same_code_cannot_be_used_twice(client, operator):
    """A code is valid for its whole window, so without remembering the last
    one it can be replayed by anybody who read it over a shoulder."""
    secret, _ = enable(operator)
    code = main.totp_at(secret, main.totp_step_now())

    assert sign_in(client, operator["identifier"], code).status_code == 200
    again = sign_in(client, operator["identifier"], code)
    assert again.status_code == 401, "the same code signed in twice"


def test_an_account_without_an_authenticator_cannot_use_this_way_in(client, operator):
    assert sign_in(client, operator["identifier"], "123456").status_code == 401


def test_an_unknown_account_answers_the_same_as_a_wrong_code(client, operator):
    """Otherwise this says which operator addresses exist."""
    enable(operator)
    unknown = sign_in(client, "nobody@nowhere.test", "123456")
    wrong = sign_in(client, operator["identifier"], "000000")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


# --- a lost phone --------------------------------------------------------------------------------

def test_a_recovery_code_signs_in(client, operator):
    """With no working mailbox these are the only remaining way back in."""
    _secret, codes = enable(operator)
    res = sign_in(client, operator["identifier"], codes[0])
    assert res.status_code == 200, res.text
    assert res.json()["used_recovery"] is True


def test_a_recovery_code_works_once(client, operator):
    _secret, codes = enable(operator)
    assert sign_in(client, operator["identifier"], codes[0]).status_code == 200
    assert sign_in(client, operator["identifier"], codes[0]).status_code == 401


def test_using_one_leaves_the_others(client, operator):
    _secret, codes = enable(operator)
    res = sign_in(client, operator["identifier"], codes[0])
    assert res.json()["recovery_codes_left"] == main.TOTP_RECOVERY_CODES - 1
    assert sign_in(client, operator["identifier"], codes[1]).status_code == 200


# --- turning it off ------------------------------------------------------------------------------

def test_it_cannot_be_removed_without_proof(operator):
    enable(operator)
    res = operator["client"].post("/api/superadmin/totp/disable", json={})
    assert res.status_code == 401, res.text
    assert operator["client"].get("/api/superadmin/totp/status").json()["enabled"] is True


def test_a_current_code_removes_it(operator):
    secret, _ = enable(operator)
    res = operator["client"].post(
        "/api/superadmin/totp/disable",
        json={"code": main.totp_at(secret, main.totp_step_now())})
    assert res.status_code == 200, res.text
    assert operator["client"].get("/api/superadmin/totp/status").json()["enabled"] is False


def test_removing_it_also_clears_the_recovery_codes(operator):
    secret, _ = enable(operator)
    operator["client"].post("/api/superadmin/totp/disable",
                            json={"code": main.totp_at(secret, main.totp_step_now())})
    with main.SessionLocal() as db:
        row = db.query(models.DBSuperAdmin).filter(
            models.DBSuperAdmin.id == operator["id"]).first()
        assert not (row.totp_recovery or "")
        assert not (row.totp_secret or "")


def test_confirming_spends_the_code_it_was_confirmed_with(client, operator):
    """Found while writing these. The code used to switch it on is used, so it
    cannot then be used to sign in - which is right, and is the same rule that
    stops one being replayed."""
    started = set_up(operator)
    code = main.totp_at(started["secret"], main.totp_step_now())
    assert operator["client"].post("/api/superadmin/totp/confirm",
                                   json={"code": code}).status_code == 200

    assert sign_in(client, operator["identifier"], code).status_code == 401

