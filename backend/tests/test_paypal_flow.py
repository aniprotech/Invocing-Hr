"""The PayPal top-up, checked before real keys go anywhere near it.

The first failure with brand new credentials is the one that tells you least,
so the messages matter as much as the mechanics: sandbox keys pointed at live
look exactly like a typo, and "Could not authenticate with PayPal" sends
somebody to check all three variables at once.

Nothing here talks to PayPal. Every response is a stand-in for one PayPal
would send.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def superadmin_client(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


@pytest.fixture
def paypal_keys(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "pp_client")
    monkeypatch.setenv("PAYPAL_SECRET", "pp_secret")
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    yield


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or (str(payload) if payload else "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


def set_currency(account, code):
    with main.SessionLocal() as db:
        main.get_wallet(db, client_id(account)).currency = code
        db.commit()


# --- which environment variables are actually read ----------------------------

def test_the_readiness_check_looks_for_the_name_that_is_used(superadmin_client,
                                                             monkeypatch):
    """It looked for PAYPAL_CLIENT_SECRET, which nothing else reads - so
    setting the one that works still reported no gateway configured."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "pp_client")
    monkeypatch.setenv("PAYPAL_SECRET", "pp_secret")

    body = superadmin_client.get("/api/superadmin/environment").json()
    gateways = next(c for c in body["checks"] if c["name"] == "Payment gateways")
    assert gateways["ok"] is True


def test_the_config_reads_client_id_and_secret(paypal_keys):
    cfg = main.gateway_config()["paypal"]
    assert cfg["client_id"] == "pp_client"
    assert cfg["secret"] == "pp_secret"
    assert cfg["mode"] == "sandbox"


def test_sandbox_and_live_hit_different_hosts(monkeypatch):
    """Pointing sandbox keys at the live host is the mistake that reads as a
    wrong key."""
    monkeypatch.setenv("PAYPAL_MODE", "sandbox")
    assert "sandbox" in main._paypal_base()
    monkeypatch.setenv("PAYPAL_MODE", "live")
    assert "sandbox" not in main._paypal_base()


def test_the_mode_defaults_to_sandbox(monkeypatch):
    """An unset mode must not quietly take real money."""
    monkeypatch.delenv("PAYPAL_MODE", raising=False)
    assert main.gateway_config()["paypal"]["mode"] == "sandbox"


# --- what a rejection says ----------------------------------------------------

def test_bad_credentials_name_all_three_variables(paypal_keys, monkeypatch):
    """The first thing anybody hits with new keys."""
    monkeypatch.setattr(main.httpx, "post", lambda *a, **k: FakeResponse(
        {"error": "invalid_client"}, status_code=401))

    with pytest.raises(main.HTTPException) as exc:
        main._paypal_token()
    detail = exc.value.detail
    assert "PAYPAL_CLIENT_ID" in detail
    assert "PAYPAL_SECRET" in detail
    assert "PAYPAL_MODE" in detail
    assert "sandbox" in detail


def test_a_token_response_with_no_token_is_not_treated_as_success(paypal_keys,
                                                                  monkeypatch):
    monkeypatch.setattr(main.httpx, "post",
                        lambda *a, **k: FakeResponse({"scope": "x"}, status_code=200))
    with pytest.raises(main.HTTPException) as exc:
        main._paypal_token()
    assert "no token" in exc.value.detail.lower()


def test_an_unsupported_currency_says_which_one(paypal_keys):
    msg = main.paypal_complaint(FakeResponse({
        "name": "UNPROCESSABLE_ENTITY",
        "details": [{"issue": "CURRENCY_NOT_SUPPORTED"}]}, status_code=422), "INR")
    assert "INR" in msg


# --- the order that gets created ----------------------------------------------
#
# PayPal is no longer a way to top up - bank debit is the only one - so these
# call the builder directly rather than through /api/wallet/topup, which now
# refuses it. The code is still here because orders taken before the change
# still have to settle and reconcile, and it still has to be right.

class _FakeRequest:
    base_url = "https://app.test/"


def build_paypal_order(tenant, account, amount_minor, return_page="app.html"):
    """Create a top-up order and hand it to the PayPal builder."""
    with main.SessionLocal() as db:
        client = db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first()
        wallet = main.get_wallet(db, client.id)
        order = models.DBTopUpOrder(
            client_id=client.id, provider="paypal", amount_minor=amount_minor,
            currency=wallet.currency, status="created")
        db.add(order)
        db.flush()
        result = main._create_paypal_order(
            order, client, _FakeRequest(), main.topup_return_page(return_page))
        db.commit()
        return result


def test_the_return_url_carries_the_order_it_belongs_to(tenant, account,
                                                        paypal_keys, monkeypatch):
    """Without it the page captures whichever payment is newest, which with two
    in flight is the wrong one."""
    set_currency(account, "GBP")
    seen = {}

    def fake_post(url, **kw):
        if "oauth2/token" in url:
            return FakeResponse({"access_token": "tok"})
        seen["json"] = kw.get("json")
        return FakeResponse({"id": "PP-1", "links": [
            {"rel": "approve", "href": "https://paypal.test/approve"}]})

    monkeypatch.setattr(main.httpx, "post", fake_post)
    build_paypal_order(tenant, account, amount_minor=2500)

    ret = seen["json"]["application_context"]["return_url"]
    assert "topup=success" in ret
    assert "order=" in ret, ret


