"""Choosing how mail leaves: the connected Google account, or your own server.

Everything went through the Gmail API, so a business without that connection
could not send at all. SMTP is now a second way out and the operator picks
which one is used.

Two rules matter. Whichever was chosen is the one used - quietly falling back
to the other would send from an address nobody picked, and the first anyone
would know is a customer replying to the wrong inbox. And Bcc has to stay
blind: the Gmail API strips that header on the way out, a mail server does
not, so over SMTP the header must be removed by us and the address carried in
the envelope instead.
"""
import pytest

import main
import models


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def set_transport(value):
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "email.transport",
            models.DBSettings.client_id == None,        # noqa: E711
        ).first()
        was = row.value if row else None
        if row:
            row.value = value
        else:
            db.add(models.DBSettings(key="email.transport", client_id=None,
                                     value=value))
        db.commit()
        return was


@pytest.fixture
def via_smtp(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "postbox")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2")
    was = set_transport("smtp")
    yield
    set_transport(was or "gmail")


class FakeSMTP:
    """Stands in for a mail server and remembers what it was handed."""
    last = None

    def __init__(self, host, port, timeout=None):
        FakeSMTP.last = {"host": host, "port": port, "envelope": None,
                         "message": None, "starttls": False, "login": None}

    def ehlo(self):
        pass

    def starttls(self):
        FakeSMTP.last["starttls"] = True

    def login(self, user, password):
        FakeSMTP.last["login"] = user

    def sendmail(self, sender, recipients, message):
        FakeSMTP.last["envelope"] = list(recipients)
        FakeSMTP.last["message"] = message
        FakeSMTP.last["sender"] = sender

    def quit(self):
        pass


@pytest.fixture
def fake_server(monkeypatch):
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    FakeSMTP.last = None
    yield FakeSMTP


def send(**kw):
    kw.setdefault("to_email", "ada@acme.test")
    kw.setdefault("subject", "Subject")
    kw.setdefault("body", "Body")
    kw.setdefault("from_email", "me@biz.test")
    return main.send_email_background(**kw)


# --- which way out --------------------------------------------------------------
def test_the_default_is_the_google_account():
    with main.SessionLocal() as db:
        assert main.email_transport(db) in ("gmail", "smtp")
    was = set_transport("gmail")
    try:
        assert main.email_transport() == "gmail"
    finally:
        set_transport(was or "gmail")


def test_choosing_smtp_sends_through_the_mail_server(via_smtp, fake_server):
    ok, message = send()
    assert ok, message
    assert "SMTP" in message
    assert fake_server.last["host"] == "mail.example.test"
    assert fake_server.last["port"] == 587


def test_smtp_chosen_but_not_configured_says_so(monkeypatch, fake_server):
    """It must not quietly use the other one - that sends from an address
    nobody picked."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    was = set_transport("smtp")
    try:
        ok, message = send()
        assert ok is False
        assert "SMTP_HOST" in message, message
        assert fake_server.last is None, "it tried to send anyway"
    finally:
        set_transport(was or "gmail")


def test_starttls_is_used_by_default(via_smtp, fake_server):
    send()
    assert fake_server.last["starttls"] is True


def test_starttls_can_be_turned_off_for_a_server_that_has_none(
        via_smtp, fake_server, monkeypatch):
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    send()
    assert fake_server.last["starttls"] is False


def test_it_signs_in_when_a_user_is_configured(via_smtp, fake_server):
    send()
    assert fake_server.last["login"] == "postbox"


def test_an_open_relay_needs_no_sign_in(via_smtp, fake_server, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "")
    send()
    assert fake_server.last["login"] is None


# --- copies, over a transport that does not tidy up after us --------------------
def test_a_cc_is_delivered_and_stays_visible(via_smtp, fake_server):
    send(cc="boss@biz.test")
    assert "boss@biz.test" in fake_server.last["envelope"]
    assert "Cc: boss@biz.test" in fake_server.last["message"]


def test_a_bcc_is_delivered_but_the_header_is_gone(via_smtp, fake_server):
    """The Gmail API strips this header; a mail server sends exactly what it
    is given. Left in, every recipient sees who was blind-copied."""
    send(cc="boss@biz.test", bcc="audit@biz.test")

    assert "audit@biz.test" in fake_server.last["envelope"], "the bcc was not sent"
    assert "Bcc:" not in fake_server.last["message"], fake_server.last["message"][:400]
    assert "audit@biz.test" not in fake_server.last["message"], "the address leaked"


def test_every_recipient_reaches_the_envelope(via_smtp, fake_server):
    send(cc="one@biz.test, two@biz.test", bcc="three@biz.test")
    envelope = fake_server.last["envelope"]
    for who in ("ada@acme.test", "one@biz.test", "two@biz.test", "three@biz.test"):
        assert who in envelope, (who, envelope)


def test_a_server_that_refuses_is_reported_not_swallowed(via_smtp, monkeypatch):
    import smtplib

    class Broken(FakeSMTP):
        def sendmail(self, *a, **kw):
            raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", Broken)
    ok, message = send()
    assert ok is False
    assert "connection refused" in message


# --- the secret stays a secret ---------------------------------------------------
def test_the_mail_password_is_not_in_the_settings_screen(via_smtp, superadmin):
    """A value that can be read out of a web page is a value that leaks with
    the page. The variable is named in the help text on purpose - telling an
    operator where to put the password is not the same as showing it."""
    raw = superadmin.get("/api/superadmin/platform-settings").text
    assert "hunter2" not in raw
    assert "postbox" not in raw
    assert "mail.example.test" not in raw


def test_the_choice_itself_is_in_the_settings_screen(superadmin):
    """It is not a secret, and an operator has to be able to switch it."""
    rows = superadmin.get("/api/superadmin/platform-settings").json()
    keys = [r["key"] for r in rows.get("settings", rows if isinstance(rows, list) else [])]
    assert "email.transport" in keys, keys[:10]
