"""Salt Edge Payment Initiation (API v6): paying an invoice from the payer's own
bank, and taking later invoices from it without asking again.

Two things, both open banking:

  * a payment - the payer is sent to Salt Edge's page, picks their bank, and
    approves a Faster Payment (GBP) or SEPA transfer (EUR) there;
  * a variable recurring payment (VRP) - the payer approves a ceiling once, and
    payments inside it are then taken with no second approval. This is what
    "autodebit" means here. It is UK only (a sort code and account number,
    in pounds), and the payer's bank has to support it.

Salt Edge is the licensed party that talks to the bank; the money goes
straight from the payer's account to the creditor account named in the
request. Nothing is held by Salt Edge or by us on the way.

Kept apart from main.py, like bankfeed.py, so the parts that decide what gets
sent and whether a message is genuine are plain functions that can be tested
without a network. Everything here reads its settings from the environment and
is silent until SALTEDGE_APP_ID and SALTEDGE_SECRET are both set.

Written from Salt Edge's own v6 reference (docs.saltedge.com/v6): the paths,
field names, statuses and the two signatures - one on what we send, one on
what they send us - are theirs.
"""
import base64
import ipaddress
import json
import os
import re
import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

API_BASE = "https://www.saltedge.com/api/v6"

# What Salt Edge signs its callbacks with (signature key version 6.0), as
# published at docs.saltedge.com/v6. It is the public half, so it is not a
# secret. SALTEDGE_CALLBACK_PUBLIC_KEY replaces it when they rotate the key,
# which is announced as a new "Signature-key-version".
CALLBACK_KEY_VERSION = "6.0"
CALLBACK_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8qxSS5BmftHK/eyW+o98
NR89TyDmz1V8e6yyFdoMPddEYN4Bcidkk2whoJEc/T/AKghHQ9Nq+DuebnRYYcSJ
YT99VbR1PpIw2R9i8z+DZ79hoizy6z+rwxGANnJOr5BDF5HUKJ8uKS9yGRieojFv
Y9j+rxH6Fj6P90bO4d2igYYspKVoI3Zb3hWS0LrWN+JXAaW9qcOmQPTgO0WG0MUK
gB3NNMfN7gMIkl3chbaULiEgVciP2qZTIGb1b7IDr5+fA9oVVGaXiybdieGHIa4J
S7JNTf0JjWrIKd2DaczKULnghqNQsnoCu+S8BurEOJR5EN1BBfQBPlbSh+ru1zgZ
AQIDAQAB
-----END PUBLIC KEY-----"""

# A payment is over once it is one of these. "executed" is the bank having
# accepted it for payment and "settled" is the bank confirming the funds moved;
# plenty of banks never report anything past executed, so waiting for settled
# would leave most invoices unpaid for good.
PAID_STATUSES = ("settled", "executed")
FAILED_STATUSES = ("failed",)

VRP_TYPES = ("commercial", "sweeping")
VRP_PERIODS = ("day", "week", "fortnight", "month", "half-year", "year")


class SaltEdgeError(Exception):
    """Salt Edge said no, or could not be reached.

    status is the HTTP status (0 when there was no answer); error_class is
    Salt Edge's own name for what went wrong ("VrpNotSupported", ...), which is
    what to match on rather than the wording of the message.
    """

    def __init__(self, status, error_class="", message=""):
        self.status = status
        self.error_class = error_class or ""
        self.message = message or ""
        super().__init__(f"Salt Edge {status} {self.error_class}: {self.message}"[:300])


# --- settings -------------------------------------------------------------

def _clean(value):
    """A value as pasted, minus the whitespace and quotes that come with it."""
    return (value or "").strip().strip('"').strip("'").strip()


def _pem(value):
    """A PEM key as a one-line environment variable.

    Dashboards that cannot hold a multi-line value are given the key with
    literal \\n in it, so those are turned back into real line breaks.
    """
    text = _clean(value).replace("\\n", "\n")
    return text


def digits(value):
    return re.sub(r"\D", "", value or "")


def settings(env=None):
    """Everything this module needs, read from the environment now rather than
    at import, so a variable changed on the host takes effect on the next
    request and a test can set one without reloading anything."""
    env = os.environ if env is None else env
    vrp_type = _clean(env.get("SALTEDGE_VRP_TYPE", "")).lower() or "commercial"
    return {
        "app_id": _clean(env.get("SALTEDGE_APP_ID", "")),
        "secret": _clean(env.get("SALTEDGE_SECRET", "")),
        "private_key": _pem(env.get("SALTEDGE_PRIVATE_KEY", "")),
        "callback_public_key": _pem(env.get("SALTEDGE_CALLBACK_PUBLIC_KEY", "")) or CALLBACK_PUBLIC_KEY,
        "creditor_name": _clean(env.get("SALTEDGE_CREDITOR_NAME", "")),
        "sort_code": digits(_clean(env.get("SALTEDGE_CREDITOR_SORT_CODE", ""))),
        "account_number": digits(_clean(env.get("SALTEDGE_CREDITOR_ACCOUNT_NUMBER", ""))),
        "iban": re.sub(r"\s", "", _clean(env.get("SALTEDGE_CREDITOR_IBAN", ""))).upper(),
        "provider_code": _clean(env.get("SALTEDGE_PROVIDER_CODE", "")),
        "vrp_type": vrp_type if vrp_type in VRP_TYPES else "commercial",
        "base": (_clean(env.get("SALTEDGE_API_BASE", "")) or API_BASE).rstrip("/"),
    }


def is_configured(cfg):
    """Both halves of the key pair, or nothing at all."""
    return bool(cfg["app_id"] and cfg["secret"])


def can_take(cfg, currency):
    """Whether a payment in this currency has somewhere to land.

    The creditor is whoever receives the money, so without an account to name
    the request would be refused - better to not offer the option at all.
    """
    if not is_configured(cfg) or not cfg["creditor_name"]:
        return False
    currency = (currency or "").upper()
    if currency == "GBP":
        return len(cfg["sort_code"]) == 6 and len(cfg["account_number"]) == 8
    if currency == "EUR":
        return len(cfg["iban"]) >= 15
    return False


def can_autodebit(cfg, currency):
    """A recurring consent names a UK account, so it is GBP and nothing else."""
    return (currency or "").upper() == "GBP" and can_take(cfg, "GBP")


# --- what we send, and signing it ------------------------------------------

def sign(private_key_pem, text):
    """base64(RSA-SHA256(text)). Salt Edge verifies this against the public key
    uploaded on its Keys & Secrets page."""
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    signature = key.sign(text.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def signed_headers(cfg, method, url, body, now=None):
    """Headers for one request.

    A client in Test status may send unsigned requests, but a Live one must
    sign every request, so the signature is added whenever there is a key to
    sign with. The string signed is "Expires-at|METHOD|full url|body", and the
    body has to be exactly the bytes that go on the wire.
    """
    headers = {
        "App-id": cfg["app_id"],
        "Secret": cfg["secret"],
        "Accept": "application/json",
        "Content-type": "application/json",
    }
    if cfg["private_key"]:
        # A minute is what they suggest; an hour is the most they accept.
        expires = int((now if now is not None else time.time()) + 60)
        headers["Expires-at"] = str(expires)
        headers["Signature"] = sign(
            cfg["private_key"], f"{expires}|{method.upper()}|{url}|{body or ''}")
    return headers


def verify_callback(public_key_pem, signature_b64, callback_url, raw_body):
    """Is this callback really from Salt Edge.

    They sign "callback_url|post_body" with their private key. The URL is the
    one they were given, not whatever this request appears to have arrived on,
    because a proxy in front of us changes that. Anything that is not a clean
    pass - no signature, a malformed key, bad base64 - is a no.
    """
    if not signature_b64 or not callback_url:
        return False
    try:
        signature = base64.b64decode(signature_b64.strip(), validate=True)
        key = serialization.load_pem_public_key(public_key_pem.encode())
        key.verify(signature, callback_url.encode("utf-8") + b"|" + (raw_body or b""),
                   padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
    except Exception:                       # noqa: BLE001 - any doubt is a no
        return False


def format_amount(amount):
    """"12.30", the way every amount field here is written: a string, two
    places. Refuses anything that is not a positive, finite number."""
    try:
        value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("That is not an amount")
    if not value.is_finite() or value <= 0:
        raise ValueError("The amount must be more than nothing")
    return format(value, "f")


def valid_ip(value):
    """The payer's address, or "" if it is not one. Salt Edge requires it on
    every payment and passes it to the bank, so a made-up one is worse than
    none."""
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return ""


# Banks restrict what a payment description may say. This is Salt Edge's own
# advice for what is safe everywhere, and the length is the shortest limit of
# the ones they list.
_DESCRIPTION_BAD = re.compile(r"[^A-Za-z0-9.,()+'? -]")


def clean_description(text, limit=140):
    cleaned = _DESCRIPTION_BAD.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:limit].strip()
    return cleaned if len(cleaned) >= 2 else "Payment"


def customer_identifier(client_id, contact):
    """Who the payer is, to Salt Edge: stable, so the same person's later
    payments and their recurring consent share a customer, and not their email
    address, which Salt Edge has no need to hold."""
    import hashlib
    digest = hashlib.sha256(f"{client_id}|{(contact or '').strip().lower()}".encode()).hexdigest()
    return f"aniprotech-{client_id}-{digest[:20]}"


def end_to_end_id(prefix, number):
    """The reference we get back on every callback and the bank shows on its
    statement. Letters and digits only, because banks reject anything else, and
    short because they cap its length."""
    token = re.sub(r"[^A-Za-z0-9]", "", f"{prefix}{number}")[:20]
    return f"{token}{os.urandom(3).hex().upper()}"[:26]


def payment_request(cfg, currency, amount, e2e, description, ip, reference="",
                    customer=None, return_to="", custom_fields=None):
    """The body for POST /payments/create.

    FPS for pounds (a sort code and account number), SEPA for euros (an IBAN).
    The creditor is always the account from the settings; nothing the payer
    sends reaches this.
    """
    currency = (currency or "").upper()
    if not can_take(cfg, currency):
        raise ValueError(f"Salt Edge cannot take {currency or 'this currency'} here")
    ip = valid_ip(ip)
    if not ip:
        raise ValueError("The payer's address is needed")

    attributes = {
        "amount": format_amount(amount),
        "currency_code": currency,
        "creditor_name": cfg["creditor_name"][:70],
        "description": clean_description(description),
        "end_to_end_id": e2e,
        "customer_ip_address": ip,
    }
    if reference:
        attributes["reference"] = clean_description(reference, 18)
    if currency == "GBP":
        template = "FPS"
        attributes["creditor_sort_code"] = cfg["sort_code"]
        attributes["creditor_account_number"] = cfg["account_number"]
    else:
        template = "SEPA"
        attributes["creditor_iban"] = cfg["iban"]
        attributes["creditor_country_code"] = cfg["iban"][:2]

    data = {
        "template_identifier": template,
        "payment_attributes": attributes,
        "customer_identifier": customer,
        "return_payment_id": True,
        "attempt": {"custom_fields": custom_fields or {}, "locale": "en"},
    }
    if return_to:
        data["attempt"]["return_to"] = return_to
    if cfg["provider_code"]:
        data["provider"] = {"code": cfg["provider_code"]}
    return {"data": data}


def consent_request(cfg, customer, provider_code, max_one_time, period_max,
                    period_type, valid_until, description, return_to="",
                    custom_fields=None):
    """The body for POST /vrp_consents/create: the ceiling the payer approves.

    max_one_time caps any single payment and period_max caps the total in a
    period. The payer approves these at their own bank, and every later
    payment is checked against them there, whatever we ask for.
    """
    if not can_autodebit(cfg, "GBP"):
        raise ValueError("Autodebit needs a UK account to be paid into")
    if not provider_code:
        raise ValueError("Choose a bank")
    if period_type not in VRP_PERIODS:
        raise ValueError("Unknown period")
    one = Decimal(format_amount(max_one_time))
    total = Decimal(format_amount(period_max))
    if total < one:
        raise ValueError("The limit for a period cannot be below the limit for one payment")
    if not isinstance(valid_until, date) or valid_until <= date.today():
        raise ValueError("The agreement has to end in the future")

    return {"data": {
        "customer_identifier": customer,
        "provider": {"code": provider_code},
        "consent_details": {
            "creditor_account": cfg["sort_code"] + cfg["account_number"],
            "creditor_name": cfg["creditor_name"][:70],
            "creditor_currency_code": "GBP",
            "valid_until": valid_until.isoformat(),
            "max_one_time_amount": float(one),
            "period_max_amount": float(total),
            "period_type": period_type,
            "period_start": "calendar",
            "description": clean_description(description, 100),
            "vrp_type": cfg["vrp_type"],
        },
        "attempt": dict({"locale": "en", "custom_fields": custom_fields or {}},
                        **({"return_to": return_to} if return_to else {})),
    }}


def vrp_payment_request(consent_id, amount, e2e, customer, custom_fields=None):
    """The body for POST /payments/vrp_payment. The creditor, currency and
    description come from the consent, not from here."""
    return {"data": {
        "payment_attributes": {"end_to_end_id": e2e, "amount": format_amount(amount)},
        "consent_id": str(consent_id),
        "customer_identifier": customer,
        "attempt": {"custom_fields": custom_fields or {}},
    }}


# --- what comes back --------------------------------------------------------

def payment_outcome(status):
    """paid, failed or pending - the only three things the rest of the app
    needs to know about a payment's state."""
    status = (status or "").strip().lower()
    if status in PAID_STATUSES:
        return "paid"
    if status in FAILED_STATUSES:
        return "failed"
    return "pending"


