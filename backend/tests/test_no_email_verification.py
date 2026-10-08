"""Nobody is asked to prove their address.

Signing up used to send a six-digit code, and an account could not send an
invoice, a statement or a credit note until it was typed back. The code often
never arrived - the platform's own mail was not always able to send it - and
Google sign-ins were asked to prove an address Google had just proved. New
people were stuck at the first step.

An account is now usable the moment it exists. What is worth holding down is
that this stays true: that signing up sends nothing and asks for nothing, that
a brand-new account sends an invoice straight away, and that nothing is left
that could ask again.

(The wider suite's accounts are no longer pre-verified either, so every test
that sends a statement or a credit note now does it as a new account.)
"""
import uuid

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield
    main.rate_limiter._hits.clear()


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def capture(to_email, subject, body, from_email, *a, **kw):
        sent.append({"to": to_email, "subject": subject, "body": body})
        return True, "captured"

    monkeypatch.setattr(main, "send_email_background", capture)
    return sent


def sign_up(client):
    email = f"new-{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Fresh Ltd"})
    assert res.status_code == 200, res.text
    assert client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"}).status_code == 200
    return email, res.json()


def an_invoice(client):
    res = client.post("/api/invoices", json={
        "contact": "Customer Ltd", "email": "customer@example.com",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "status": "Awaiting Payment", "tax_type": "exclusive",
        "line_items": [{"description": "Work", "qty": 1, "price": 100.0, "tax_rate": "No Tax"}]})
    assert res.status_code == 200, res.text
    return res.json()


# --- signing up --------------------------------------------------------------------

def test_signing_up_sends_nothing_and_asks_for_nothing(client, outbox):
    email, body = sign_up(client)
    assert outbox == [], "a signup must not send a code"
    assert body == {"message": "Account created", "client_id": body["client_id"]}
    with main.SessionLocal() as db:
        kinds = [d.kind for d in db.query(models.DBEmailDelivery).filter(
            models.DBEmailDelivery.client_id == body["client_id"]).all()]
    assert "verification" not in kinds


def test_signing_up_does_not_depend_on_mail_working_at_all(client, outbox, monkeypatch):
    """This is the case that was stranding people."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    _email, body = sign_up(client)
    assert body["message"] == "Account created" and outbox == []


def test_the_account_is_never_stamped_proved_because_nothing_asks(client):
    sign_up(client)
    cid = client.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        assert (db.get(models.DBClient, cid).email_verified_at or "") == ""


# --- using it at once ----------------------------------------------------------------

def test_a_brand_new_account_can_send_an_invoice_straight_away(client, outbox):
    sign_up(client)
    inv = an_invoice(client)
    res = client.post(f"/api/invoices/{inv['number']}/send", json={})
    assert res.status_code == 200, res.text
    assert any(m["to"] == "customer@example.com" for m in outbox), outbox
    assert client.get(f"/api/invoices/{inv['number']}").json()["status"] == "Sent"


def test_nothing_in_the_server_still_tells_somebody_to_confirm_their_address():
    import pathlib
    src = (pathlib.Path(main.__file__)).read_text(encoding="utf-8")
    for phrase in ("Confirm your email address before", "email_is_verified", "issue_verification"):
        assert phrase not in src, f"{phrase!r} is back"


# --- the old way in is gone ---------------------------------------------------------------

@pytest.mark.parametrize("method,path", [("post", "/api/client/verify-email"), ("post", "/api/client/resend-verification")])
def test_the_code_endpoints_no_longer_exist(client, method, path):
    sign_up(client)
    res = getattr(client, method)(path, json={"code": "123456"})
    assert res.status_code in (404, 405), (path, res.status_code)


# --- what the screens still ask --------------------------------------------------------------

def test_the_account_status_carries_the_trial_and_whether_mail_can_send_and_no_verification(client):
    sign_up(client)
    got = client.get("/api/client/account-status")
    assert got.status_code == 200, got.text
    data = got.json()
    assert set(data) >= {"email", "mine", "trial"}
    for gone in ("verified", "can_send", "blocked_reason"):
        assert gone not in data, gone
    assert data["trial"]["active"] is True


def test_a_page_opened_before_this_change_still_gets_an_answer_from_the_old_address(client):
    sign_up(client)
    old = client.get("/api/client/verification-status")
    assert old.status_code == 200 and old.json() == client.get("/api/client/account-status").json()


def test_the_status_needs_a_session(client):
    client.post("/api/client/logout")
    assert client.get("/api/client/account-status").status_code in (401, 403)
    assert client.get("/api/client/verification-status").status_code in (401, 403)
