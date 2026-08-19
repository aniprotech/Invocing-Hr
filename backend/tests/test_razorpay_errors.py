"""Saying what Razorpay actually said, and getting a wallet into a currency
it will accept.

A top-up in GBP came back as "Razorpay rejected the payment request." The
reason - Razorpay accounts take INR unless international payments are enabled -
was in the response body, logged, and thrown away. Every failure looked the
same, so none of them could be acted on.
"""
import pytest

import main
import models


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


class FakeResponse:
    """Only what the reader touches."""

    def __init__(self, payload=None, text="", status_code=400):
        self._payload = payload
        self.text = text or (str(payload) if payload else "")
        self.status_code = status_code

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def complaint(payload=None, text="", status=400, currency="GBP"):
    return main.razorpay_complaint(FakeResponse(payload, text, status), currency)


# --- what the message says ----------------------------------------------------

def test_a_currency_rejection_names_the_currency_and_the_fix():
    """The one that actually happened."""
    msg = complaint({"error": {
        "description": "Currency is not supported",
        "field": "currency"}}, currency="GBP")
    assert "GBP" in msg
    assert "INR" in msg
    assert "international" in msg.lower()


def test_an_international_rejection_reads_the_same_way():
    msg = complaint({"error": {
        "description": "International payments are not enabled for this account"}})
    assert "INR" in msg


def test_bad_keys_point_at_the_keys():
    msg = complaint({"error": {"description": "Authentication failed"}}, status=401)
    assert "RAZORPAY_KEY_ID" in msg
    assert "RAZORPAY_KEY_SECRET" in msg


def test_any_other_reason_is_passed_through_rather_than_swallowed():
    msg = complaint({"error": {"description": "Amount exceeds maximum permitted"}})
    assert "Amount exceeds maximum permitted" in msg


def test_a_body_that_is_not_json_still_gives_an_answer():
    """A gateway having a bad day returns HTML, and that must not be a crash."""
    msg = complaint(None, text="<html>502 Bad Gateway</html>", status=502)
    assert msg
    assert "rejected" in msg.lower()


def test_it_never_returns_an_empty_message():
    assert complaint({"error": {}}, status=400)


# --- getting the wallet into a currency Razorpay accepts ----------------------

def a_tenant(client):
    import uuid
    email = f"cur-{uuid.uuid4().hex[:8]}@example.com"
    main.rate_limiter._hits.clear()
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Cur Ltd"})
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == email).first().id


def test_an_empty_wallet_can_be_switched(client, superadmin):
    cid = a_tenant(client)
    res = superadmin.put(f"/api/superadmin/wallets/{cid}/currency",
                         json={"currency": "INR"})
    assert res.status_code == 200, res.text
    assert res.json()["currency"] == "INR"
    assert res.json()["changed"] is True


def test_a_wallet_with_money_in_it_is_not_silently_converted(client, superadmin):
    """Relabelling GBP as INR would restate the balance at a rate nobody chose."""
    cid = a_tenant(client)
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust",
                    json={"amount": 50, "reason": "seed"})

    res = superadmin.put(f"/api/superadmin/wallets/{cid}/currency",
                         json={"currency": "INR"})
    assert res.status_code == 409
    assert "exchange rate" in res.json()["detail"]

    # And it is untouched.
    with main.SessionLocal() as db:
        w = main.get_wallet(db, cid)
        assert w.currency != "INR"
        assert w.balance_minor > 0


def test_emptying_it_first_is_the_way_through(client, superadmin):
    cid = a_tenant(client)
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust",
                    json={"amount": 50, "reason": "seed"})
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust",
                    json={"amount": -50, "reason": "clearing to change currency"})

    res = superadmin.put(f"/api/superadmin/wallets/{cid}/currency",
                         json={"currency": "INR"})
    assert res.status_code == 200, res.text


def test_switching_turns_auto_topup_off(client, superadmin):
    """Its threshold and amount were figures in the old currency."""
    cid = a_tenant(client)
    with main.SessionLocal() as db:
        w = main.get_wallet(db, cid)
        w.auto_topup_enabled = True
        w.auto_topup_amount_minor = 2000
        db.commit()

    superadmin.put(f"/api/superadmin/wallets/{cid}/currency", json={"currency": "INR"})
    with main.SessionLocal() as db:
        w = main.get_wallet(db, cid)
        assert w.auto_topup_enabled is False
        assert w.auto_topup_amount_minor == 0


def test_a_nonsense_code_is_refused(client, superadmin):
    cid = a_tenant(client)
    for bad in ("RUPEES", "I", "12A", ""):
        assert superadmin.put(f"/api/superadmin/wallets/{cid}/currency",
                              json={"currency": bad}).status_code == 400


def test_only_the_operator_can_change_it(tenant):
    assert tenant.put("/api/superadmin/wallets/1/currency",
                      json={"currency": "INR"}).status_code in (401, 403)


# --- PayPal says its useful part somewhere else --------------------------------

def paypal_complaint(payload=None, text="", status=400, currency="GBP"):
    return main.paypal_complaint(FakeResponse(payload, text, status), currency)


def test_paypal_currency_rejection_names_the_currency():
    msg = paypal_complaint({
        "name": "UNPROCESSABLE_ENTITY",
        "details": [{"issue": "CURRENCY_NOT_SUPPORTED"}]}, currency="GBP")
    assert "GBP" in msg


def test_paypal_bad_credentials_mention_the_mode():
    """Sandbox keys against live is the mistake that looks like a wrong key."""
    msg = paypal_complaint({"error": "invalid_client"}, status=401)
    assert "PAYPAL_MODE" in msg
    assert "sandbox" in msg


def test_paypal_reads_the_nested_issue_not_the_vague_top_line():
    """"Request is not well-formed" says nothing; the issue says which field."""
    msg = paypal_complaint({
        "name": "INVALID_REQUEST",
        "message": "Request is not well-formed, syntactically incorrect",
        "details": [{"issue": "MISSING_REQUIRED_PARAMETER"}]})
    assert "MISSING_REQUIRED_PARAMETER" in msg


def test_paypal_falls_back_to_the_message_when_there_is_no_issue():
    msg = paypal_complaint({"message": "Payee account is restricted"})
    assert "Payee account is restricted" in msg


def test_paypal_never_returns_nothing():
    assert paypal_complaint(None, text="<html>bad gateway</html>", status=502)