def consent_outcome(status):
    """active, pending or closed. Closed covers everything that ends a consent
    for good: refused, lapsed, cancelled by the payer or revoked by us."""
    status = (status or "").strip().lower()
    if status == "active":
        return "active"
    if status in ("rejected", "expired", "canceled", "cancelled", "revoked"):
        return "closed"
    return "pending"


def parse_callback(raw):
    """What a callback body says, or ValueError if it is not one."""
    try:
        body = json.loads(raw or b"")
    except (ValueError, TypeError):
        raise ValueError("Not JSON")
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        raise ValueError("No data")
    payment_id = str(data.get("payment_id") or "").strip()
    if not payment_id:
        raise ValueError("No payment")
    return {
        "payment_id": payment_id,
        "customer_id": str(data.get("customer_id") or ""),
        "status": str(data.get("status") or "").lower(),
        "raw_provider_status": str(data.get("raw_provider_status") or ""),
        "error_class": str(data.get("error_class") or ""),
        "error_message": str(data.get("error_message") or ""),
        "custom_fields": data.get("custom_fields") if isinstance(data.get("custom_fields"), dict) else {},
    }


# --- talking to Salt Edge ----------------------------------------------------

def _send(method, url, headers, body, timeout):
    """The one place a request leaves. Tests replace this."""
    res = httpx.request(method, url, headers=headers,
                        content=body.encode("utf-8") if body else None, timeout=timeout)
    return res.status_code, res.text


