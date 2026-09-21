"""The bank feed: transactions arriving on their own.

What Xero does through Tink, this does through GoCardless Bank Account
Data: an open-banking provider that is the regulated party. The business
picks its bank, is sent to the bank's own login to say yes, comes back, and
from then on each account's transactions are pulled every morning into the
Bank screen - the same lines a statement file would have brought in, matched
to invoices the same way. Consent lasts ninety days, which is regulation and
not our choice, so the business is told before it runs out and asked again.

Everything provider-specific is in here, behind six methods, so a different
provider is a different class and nothing else moves. The tests use a fake
with the same six.
"""
import logging
import time
from datetime import date, datetime

import httpx

logger = logging.getLogger("main")

PROVIDER_NAME = "GoCardless Bank Account Data"
PROVIDER_BLURB = ("aniprotech partners with GoCardless to securely import your transactions. "
                  "GoCardless creates a one-way connection from your bank to aniprotech and is "
                  "authorised and regulated by the Financial Conduct Authority.")
CONSENT_DAYS = 90            # the most PSD2 allows before the customer must say yes again
HISTORY_DAYS = 90            # how far back the first pull reaches
SANDBOX_INSTITUTION = "SANDBOXFINANCE_SFIN0000"


class BankFeedError(Exception):
    """The provider said no, or could not be reached; the message is fit to show."""


class GoCardlessBankData:
    BASE = "https://bankaccountdata.gocardless.com/api/v2"

    def __init__(self, secret_id, secret_key, timeout=25.0):
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.timeout = timeout
        self._token = ""
        self._token_until = 0.0

    def configured(self):
        return bool(self.secret_id and self.secret_key)

    # --- the wire --------------------------------------------------------------
    def _access(self):
        if self._token and time.time() < self._token_until - 60:
            return self._token
        r = httpx.post(f"{self.BASE}/token/new/", json={"secret_id": self.secret_id, "secret_key": self.secret_key},
                       timeout=self.timeout)
        if r.status_code != 200:
            raise BankFeedError("The bank feed provider refused our keys - check BANK_FEED_SECRET_ID and BANK_FEED_SECRET_KEY")
        data = r.json()
        self._token = data.get("access", "")
        self._token_until = time.time() + int(data.get("access_expires", 86400))
        return self._token

    def _call(self, method, path, **kw):
        headers = {"Authorization": f"Bearer {self._access()}", "Accept": "application/json"}
        try:
            r = httpx.request(method, f"{self.BASE}{path}", headers=headers, timeout=self.timeout, **kw)
        except httpx.HTTPError as e:
            raise BankFeedError(f"Could not reach the bank feed provider: {e.__class__.__name__}")
        if r.status_code == 429:
            raise BankFeedError("The bank allows only a few refreshes a day; try again tomorrow")
        if r.status_code >= 400:
            detail = ""
            try:
                body = r.json()
                detail = body.get("detail") or body.get("summary") or ""
            except Exception:
                pass
            raise BankFeedError(f"The bank feed provider said no ({r.status_code}){': ' + detail if detail else ''}")
        return r.json() if r.content else {}

    # --- the six things a provider does ---------------------------------------------
    def institutions(self, country="gb"):
        rows = self._call("GET", f"/institutions/?country={country}")
        return [{"id": i.get("id"), "name": i.get("name"), "logo": i.get("logo") or "",
                 "history_days": int(i.get("transaction_total_days") or HISTORY_DAYS),
                 "consent_days": int(i.get("max_access_valid_for_days") or CONSENT_DAYS)} for i in rows]

    def start(self, institution_id, redirect, reference, consent_days=CONSENT_DAYS, history_days=HISTORY_DAYS):
        """Begin a connection: the agreement (what for, how long) and the
        requisition (the link the customer follows to their bank)."""
        agreement = self._call("POST", "/agreements/enduser/", json={
            "institution_id": institution_id,
            "max_historical_days": int(history_days),
            "access_valid_for_days": int(consent_days),
            "access_scope": ["balances", "details", "transactions"],
        })
        req = self._call("POST", "/requisitions/", json={
            "redirect": redirect, "institution_id": institution_id, "reference": reference,
            "agreement": agreement["id"], "user_language": "EN",
        })
        return {"requisition_id": req["id"], "agreement_id": agreement["id"], "link": req["link"]}

    def status(self, requisition_id):
        """'linked' once the customer has said yes at the bank; 'pending' until
        then; 'expired' or 'rejected' when it is over."""
        req = self._call("GET", f"/requisitions/{requisition_id}/")
        code = req.get("status", "")
        state = {"LN": "linked", "CR": "pending", "GC": "pending", "UA": "pending", "GA": "pending",
                 "SA": "pending", "EX": "expired", "RJ": "rejected", "SU": "suspended"}.get(code, "pending")
        return {"state": state, "accounts": list(req.get("accounts") or [])}

    def account(self, account_id):
        details = (self._call("GET", f"/accounts/{account_id}/details/") or {}).get("account") or {}
        bban = str(details.get("bban") or "")
        # A UK BBAN is the sort code and the account number run together.
        sort_code = "-".join([bban[0:2], bban[2:4], bban[4:6]]) if len(bban) == 14 else ""
        number = bban[6:] if len(bban) == 14 else bban
        return {"name": details.get("name") or details.get("product") or details.get("ownerName") or "Account",
                "owner": details.get("ownerName") or "", "iban": details.get("iban") or "",
                "sort_code": sort_code, "account_number": number, "currency": (details.get("currency") or "GBP").upper()}

    def balance(self, account_id):
        rows = (self._call("GET", f"/accounts/{account_id}/balances/") or {}).get("balances") or []
        # The bank's own idea of the balance, in order of preference.
        for kind in ("closingBooked", "expected", "interimBooked", "interimAvailable", "openingBooked"):
            for b in rows:
                if b.get("balanceType") == kind:
                    amt = b.get("balanceAmount") or {}
                    return {"amount": float(amt.get("amount") or 0), "currency": (amt.get("currency") or "GBP").upper(),
                            "on": b.get("referenceDate") or date.today().isoformat()}
        if rows:
            amt = rows[0].get("balanceAmount") or {}
            return {"amount": float(amt.get("amount") or 0), "currency": (amt.get("currency") or "GBP").upper(),
                    "on": rows[0].get("referenceDate") or date.today().isoformat()}
        return None

    def transactions(self, account_id, date_from):
        data = (self._call("GET", f"/accounts/{account_id}/transactions/?date_from={date_from}") or {}).get("transactions") or {}
        out = []
        for t in data.get("booked") or []:
            amt = t.get("transactionAmount") or {}
            who = t.get("creditorName") or t.get("debtorName") or ""
            words = t.get("remittanceInformationUnstructured") or " ".join(t.get("remittanceInformationUnstructuredArray") or []) or ""
            out.append({
                "external_id": t.get("transactionId") or t.get("internalTransactionId") or "",
                "date": (t.get("bookingDate") or t.get("valueDate") or "")[:10],
                "description": (f"{who} {words}".strip() or "Transaction")[:300],
                "reference": (t.get("endToEndId") or t.get("entryReference") or "")[:120],
                "amount": float(amt.get("amount") or 0),
                "currency": (amt.get("currency") or "GBP").upper(),
            })
        return out

    def disconnect(self, requisition_id):
        try:
            self._call("DELETE", f"/requisitions/{requisition_id}/")
        except BankFeedError as e:
            logger.warning("bank feed disconnect: %s", e)


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
