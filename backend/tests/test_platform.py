"""Platform-level behaviour: auth, rate limiting, health and error handling."""
import time

import pytest

import main


# --- password hashing ------------------------------------------------------

def test_password_roundtrip():
    stored = main.hash_password("Correct horse")
    assert main.verify_password("Correct horse", stored)
    assert not main.verify_password("wrong", stored)


@pytest.mark.parametrize("stored", ["", None, "not-a-hash", "zz:zz", ":"])
def test_verify_password_tolerates_bad_hashes(stored):
    """A malformed stored hash used to raise and surface as a 500 instead of a
    failed login."""
    assert main.verify_password("anything", stored) is False


def test_legacy_sha256_hashes_still_verify():
    import hashlib
    legacy = hashlib.sha256(b"legacy-pass").hexdigest()
    assert main.verify_password("legacy-pass", legacy)
    assert not main.verify_password("other", legacy)


# --- rate limiter ----------------------------------------------------------

def test_rate_limiter_blocks_after_the_limit():
    limiter = main.RateLimiter()
    for _ in range(3):
        assert limiter.is_rate_limited("k", max_requests=3, window=60) is False
    assert limiter.is_rate_limited("k", max_requests=3, window=60) is True


def test_rate_limiter_window_expires():
    limiter = main.RateLimiter()
    assert limiter.is_rate_limited("k", max_requests=1, window=1) is False
    assert limiter.is_rate_limited("k", max_requests=1, window=1) is True
    time.sleep(1.1)
    assert limiter.is_rate_limited("k", max_requests=1, window=1) is False


def test_rate_limiter_sweeps_stale_keys():
    """Keys were previously retained forever, growing memory without bound."""
    limiter = main.RateLimiter()
    for i in range(50):
        limiter.is_rate_limited(f"key-{i}", max_requests=10, window=60)
    assert len(limiter._hits) == 50

    # Age every entry past the sweep horizon and force a sweep.
    old = time.time() - 7200
    for key in limiter._hits:
        limiter._hits[key] = [old]
    limiter._last_sweep = 0
    limiter.is_rate_limited("fresh", max_requests=10, window=60)
    assert len(limiter._hits) == 1


def test_login_is_rate_limited(client):
    main.rate_limiter._hits.clear()
    codes = [
        client.post("/api/client/login", json={"email": "nobody@example.com", "password": "x"}).status_code
        for _ in range(15)
    ]
    assert 429 in codes


# --- auth ------------------------------------------------------------------

def test_registration_enforces_password_policy(client):
    for bad in ("short", "alllowercase1", "NODIGITSHERE"):
        res = client.post("/api/client/register", json={"email": f"x-{bad}@example.com", "password": bad})
        assert res.status_code == 400, f"{bad} should have been rejected"


def test_duplicate_registration_rejected(client):
    payload = {"email": "dupe@example.com", "password": "Passw0rdTest"}
    assert client.post("/api/client/register", json=payload).status_code == 200
    assert client.post("/api/client/register", json=payload).status_code == 400


def test_wrong_password_is_unauthorised(client, account):
    client.post("/api/client/logout")
    res = client.post("/api/client/login", json={"email": account["email"], "password": "WrongPass1"})
    assert res.status_code == 401


def test_logout_clears_the_session(client, account):
    assert client.get("/api/client/me").status_code == 200
    client.post("/api/client/logout")
    assert client.get("/api/client/me").status_code == 401


# --- health ----------------------------------------------------------------

def test_health_reports_database_state(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok" and body["database"] == "ok", body
    # Mail readiness rides along; it is a separate fact from the database.
    assert body["email"] in ("ready", "not_configured", "unknown"), body


# --- money helpers ---------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (0.1 + 0.2, 0.30),
    (2.675, 2.68),      # half-up, not banker's rounding
    (1.005, 1.01),
    (None, 0.0),
    ("12.345", 12.35),
])
def test_money_rounds_half_up(value, expected):
    assert main.money(value) == pytest.approx(expected)


def test_invoice_overdue_days_ignores_settled_invoices():
    class Inv:
        status, due, due_date = "Paid", 0.0, "2020-01-01"
    assert main.invoice_overdue_days(Inv()) == 0

    class Draft:
        status, due, due_date = "Draft", 100.0, "2020-01-01"
    assert main.invoice_overdue_days(Draft()) == 0

    class Open:
        status, due, due_date = "Sent", 100.0, "2020-01-01"
    assert main.invoice_overdue_days(Open()) > 0
