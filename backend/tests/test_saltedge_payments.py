"""Paying from the payer's own bank through Salt Edge, and being paid
automatically afterwards.

Only the network is stood in for - a fake Salt Edge that answers the way their
reference says they do. Everything the rule turns on is real: whether a
callback is believed, which invoice it pays and for how much, and what is
allowed to be charged without anyone being there.

The rules, in the order they matter:

  * Returning from the bank settles nothing. An invoice is paid when Salt Edge
    says so - in a signed callback, or in answer to our own authenticated
    question - and never because the payer, or anyone else, said it was.
  * A callback that does not verify is refused before it is read.
  * Which invoice, and how much, comes from what we wrote down before asking
    the bank, not from the message.
  * Nothing is taken automatically except under an agreement the payer
    approved, inside the limits they set, and never twice for one invoice.
"""
import base64
import json
from datetime import date, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import serialization

import main
import models
import saltedge
from conftest import make_invoice

BASE = "https://pay.example.test"
PAYER_IP = "203.0.113.9"


# --- the two ends -----------------------------------------------------------------------

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = _KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def signed(url, raw, key=None):
    sig = (key or _KEY).sign(url.encode() + b"|" + raw, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


class FakeSaltEdge:
    """Answers the way docs.saltedge.com/v6 says Salt Edge does."""

    def __init__(self):
        self.calls = []
        self.n = 0
        self.payment_status = "initiated"
        self.refresh_status = None          # what a refresh adds, if different
        self.consent_status = "initiated"
        self.vrp_status = "initiated"
        self.fail = {}                      # "METHOD /path-prefix" -> (http status, class)
        self.down = False
        self.banks = [
            {"code": "fake_vrp_bank_gb", "name": "Fake VRP Bank", "payment_templates": ["FPS", "VRP_COMMERCIAL"]},
            {"code": "no_vrp_bank_gb", "name": "Plain Bank", "payment_templates": ["FPS"]},
        ]

    def of(self, method, prefix):
        return [c for c in self.calls if c["method"] == method and c["path"].startswith(prefix)]

    def __call__(self, method, url, headers, body, timeout):
        if self.down:
            raise ConnectionError("no route to Salt Edge")
        path = url.split("/api/v6", 1)[1]
        data = json.loads(body) if body else None
        self.calls.append({"method": method, "path": path, "body": data, "headers": headers})
        for key, (status, klass) in self.fail.items():
            m, _, prefix = key.partition(" ")
            if m == method and path.startswith(prefix):
                return status, json.dumps({"error": {"class": klass, "message": "refused by the fake"}})
        self.n += 1
        if method == "POST" and path == "/payments/create":
            return 200, json.dumps({"data": {
                "payment_id": f"SEP{self.n}", "customer_id": "9",
                "payment_url": f"https://www.saltedge.com/payments/connect?token=t{self.n}",
                "expires_at": "2030-01-01T00:00:00Z"}})
        if method == "GET" and path.startswith("/payments/"):
            pid = path.split("/")[2]
            return 200, json.dumps({"data": {"id": pid, "status": self.payment_status,
                                             "raw_provider_status": "ACTC"}})
        if method == "PUT" and path.endswith("/refresh"):
            pid = path.split("/")[2]
            return 200, json.dumps({"data": {"id": pid, "status": self.refresh_status or self.payment_status,
                                             "raw_provider_status": "ACTC"}})
        if method == "POST" and path == "/vrp_consents/create":
            return 200, json.dumps({"data": {
                "vrp_consent_id": f"VC{self.n}", "customer_id": "9",
                "consent_url": f"https://www.saltedge.com/vrp_payments/checkout?token=c{self.n}"}})
        if method == "GET" and path.startswith("/vrp_consents/"):
            return 200, json.dumps({"data": {"id": path.split("/")[2], "status": self.consent_status}})
        if method == "PUT" and path.endswith("/revoke"):
            return 200, json.dumps({"data": {"id": path.split("/")[2], "status": "revoked"}})
        if method == "POST" and path == "/payments/vrp_payment":
            return 200, json.dumps({"data": {"payment_id": f"VP{self.n}", "status": self.vrp_status}})
        if method == "GET" and path.startswith("/providers"):
            return 200, json.dumps({"data": self.banks, "meta": {}})
        return 404, json.dumps({"error": {"class": "NotFake", "message": path}})


@pytest.fixture
def fake(monkeypatch):
    f = FakeSaltEdge()
    monkeypatch.setattr(saltedge, "_send", f)
    return f


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    main.rate_limiter._hits.clear()
    main._saltedge_banks.update(key="", at=0.0, banks=[])
    for name in ("SALTEDGE_APP_ID", "SALTEDGE_SECRET", "SALTEDGE_PRIVATE_KEY",
                 "SALTEDGE_CREDITOR_NAME", "SALTEDGE_CREDITOR_SORT_CODE",
                 "SALTEDGE_CREDITOR_ACCOUNT_NUMBER", "SALTEDGE_CREDITOR_IBAN",
                 "SALTEDGE_PROVIDER_CODE", "SALTEDGE_VRP_TYPE", "SALTEDGE_API_BASE",
                 "SALTEDGE_CALLBACK_PUBLIC_KEY", "APP_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture(autouse=True)
def _fresh_state():
    """Every test starts with no Salt Edge payments or agreements. They live in
    the module's one database, and a test that counts them or runs the job
    over all of them would otherwise be answering for the tests before it."""
    with main.SessionLocal() as db:
        ids = [m.id for m in db.query(models.DBPaymentMandate).filter(
            models.DBPaymentMandate.provider == "saltedge").all()]
        if ids:
            db.query(models.DBAutoCharge).filter(
                models.DBAutoCharge.mandate_id.in_(ids)).delete(synchronize_session=False)
        db.query(models.DBSaltEdgePayment).delete(synchronize_session=False)
        db.query(models.DBPaymentMandate).filter(
            models.DBPaymentMandate.provider == "saltedge").delete(synchronize_session=False)
        db.commit()
    yield


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("SALTEDGE_APP_ID", "app_test")
    monkeypatch.setenv("SALTEDGE_SECRET", "secret_test")
    monkeypatch.setenv("SALTEDGE_CREDITOR_NAME", "Aniprotech Ltd")
    monkeypatch.setenv("SALTEDGE_CREDITOR_SORT_CODE", "12-34-56")
    monkeypatch.setenv("SALTEDGE_CREDITOR_ACCOUNT_NUMBER", "12345678")
    monkeypatch.setenv("SALTEDGE_CREDITOR_IBAN", "GB29NWBK60161331926819")
    monkeypatch.setenv("SALTEDGE_CALLBACK_PUBLIC_KEY", PUBLIC_PEM)
    monkeypatch.setenv("APP_BASE_URL", BASE)


def set_mode(value):
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == main.COLLECTION_SETTING,
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = value
        else:
            db.add(models.DBSettings(key=main.COLLECTION_SETTING, client_id=None, value=value))
        db.commit()
        return was


@pytest.fixture(autouse=True)
def _mode_is_restored():
    was = set_mode("direct")
    yield
    set_mode(was or "direct")


@pytest.fixture
def platform(configured):
    set_mode("platform")


@pytest.fixture
def payer(monkeypatch):
    """The payer's address. The test client is not at a real one."""
    monkeypatch.setattr(main, "saltedge_payer_ip", lambda request: PAYER_IP)


def payable(tenant, **over):
    over.setdefault("currency", "GBP")
    return make_invoice(tenant, status="Awaiting Payment", **over)


def tracking_of(tenant, inv):
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        return db.query(models.DBInvoice).filter(
            models.DBInvoice.number == inv["number"],
            models.DBInvoice.client_id == me["id"]).first().tracking_id


def invoice_row(tracking):
    with main.SessionLocal() as db:
        r = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == tracking).first()
        return {"id": r.id, "status": r.status, "due": float(r.due or 0), "paid": float(r.paid or 0),
                "client_id": r.client_id}


def payments_of(invoice_id):
    with main.SessionLocal() as db:
        return [(p.method, float(p.amount), p.reference) for p in db.query(models.DBPayment)
                .filter(models.DBPayment.invoice_id == invoice_id).all()]


def settlements_of(invoice_id):
    with main.SessionLocal() as db:
        return [(s.gateway, s.amount_minor, s.currency, s.status, s.gateway_payment_id)
                for s in db.query(models.DBSettlement).filter(models.DBSettlement.invoice_id == invoice_id).all()]


def se_rows(invoice_id=None, kind=None):
    with main.SessionLocal() as db:
        q = db.query(models.DBSaltEdgePayment)
        if invoice_id:
            q = q.filter(models.DBSaltEdgePayment.invoice_id == invoice_id)
        if kind:
            q = q.filter(models.DBSaltEdgePayment.kind == kind)
        return [{"id": r.id, "payment_id": r.payment_id, "status": r.status, "outcome": r.outcome,
                 "amount_minor": r.amount_minor, "currency": r.currency, "e2e": r.end_to_end_id,
                 "reason": r.failure_reason, "mandate_id": r.mandate_id, "kind": r.kind,
                 "customer": r.customer_identifier} for r in q.order_by(models.DBSaltEdgePayment.id).all()]


def callback(tenant, kind, payment_id, status="executed", key=None, url_kind=None, body=None,
             custom_fields=None, **extra):
    data = {"payment_id": payment_id, "customer_id": "9", "status": status,
            "raw_provider_status": "ACTC", "custom_fields": custom_fields or {}}
    data.update(extra)
    raw = body if body is not None else json.dumps({"data": data, "meta": {"version": "6"}}).encode()
    sig = signed(f"{BASE}/api/saltedge/callback/{url_kind or kind}", raw, key)
    return tenant.post(f"/api/saltedge/callback/{kind}", content=raw,
                       headers={"Signature": sig, "Signature-key-version": "6.0",
                                "Content-Type": "application/json"})


def start_payment(tenant, inv):
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 200, res.text
    return res.json()


# =====================================================================================
# When it is offered
# =====================================================================================

def methods(tenant, inv):
    return tenant.get(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/methods").json()


def test_bank_payment_is_offered_when_the_platform_collects(tenant, platform):
    got = methods(tenant, payable(tenant))
    assert "saltedge" in [m["provider"] for m in got["methods"]], got
    assert got["autodebit"]["provider"] == "saltedge" and got["autodebit"]["currency"] == "GBP"


def test_it_is_not_offered_when_businesses_collect_for_themselves(tenant, configured):
    """The platform's account would take the money while the business is
    expecting it in theirs."""
    set_mode("direct")
    got = methods(tenant, payable(tenant))
    assert "saltedge" not in [m["provider"] for m in got["methods"]]
    assert got["autodebit"] is None


@pytest.mark.parametrize("missing", ["SALTEDGE_APP_ID", "SALTEDGE_SECRET", "SALTEDGE_CREDITOR_NAME",
                                     "SALTEDGE_CREDITOR_SORT_CODE", "SALTEDGE_CREDITOR_ACCOUNT_NUMBER"])
def test_it_is_not_offered_without_keys_or_somewhere_for_the_money_to_land(tenant, platform, monkeypatch, missing):
    monkeypatch.delenv(missing)
    got = methods(tenant, payable(tenant))
    assert "saltedge" not in [m["provider"] for m in got["methods"]]
    assert got["autodebit"] is None


def test_a_currency_it_has_no_account_for_is_not_offered(tenant, platform):
    assert "saltedge" not in [m["provider"] for m in methods(tenant, payable(tenant, currency="USD"))["methods"]]
    assert "saltedge" not in [m["provider"] for m in methods(tenant, payable(tenant, currency="INR"))["methods"]]


def test_euros_go_by_sepa_but_cannot_be_autodebited(tenant, platform):
    got = methods(tenant, payable(tenant, currency="EUR"))
    assert "saltedge" in [m["provider"] for m in got["methods"]]
    assert got["autodebit"] is None


def test_autodebit_needs_a_customer_to_attach_it_to(tenant, platform):
    got = methods(tenant, payable(tenant, contact=""))
    assert got["autodebit"] is None


def test_nothing_is_offered_on_a_paid_invoice(tenant, platform):
    inv = payable(tenant)
    assert tenant.post(f"/api/invoices/{inv['number']}/mark-paid").status_code == 200
    got = methods(tenant, inv)
    assert got["is_paid"] is True
    assert got["methods"] == [] and got["autodebit"] is None


# =====================================================================================
# Starting a payment
# =====================================================================================

def test_starting_sends_the_bank_the_invoice_to_the_platform_account_and_nothing_is_paid(
        tenant, platform, fake, payer):
    inv = payable(tenant)
    tracking = tracking_of(tenant, inv)
    got = start_payment(tenant, inv)

    assert got["payment_url"].startswith("https://www.saltedge.com/payments/connect")
    assert got["settles_immediately"] is False and got["amount"] == 12000 and got["currency"] == "GBP"

    sent = fake.of("POST", "/payments/create")[0]["body"]["data"]
    a = sent["payment_attributes"]
    assert sent["template_identifier"] == "FPS"
    assert a["amount"] == "120.00" and a["currency_code"] == "GBP"
    assert a["creditor_sort_code"] == "123456" and a["creditor_account_number"] == "12345678"
    assert a["creditor_name"] == "Aniprotech Ltd" and a["customer_ip_address"] == PAYER_IP
    assert a["description"] == f"Invoice {inv['number']}"
    assert sent["attempt"]["return_to"] == f"{BASE}/invoice.html?id={tracking}&saltedge=return"
    assert sent["attempt"]["custom_fields"]["invoice_id"] == str(invoice_row(tracking)["id"])

    row = se_rows(invoice_row(tracking)["id"])[0]
    assert row["outcome"] == "pending" and row["payment_id"] == got["payment_id"]
    assert row["amount_minor"] == 12000 and row["kind"] == "payment"
    assert a["end_to_end_id"] == row["e2e"]
    assert invoice_row(tracking)["status"] != "Paid"


def test_the_request_is_signed_when_there_is_a_private_key(tenant, platform, fake, payer, monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    monkeypatch.setenv("SALTEDGE_PRIVATE_KEY", pem.replace("\n", "\\n"))
    start_payment(tenant, payable(tenant))
    h = fake.of("POST", "/payments/create")[0]["headers"]
    assert h["App-id"] == "app_test" and h["Secret"] == "secret_test"
    assert h["Signature"] and h["Expires-at"].isdigit()


def test_euros_are_sent_as_a_sepa_transfer_to_the_iban(tenant, platform, fake, payer):
    start_payment(tenant, payable(tenant, currency="EUR"))
    sent = fake.of("POST", "/payments/create")[0]["body"]["data"]
    assert sent["template_identifier"] == "SEPA"
    assert sent["payment_attributes"]["creditor_iban"] == "GB29NWBK60161331926819"


def test_what_the_payer_posts_changes_nothing(tenant, platform, fake, payer):
    inv = payable(tenant)
    tracking = tracking_of(tenant, inv)
    res = tenant.post(f"/api/public/invoices/{tracking}/pay/saltedge/start",
                      json={"amount": 0.01, "creditor_account": "99999999", "creditor_sort_code": "000000",
                            "currency": "USD", "invoice_id": 1})
    assert res.status_code == 200
    a = fake.of("POST", "/payments/create")[0]["body"]["data"]["payment_attributes"]
    assert a["amount"] == "120.00" and a["creditor_account_number"] == "12345678"
    assert a["creditor_sort_code"] == "123456" and a["currency_code"] == "GBP"


def test_it_is_refused_in_direct_mode(tenant, configured, fake, payer):
    set_mode("direct")
    inv = payable(tenant)
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 503 and fake.calls == []


def test_it_is_refused_when_not_set_up(tenant, fake, payer):
    inv = payable(tenant)
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 503 and fake.calls == []


def test_it_is_refused_for_a_draft_and_a_paid_invoice(tenant, platform, fake, payer):
    draft = make_invoice(tenant, currency="GBP")
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, draft)}/pay/saltedge/start")
    assert res.status_code == 404
    inv = payable(tenant)
    assert tenant.post(f"/api/invoices/{inv['number']}/mark-paid").status_code == 200
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 409 and fake.calls == []


def test_without_a_real_payer_address_it_is_refused_not_invented(tenant, platform, fake):
    """The test client connects from "testclient", which is not an address,
    and Salt Edge passes this one to the bank."""
    inv = payable(tenant)
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 400 and fake.calls == []


def test_when_salt_edge_says_no_the_payer_is_told_kindly_and_the_row_says_why(tenant, platform, fake, payer):
    fake.fail["POST /payments/create"] = (406, "PaymentTemplateNotSupported")
    inv = payable(tenant)
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 502
    assert "PaymentTemplate" not in res.text and "refused by the fake" not in res.text
    row = se_rows(invoice_row(tracking_of(tenant, inv))["id"])[0]
    assert row["outcome"] == "failed" and "PaymentTemplateNotSupported" in row["reason"]


def test_when_salt_edge_cannot_be_reached_it_is_a_clean_failure(tenant, platform, fake, payer):
    fake.down = True
    inv = payable(tenant)
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 502
    assert se_rows(invoice_row(tracking_of(tenant, inv))["id"])[0]["outcome"] == "failed"
    assert invoice_row(tracking_of(tenant, inv))["status"] != "Paid"


def test_an_answer_with_no_address_to_send_the_payer_to_is_a_failure(tenant, platform, fake, payer, monkeypatch):
    monkeypatch.setattr(saltedge, "_send", lambda *a, **k: (200, json.dumps({"data": {"payment_id": "X"}})))
    inv = payable(tenant)
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 502
    assert se_rows(invoice_row(tracking_of(tenant, inv))["id"])[0]["outcome"] == "failed"


def test_an_address_that_is_not_a_web_address_is_never_passed_on(tenant, platform, fake, payer, monkeypatch):
    monkeypatch.setattr(saltedge, "_send", lambda *a, **k: (200, json.dumps(
        {"data": {"payment_id": "X", "payment_url": "javascript:alert(1)"}})))
    inv = payable(tenant)
    res = tenant.post(f"/api/public/invoices/{tracking_of(tenant, inv)}/pay/saltedge/start")
    assert res.status_code == 502 and "javascript" not in res.text


# =====================================================================================
# Callbacks: what is believed
# =====================================================================================

def started(tenant, inv=None):
    inv = inv or payable(tenant)
    got = start_payment(tenant, inv)
    return inv, tracking_of(tenant, inv), got["payment_id"]


def test_a_genuine_success_callback_pays_the_invoice_and_owes_the_business(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    res = callback(tenant, "success", pid, "executed")
    assert res.status_code == 200, res.text
    row = invoice_row(tracking)
    assert row["status"] == "Paid" and row["due"] == 0 and row["paid"] == 120.0
    assert payments_of(row["id"]) == [("saltedge", 120.0, pid)]
    assert settlements_of(row["id"]) == [("saltedge", 12000, "GBP", "owed", pid)]
    assert se_rows(row["id"])[0]["outcome"] == "paid"


def test_settled_pays_it_too(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    callback(tenant, "success", pid, "settled")
    assert invoice_row(tracking)["status"] == "Paid"


def test_a_bank_that_has_only_authorised_it_has_not_paid_it(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    for status in ("initiated", "authorizing", "authorized"):
        assert callback(tenant, "notify", pid, status).status_code == 200
    row = invoice_row(tracking)
    assert row["status"] != "Paid" and row["due"] == 120.0
    assert payments_of(row["id"]) == [] and settlements_of(row["id"]) == []
    assert se_rows(row["id"])[0]["status"] == "authorized" and se_rows(row["id"])[0]["outcome"] == "pending"


def test_a_failure_is_noted_and_pays_nothing(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    callback(tenant, "fail", pid, "failed", error_class="Unfinished", error_message="Payment abandoned.")
    row = se_rows(invoice_row(tracking)["id"])[0]
    assert row["outcome"] == "failed" and "abandoned" in row["reason"]
    assert invoice_row(tracking)["status"] != "Paid"


def test_a_fail_callback_with_no_status_is_still_a_failure(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    callback(tenant, "fail", pid, "")
    assert se_rows(invoice_row(tracking)["id"])[0]["outcome"] == "failed"


def test_the_same_callback_twice_pays_once(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    for _ in range(3):
        assert callback(tenant, "success", pid, "executed").status_code == 200
    row = invoice_row(tracking)
    assert row["paid"] == 120.0 and len(payments_of(row["id"])) == 1 and len(settlements_of(row["id"])) == 1


def test_paid_is_final_a_later_failure_does_not_unpay_it(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    callback(tenant, "success", pid, "executed")
    callback(tenant, "fail", pid, "failed")
    assert invoice_row(tracking)["status"] == "Paid"
    assert se_rows(invoice_row(tracking)["id"])[0]["outcome"] == "paid"


def test_a_callback_with_a_wrong_signature_is_refused_and_pays_nothing(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    res = callback(tenant, "success", pid, "executed", key=stranger)
    assert res.status_code == 400
    assert invoice_row(tracking)["status"] != "Paid"


def test_an_unsigned_callback_is_refused(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    raw = json.dumps({"data": {"payment_id": pid, "status": "executed"}}).encode()
    for headers in ({}, {"Signature": ""}, {"Signature": "AAAA"}, {"Signature": "not base64 !"}):
        res = tenant.post("/api/saltedge/callback/success", content=raw, headers=headers)
        assert res.status_code == 400, headers
    assert invoice_row(tracking)["status"] != "Paid"


def test_a_signed_message_cannot_be_edited_afterwards(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    raw = json.dumps({"data": {"payment_id": pid, "status": "initiated"}}).encode()
    sig = signed(f"{BASE}/api/saltedge/callback/notify", raw)
    forged = raw.replace(b"initiated", b"executed")
    res = tenant.post("/api/saltedge/callback/notify", content=forged, headers={"Signature": sig})
    assert res.status_code == 400
    assert invoice_row(tracking)["status"] != "Paid"


def test_a_signature_for_one_address_is_no_good_at_another(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    res = callback(tenant, "success", pid, "executed", url_kind="notify")
    assert res.status_code == 400
    assert invoice_row(tracking)["status"] != "Paid"


def test_a_callback_is_refused_when_the_keys_or_address_are_not_set(tenant, platform, fake, payer, monkeypatch):
    inv, tracking, pid = started(tenant)
    monkeypatch.delenv("APP_BASE_URL")
    assert callback(tenant, "success", pid, "executed").status_code == 503
    monkeypatch.setenv("APP_BASE_URL", BASE)
    monkeypatch.delenv("SALTEDGE_SECRET")
    assert callback(tenant, "success", pid, "executed").status_code == 503
    assert invoice_row(tracking)["status"] != "Paid"


def test_a_callback_for_a_payment_we_never_made_is_acknowledged_and_ignored(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    res = callback(tenant, "success", "SOMEONE_ELSES_PAYMENT", "executed")
    assert res.status_code == 200 and res.json().get("ignored")
    assert invoice_row(tracking)["status"] != "Paid"


def test_a_signed_message_that_is_not_a_payment_callback_is_an_error(tenant, platform, fake, payer):
    assert callback(tenant, "success", "", body=b"not json").status_code == 400
    assert callback(tenant, "success", "", body=b'{"data":{}}').status_code == 400


def test_there_are_only_three_callback_addresses(tenant, platform, fake, payer):
    assert callback(tenant, "other", "X").status_code == 404


def test_the_message_cannot_point_a_payment_at_a_different_invoice(tenant, platform, fake, payer):
    """The invoice and the amount are ours. A signed message that names another
    invoice in its custom fields still pays only the one it was made for."""
    a, track_a, pid = started(tenant, payable(tenant))
    b = payable(tenant, line_items=[{"description": "Other", "qty": 1, "price": 500.0, "tax_rate": "No Tax"}])
    track_b = tracking_of(tenant, b)
    callback(tenant, "success", pid, "executed",
             custom_fields={"invoice_id": str(invoice_row(track_b)["id"]), "client_id": "999"},
             amount="500.00")
    assert invoice_row(track_a)["status"] == "Paid"
    assert invoice_row(track_b)["status"] != "Paid" and invoice_row(track_b)["paid"] == 0


def test_the_amount_paid_is_the_one_asked_for_not_one_in_the_message(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    callback(tenant, "success", pid, "executed", amount="0.01", payment_attributes={"amount": "0.01"})
    assert invoice_row(tracking)["paid"] == 120.0


def test_the_business_is_told_once_however_many_times_the_bank_says_so(tenant, platform, fake, payer, monkeypatch):
    told = []
    monkeypatch.setattr(main, "online_payment_recorded",
                        lambda db, inv, method, amount, reference: told.append((method, amount, reference)))
    inv, tracking, pid = started(tenant)
    for _ in range(3):
        callback(tenant, "success", pid, "executed")
    assert told == [("saltedge", 120.0, pid)]


def test_what_the_bank_moved_is_recorded_even_if_the_invoice_was_part_paid_meanwhile(tenant, platform, fake, payer):
    """The payer approved £120 and the bank sent it. If the business recorded
    a £20 payment in between, the ledger still has to say £120 arrived -
    the books describe what happened, not what would have tidied up."""
    inv, tracking, pid = started(tenant)
    assert tenant.post(f"/api/invoices/{inv['number']}/payments", json={"amount": 20.0}).status_code == 200
    callback(tenant, "success", pid, "executed")
    got = sorted((m, a) for m, a, _ref in payments_of(invoice_row(tracking)["id"]))
    assert got == [("bank_transfer", 20.0), ("saltedge", 120.0)], got
    assert settlements_of(invoice_row(tracking)["id"])[0][1] == 12000


def test_a_payment_row_that_does_not_belong_to_its_invoices_business_pays_nothing(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    with main.SessionLocal() as db:
        db.query(models.DBSaltEdgePayment).filter(models.DBSaltEdgePayment.payment_id == pid).update(
            {"client_id": 999999})
        db.commit()
    assert callback(tenant, "success", pid, "executed").status_code == 200
    assert invoice_row(tracking)["status"] != "Paid"
    assert payments_of(invoice_row(tracking)["id"]) == [] and settlements_of(invoice_row(tracking)["id"]) == []


def test_each_business_is_paid_only_for_its_own_invoice(tenant, platform, fake, payer, client):
    inv, tracking, pid = started(tenant)
    other_email = "other-saltedge@example.com"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other_email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    theirs = payable(client)
    callback(client, "success", pid, "executed")
    assert invoice_row(tracking)["status"] == "Paid"
    assert invoice_row(tracking_of(client, theirs))["status"] != "Paid"
    assert settlements_of(invoice_row(tracking)["id"])[0][0] == "saltedge"


# =====================================================================================
# The payer comes back
# =====================================================================================

def check(tenant, tracking, **kw):
    return tenant.post(f"/api/public/invoices/{tracking}/pay/saltedge/check", **kw)


def test_coming_back_asks_salt_edge_and_pays_when_they_say_so(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.payment_status = "executed"
    got = check(tenant, tracking).json()
    assert got["paid"] is True and got["outcome"] == "paid"
    assert invoice_row(tracking)["status"] == "Paid"
    assert fake.of("GET", f"/payments/{pid}")


def test_coming_back_early_leaves_it_waiting(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.payment_status = "authorizing"
    got = check(tenant, tracking).json()
    assert got["paid"] is False and got["outcome"] == "pending" and got["status"] == "authorizing"
    assert invoice_row(tracking)["status"] != "Paid"
    assert fake.of("PUT", f"/payments/{pid}/refresh"), "a payment still going is asked of the bank again"


def test_a_refresh_can_be_what_finishes_it(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.payment_status, fake.refresh_status = "authorized", "executed"
    assert check(tenant, tracking).json()["paid"] is True


def test_a_failed_payment_is_reported_with_its_reason(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.payment_status = "failed"
    got = check(tenant, tracking).json()
    assert got["paid"] is False and got["outcome"] == "failed" and got["reason"]


def test_salt_edge_being_down_leaves_things_as_they_were(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.down = True
    res = check(tenant, tracking)
    assert res.status_code == 200 and res.json()["paid"] is False and res.json()["outcome"] == "pending"


def test_asking_about_an_invoice_with_no_payment_says_so(tenant, platform, fake, payer):
    tracking = tracking_of(tenant, payable(tenant))
    assert check(tenant, tracking).json() == {"paid": False, "outcome": "none", "status": "", "reason": ""}
    assert fake.calls == []


def test_the_payer_cannot_name_which_payment_to_ask_about(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.payment_status = "executed"
    check(tenant, tracking, json={"payment_id": "SOMEONE_ELSES", "status": "executed"})
    assert all(c["path"] != "/payments/SOMEONE_ELSES" for c in fake.calls)


def test_coming_back_after_the_callback_does_not_pay_twice(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    callback(tenant, "success", pid, "executed")
    fake.payment_status = "executed"
    check(tenant, tracking)
    assert invoice_row(tracking)["paid"] == 120.0 and len(payments_of(invoice_row(tracking)["id"])) == 1


def test_asking_over_and_over_is_limited(tenant, platform, fake, payer):
    tracking = tracking_of(tenant, payable(tenant))
    codes = [check(tenant, tracking).status_code for _ in range(32)]
    assert codes[0] == 200 and codes[-1] == 429


# =====================================================================================
# Autodebit: the agreement
# =====================================================================================

LIMITS = {"provider_code": "fake_vrp_bank_gb", "max_amount": 150, "period_max_amount": 450, "period_type": "month"}


def banks_url(tenant, inv):
    return f"/api/public/invoices/{tracking_of(tenant, inv)}/autopay/saltedge/banks"


def start_url(tenant, inv):
    return f"/api/public/invoices/{tracking_of(tenant, inv)}/autopay/saltedge/start"


def check_url(tenant, inv):
    return f"/api/public/invoices/{tracking_of(tenant, inv)}/autopay/saltedge/check"


def mandates_for(client_id=None):
    with main.SessionLocal() as db:
        q = db.query(models.DBPaymentMandate).filter(models.DBPaymentMandate.provider == "saltedge")
        return [{"id": m.id, "status": m.status, "token": m.token_id, "ref": m.payer_ref,
                 "max": m.max_amount_minor, "customer": m.customer_id, "bank": m.masked,
                 "reason": m.failure_reason, "invoice": m.created_from_invoice_id,
                 "client_id": m.client_id} for m in q.order_by(models.DBPaymentMandate.id).all()]


def test_the_banks_offered_are_only_those_that_can_do_it(tenant, platform, fake):
    inv = payable(tenant)
    got = tenant.get(banks_url(tenant, inv)).json()
    assert got["banks"] == [{"code": "fake_vrp_bank_gb", "name": "Fake VRP Bank"}]
    assert got["currency"] == "GBP" and got["amount_due"] == 120.0
    assert got["suggested_per_payment"] == 150.0 and got["suggested_per_month"] == 450.0


def test_the_list_of_banks_is_asked_for_once_not_on_every_page_view(tenant, platform, fake):
    inv = payable(tenant)
    tenant.get(banks_url(tenant, inv))
    tenant.get(banks_url(tenant, inv))
    assert len(fake.of("GET", "/providers")) == 1


def test_no_banks_are_offered_where_autodebit_is_not(tenant, platform, fake):
    assert tenant.get(banks_url(tenant, payable(tenant, currency="EUR"))).status_code == 503
    assert tenant.get(banks_url(tenant, payable(tenant, contact=""))).status_code == 503
    set_mode("direct")
    assert tenant.get(banks_url(tenant, payable(tenant))).status_code == 503


def test_the_list_of_banks_is_limited(tenant, platform, fake):
    inv = payable(tenant)
    codes = [tenant.get(banks_url(tenant, inv)).status_code for _ in range(32)]
    assert codes[0] == 200 and codes[-1] == 429


def test_a_failing_bank_list_is_a_clean_error(tenant, platform, fake):
    fake.fail["GET /providers"] = (401, "ApiKeyNotFound")
    res = tenant.get(banks_url(tenant, payable(tenant)))
    assert res.status_code == 502 and "ApiKeyNotFound" not in res.text


def test_starting_an_agreement_asks_the_bank_for_exactly_what_the_payer_set(tenant, platform, fake):
    inv = payable(tenant)
    res = tenant.post(start_url(tenant, inv), json=LIMITS)
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["consent_url"].startswith("https://www.saltedge.com/vrp_payments/checkout")
    assert got["max_amount"] == 150.0 and got["period_max_amount"] == 450.0 and got["bank"] == "Fake VRP Bank"

    sent = fake.of("POST", "/vrp_consents/create")[0]["body"]["data"]
    c = sent["consent_details"]
    assert sent["provider"] == {"code": "fake_vrp_bank_gb"}
    assert c["creditor_account"] == "12345612345678" and c["creditor_currency_code"] == "GBP"
    assert c["max_one_time_amount"] == 150.0 and c["period_max_amount"] == 450.0
    assert c["period_type"] == "month" and c["vrp_type"] == "commercial"
    assert c["valid_until"] == (date.today() + timedelta(days=365)).isoformat()
    assert sent["attempt"]["return_to"].endswith("&autodebit=return")

    m = mandates_for()[-1]
    assert m["status"] == "pending" and m["token"].startswith("VC")
    assert m["max"] == 15000 and m["ref"] == "Customer Ltd" and m["bank"] == "Fake VRP Bank"
    assert m["invoice"] == invoice_row(tracking_of(tenant, inv))["id"]
    assert m["customer"] == saltedge.customer_identifier(invoice_row(tracking_of(tenant, inv))["client_id"],
                                                         "Customer Ltd")


def test_a_pending_agreement_can_be_charged_against_by_nobody(tenant, platform, fake):
    inv = payable(tenant)
    tenant.post(start_url(tenant, inv), json=LIMITS)
    with main.SessionLocal() as db:
        got = db.query(models.DBInvoice).filter(models.DBInvoice.number == inv["number"]).first()
        assert main.mandate_for_customer(db, got.client_id, "Customer Ltd") is None


@pytest.mark.parametrize("over,why", [
    ({"max_amount": None}, "no limit for one payment"),
    ({"period_max_amount": None}, "no limit for the period"),
    ({"max_amount": 0}, "nothing"),
    ({"max_amount": -5}, "negative"),
    ({"max_amount": "lots"}, "not a number"),
    ({"max_amount": 500, "period_max_amount": 100}, "a month below one payment"),
    ({"period_type": "fortnightly"}, "unknown period"),
    ({"provider_code": "not_in_the_list"}, "a bank Salt Edge never listed"),
    ({"provider_code": "no_vrp_bank_gb"}, "a bank that cannot do it"),
    ({"provider_code": ""}, "no bank"),
    ({"max_amount": float("nan")}, "not a number at all"),
    ({"max_amount": float("inf"), "period_max_amount": float("inf")}, "no limit"),
    ({"max_amount": 5_000_000, "period_max_amount": 9_000_000}, "more than any invoice here"),
])
def test_an_agreement_with_missing_or_nonsense_terms_is_refused(tenant, platform, fake, over, why):
    body = dict(LIMITS)
    body.update(over)
    # As text, because NaN and infinity are things Python's own JSON parser
    # accepts that the test client's encoder would refuse to write.
    res = tenant.post(start_url(tenant, payable(tenant)), content=json.dumps(body),
                      headers={"Content-Type": "application/json"})
    assert res.status_code == 400, why
    assert fake.of("POST", "/vrp_consents/create") == [] and mandates_for() == []


def test_there_is_no_default_for_how_much_may_be_taken(tenant, platform, fake):
    res = tenant.post(start_url(tenant, payable(tenant)), json={"provider_code": "fake_vrp_bank_gb"})
    assert res.status_code == 400 and mandates_for() == []


def test_an_agreement_cannot_be_started_where_it_is_not_offered(tenant, platform, fake):
    assert tenant.post(start_url(tenant, payable(tenant, currency="EUR")), json=LIMITS).status_code == 503
    assert tenant.post(start_url(tenant, payable(tenant, contact="")), json=LIMITS).status_code == 503
    set_mode("direct")
    assert tenant.post(start_url(tenant, payable(tenant)), json=LIMITS).status_code == 503
    assert fake.of("POST", "/vrp_consents/create") == []


def test_a_bank_that_turns_out_not_to_support_it_is_said_so_and_leaves_nothing_active(tenant, platform, fake):
    fake.fail["POST /vrp_consents/create"] = (406, "VrpNotSupported")
    res = tenant.post(start_url(tenant, payable(tenant)), json=LIMITS)
    assert res.status_code == 409 and "another" in res.json()["detail"]
    assert mandates_for()[-1]["status"] == "failed"


def test_any_other_failure_to_start_is_a_clean_error(tenant, platform, fake):
    fake.fail["POST /vrp_consents/create"] = (500, "InternalError")
    res = tenant.post(start_url(tenant, payable(tenant)), json=LIMITS)
    assert res.status_code == 502 and "InternalError" not in res.text
    assert mandates_for()[-1]["status"] == "failed"


def test_when_the_payer_approves_the_agreement_becomes_active(tenant, platform, fake):
    inv = payable(tenant)
    tenant.post(start_url(tenant, inv), json=LIMITS)
    fake.consent_status = "active"
    got = tenant.post(check_url(tenant, inv)).json()
    assert got["active"] is True and got["status"] == "active" and got["bank"] == "Fake VRP Bank"
    assert mandates_for()[-1]["status"] == "active"


def test_until_they_approve_it_stays_pending(tenant, platform, fake):
    inv = payable(tenant)
    tenant.post(start_url(tenant, inv), json=LIMITS)
    got = tenant.post(check_url(tenant, inv)).json()
    assert got["active"] is False and got["status"] == "pending"


@pytest.mark.parametrize("status", ["rejected", "expired", "canceled", "revoked"])
def test_an_agreement_the_bank_ends_is_over_here_too(tenant, platform, fake, status):
    inv = payable(tenant)
    tenant.post(start_url(tenant, inv), json=LIMITS)
    fake.consent_status = status
    got = tenant.post(check_url(tenant, inv)).json()
    assert got["active"] is False and got["status"] == "cancelled"
    assert status in mandates_for()[-1]["reason"]


def test_salt_edge_being_down_leaves_an_agreement_pending(tenant, platform, fake):
    inv = payable(tenant)
    tenant.post(start_url(tenant, inv), json=LIMITS)
    fake.down = True
    assert tenant.post(check_url(tenant, inv)).json()["status"] == "pending"


def test_asking_about_an_agreement_that_was_never_started(tenant, platform, fake):
    assert tenant.post(check_url(tenant, payable(tenant))).json() == {"status": "none", "active": False}


def test_a_newer_agreement_replaces_the_one_before_and_ends_it_at_the_bank(tenant, platform, fake):
    inv = payable(tenant)
    tenant.post(start_url(tenant, inv), json=LIMITS)
    fake.consent_status = "active"
    tenant.post(check_url(tenant, inv))
    first = mandates_for()[-1]
    fake.consent_status = "initiated"
    tenant.post(start_url(tenant, inv), json=dict(LIMITS, max_amount=300, period_max_amount=900))
    fake.consent_status = "active"
    tenant.post(check_url(tenant, inv))
    got = {m["id"]: m for m in mandates_for()}
    assert got[first["id"]]["status"] == "cancelled" and "Replaced" in got[first["id"]]["reason"]
    assert sorted(m["status"] for m in got.values()) == ["active", "cancelled"]
    assert [c["path"] for c in fake.of("PUT", "/vrp_consents/")] == [f"/vrp_consents/{first['token']}/revoke"]


def test_the_check_is_limited(tenant, platform, fake):
    inv = payable(tenant)
    codes = [tenant.post(check_url(tenant, inv)).status_code for _ in range(32)]
    assert codes[0] == 200 and codes[-1] == 429


# =====================================================================================
# Autodebit: taking an invoice
# =====================================================================================

def page_invoice(tenant, **over):
    """The invoice somebody is looking at when they set up automatic payment.
    Not yet due, so the job that follows does not take it as well."""
    over.setdefault("currency", "GBP")
    return make_invoice(
        tenant, status="Awaiting Payment", issue_date=date.today().isoformat(),
        due_date=(date.today() + timedelta(days=60)).isoformat(), **over)


def agreement(tenant, inv=None, **over):
    """A pending agreement, the way starting one from an invoice leaves it."""
    inv = inv or page_invoice(tenant)
    fake_ok = {"provider_code": "fake_vrp_bank_gb", "max_amount": 150, "period_max_amount": 450}
    fake_ok.update(over)
    res = tenant.post(start_url(tenant, inv), json=fake_ok)
    assert res.status_code == 200, res.text
    return res.json()["mandate_id"]


def activate(tenant, fake, inv):
    fake.consent_status = "active"
    tenant.post(check_url(tenant, inv))


def due_invoice(tenant, price=100.0, **over):
    due = date.today() - timedelta(days=1)
    over.setdefault("currency", "GBP")
    return make_invoice(
        tenant, status="Awaiting Payment", issue_date=(due - timedelta(days=14)).isoformat(),
        due_date=due.isoformat(),
        line_items=[{"description": "Work", "qty": 1, "price": price, "tax_rate": "No Tax"}], **over)


def run_job():
    with main.SessionLocal() as db:
        return main.job_invoice_autopay(db, datetime.now())


def charges_for(mandate_id):
    with main.SessionLocal() as db:
        return [(c.status, c.amount_minor, c.gateway_payment_id, c.failure_reason)
                for c in db.query(models.DBAutoCharge).filter(models.DBAutoCharge.mandate_id == mandate_id).all()]


def test_a_due_invoice_is_taken_under_the_agreement_but_not_marked_paid_until_the_bank_says(
        tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    inv = due_invoice(tenant, price=100.0)

    assert run_job() == {"charged": 1, "failed": 0}
    sent = fake.of("POST", "/payments/vrp_payment")[0]["body"]["data"]
    assert sent["consent_id"] == mandates_for()[-1]["token"]
    assert sent["payment_attributes"]["amount"] == "100.00"
    assert sent["customer_identifier"] == mandates_for()[-1]["customer"]

    tracking = tracking_of(tenant, inv)
    assert invoice_row(tracking)["status"] != "Paid", "requested is not paid"
    rows = se_rows(invoice_row(tracking)["id"], kind="vrp")
    assert len(rows) == 1 and rows[0]["outcome"] == "pending" and rows[0]["mandate_id"] == mid
    assert charges_for(mid)[0][0] == "requested"

    callback(tenant, "success", rows[0]["payment_id"], "executed")
    assert invoice_row(tracking)["status"] == "Paid"
    assert settlements_of(invoice_row(tracking)["id"])[0][:3] == ("saltedge", 10000, "GBP")
    assert charges_for(mid)[0][0] == "succeeded"


def test_when_the_bank_accepts_it_straight_away_it_is_paid_straight_away(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    fake.vrp_status = "executed"
    inv = due_invoice(tenant, price=100.0)
    run_job()
    assert invoice_row(tracking_of(tenant, inv))["status"] == "Paid"
    assert charges_for(mid)[0][0] == "succeeded"


def test_an_invoice_is_never_taken_twice(tenant, platform, fake):
    page = page_invoice(tenant)
    agreement(tenant, page)
    activate(tenant, fake, page)
    due_invoice(tenant, price=100.0)
    run_job()
    run_job()
    run_job()
    assert len(fake.of("POST", "/payments/vrp_payment")) == 1


def test_nothing_is_taken_above_the_limit_the_payer_set(tenant, platform, fake):
    page = page_invoice(tenant)
    agreement(tenant, page, max_amount=50, period_max_amount=500)
    activate(tenant, fake, page)
    due_invoice(tenant, price=100.0)
    assert run_job() == {"charged": 0, "failed": 0}
    assert fake.of("POST", "/payments/vrp_payment") == []


def test_nothing_is_taken_before_they_have_approved(tenant, platform, fake):
    agreement(tenant)
    due_invoice(tenant, price=100.0)
    run_job()
    assert fake.of("POST", "/payments/vrp_payment") == []


def test_nothing_is_taken_after_the_agreement_is_cancelled(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    tenant.delete(f"/api/autopay/mandates/{mid}")
    due_invoice(tenant, price=100.0)
    run_job()
    assert fake.of("POST", "/payments/vrp_payment") == []


def test_an_invoice_not_yet_due_is_left_alone(tenant, platform, fake):
    page = page_invoice(tenant)
    agreement(tenant, page)
    activate(tenant, fake, page)
    later = date.today() + timedelta(days=10)
    make_invoice(tenant, status="Awaiting Payment", currency="GBP", due_date=later.isoformat(),
                 issue_date=date.today().isoformat(),
                 line_items=[{"description": "W", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}])
    run_job()
    assert fake.of("POST", "/payments/vrp_payment") == []


def test_another_customers_invoice_is_not_taken_from_this_agreement(tenant, platform, fake):
    page = page_invoice(tenant)
    agreement(tenant, page)
    activate(tenant, fake, page)
    due_invoice(tenant, price=100.0, contact="Somebody Else Ltd")
    run_job()
    assert fake.of("POST", "/payments/vrp_payment") == []


def test_a_euro_invoice_is_never_taken_under_a_pound_agreement(tenant, platform, fake):
    page = page_invoice(tenant)
    agreement(tenant, page)
    activate(tenant, fake, page)
    due_invoice(tenant, price=100.0, currency="EUR")
    assert run_job() == {"charged": 0, "failed": 1}
    assert fake.of("POST", "/payments/vrp_payment") == []


def test_an_active_agreement_with_no_consent_to_charge_against_is_not_charged(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    with main.SessionLocal() as db:
        db.query(models.DBPaymentMandate).filter(models.DBPaymentMandate.id == mid).update({"token_id": ""})
        db.commit()
    due_invoice(tenant, price=100.0)
    assert run_job() == {"charged": 0, "failed": 1}
    assert fake.of("POST", "/payments/vrp_payment") == []


def _direct_charge(tenant, fake, amount_minor, price=100.0):
    """The charge function itself, called the way the job calls it - but
    without the job's own filtering first, so its guards are tested as guards."""
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    inv = due_invoice(tenant, price=price)
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == tracking_of(tenant, inv)).first()
        mandate = db.get(models.DBPaymentMandate, mid)
        return main.charge_saltedge_mandate(db, row, mandate, amount_minor)


def test_the_charge_function_refuses_to_charge_the_same_invoice_twice_on_its_own(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    inv = due_invoice(tenant, price=100.0)
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == tracking_of(tenant, inv)).first()
        mandate = db.get(models.DBPaymentMandate, mid)
        first = main.charge_saltedge_mandate(db, row, mandate, 10000)
        second = main.charge_saltedge_mandate(db, row, mandate, 10000)
    assert first == (True, "") and second == (False, "already_attempted")
    assert len(fake.of("POST", "/payments/vrp_payment")) == 1


def test_the_charge_function_refuses_an_amount_over_the_limit_on_its_own(tenant, platform, fake):
    assert _direct_charge(tenant, fake, 15001) == (False, "not_permitted")
    assert fake.of("POST", "/payments/vrp_payment") == []


def test_it_stops_if_the_platform_stops_collecting(tenant, platform, fake):
    """The account the money would land in is the platform's. If businesses
    collect for themselves again it must not keep going there."""
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    due_invoice(tenant, price=100.0)
    set_mode("direct")
    assert run_job() == {"charged": 0, "failed": 1}
    assert fake.of("POST", "/payments/vrp_payment") == []
    assert charges_for(mid) == []


def test_an_agreement_the_bank_says_is_over_is_given_up_on_and_not_retried_nightly(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    due_invoice(tenant, price=100.0)
    fake.fail["POST /payments/vrp_payment"] = (406, "VrpConsentRevoked")
    assert run_job() == {"charged": 0, "failed": 1}
    assert mandates_for()[-1]["status"] == "failed"
    assert charges_for(mid)[0][0] == "failed"
    run_job()
    assert len(fake.of("POST", "/payments/vrp_payment")) == 1


def test_a_payment_that_fails_for_another_reason_leaves_the_agreement_alone(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    inv = due_invoice(tenant, price=100.0)
    fake.fail["POST /payments/vrp_payment"] = (500, "InternalError")
    run_job()
    assert mandates_for()[-1]["status"] == "active"
    assert invoice_row(tracking_of(tenant, inv))["status"] != "Paid"
    assert se_rows(invoice_row(tracking_of(tenant, inv))["id"], kind="vrp")[0]["outcome"] == "failed"


def test_a_payment_the_bank_rejects_later_is_marked_failed_and_the_invoice_stays_owed(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    inv = due_invoice(tenant, price=100.0)
    run_job()
    row = se_rows(invoice_row(tracking_of(tenant, inv))["id"], kind="vrp")[0]
    callback(tenant, "fail", row["payment_id"], "failed", error_message="Insufficient funds")
    assert invoice_row(tracking_of(tenant, inv))["status"] != "Paid"
    assert charges_for(mid)[0][0] == "failed" and "Insufficient" in charges_for(mid)[0][3]


def test_other_gateways_agreements_still_go_the_old_way(tenant, platform, fake, monkeypatch):
    """A Razorpay mandate must not be sent to Salt Edge."""
    called = []
    monkeypatch.setattr(main, "charge_mandate", lambda *a, **k: called.append(a) or ("pay_1", None))
    tenant.put("/api/payment-gateways/razorpay", json={"public_key": "rzp_k", "secret_key": "sec", "is_active": True})
    with main.SessionLocal() as db:
        cid = db.query(models.DBClient).filter(models.DBClient.email == tenant.get("/api/client/me").json()["email"]).first().id
        db.add(models.DBPaymentMandate(client_id=cid, payer_type="customer", payer_ref="Customer Ltd",
                                       token_id="tok", customer_id="cust", method="card", masked="1111",
                                       currency="GBP", provider="razorpay", status="active"))
        db.commit()
    set_mode("direct")
    due_invoice(tenant, price=100.0)
    run_job()
    assert fake.calls == []


# =====================================================================================
# Stopping, and what the business sees
# =====================================================================================

def test_cancelling_ends_it_at_the_bank_too(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    res = tenant.delete(f"/api/autopay/mandates/{mid}")
    assert res.status_code == 200 and res.json()["status"] == "cancelled" and res.json()["revoked_at_bank"] is True
    assert fake.of("PUT", "/vrp_consents/")[0]["path"].endswith("/revoke")


def test_cancelling_works_even_if_the_bank_cannot_be_reached_and_says_so(tenant, platform, fake):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    activate(tenant, fake, page)
    fake.down = True
    res = tenant.delete(f"/api/autopay/mandates/{mid}")
    assert res.status_code == 200 and res.json()["status"] == "cancelled" and res.json()["revoked_at_bank"] is False
    assert mandates_for()[-1]["status"] == "cancelled"


def test_cancelling_another_businesses_agreement_is_refused(tenant, platform, fake, client):
    page = page_invoice(tenant)
    mid = agreement(tenant, page)
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": "intruder-se@example.com", "password": "Passw0rdTest"})
    client.post("/api/client/login", json={"email": "intruder-se@example.com", "password": "Passw0rdTest"})
    assert client.delete(f"/api/autopay/mandates/{mid}").status_code == 404
    assert mandates_for()[-1]["status"] == "pending"


def test_the_business_sees_the_agreement_with_its_bank(tenant, platform, fake):
    page = page_invoice(tenant)
    agreement(tenant, page)
    activate(tenant, fake, page)
    got = tenant.get("/api/autopay/mandates").json()["customers"][0]
    assert got["provider"] == "saltedge" and got["masked"] == "Fake VRP Bank" and got["status"] == "active"
    assert got["max_amount"] == 150.0


def test_the_operator_sees_what_is_still_missing_and_where_to_point_salt_edge(client, monkeypatch):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={"identifier": "hello@keyroutes.co",
                                                     "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    row = {p["key"]: p for p in client.get("/api/superadmin/gateways").json()["providers"]}["saltedge"]
    assert row["enabled"] is False and row["webhook_ready"] is False and row["signing"] is False
    assert "SALTEDGE_APP_ID" in row["missing"] and "APP_BASE_URL" in row["missing"]
    assert row["webhook_urls"] == ["/api/saltedge/callback/success", "/api/saltedge/callback/fail",
                                   "/api/saltedge/callback/notify"]

    monkeypatch.setenv("SALTEDGE_APP_ID", "a")
    monkeypatch.setenv("SALTEDGE_SECRET", "s")
    monkeypatch.setenv("SALTEDGE_CREDITOR_NAME", "N")
    monkeypatch.setenv("SALTEDGE_CREDITOR_SORT_CODE", "123456")
    monkeypatch.setenv("SALTEDGE_CREDITOR_ACCOUNT_NUMBER", "12345678")
    monkeypatch.setenv("APP_BASE_URL", BASE)
    monkeypatch.setenv("SALTEDGE_PRIVATE_KEY", "x")
    row = {p["key"]: p for p in client.get("/api/superadmin/gateways").json()["providers"]}["saltedge"]
    assert row["enabled"] and row["webhook_ready"] and row["signing"] and row["missing"] == []
    assert "SALTEDGE_SECRET" not in json.dumps(row) or "secret_value" not in json.dumps(row)


# =====================================================================================
# The sync job
# =====================================================================================

def run_sync(now=None):
    with main.SessionLocal() as db:
        return main.job_saltedge_sync(db, now or datetime.now())


def test_the_job_does_nothing_without_keys(tenant, fake):
    assert run_sync() == "not configured" and fake.calls == []


def test_the_job_settles_a_payment_whose_callback_never_came(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.payment_status = "executed"
    assert run_sync().startswith("1 paid")
    assert invoice_row(tracking)["status"] == "Paid"


def test_the_job_leaves_a_payment_still_in_flight_alone(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    fake.payment_status = "authorizing"
    assert run_sync().startswith("0 paid")
    assert invoice_row(tracking)["status"] != "Paid"


def test_the_job_does_not_keep_asking_about_old_payments(tenant, platform, fake, payer):
    inv, tracking, pid = started(tenant)
    with main.SessionLocal() as db:
        db.query(models.DBSaltEdgePayment).update(
            {"created_at": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")})
        db.commit()
    fake.calls.clear()
    run_sync()
    assert fake.of("GET", "/payments/") == []


def test_the_job_activates_an_agreement_approved_while_nobody_was_looking(tenant, platform, fake):
    page = page_invoice(tenant)
    agreement(tenant, page)
    fake.consent_status = "active"
    assert "1 agreements active" in run_sync()
    assert mandates_for()[-1]["status"] == "active"


def test_the_job_gives_up_on_an_agreement_never_approved(tenant, platform, fake):
    agreement(tenant)
    with main.SessionLocal() as db:
        db.query(models.DBPaymentMandate).filter(models.DBPaymentMandate.provider == "saltedge").update(
            {"created_at": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")})
        db.commit()
    assert "1 abandoned" in run_sync()
    m = mandates_for()[-1]
    assert m["status"] == "cancelled" and "Never approved" in m["reason"]


def test_a_fresh_agreement_is_not_given_up_on(tenant, platform, fake):
    agreement(tenant)
    assert "0 abandoned" in run_sync()
    assert mandates_for()[-1]["status"] == "pending"


def test_the_job_is_registered_and_runs_with_the_others(tenant, platform, fake):
    assert "saltedge_sync" in [name for name, _k, _f in main.SCHEDULED_JOBS]
    got = main.run_due_jobs(only="saltedge_sync")
    assert got and got[0]["job"] == "saltedge_sync" and got[0]["status"] in ("done", "already_done")
