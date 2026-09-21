"""Bank feeds: what Xero does through Tink, done through the provider.

A business picks its bank, says yes at the bank, comes back, and its
transactions arrive as bank lines every morning - matched to invoices the
same way a statement file's lines are. Consent lasts ninety days; the
business is told before it ends and asked again. The provider is a fake
here with the same six methods as the real one.
"""
from datetime import date, timedelta

import pytest

import bankfeed
import main
from conftest import make_invoice


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


class FakeBank:
    """The provider as the tests need it: a bank with one account whose
    transactions and balance the test sets."""

    def __init__(self):
        self.linked = True
        self.txns = [
            {"external_id": "t1", "date": d(-3), "description": "ACME LTD INV-0001", "reference": "INV-0001", "amount": 120.0, "currency": "GBP"},
            {"external_id": "t2", "date": d(-2), "description": "BRITISH GAS", "reference": "", "amount": -80.5, "currency": "GBP"},
            {"external_id": "t3", "date": d(-1), "description": "BOLT CO", "reference": "", "amount": 300.0, "currency": "GBP"},
        ]
        self.bal = {"amount": 4289.33, "currency": "GBP", "on": d(0)}
        self.deleted = []
        self.calls = []
        self.fail = None

    def configured(self):
        return True

    def institutions(self, country="gb"):
        return [{"id": "TSB_TSBSGB2A", "name": "TSB (UK)", "logo": "https://cdn.example/tsb.png", "history_days": 90, "consent_days": 90},
                {"id": "BARCLAYS_BUKBGB22", "name": "Barclays", "logo": "", "history_days": 730, "consent_days": 90},
                {"id": bankfeed.SANDBOX_INSTITUTION, "name": "Sandbox Finance", "logo": "", "history_days": 90, "consent_days": 90}]

    def start(self, institution_id, redirect, reference, consent_days=90, history_days=90):
        self.calls.append(("start", institution_id, redirect, reference, consent_days))
        return {"requisition_id": "req-" + reference[:6], "agreement_id": "agr-1", "link": "https://ob.example/consent/" + reference}

    def status(self, requisition_id):
        return {"state": "linked" if self.linked else "pending", "accounts": ["acc-1"] if self.linked else []}

    def account(self, account_id):
        return {"name": "Business Current", "owner": "ANIKACARE LIMITED", "iban": "GB00TSBS77682900028276",
                "sort_code": "77-68-29", "account_number": "00028276", "currency": "GBP"}

    def balance(self, account_id):
        return dict(self.bal)

    def transactions(self, account_id, date_from):
        self.calls.append(("transactions", account_id, date_from))
        if self.fail:
            raise bankfeed.BankFeedError(self.fail)
        return [t for t in self.txns if t["date"] >= date_from]

    def disconnect(self, requisition_id):
        self.deleted.append(requisition_id)


@pytest.fixture
def bank(monkeypatch):
    fake = FakeBank()
    monkeypatch.setattr(main, "bank_provider", lambda: fake)
    main._INSTITUTIONS["rows"] = []
    main._INSTITUTIONS["at"] = 0.0
    return fake


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, *a, **kw: (sent.append({"to": to, "subject": subject, "body": body}), (True, "sent"))[1])
    return sent


def connect(tenant, bank, institution="TSB_TSBSGB2A"):
    started = tenant.post("/api/bank/feeds", json={"institution_id": institution}).json()
    done = tenant.post("/api/bank/feeds/complete", json={"reference": started["reference"]})
    assert done.status_code == 200, done.text
    return done.json()


# --- the flow, screen by screen ------------------------------------------------------
def test_without_keys_the_bank_screen_offers_files_only(tenant, monkeypatch):
    monkeypatch.setattr(main, "bank_provider", lambda: None)
    d0 = tenant.get("/api/bank/feeds").json()
    assert d0["configured"] is False and d0["feeds"] == []
    assert tenant.get("/api/bank/feeds/institutions?q=tsb").json() == {"institutions": [], "configured": False}
    r = tenant.post("/api/bank/feeds", json={"institution_id": "x"})
    assert r.status_code == 400 and "not switched on" in r.text