def call(cfg, method, path, payload=None, query=None, timeout=30):
    """One signed request. Returns the "data" of the answer, or raises
    SaltEdgeError."""
    if not is_configured(cfg):
        raise SaltEdgeError(0, "NotConfigured", "Salt Edge is not set up")
    url = cfg["base"] + path + ("?" + urlencode(query) if query else "")
    body = json.dumps(payload, separators=(",", ":")) if payload is not None else ""
    try:
        status, text = _send(method.upper(), url, signed_headers(cfg, method, url, body),
                             body, timeout)
    except Exception as exc:                 # noqa: BLE001
        raise SaltEdgeError(0, "Unreachable", str(exc)[:160])
    try:
        answer = json.loads(text) if text else {}
    except ValueError:
        answer = {}
    if status >= 300:
        err = answer.get("error") if isinstance(answer, dict) else None
        err = err if isinstance(err, dict) else {}
        raise SaltEdgeError(status, err.get("class", ""), err.get("message", "") or (text or "")[:160])
    return answer.get("data", answer) if isinstance(answer, dict) else {}


def create_payment(cfg, body):
    return call(cfg, "POST", "/payments/create", body)


def show_payment(cfg, payment_id):
    return call(cfg, "GET", f"/payments/{payment_id}")


def refresh_payment(cfg, payment_id):
    return call(cfg, "PUT", f"/payments/{payment_id}/refresh")


