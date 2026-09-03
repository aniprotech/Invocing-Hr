"""Proving the address on a new account belongs to whoever signed up.

Signing up asked for an address and believed it. Anybody could register with
somebody else's, and then set the platform to send invoices from it - which
is the thing an unproved address is actually good for.

The account is created either way. Refusing to create it would mean losing a
signup whenever mail is slow, and the address can be proved afterwards. What
an unproved account may not do is send email as that address.
"""
import re
import uuid

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield
    main.rate_limiter._hits.clear()


@pytest.fixture(autouse=True)
def _email_can_send(monkeypatch):
    """A transport that exists, so the readiness check runs for real."""
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = "smtp"
        else:
            db.add(models.DBSettings(key="email.transport", client_id=None,
                                     value="smtp"))
        db.commit()
    yield
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        if row:
            row.value = was or "gmail"
            db.commit()


@pytest.fixture
def sent(monkeypatch):
    posted = []

    def capture(to_email, subject, body, from_email, *a, **kw):
        posted.append({"to": to_email, "subject": subject, "body": body})
        return True, "captured"

    monkeypatch.setattr(main, "send_email_background", capture)
    return posted


def code_from(sent):
    for message in reversed(sent):
        found = re.search(r"\b(\d{6})\b", message["subject"] + " " + message["body"])
        if found:
            return found.group(1)
    return None


def sign_up(client, sent):
    email = f"new-{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Fresh Ltd"})
    assert res.status_code == 200, res.text
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
    return email, res.json()


# --- signing up ---------------------------------------------------------------------
def test_a_code_is_sent_when_the_account_is_made(client, sent):
    email, body = sign_up(client, sent)
    assert body["verification_sent"] is True, body
    assert body["email_verified"] is False
    assert sent and sent[-1]["to"] == email
    assert code_from(sent), "no code in the email"


def test_the_code_is_never_in_the_answer(client, sent):
    _email, body = sign_up(client, sent)
    code = code_from(sent)
    assert code and code not in str(body), body


def test_the_account_starts_unverified(client, sent):
    sign_up(client, sent)
    assert client.get("/api/client/verification-status").json()["verified"] is False