def test_the_bank_is_found_by_name(tenant, bank):
    hits = tenant.get("/api/bank/feeds/institutions?q=tsb").json()["institutions"]
    assert [h["name"] for h in hits] == ["TSB (UK)"] and hits[0]["logo"].endswith("tsb.png")
    assert len(tenant.get("/api/bank/feeds/institutions").json()["institutions"]) == 3
    d0 = tenant.get("/api/bank/feeds").json()
    assert d0["configured"] and d0["provider"] == "GoCardless Bank Account Data" and "regulated" in d0["blurb"] and d0["consent_days"] == 90


def test_starting_sends_the_customer_to_their_bank_and_back_to_the_bank_screen(tenant, bank):
    r = tenant.post("/api/bank/feeds", json={"institution_id": "TSB_TSBSGB2A"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["link"].startswith("https://ob.example/consent/") and out["consent_days"] == 90
    kind, inst, redirect, reference, days = bank.calls[-1]
    assert inst == "TSB_TSBSGB2A" and reference == out["reference"] and days == 90
    assert redirect.endswith(f"/app.html?feed={reference}#/bank")
    feed = tenant.get("/api/bank/feeds").json()["feeds"][0]
    assert feed["status"] == "pending" and feed["institution_name"] == "TSB (UK)" and feed["consent_expires_on"] == d(90)
    assert tenant.post("/api/bank/feeds", json={"institution_id": "NOT_A_BANK"}).status_code == 400
    assert tenant.post("/api/bank/feeds", json={}).status_code == 400


def test_back_from_the_bank_the_accounts_are_taken_and_the_first_lines_pulled(tenant, bank):
    feed = connect(tenant, bank)
    assert feed["status"] == "linked" and feed["days_left"] == 90 and not feed["renew_soon"]
    acc = feed["accounts"][0]
    assert acc["name"] == "Business Current" and acc["sort_code"] == "77-68-29" and acc["account_number"] == "00028276"
    assert acc["enabled"] and acc["account"].startswith("TSB (UK) Business Current") and acc["account"].endswith("8276")
    assert acc["statement_balance"] == 4289.33 and acc["balance_on"] == d(0)
    # Three transactions; the two money-in are to match, the money-out is kept.
    lines = tenant.get("/api/bank/lines?status=unmatched").json()["lines"]
    assert sorted(l["amount"] for l in lines) == [120.0, 300.0]
    assert [l["amount"] for l in tenant.get("/api/bank/lines?status=out").json()["lines"]] == [-80.5]
    assert acc["lines_total"] == 3 and acc["to_match"] == 2 and acc["difference"] == 420.0 and acc["in_app"] == 3869.33
    imports = tenant.get("/api/bank/imports").json()["imports"]
    assert imports[0]["kind"] == "feed" and imports[0]["imported_by"] == "bank feed" and imports[0]["lines"] == 3
    # The first pull reaches ninety days back.
    assert bank.calls[-1][2] == d(-90)


def test_the_bank_not_yet_confirmed_or_refusing(tenant, bank):
    bank.linked = False
    started = tenant.post("/api/bank/feeds", json={"institution_id": "TSB_TSBSGB2A"}).json()
    r = tenant.post("/api/bank/feeds/complete", json={"reference": started["reference"]})
    assert r.status_code == 409 and "not confirmed" in r.text
    bank.status = lambda rid: {"state": "rejected", "accounts": []}
    r = tenant.post("/api/bank/feeds/complete", json={"reference": started["reference"]})
    assert r.status_code == 400 and "did not give access" in r.text
    assert tenant.post("/api/bank/feeds/complete", json={"reference": "nope"}).status_code == 404


def test_a_line_from_the_feed_is_matched_and_recorded_like_any_other(tenant, bank):
    inv = make_invoice(tenant, status="Awaiting Payment", contact="Acme Ltd", email="acme@example.com",
                       line_items=[{"description": "x", "qty": 1, "price": 120.0, "tax_rate": "0%"}])
    connect(tenant, bank)
    lines = tenant.get("/api/bank/lines?status=unmatched").json()["lines"]
    line = next(l for l in lines if l["amount"] == 120.0)
    assert line["suggestions"] and line["suggestions"][0]["number"] == inv["number"]
    r = tenant.post(f"/api/bank/lines/{line['id']}/record", json={"invoice_number": inv["number"]})
    assert r.status_code == 200, r.text
    assert tenant.get(f"/api/invoices/{inv['number']}").json()["status"] == "Paid"
    acc = tenant.get("/api/bank/feeds").json()["feeds"][0]["accounts"][0]
    assert acc["to_match"] == 1 and acc["difference"] == 300.0 and acc["in_app"] == 3989.33


# --- every morning -------------------------------------------------------------------------
def test_the_morning_pull_brings_only_what_is_new(tenant, bank):
    connect(tenant, bank)
    bank.txns.append({"external_id": "t4", "date": d(0), "description": "NEW CUSTOMER", "reference": "", "amount": 55.0, "currency": "GBP"})
    bank.bal["amount"] = 4344.33
    with main.SessionLocal() as db:
        db.query(main.models.DBJobRun).delete()
        db.commit()
        out = main.run_due_jobs(only="bank_feed_sync")
    # The job is platform-wide, so the count covers every business with a
    # feed; this business's own account is checked below.
    assert out and out[0]["job"] == "bank_feed_sync" and out[0]["status"] == "done" and int(out[0]["detail"].split()[0]) >= 1, out
    acc = tenant.get("/api/bank/feeds").json()["feeds"][0]["accounts"][0]
    assert acc["lines_total"] == 4 and acc["statement_balance"] == 4344.33
    assert bank.calls[-1][2] == d(-5), "a few days back, because banks book late"
    # Run again: nothing is new, nothing is doubled.
    with main.SessionLocal() as db:
        db.query(main.models.DBJobRun).delete()
        db.commit()
        main.run_due_jobs(only="bank_feed_sync")
    assert tenant.get("/api/bank/feeds").json()["feeds"][0]["accounts"][0]["lines_total"] == 4


def test_refresh_now_is_allowed_a_few_times_a_day(tenant, bank):
    feed = connect(tenant, bank)
    for _ in range(3):
        assert tenant.post(f"/api/bank/feeds/{feed['id']}/sync").status_code == 200
    r = tenant.post(f"/api/bank/feeds/{feed['id']}/sync")
    assert r.status_code == 429 and "tomorrow" in r.text
    assert tenant.get("/api/bank/feeds").json()["feeds"][0]["syncs_left_today"] == 0


def test_a_provider_failure_is_shown_not_thrown(tenant, bank):
    feed = connect(tenant, bank)
    bank.fail = "The bank feed provider said no (500)"
    r = tenant.post(f"/api/bank/feeds/{feed['id']}/sync")
    assert r.status_code == 502 and "said no" in r.text
    assert tenant.get("/api/bank/feeds").json()["feeds"][0]["last_error"].startswith("The bank feed provider said no")


# --- ninety days ------------------------------------------------------------------------------
def test_the_business_is_told_once_before_consent_ends_and_again_when_it_has(tenant, bank, outbox, account):
    feed = connect(tenant, bank)
    with main.SessionLocal() as db:
        row = db.get(main.models.DBBankFeed, feed["id"])
        row.consent_expires_on = d(7)
        db.commit()
    for _ in range(2):
        with main.SessionLocal() as db:
            db.query(main.models.DBJobRun).delete()
            db.commit()
            main.run_due_jobs(only="bank_feed_sync")
    warnings = [m for m in outbox if m["to"] == account["email"] and m["subject"].startswith("Renew your TSB (UK)")]
    assert len(warnings) == 1 and d(7) in warnings[0]["subject"] and "/app.html#/bank" in warnings[0]["body"]
    assert tenant.get("/api/bank/feeds").json()["feeds"][0]["renew_soon"] is True
    with main.SessionLocal() as db:
        row = db.get(main.models.DBBankFeed, feed["id"])
        row.consent_expires_on = d(-1)
        db.commit()
        db.query(main.models.DBJobRun).delete()
        db.commit()
        main.run_due_jobs(only="bank_feed_sync")
    stopped = [m for m in outbox if m["to"] == account["email"] and "has stopped" in m["subject"]]
    assert len(stopped) == 1
    f = tenant.get("/api/bank/feeds").json()["feeds"][0]
    assert f["status"] == "expired"
    assert tenant.post(f"/api/bank/feeds/{f['id']}/sync").status_code == 400


def test_renewing_replaces_the_old_connection_and_keeps_the_money_account(tenant, bank):
    first = connect(tenant, bank)
    money_account = first["accounts"][0]["account_id"]
    second = connect(tenant, bank)
    feeds = tenant.get("/api/bank/feeds").json()["feeds"]
    assert [f["id"] for f in feeds] == [second["id"]], "the old connection is gone from the list"
    assert second["accounts"][0]["account_id"] == money_account, "the same money account, so nothing is doubled"
    assert len(bank.deleted) == 1 and bank.deleted[0].startswith("req-"), "the old consent is withdrawn at the provider"
    # The lines already there are not brought in again, and they still count
    # as this account's, so the card does not start from nothing.
    acc = tenant.get("/api/bank/feeds").json()["feeds"][0]["accounts"][0]
    assert acc["lines_total"] == 3 and acc["to_match"] == 2 and acc["difference"] == 420.0
    assert len(tenant.get("/api/bank/lines?status=unmatched").json()["lines"]) == 2


# --- switching off ---------------------------------------------------------------------------------
def test_an_account_can_be_switched_off_or_pointed_elsewhere(tenant, bank):
    feed = connect(tenant, bank)
    acc = feed["accounts"][0]
    other = tenant.post("/api/accounts", json={"name": "Savings", "kind": "bank"}).json()
    r = tenant.post(f"/api/bank/feeds/{feed['id']}/accounts/{acc['id']}", json={"enabled": False, "account_id": other["id"]})
    assert r.status_code == 200 and r.json()["enabled"] is False and r.json()["account"] == "Savings"
    bank.txns.append({"external_id": "t9", "date": d(0), "description": "LATE", "reference": "", "amount": 9.0, "currency": "GBP"})
    assert tenant.post(f"/api/bank/feeds/{feed['id']}/sync").json()["new_lines"] == 0, "a switched-off account is not pulled"


def test_disconnecting_stops_the_feed_and_keeps_the_lines(tenant, bank):
    feed = connect(tenant, bank)
    assert tenant.delete(f"/api/bank/feeds/{feed['id']}").status_code == 200
    assert len(bank.deleted) == 1 and bank.deleted[0].startswith("req-"), "the consent is withdrawn at the provider"
    assert tenant.get("/api/bank/feeds").json()["feeds"] == []
    assert len(tenant.get("/api/bank/lines?status=unmatched").json()["lines"]) == 2


def test_another_business_cannot_see_or_touch_the_connection(tenant, bank, client, account):
    feed = connect(tenant, bank)
    other = f"other-{account['email']}"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/bank/feeds").json()["feeds"] == []
    assert client.post(f"/api/bank/feeds/{feed['id']}/sync").status_code == 404
    assert client.delete(f"/api/bank/feeds/{feed['id']}").status_code == 404
    assert client.post("/api/bank/feeds/complete", json={"reference": feed and "x"}).status_code == 404
    assert client.get("/api/bank/lines?status=unmatched").json()["lines"] == []


# --- the real provider's wire, without the wire ----------------------------------------------------
def test_the_real_provider_reads_a_uk_account_and_a_transaction(monkeypatch):
    p = bankfeed.GoCardlessBankData("id", "key")
    answers = {
        "/accounts/a1/details/": {"account": {"bban": "77682900028276", "currency": "GBP", "ownerName": "ANIKACARE LIMITED", "name": "Business Current"}},
        "/accounts/a1/balances/": {"balances": [{"balanceType": "interimAvailable", "balanceAmount": {"amount": "4000.00", "currency": "GBP"}},
                                                {"balanceType": "closingBooked", "balanceAmount": {"amount": "4289.33", "currency": "GBP"}, "referenceDate": "2026-09-20"}]},
        "/accounts/a1/transactions/?date_from=2026-06-22": {"transactions": {"booked": [
            {"transactionId": "abc", "bookingDate": "2026-09-19", "transactionAmount": {"amount": "-12.34", "currency": "GBP"},
             "creditorName": "BRITISH GAS", "remittanceInformationUnstructured": "DD 1234"}], "pending": []}},
        "/requisitions/r1/": {"status": "LN", "accounts": ["a1"]},
    }
    monkeypatch.setattr(p, "_call", lambda method, path, **kw: answers[path])
    acc = p.account("a1")
    assert acc["sort_code"] == "77-68-29" and acc["account_number"] == "00028276" and acc["owner"] == "ANIKACARE LIMITED"
    bal = p.balance("a1")
    assert bal["amount"] == 4289.33 and bal["on"] == "2026-09-20", "the booked balance is preferred over the available one"
    t = p.transactions("a1", "2026-06-22")[0]
    assert t == {"external_id": "abc", "date": "2026-09-19", "description": "BRITISH GAS DD 1234", "reference": "", "amount": -12.34, "currency": "GBP"}
    assert p.status("r1") == {"state": "linked", "accounts": ["a1"]}
    assert not bankfeed.GoCardlessBankData("", "").configured()