def test_the_buyer_comes_back_to_the_portal_they_left(tenant, account,
                                                      paypal_keys, monkeypatch):
    set_currency(account, "GBP")
    seen = {}

    def fake_post(url, **kw):
        if "oauth2/token" in url:
            return FakeResponse({"access_token": "tok"})
        seen["json"] = kw.get("json")
        return FakeResponse({"id": "PP-1", "links": [
            {"rel": "approve", "href": "https://paypal.test/approve"}]})

    monkeypatch.setattr(main.httpx, "post", fake_post)
    build_paypal_order(tenant, account, amount_minor=2500, return_page="hr.html")
    assert "hr.html" in seen["json"]["application_context"]["return_url"]


@pytest.mark.parametrize("asked", [
    "https://evil.test/steal", "//evil.test", "../../etc/passwd", "nonsense.html", "",
])
def test_the_return_page_is_never_whatever_was_asked_for(asked):
    """A return_url is a redirect target, and an open one is somebody else's
    phishing page."""
    assert main.topup_return_page(asked) in main.RETURN_PAGES


def test_the_amount_reaches_paypal_in_major_units(tenant, account, paypal_keys,
                                                  monkeypatch):
    """Razorpay wants minor units and PayPal wants major ones; sending 2500
    instead of 25.00 would charge a hundred times over."""
    set_currency(account, "GBP")
    seen = {}

    def fake_post(url, **kw):
        if "oauth2/token" in url:
            return FakeResponse({"access_token": "tok"})
        seen["json"] = kw.get("json")
        return FakeResponse({"id": "PP-1", "links": []})

    monkeypatch.setattr(main.httpx, "post", fake_post)
    build_paypal_order(tenant, account, amount_minor=2500)
    amount = seen["json"]["purchase_units"][0]["amount"]
    assert amount["value"] == "25.00"
    assert amount["currency_code"] == "GBP"


def test_paypal_is_refused_for_a_currency_it_cannot_hold(paypal_keys):
    """PayPal publishes a fixed list of balance currencies and INR is not on
    it. Checked at the rule now rather than through the top-up endpoint, which
    no longer offers PayPal at all."""
    assert main.provider_takes_currency("paypal", "INR") is False
    assert "INR" in main.why_not_available("paypal", "INR", configured=True)


# --- capturing ----------------------------------------------------------------

def pending_order(account, provider_order_id="PP-1"):
    with main.SessionLocal() as db:
        order = models.DBTopUpOrder(
            client_id=client_id(account), provider="paypal", amount_minor=2500,
            currency="GBP", status="pending", provider_order_id=provider_order_id)
        db.add(order)
        db.commit()
        return order.id


def test_a_completed_capture_credits_the_wallet_once(tenant, account, paypal_keys,
                                                     monkeypatch):
    set_currency(account, "GBP")
    order_id = pending_order(account)

    def fake_post(url, **kw):
        if "oauth2/token" in url:
            return FakeResponse({"access_token": "tok"})
        # A real capture always says what it took. The wallet is credited
        # against this now rather than against our own order, so a stub
        # without it is not a capture anybody would ever receive.
        return FakeResponse({"status": "COMPLETED", "purchase_units": [
            {"payments": {"captures": [{
                "id": "CAP-1",
                "amount": {"value": "25.00", "currency_code": "GBP"},
            }]}}]})

    monkeypatch.setattr(main.httpx, "post", fake_post)

    first = tenant.post(f"/api/wallet/topup/{order_id}/capture-paypal")
    assert first.status_code == 200, first.text
    assert first.json()["credited"] is True
    after = first.json()["balance"]

    # Coming back to the return URL twice must not pay twice.
    second = tenant.post(f"/api/wallet/topup/{order_id}/capture-paypal")
    assert second.status_code == 200
    assert second.json()["balance"] == after


def test_a_capture_that_is_not_complete_credits_nothing(tenant, account,
                                                        paypal_keys, monkeypatch):
    set_currency(account, "GBP")
    order_id = pending_order(account)

    def fake_post(url, **kw):
        if "oauth2/token" in url:
            return FakeResponse({"access_token": "tok"})
        return FakeResponse({"status": "PENDING"})

    monkeypatch.setattr(main.httpx, "post", fake_post)
    body = tenant.post(f"/api/wallet/topup/{order_id}/capture-paypal").json()
    assert body["credited"] is False

    with main.SessionLocal() as db:
        assert main.get_wallet(db, client_id(account)).balance_minor == 0


def test_a_failed_capture_says_what_paypal_said(tenant, account, paypal_keys,
                                                monkeypatch):
    """It used to say only that it failed, while the reader that explains it
    was sitting right there."""
    set_currency(account, "GBP")
    order_id = pending_order(account)

    def fake_post(url, **kw):
        if "oauth2/token" in url:
            return FakeResponse({"access_token": "tok"})
        return FakeResponse({"name": "UNPROCESSABLE_ENTITY", "details": [
            {"issue": "INSTRUMENT_DECLINED"}]}, status_code=422)

    monkeypatch.setattr(main.httpx, "post", fake_post)
    res = tenant.post(f"/api/wallet/topup/{order_id}/capture-paypal")
    assert res.status_code == 502
    assert "INSTRUMENT_DECLINED" in res.json()["detail"]

    with main.SessionLocal() as db:
        order = db.query(models.DBTopUpOrder).filter(
            models.DBTopUpOrder.id == order_id).first()
        assert "INSTRUMENT_DECLINED" in order.failure_reason


def test_one_tenant_cannot_capture_anothers_order(tenant, account, paypal_keys):
    import uuid
    from fastapi.testclient import TestClient

    order_id = pending_order(account)
    with TestClient(main.app) as other:
        main.rate_limiter._hits.clear()
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"})
        assert other.post(
            f"/api/wallet/topup/{order_id}/capture-paypal").status_code == 404


def test_capturing_needs_a_session(client):
    assert client.post("/api/wallet/topup/1/capture-paypal").status_code in (401, 403)
