"""Setting up SMTP from the product, not from the hosting provider.

The platform's mail server lived only in environment variables. The screen
that chose "smtp" said so in its help text, and nothing else in the product
mentioned it - so an operator who wanted sign-in codes to go out through a
Gmail address with an app password had no idea where to put it, and reported
it as "there is no place to keep my Gmail and app password". Which was true.

The tenants had a screen for exactly this all along. The operator gets the
same: host, port, username, password, and a button that sends one message to
their own address and says exactly what happened. The password is stored and
never sent back. The environment is still read when nothing is set here, so
an install that was configured that way keeps working.
"""
import pytest

import main
import models


@pytest.fixture
def superadmin():
    from fastapi.testclient import TestClient
    main.rate_limiter._hits.clear()
    with TestClient(main.app) as op:
        res = op.post("/api/superadmin/login", json={
            "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
        assert res.status_code == 200, res.text
        yield op


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for v in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_STARTTLS", "FROM_EMAIL"):
        monkeypatch.delenv(v, raising=False)
    keys = ("email.transport", "email.smtp_host", "email.smtp_port", "email.smtp_user",
            "email.smtp_password", "email.smtp_starttls", "email.from_address")

    def clear():
        with main.SessionLocal() as db:
            db.query(models.DBSettings).filter(
                models.DBSettings.key.in_(keys),
                models.DBSettings.client_id == None).delete(  # noqa: E711
                    synchronize_session=False)
            db.commit()
    clear()
    main.rate_limiter._hits.clear()
    yield
    clear()


def put(op, **settings):
    res = op.put("/api/superadmin/platform-settings", json={"settings": settings})
    assert res.status_code == 200, res.text
    return res.json()


def screen(op):
    return {r["key"]: r for r in op.get("/api/superadmin/platform-settings").json()["settings"]}


# --- there is a place for it now -------------------------------------------------------

def test_the_screen_has_the_fields(superadmin):
    s = screen(superadmin)
    for key in ("email.smtp_host", "email.smtp_port", "email.smtp_user",
                "email.smtp_password", "email.smtp_starttls", "email.from_address"):
        assert key in s, key
        assert s[key]["group"] == "Email"


def test_the_help_says_what_gmail_needs(superadmin):
    """The thing that was missing was not a field, it was being told. An app
    password is not the normal password, and nobody finds that out by
    guessing."""
    s = screen(superadmin)
    assert "smtp.gmail.com" in s["email.smtp_host"]["help"]
    assert "App Password" in s["email.smtp_password"]["help"]
    assert "2-Step" in s["email.smtp_password"]["help"]
    assert "587" in s["email.smtp_port"]["help"]


def test_what_is_typed_is_what_sends(superadmin):
    put(superadmin, **{
        "email.smtp_host": "smtp.gmail.com", "email.smtp_port": "587",
        "email.smtp_user": "me@gmail.com", "email.smtp_password": "abcd efgh ijkl mnop",
        "email.smtp_starttls": "true"})
    cfg = main.smtp_config()
    assert cfg == {"host": "smtp.gmail.com", "port": 587, "user": "me@gmail.com",
                   "password": "abcd efgh ijkl mnop", "starttls": True}


def test_and_the_environment_still_works_when_nothing_is_set(monkeypatch):
    """An install configured on the hosting provider's variables page keeps
    working. This is a second way in, not a replacement."""
    monkeypatch.setenv("SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("SMTP_USER", "postbox")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2")
    cfg = main.smtp_config()
    assert cfg["host"] == "mail.example.test"
    assert cfg["user"] == "postbox"
    assert cfg["password"] == "hunter2"


def test_the_screen_wins_over_the_environment(superadmin, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "old.example.test")
    put(superadmin, **{"email.smtp_host": "new.example.test"})
    assert main.smtp_config()["host"] == "new.example.test"


# --- the password ----------------------------------------------------------------------

def test_the_password_is_never_sent_back(superadmin):
    put(superadmin, **{"email.smtp_password": "abcd efgh ijkl mnop"})
    s = screen(superadmin)
    assert s["email.smtp_password"]["value"] == ""
    assert s["email.smtp_password"]["is_set"] is True
    assert "abcd efgh" not in superadmin.get("/api/superadmin/platform-settings").text


def test_saving_other_things_does_not_wipe_it(superadmin):
    """The form sends every field back. An empty password box means "keep
    the one that is there", or changing the port would log the server out."""
    put(superadmin, **{"email.smtp_password": "abcd efgh ijkl mnop"})
    put(superadmin, **{"email.smtp_password": "", "email.smtp_port": "465"})
    assert main.smtp_config()["password"] == "abcd efgh ijkl mnop"
    assert main.smtp_config()["port"] == 465


def test_a_new_password_replaces_the_old(superadmin):
    put(superadmin, **{"email.smtp_password": "first"})
    put(superadmin, **{"email.smtp_password": "second"})
    assert main.smtp_config()["password"] == "second"


def test_not_set_says_not_set(superadmin):
    assert screen(superadmin)["email.smtp_password"]["is_set"] is False


# --- readiness follows the screen --------------------------------------------------------

def test_choosing_smtp_with_no_server_is_not_ready(superadmin):
    put(superadmin, **{"email.transport": "smtp"})
    with main.SessionLocal() as db:
        ready, why = main.email_delivery_ready(db)
    assert ready is False
    assert "SMTP" in why


def test_and_with_one_it_is(superadmin):
    put(superadmin, **{"email.transport": "smtp", "email.smtp_host": "smtp.gmail.com",
                       "email.smtp_user": "me@gmail.com", "email.smtp_password": "x"})
    with main.SessionLocal() as db:
        ready, _ = main.email_delivery_ready(db)
    assert ready is True


# --- mail says it is from the account that sends it ---------------------------------------------

def test_under_smtp_the_from_address_is_the_login(superadmin):
    """Gmail sends as the account that authenticated whatever the header says,
    so anything else is a header Google rewrites - or a spam-folder trip."""
    put(superadmin, **{"email.transport": "smtp", "email.smtp_user": "me@gmail.com"})
    assert main.platform_from_address() == "me@gmail.com"


def test_unless_the_operator_chose_one(superadmin):
    put(superadmin, **{"email.transport": "smtp", "email.smtp_user": "me@gmail.com",
                       "email.from_address": "noreply@mycompany.test"})
    assert main.platform_from_address() == "noreply@mycompany.test"


# --- the test button --------------------------------------------------------------------------

def test_a_test_send_says_why_when_it_cannot(superadmin):
    put(superadmin, **{"email.transport": "smtp"})
    res = superadmin.post("/api/superadmin/send-test-email")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] is False
    assert "SMTP" in body["reason"]
    assert body["transport"] == "smtp"


def test_a_test_send_goes_to_the_operator_and_reports_the_result(superadmin, monkeypatch):
    put(superadmin, **{"email.transport": "smtp", "email.smtp_host": "smtp.gmail.com",
                       "email.smtp_user": "me@gmail.com", "email.smtp_password": "x"})
    seen = {}
    def fake(to, subject, body, from_email, *a, **k):
        seen.update(to=to, subject=subject, from_email=from_email)
        return True, "sent"
    monkeypatch.setattr(main, "_send_email_now", fake)
    body = superadmin.post("/api/superadmin/send-test-email").json()
    assert body["sent"] is True
    assert body["to"] == "hello@keyroutes.co"
    assert seen["to"] == "hello@keyroutes.co"
    assert seen["from_email"] == "me@gmail.com"


def test_and_reports_the_exact_failure(superadmin, monkeypatch):
    """The whole point of the button. "It did not work" is what they already
    knew; "535 Username and Password not accepted" is what fixes it."""
    put(superadmin, **{"email.transport": "smtp", "email.smtp_host": "smtp.gmail.com",
                       "email.smtp_user": "me@gmail.com", "email.smtp_password": "wrong"})
    monkeypatch.setattr(main, "_send_email_now",
                        lambda *a, **k: (False, "SMTP error: (535, b'5.7.8 Username and Password not accepted')"))
    body = superadmin.post("/api/superadmin/send-test-email").json()
    assert body["sent"] is False
    assert "535" in body["reason"]


def test_a_test_send_is_recorded_like_any_platform_send(superadmin, monkeypatch):
    put(superadmin, **{"email.transport": "smtp", "email.smtp_host": "h",
                       "email.smtp_user": "u", "email.smtp_password": "p"})
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (False, "refused"))
    superadmin.post("/api/superadmin/send-test-email")
    got = superadmin.get("/api/superadmin/email-failures").json()
    assert any(f["what"] == "Test email from your platform" for f in got["failures"]), got


def test_only_the_operator_can_press_it(client):
    assert client.post("/api/superadmin/send-test-email").status_code in (401, 403)