def create_consent(cfg, body):
    return call(cfg, "POST", "/vrp_consents/create", body)


def show_consent(cfg, consent_id):
    return call(cfg, "GET", f"/vrp_consents/{consent_id}")


def revoke_consent(cfg, consent_id):
    return call(cfg, "PUT", f"/vrp_consents/{consent_id}/revoke")


def create_vrp_payment(cfg, body):
    return call(cfg, "POST", "/payments/vrp_payment", body)


def supports_vrp(provider, vrp_type):
    """Whether a bank from the providers list can do this kind of recurring
    payment. Salt Edge lists the templates a provider supports, and says to
    look at vrp_consent_fields for one that does VRP, so either is enough."""
    wanted = "VRP_" + vrp_type.upper()
    templates = [str(t).upper() for t in (provider.get("payment_templates") or [])]
    return wanted in templates or bool(provider.get("vrp_consent_fields"))


def list_vrp_banks(cfg, country="GB", pages=8):
    """[{code, name}] of the banks that can be asked for a recurring consent."""
    out, from_id = [], None
    for _ in range(pages):
        query = {"country_code": country, "include_pis_fields": "true",
                 "exclude_inactive": "true", "per_page": 250}
        if from_id:
            query["from_id"] = from_id
        url = cfg["base"] + "/providers?" + urlencode(query)
        try:
            status, text = _send("GET", url, signed_headers(cfg, "GET", url, ""), "", 30)
        except Exception as exc:             # noqa: BLE001
            raise SaltEdgeError(0, "Unreachable", str(exc)[:160])
        try:
            answer = json.loads(text) if text else {}
        except ValueError:
            answer = {}
        if status >= 300:
            err = answer.get("error") if isinstance(answer, dict) else None
            err = err if isinstance(err, dict) else {}
            raise SaltEdgeError(status, err.get("class", ""), err.get("message", ""))
        for p in answer.get("data") or []:
            if isinstance(p, dict) and p.get("code") and supports_vrp(p, cfg["vrp_type"]):
                out.append({"code": p["code"], "name": p.get("name") or p["code"]})
        next_page = ((answer.get("meta") or {}).get("next_id")
                     or (re.search(r"from_id=(\d+)", (answer.get("meta") or {}).get("next_page") or "") or [None, None])[1])
        if not next_page:
            break
        from_id = next_page
    seen, unique = set(), []
    for bank in sorted(out, key=lambda b: b["name"].lower()):
        if bank["code"] not in seen:
            seen.add(bank["code"])
            unique.append(bank)
    return unique
