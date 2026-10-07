"""Salt Edge, the part that needs no network: what is sent, how it is signed,
and whether a message that says it is from Salt Edge really is.

Everything here is a plain function. The routes that use it, and the whole
flow end to end, are in test_saltedge_payments.py.
"""
import base64
import json
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import saltedge as se


# --- keys of our own, standing in for both sides -------------------------------------------

def _make_pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return private, private_pem, public_pem


@pytest.fixture(scope="module")
def ours():
    """The pair a business generates: the private half signs requests to Salt
    Edge, the public half is uploaded to their dashboard."""
    return _make_pair()


@pytest.fixture(scope="module")
def theirs():
    """Stands in for Salt Edge's callback key."""
    return _make_pair()


def sign_as_salt_edge(theirs, url, raw):
    key = theirs[0]
    sig = key.sign(url.encode() + b"|" + raw, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


FULL = {
    "SALTEDGE_APP_ID": "app", "SALTEDGE_SECRET": "sec",
    "SALTEDGE_CREDITOR_NAME": "Aniprotech Ltd",
    "SALTEDGE_CREDITOR_SORT_CODE": "12-34-56",
    "SALTEDGE_CREDITOR_ACCOUNT_NUMBER": "1234 5678",
    "SALTEDGE_CREDITOR_IBAN": "gb29 nwbk 6016 1331 9268 19",
}


def cfg(**over):
    env = dict(FULL)
    env.update(over)
    return se.settings(env)


# --- the key they publish ---------------------------------------------------------------------

def test_the_published_callback_key_is_a_real_2048_bit_rsa_key():
    key = serialization.load_pem_public_key(se.CALLBACK_PUBLIC_KEY.encode())
    assert key.key_size == 2048
    assert se.CALLBACK_KEY_VERSION == "6.0"


# --- settings ---------------------------------------------------------------------------------

def test_nothing_is_configured_without_both_keys():
    assert not se.is_configured(se.settings({}))
    assert not se.is_configured(se.settings({"SALTEDGE_APP_ID": "a"}))
    assert not se.is_configured(se.settings({"SALTEDGE_SECRET": "s"}))
    assert se.is_configured(se.settings({"SALTEDGE_APP_ID": "a", "SALTEDGE_SECRET": "s"}))


def test_pasted_values_are_cleaned():
    c = cfg(SALTEDGE_APP_ID='  "app"\n', SALTEDGE_SECRET="  sec \r\n",
            SALTEDGE_CREDITOR_SORT_CODE=" 12-34-56 ", SALTEDGE_CREDITOR_ACCOUNT_NUMBER="1234 5678")
    assert c["app_id"] == "app" and c["secret"] == "sec"
    assert c["sort_code"] == "123456" and c["account_number"] == "12345678"
    assert c["iban"] == "GB29NWBK60161331926819"


def test_a_private_key_can_be_pasted_on_one_line():
    c = cfg(SALTEDGE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\\nABC\\n-----END PRIVATE KEY-----")
    assert c["private_key"].count("\n") == 2


def test_the_vrp_type_is_commercial_unless_told_otherwise_and_never_garbage():
    assert cfg()["vrp_type"] == "commercial"
    assert cfg(SALTEDGE_VRP_TYPE="Sweeping")["vrp_type"] == "sweeping"
    assert cfg(SALTEDGE_VRP_TYPE="whatever")["vrp_type"] == "commercial"


def test_the_api_address_is_theirs_unless_overridden():
    assert cfg()["base"] == "https://www.saltedge.com/api/v6"
    assert cfg(SALTEDGE_API_BASE="http://127.0.0.1:9/api/v6/")["base"] == "http://127.0.0.1:9/api/v6"


def test_the_public_key_is_overridable_for_a_rotation(theirs):
    assert cfg()["callback_public_key"] == se.CALLBACK_PUBLIC_KEY
    assert cfg(SALTEDGE_CALLBACK_PUBLIC_KEY=theirs[2])["callback_public_key"] == theirs[2].strip()


@pytest.mark.parametrize("currency,drop,expected", [
    ("GBP", None, True),
    ("gbp", None, True),
    ("EUR", None, True),
    ("USD", None, False),
    ("INR", None, False),
    ("", None, False),
    ("GBP", "SALTEDGE_CREDITOR_NAME", False),
    ("GBP", "SALTEDGE_CREDITOR_SORT_CODE", False),
    ("GBP", "SALTEDGE_CREDITOR_ACCOUNT_NUMBER", False),
    ("GBP", "SALTEDGE_APP_ID", False),
    ("GBP", "SALTEDGE_SECRET", False),
    ("EUR", "SALTEDGE_CREDITOR_IBAN", False),
    ("EUR", "SALTEDGE_CREDITOR_SORT_CODE", True),      # a euro payment does not need one
])
def test_which_currencies_have_somewhere_to_land(currency, drop, expected):
    env = dict(FULL)
    if drop:
        env.pop(drop)
    assert se.can_take(se.settings(env), currency) is expected


def test_a_short_sort_code_or_account_number_is_not_good_enough():
    assert not se.can_take(cfg(SALTEDGE_CREDITOR_SORT_CODE="12345"), "GBP")
    assert not se.can_take(cfg(SALTEDGE_CREDITOR_ACCOUNT_NUMBER="1234567"), "GBP")


def test_autodebit_is_pounds_only():
    assert se.can_autodebit(cfg(), "GBP")
    assert not se.can_autodebit(cfg(), "EUR")
    assert not se.can_autodebit(cfg(SALTEDGE_CREDITOR_SORT_CODE=""), "GBP")


# --- signing what we send -------------------------------------------------------------------------

def test_a_request_is_signed_over_expiry_method_url_and_body(ours):
    url = "https://www.saltedge.com/api/v6/customers/"
    body = '{"data":{"identifier":"x"}}'
    h = se.signed_headers(cfg(SALTEDGE_PRIVATE_KEY=ours[1]), "post", url, body, now=1000)
    assert h["App-id"] == "app" and h["Secret"] == "sec"
    assert h["Expires-at"] == "1060"
    ours[0].public_key().verify(
        base64.b64decode(h["Signature"]), f"1060|POST|{url}|{body}".encode(),
        padding.PKCS1v15(), hashes.SHA256())


def test_a_get_is_signed_with_an_empty_body(ours):
    url = "https://www.saltedge.com/api/v6/providers?from_id=123"
    h = se.signed_headers(cfg(SALTEDGE_PRIVATE_KEY=ours[1]), "GET", url, "", now=5)
    ours[0].public_key().verify(base64.b64decode(h["Signature"]), f"65|GET|{url}|".encode(),
                                padding.PKCS1v15(), hashes.SHA256())


def test_the_signature_changes_with_every_part_it_covers(ours):
    c = cfg(SALTEDGE_PRIVATE_KEY=ours[1])
    base = se.signed_headers(c, "POST", "https://x/a", "{}", now=1)["Signature"]
    for other in (se.signed_headers(c, "PUT", "https://x/a", "{}", now=1),
                  se.signed_headers(c, "POST", "https://x/b", "{}", now=1),
                  se.signed_headers(c, "POST", "https://x/a", "{ }", now=1),
                  se.signed_headers(c, "POST", "https://x/a", "{}", now=2)):
        assert other["Signature"] != base


def test_without_a_private_key_a_request_goes_unsigned_which_test_mode_allows():
    h = se.signed_headers(cfg(), "GET", "https://x/y", "")
    assert "Signature" not in h and "Expires-at" not in h
    assert h["App-id"] == "app"


# --- verifying what they send ------------------------------------------------------------------

URL = "https://www.aniprotech.com/api/saltedge/callback/success"
RAW = b'{"data":{"payment_id":"1","status":"executed"},"meta":{"version":"6"}}'


def test_a_genuine_callback_verifies(theirs):
    sig = sign_as_salt_edge(theirs, URL, RAW)
    assert se.verify_callback(theirs[2], sig, URL, RAW) is True


def test_a_changed_body_is_refused(theirs):
    sig = sign_as_salt_edge(theirs, URL, RAW)
    assert not se.verify_callback(theirs[2], sig, URL, RAW.replace(b"executed", b"settled"))
    assert not se.verify_callback(theirs[2], sig, URL, RAW + b" ")
    assert not se.verify_callback(theirs[2], sig, URL, b"")


def test_the_url_is_part_of_what_was_signed(theirs):
    sig = sign_as_salt_edge(theirs, URL, RAW)
    assert not se.verify_callback(theirs[2], sig, URL.replace("success", "fail"), RAW)
    assert not se.verify_callback(theirs[2], sig, URL.replace("https", "http"), RAW)
    assert not se.verify_callback(theirs[2], sig, URL + "/", RAW)


def test_a_signature_from_anyone_else_is_refused(theirs):
    stranger = _make_pair()
    sig = sign_as_salt_edge(stranger, URL, RAW)
    assert not se.verify_callback(theirs[2], sig, URL, RAW)


@pytest.mark.parametrize("sig", ["", None, "   ", "not base64 !!!", "AAAA", "Zm9v"])
def test_a_missing_or_nonsense_signature_is_refused(theirs, sig):
    assert se.verify_callback(theirs[2], sig, URL, RAW) is False


def test_a_broken_key_or_missing_url_is_refused_not_an_error(theirs):
    sig = sign_as_salt_edge(theirs, URL, RAW)
    assert se.verify_callback("", sig, URL, RAW) is False
    assert se.verify_callback("-----BEGIN PUBLIC KEY-----\nzzzz\n-----END PUBLIC KEY-----", sig, URL, RAW) is False
    assert se.verify_callback(theirs[2], sig, "", RAW) is False


def test_a_callback_is_not_accepted_under_the_published_key_unless_it_is_theirs(theirs):
    """The real published key is the default, and a signature made with some
    other key does not pass it."""
    sig = sign_as_salt_edge(theirs, URL, RAW)
    assert not se.verify_callback(se.CALLBACK_PUBLIC_KEY, sig, URL, RAW)


# --- amounts, addresses, words ----------------------------------------------------------------------

@pytest.mark.parametrize("given,written", [
    (12.3, "12.30"), ("12.3", "12.30"), (100, "100.00"), (0.01, "0.01"),
    ("0.005", "0.01"), ("1.005", "1.01"), (19.999, "20.00"), (1234567.891, "1234567.89"),
])
def test_an_amount_is_a_two_place_string(given, written):
    assert se.format_amount(given) == written


@pytest.mark.parametrize("bad", [0, -1, "-0.01", "0.004", "abc", "", None, float("nan"),
                                 float("inf"), "1e999"])
def test_a_bad_amount_is_refused(bad):
    with pytest.raises(ValueError):
        se.format_amount(bad)


@pytest.mark.parametrize("given,kept", [
    ("203.0.113.9", "203.0.113.9"), (" 203.0.113.9 ", "203.0.113.9"),
    ("2001:db8::1", "2001:db8::1"),
    ("testclient", ""), ("", ""), (None, ""), ("999.1.1.1", ""), ("1.2.3", ""),
])
def test_only_a_real_address_is_passed_on(given, kept):
    assert se.valid_ip(given) == kept


def test_a_description_keeps_only_what_banks_accept():
    assert se.clean_description("Invoice INV-0042 for Acme & Sons!") == "Invoice INV-0042 for Acme Sons"
    assert se.clean_description("a\n\nb\t c") == "a b c"
    assert se.clean_description("<script>x</script>") == "script x script"
    assert se.clean_description("") == "Payment" and se.clean_description("!") == "Payment"
    assert len(se.clean_description("x" * 5000)) == 140
    assert len(se.clean_description("word " * 100, 18)) <= 18


def test_the_payer_has_a_stable_identity_that_is_not_their_email():
    a = se.customer_identifier(7, "Pat@Example.com")
    assert a == se.customer_identifier(7, " pat@example.com ")
    assert a != se.customer_identifier(8, "pat@example.com")
    assert a != se.customer_identifier(7, "sam@example.com")
    assert "pat" not in a.lower().replace("aniprotech", "") and "@" not in a


def test_references_are_short_alphanumeric_and_unique():
    ids = {se.end_to_end_id("INV", "2026/0042 #1") for _ in range(50)}
    assert len(ids) == 50
    for i in ids:
        assert i.isalnum() and len(i) <= 26 and i.startswith("INV20260042")


# --- the payment we ask for -----------------------------------------------------------------------------

def make_payment(**over):
    args = dict(cfg=cfg(), currency="GBP", amount=120.5, e2e="INV42ABC123",
                description="Invoice INV-0042", ip="203.0.113.9", customer="cust-1",
                return_to="https://app.example/invoice.html?id=t", custom_fields={"invoice_id": "42"})
    args.update(over)
    return se.payment_request(**args)["data"]


def test_a_pound_payment_is_a_faster_payment_to_the_configured_account():
    d = make_payment()
    a = d["payment_attributes"]
    assert d["template_identifier"] == "FPS"
    assert a["amount"] == "120.50" and a["currency_code"] == "GBP"
    assert a["creditor_sort_code"] == "123456" and a["creditor_account_number"] == "12345678"
    assert a["creditor_name"] == "Aniprotech Ltd" and "creditor_iban" not in a
    assert a["end_to_end_id"] == "INV42ABC123" and a["customer_ip_address"] == "203.0.113.9"
    assert a["description"] == "Invoice INV-0042"
    assert d["customer_identifier"] == "cust-1" and d["return_payment_id"] is True
    assert d["attempt"]["return_to"].startswith("https://app.example/") and d["attempt"]["custom_fields"] == {"invoice_id": "42"}


def test_a_euro_payment_is_sepa_to_the_configured_iban():
    d = make_payment(currency="eur")
    a = d["payment_attributes"]
    assert d["template_identifier"] == "SEPA"
    assert a["creditor_iban"] == "GB29NWBK60161331926819" and a["creditor_country_code"] == "GB"
    assert "creditor_sort_code" not in a and a["currency_code"] == "EUR"


def test_the_bank_is_left_to_the_payer_unless_one_is_fixed():
    assert "provider" not in make_payment()
    assert make_payment(cfg=cfg(SALTEDGE_PROVIDER_CODE="fake_oauth_client_xf"))["provider"] == {"code": "fake_oauth_client_xf"}


def test_a_payment_that_cannot_land_or_has_no_payer_address_is_refused_before_it_is_sent():
    with pytest.raises(ValueError):
        make_payment(currency="USD")
    with pytest.raises(ValueError):
        make_payment(cfg=cfg(SALTEDGE_CREDITOR_NAME=""))
    with pytest.raises(ValueError):
        make_payment(ip="testclient")
    with pytest.raises(ValueError):
        make_payment(amount=0)


def test_a_reference_is_shortened_for_the_banks_that_cap_it():
    a = make_payment(reference="INV-2026-0042-REVISED-AGAIN")["payment_attributes"]
    assert 0 < len(a["reference"]) <= 18
    assert "reference" not in make_payment()["payment_attributes"]


# --- the recurring agreement ---------------------------------------------------------------------------------

def make_consent(**over):
    args = dict(cfg=cfg(), customer="cust-1", provider_code="natwest_oauth_client_gb_xf",
                max_one_time=500, period_max=1500, period_type="month",
                valid_until=date.today() + timedelta(days=365), description="Invoices from Aniprotech",
                return_to="https://app.example/back", custom_fields={"mandate": "9"})
    args.update(over)
    return se.consent_request(**args)["data"]


def test_a_consent_names_the_account_the_limits_and_the_end():
    d = make_consent()
    c = d["consent_details"]
    assert d["provider"] == {"code": "natwest_oauth_client_gb_xf"} and d["customer_identifier"] == "cust-1"
    assert c["creditor_account"] == "123456" + "12345678" and len(c["creditor_account"]) == 14
    assert c["creditor_currency_code"] == "GBP" and c["creditor_name"] == "Aniprotech Ltd"
    assert c["max_one_time_amount"] == 500.0 and c["period_max_amount"] == 1500.0
    assert c["period_type"] == "month" and c["period_start"] == "calendar"
    assert c["valid_until"] == (date.today() + timedelta(days=365)).isoformat()
    assert c["vrp_type"] == "commercial"
    assert d["attempt"]["return_to"] == "https://app.example/back" and d["attempt"]["custom_fields"] == {"mandate": "9"}


def test_the_kind_of_recurring_payment_follows_the_setting():
    assert make_consent(cfg=cfg(SALTEDGE_VRP_TYPE="sweeping"))["consent_details"]["vrp_type"] == "sweeping"


@pytest.mark.parametrize("over", [
    dict(provider_code=""),
    dict(period_type="fortnightly"),
    dict(max_one_time=0),
    dict(period_max=-5),
    dict(max_one_time=600, period_max=500),
    dict(valid_until=date.today()),
    dict(valid_until=date.today() - timedelta(days=1)),
    dict(valid_until="2030-01-01"),
    dict(cfg=cfg(SALTEDGE_CREDITOR_SORT_CODE="")),
])
def test_a_consent_that_makes_no_sense_is_refused(over):
    with pytest.raises(ValueError):
        make_consent(**over)


def test_a_recurring_payment_carries_only_an_amount_and_a_reference():
    d = se.vrp_payment_request(42, 99.9, "REF1", "cust-1", {"invoice_id": "7"})["data"]
    assert d["payment_attributes"] == {"end_to_end_id": "REF1", "amount": "99.90"}
    assert d["consent_id"] == "42" and d["customer_identifier"] == "cust-1"
    assert d["attempt"]["custom_fields"] == {"invoice_id": "7"}
    with pytest.raises(ValueError):
        se.vrp_payment_request(42, 0, "REF1", "cust-1")


# --- what their statuses mean --------------------------------------------------------------------------------------

@pytest.mark.parametrize("status,outcome", [
    ("settled", "paid"), ("executed", "paid"), ("EXECUTED", "paid"), (" settled ", "paid"),
    ("failed", "failed"),
    ("initiated", "pending"), ("initiated_info_required", "pending"),
    ("authorizing", "pending"), ("authorized", "pending"),
    ("", "pending"), (None, "pending"), ("something new", "pending"),
])
def test_a_payment_is_paid_failed_or_still_going(status, outcome):
    assert se.payment_outcome(status) == outcome


@pytest.mark.parametrize("status,outcome", [
    ("active", "active"), ("ACTIVE", "active"),
    ("initiated", "pending"), ("", "pending"), (None, "pending"),
    ("rejected", "closed"), ("expired", "closed"), ("canceled", "closed"),
    ("cancelled", "closed"), ("revoked", "closed"),
])
def test_a_consent_is_active_pending_or_closed(status, outcome):
    assert se.consent_outcome(status) == outcome


def test_an_authorised_but_unexecuted_payment_is_not_yet_paid():
    assert se.payment_outcome("authorized") != "paid"
    assert se.payment_outcome("authorizing") != "paid"


def test_a_callback_body_is_read_into_what_matters():
    raw = json.dumps({"data": {"payment_id": 123, "customer_id": 9, "status": "Executed",
                               "raw_provider_status": "ACTC", "custom_fields": {"invoice_id": "5"}},
                      "meta": {"version": "6"}}).encode()
    got = se.parse_callback(raw)
    assert got == {"payment_id": "123", "customer_id": "9", "status": "executed",
                   "raw_provider_status": "ACTC", "error_class": "", "error_message": "",
                   "custom_fields": {"invoice_id": "5"}}


def test_a_failure_callback_carries_its_reason():
    raw = json.dumps({"data": {"payment_id": "1", "status": "failed", "error_class": "Unfinished",
                               "error_message": "Payment abandoned."}}).encode()
    got = se.parse_callback(raw)
    assert got["error_class"] == "Unfinished" and got["error_message"] == "Payment abandoned."


@pytest.mark.parametrize("raw", [b"", b"nope", b"[]", b"{}", b'{"data":[]}', b'{"data":{}}',
                                 b'{"data":{"payment_id":""}}', b'{"data":{"payment_id":null}}', None])
def test_a_callback_that_is_not_one_is_an_error(raw):
    with pytest.raises(ValueError):
        se.parse_callback(raw)


# --- talking to them --------------------------------------------------------------------------------------------------

class Wire:
    """Stands in for the network: records what was sent, answers as told."""

    def __init__(self, status=200, text='{"data":{"ok":true}}', boom=None):
        self.status, self.text, self.boom, self.sent = status, text, boom, []

    def __call__(self, method, url, headers, body, timeout):
        self.sent.append({"method": method, "url": url, "headers": headers, "body": body})
        if self.boom:
            raise self.boom
        return self.status, self.text


@pytest.fixture
def wire(monkeypatch):
    w = Wire()
    monkeypatch.setattr(se, "_send", w)
    return w


def test_a_call_goes_to_the_right_place_with_the_body_it_signed(wire, ours):
    c = cfg(SALTEDGE_PRIVATE_KEY=ours[1])
    out = se.create_payment(c, {"data": {"a": "é"}})
    sent = wire.sent[0]
    assert out == {"ok": True}
    assert sent["method"] == "POST" and sent["url"] == "https://www.saltedge.com/api/v6/payments/create"
    assert sent["body"] == '{"data":{"a":"\\u00e9"}}'
    expires = sent["headers"]["Expires-at"]
    ours[0].public_key().verify(
        base64.b64decode(sent["headers"]["Signature"]),
        f"{expires}|POST|{sent['url']}|{sent['body']}".encode(), padding.PKCS1v15(), hashes.SHA256())


@pytest.mark.parametrize("fn,args,method,path", [
    (se.show_payment, ("11",), "GET", "/payments/11"),
    (se.refresh_payment, ("11",), "PUT", "/payments/11/refresh"),
    (se.show_consent, ("22",), "GET", "/vrp_consents/22"),
    (se.revoke_consent, ("22",), "PUT", "/vrp_consents/22/revoke"),
])
def test_each_call_uses_the_method_and_path_in_their_reference(wire, fn, args, method, path):
    fn(cfg(), *args)
    assert wire.sent[0]["method"] == method
    assert wire.sent[0]["url"] == "https://www.saltedge.com/api/v6" + path
    assert wire.sent[0]["body"] == ""


def test_creating_a_consent_and_a_recurring_payment_post_to_their_paths(wire):
    se.create_consent(cfg(), {"data": {}})
    se.create_vrp_payment(cfg(), {"data": {}})
    assert [s["url"].rsplit("/api/v6", 1)[1] for s in wire.sent] == ["/vrp_consents/create", "/payments/vrp_payment"]
    assert all(s["method"] == "POST" for s in wire.sent)


def test_nothing_is_sent_when_it_is_not_set_up(wire):
    with pytest.raises(se.SaltEdgeError) as e:
        se.show_payment(se.settings({}), "1")
    assert e.value.error_class == "NotConfigured" and wire.sent == []


def test_an_error_carries_their_class_and_message(wire):
    wire.status = 406
    wire.text = json.dumps({"error": {"class": "VrpNotSupported", "message": "No VRP at this bank"}})
    with pytest.raises(se.SaltEdgeError) as e:
        se.create_consent(cfg(), {"data": {}})
    assert e.value.status == 406 and e.value.error_class == "VrpNotSupported"
    assert "No VRP" in e.value.message


def test_an_answer_that_is_not_json_is_still_an_error(wire):
    wire.status, wire.text = 502, "<html>Bad gateway</html>"
    with pytest.raises(se.SaltEdgeError) as e:
        se.show_payment(cfg(), "1")
    assert e.value.status == 502 and "Bad gateway" in e.value.message


def test_no_answer_at_all_is_an_error_with_status_zero(wire):
    wire.boom = TimeoutError("slow")
    with pytest.raises(se.SaltEdgeError) as e:
        se.show_payment(cfg(), "1")
    assert e.value.status == 0 and e.value.error_class == "Unreachable"


def test_an_empty_success_is_an_empty_answer_not_a_crash(wire):
    wire.text = ""
    assert se.show_payment(cfg(), "1") == {}


# --- finding a bank for a recurring agreement ------------------------------------------------------------------------------

def test_a_bank_can_do_recurring_payments_if_it_lists_the_template_or_the_fields():
    assert se.supports_vrp({"payment_templates": ["FPS", "VRP_COMMERCIAL"]}, "commercial")
    assert not se.supports_vrp({"payment_templates": ["FPS", "VRP_SWEEPING"]}, "commercial")
    assert se.supports_vrp({"payment_templates": ["FPS"], "vrp_consent_fields": [{"name": "x"}]}, "commercial")
    assert not se.supports_vrp({"payment_templates": ["FPS"]}, "commercial")
    assert not se.supports_vrp({}, "sweeping")


def test_the_bank_list_is_filtered_sorted_and_followed_across_pages(wire, monkeypatch):
    pages = [
        {"data": [{"code": "b_bank", "name": "B Bank", "payment_templates": ["VRP_COMMERCIAL"]},
                  {"code": "cards_only", "name": "Cards", "payment_templates": ["FPS"]}],
         "meta": {"next_id": "250", "next_page": "/api/v6/providers?from_id=250"}},
        {"data": [{"code": "a_bank", "name": "a Bank", "payment_templates": ["VRP_COMMERCIAL"]},
                  {"code": "b_bank", "name": "B Bank", "payment_templates": ["VRP_COMMERCIAL"]}],
         "meta": {}},
    ]
    answers = iter(pages)

    def send(method, url, headers, body, timeout):
        wire.sent.append({"url": url})
        return 200, json.dumps(next(answers))

    monkeypatch.setattr(se, "_send", send)
    banks = se.list_vrp_banks(cfg())
    assert banks == [{"code": "a_bank", "name": "a Bank"}, {"code": "b_bank", "name": "B Bank"}]
    assert "country_code=GB" in wire.sent[0]["url"] and "include_pis_fields=true" in wire.sent[0]["url"]
    assert "from_id=250" in wire.sent[1]["url"]
    assert len(wire.sent) == 2


def test_a_failing_bank_list_is_an_error(wire):
    wire.status, wire.text = 401, json.dumps({"error": {"class": "ApiKeyNotFound", "message": "no"}})
    with pytest.raises(se.SaltEdgeError) as e:
        se.list_vrp_banks(cfg())
    assert e.value.status == 401 and e.value.error_class == "ApiKeyNotFound"


def test_the_bank_list_stops_at_the_page_limit(wire, monkeypatch):
    def send(method, url, headers, body, timeout):
        wire.sent.append({"url": url})
        return 200, json.dumps({"data": [], "meta": {"next_id": str(len(wire.sent))}})

    monkeypatch.setattr(se, "_send", send)
    assert se.list_vrp_banks(cfg(), pages=3) == []
    assert len(wire.sent) == 3
