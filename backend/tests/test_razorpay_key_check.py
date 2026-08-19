"""Telling a wrong key from a badly pasted one.

A trailing space in a dashboard variable is invisible and fails basic auth
exactly like a wrong key: both come back 401. Finding that out through a failed
top-up means guessing at which of several things went wrong, so the keys can
now be tested directly - and are trimmed, so the commonest cause stops
happening at all.

Nothing here ever returns a key.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


# --- pasting ------------------------------------------------------------------

def test_whitespace_around_a_key_is_trimmed(monkeypatch):
    """The commonest way a correct key stops working."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "  rzp_test_abc123  ")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_value\n")
    cfg = main.gateway_config()["razorpay"]
    assert cfg["key_id"] == "rzp_test_abc123"
    assert cfg["key_secret"] == "secret_value"


def test_the_other_providers_are_trimmed_too(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", " sk_test_x ")
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "\tclient\t")
    cfg = main.gateway_config()
    assert cfg["stripe"]["secret"] == "sk_test_x"
    assert cfg["paypal"]["client_id"] == "client"


def test_a_missing_key_is_still_empty(monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    assert main.gateway_config()["razorpay"]["key_id"] == ""


# --- what can be said without asking Razorpay ---------------------------------

def test_it_recognises_test_and_live(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "s")
    assert main.razorpay_key_shape("rzp_test_abc", "s")["mode"] == "test"
    assert main.razorpay_key_shape("rzp_live_abc", "s")["mode"] == "live"
    assert main.razorpay_key_shape("something", "s")["mode"] == "unknown"


def test_it_notices_whitespace_that_was_pasted(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", " rzp_test_abc ")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "s")
    notes = main.razorpay_key_shape("rzp_test_abc", "s")["notes"]
    assert any("whitespace" in n.lower() for n in notes)


def test_it_notices_the_two_values_being_swapped(monkeypatch):
    """Pasting the key id into both boxes is easy and the failure is opaque."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "rzp_test_abc")
    notes = main.razorpay_key_shape("rzp_test_abc", "rzp_test_abc")["notes"]
    assert any("key id" in n.lower() for n in notes)


def test_the_shape_never_carries_the_key(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_SECRETID")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "the_actual_secret")
    shape = main.razorpay_key_shape("rzp_test_SECRETID", "the_actual_secret")
    assert "the_actual_secret" not in str(shape)
    assert shape["key_id_tail"] == "TID"[-4:] or len(shape["key_id_tail"]) <= 4


# --- the check itself ---------------------------------------------------------

def test_it_says_so_when_nothing_is_configured(superadmin, monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    body = superadmin.get("/api/superadmin/razorpay-check").json()
    assert body["ok"] is False
    assert "RAZORPAY_KEY_ID" in body["reason"]


def test_a_rejection_explains_the_rotation_trap(superadmin, monkeypatch):
    """Regenerating replaces both halves, and a new id with an old secret fails
    exactly like a wrong key."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "wrong")

    class Rejected:
        status_code = 401
        text = '{"error":{"description":"Authentication failed"}}'

        def json(self):
            return {"error": {"description": "Authentication failed"}}

    monkeypatch.setattr(main.httpx, "get", lambda *a, **k: Rejected())
    body = superadmin.get("/api/superadmin/razorpay-check").json()
    assert body["ok"] is False
    assert "RAZORPAY_KEY_SECRET" in body["reason"]
    assert "Regenerating" in body["hint"]


def test_working_keys_report_the_mode_and_the_currency_catch(superadmin, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "right")

    class Fine:
        status_code = 200

        def json(self):
            return {"items": []}

    monkeypatch.setattr(main.httpx, "get", lambda *a, **k: Fine())
    body = superadmin.get("/api/superadmin/razorpay-check").json()
    assert body["ok"] is True
    assert "test" in body["reason"]
    assert "INR" in body["next"]


def test_an_unreachable_gateway_is_not_a_crash(superadmin, monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "right")

    def boom(*a, **k):
        raise RuntimeError("dns went away")

    monkeypatch.setattr(main.httpx, "get", boom)
    body = superadmin.get("/api/superadmin/razorpay-check").json()
    assert body["ok"] is False
    assert "reach" in body["reason"].lower()


def test_it_is_operator_only(tenant):
    assert tenant.get("/api/superadmin/razorpay-check").status_code in (401, 403)

def test_a_secret_of_the_wrong_length_is_called_out():
    """A half-pasted secret is indistinguishable from a wrong one at the
    gateway - both come back 401 - but the length is knowable here."""
    shape = main.razorpay_key_shape("rzp_test_abcdefghij", "tooshort")
    assert any("24" in n for n in shape["notes"]), shape["notes"]


def test_a_secret_of_the_right_length_passes_without_comment():
    shape = main.razorpay_key_shape("rzp_test_abcdefghij", "x" * 24)
    assert not any("24" in n for n in shape["notes"]), shape["notes"]


def test_no_secret_at_all_is_not_reported_as_a_length_problem():
    """Missing and mistyped are different failures with different fixes."""
    shape = main.razorpay_key_shape("rzp_test_abcdefghij", "")
    assert not any("24" in n for n in shape["notes"]), shape["notes"]