def test_the_account_is_still_made_when_mail_is_down(client, sent, monkeypatch):
    """A signup is not lost because email is broken - the code can be asked
    for again once it is fixed."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    email = f"nomail-{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "No Mail Ltd"})
    assert res.status_code == 200, res.text
    assert res.json()["verification_sent"] is False


# --- using the code -------------------------------------------------------------------
def test_the_right_code_proves_the_address(client, sent):
    sign_up(client, sent)
    res = client.post("/api/client/verify-email", json={"code": code_from(sent)})
    assert res.status_code == 200, res.text
    assert res.json()["verified"] is True
    assert client.get("/api/client/verification-status").json()["verified"] is True


def test_a_wrong_code_is_refused(client, sent):
    sign_up(client, sent)
    assert client.post("/api/client/verify-email",
                       json={"code": "000000"}).status_code == 400


def test_no_code_is_refused(client, sent):
    sign_up(client, sent)
    assert client.post("/api/client/verify-email", json={"code": ""}).status_code == 400


def test_the_code_is_not_stored_as_typed(client, sent):
    """Reading this table must not be enough to use what is in it."""
    sign_up(client, sent)
    code = code_from(sent)
    with main.SessionLocal() as db:
        row = db.query(models.DBEmailVerification).order_by(
            models.DBEmailVerification.id.desc()).first()
    assert row.code_hash != code
    assert code not in row.code_hash


def test_a_code_works_once(client, sent):
    sign_up(client, sent)
    code = code_from(sent)
    assert client.post("/api/client/verify-email", json={"code": code}).status_code == 200
    # Already verified, so it answers plainly rather than pretending to work.
    again = client.post("/api/client/verify-email", json={"code": code})
    assert again.json()["verified"] is True


def test_five_wrong_guesses_kill_the_code(client, sent):
    """Six digits is a million guesses, which is nothing to a script."""
    sign_up(client, sent)
    real = code_from(sent)
    for _ in range(main.VERIFY_MAX_ATTEMPTS):
        client.post("/api/client/verify-email", json={"code": "000000"})
    assert client.post("/api/client/verify-email",
                       json={"code": real}).status_code == 400


def test_asking_again_retires_the_previous_code(client, sent):
    sign_up(client, sent)
    first = code_from(sent)
    assert client.post("/api/client/resend-verification").status_code == 200
    assert client.post("/api/client/verify-email",
                       json={"code": first}).status_code == 400, "the old code still worked"


def test_a_resend_when_mail_is_down_says_so(client, sent, monkeypatch):
    sign_up(client, sent)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    res = client.post("/api/client/resend-verification")
    assert res.status_code == 503
    assert "cannot send email" in res.json()["detail"]


# --- other people's accounts -------------------------------------------------------------
def test_a_code_for_one_account_does_not_verify_another(client, sent):
    """Ordered so it actually bites.

    The lookup takes the newest unused code, so if the newest happens to be
    the account's own, dropping the per-account filter changes nothing and the
    test proves nothing. The other account signs up second, so its code is the
    newest one - and using it must still be refused.
    """
    mine = f"mine-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": mine, "password": "Passw0rdTest", "company_name": "Mine Ltd"})

    theirs_email = f"theirs-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": theirs_email, "password": "Passw0rdTest", "company_name": "Theirs Ltd"})
    theirs_code = code_from(sent)          # the newest code in the table

    client.post("/api/client/login", json={"email": mine, "password": "Passw0rdTest"})
    assert client.post("/api/client/verify-email",
                       json={"code": theirs_code}).status_code == 400,         "somebody else's code verified this account"
    assert client.get("/api/client/verification-status").json()["verified"] is False


def test_it_needs_a_session(client):
    assert client.post("/api/client/verify-email",
                       json={"code": "123456"}).status_code in (401, 403)
    assert client.get("/api/client/verification-status").status_code in (401, 403)


# --- what an unproved account may and may not do -------------------------------------
def make_invoice_for(client):
    res = client.post("/api/invoices", json={
        "contact": "Customer Ltd", "email": "customer@example.com",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "status": "Awaiting Payment", "tax_type": "exclusive",
        "line_items": [{"description": "Work", "qty": 1, "price": 100.0,
                        "tax_rate": "No Tax"}]})
    assert res.status_code == 200, res.text
    return res.json()


def test_an_unproved_account_cannot_send_an_invoice(client, sent):
    """Anybody could sign up as somebody else; this is what that would buy
    them, so it is the one thing held back."""
    sign_up(client, sent)
    inv = make_invoice_for(client)
    res = client.post(f"/api/invoices/{inv['number']}/send", json={})
    assert res.status_code == 403, res.text
    assert "Confirm your email" in res.json()["detail"]


def test_but_it_can_do_everything_else(client, sent):
    """Holding back the whole product would punish somebody whose only
    mistake was that our email was slow."""
    sign_up(client, sent)
    inv = make_invoice_for(client)
    assert client.get("/api/invoices").status_code == 200
    assert client.get(f"/api/invoices/{inv['number']}").status_code == 200
    assert client.post(f"/api/invoices/{inv['number']}/payments",
                       json={"amount": 10}).status_code == 200
    assert client.get("/api/insights").status_code == 200


def test_proving_it_lets_the_invoice_go(client, sent):
    sign_up(client, sent)
    assert client.post("/api/client/verify-email",
                       json={"code": code_from(sent)}).status_code == 200

    inv = make_invoice_for(client)
    res = client.post(f"/api/invoices/{inv['number']}/send", json={})
    # Whatever the mail provider then does, it is no longer refused for
    # being unverified.
    assert res.status_code != 403, res.text


# --- nothing is charged for, or recorded as, a send that cannot happen -----------
def test_an_invoice_is_not_marked_sent_when_mail_is_down(client, sent, monkeypatch):
    """It charged credit and wrote "Sent" with today's date before knowing
    whether the message could go anywhere. A business paid for an invoice the
    customer never got, and the record said it had gone."""
    sign_up(client, sent)
    client.post("/api/client/verify-email", json={"code": code_from(sent)})
    inv = make_invoice_for(client)

    monkeypatch.delenv("SMTP_HOST", raising=False)
    res = client.post(f"/api/invoices/{inv['number']}/send", json={})
    assert res.status_code == 503, res.text
    assert "cannot be emailed" in res.json()["detail"]

    after = client.get(f"/api/invoices/{inv['number']}").json()
    assert after["status"] != "Sent", after["status"]
    assert not after.get("sent"), after.get("sent")
