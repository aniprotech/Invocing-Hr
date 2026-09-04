"""The operator's own way to set the platform up to send.

Every code the product sends itself - a signup code, an operator's sign-in
code, a password reset - leaves on the platform transport. That transport
defaults to Gmail, which needs a refresh token filed against no tenant at all,
and nothing in the product could write one: the tenant connect flow files it
against the tenant, so does the sign-in callback, and this screen did not
exist. So unless somebody set SMTP variables in the environment, the platform
could send to nobody and every OTP failed the quietest way available.

The token this writes is platform-wide - it is the account every tenant's mail
goes out through until they connect their own - so most of what is here is
about who is allowed to write it.
"""
import uuid

import pytest

import main
import models


@pytest.fixture
def superadmin():
    """The operator, on a session of their own - a tenant signing in on the
    same cookie starts a fresh session and would evict this one."""
    from fastapi.testclient import TestClient
    main.rate_limiter._hits.clear()
    with TestClient(main.app) as operator:
        res = operator.post("/api/superadmin/login", json={
            "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
        assert res.status_code == 200, res.text
        yield operator


@pytest.fixture
def google(monkeypatch):
    """The round trip to Google, with both ends replaced."""
    state = {"refresh_token": "platform-refresh", "email": "ops@aniprotech.com",
             "refuses": False, "asked_for": {}, "redirect_uri": ""}

    async def fake_redirect(request, redirect_uri, **kw):
        state["redirect_uri"] = redirect_uri
        state["asked_for"] = kw
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="https://accounts.google.example/stub")

    async def fake_token(request):
        if state["refuses"]:
            raise RuntimeError("no")
        out = {"userinfo": {"email": state["email"]}}
        if state["refresh_token"]:
            out["refresh_token"] = state["refresh_token"]
        return out

    monkeypatch.setattr(main.oauth.google, "authorize_redirect", fake_redirect)
    monkeypatch.setattr(main.oauth.google, "authorize_access_token", fake_token)
    # Reading the connected address calls Google; nothing here is about that.
    monkeypatch.setattr(main, "build", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("no network in tests")))
    return state


@pytest.fixture(autouse=True)
def _no_platform_token():
    """Start with nothing connected, and leave nothing behind."""
    def clear():
        with main.SessionLocal() as db:
            # Every one, not only the platform's. Where there is no platform
            # token, get_stored_refresh_token falls back to any it can find -
            # so a token another file left on a tenant makes the platform look
            # ready here, and these tests pass alone and fail in a full run.
            db.query(models.DBSettings).filter(
                models.DBSettings.key == "GOOGLE_REFRESH_TOKEN").delete()
            db.commit()
    clear()
    yield
    clear()


def platform_token():
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "GOOGLE_REFRESH_TOKEN",
            models.DBSettings.client_id == None).first()           # noqa: E711
        return row.value if row else None


def connect(operator):
    started = operator.get("/api/superadmin/gmail/connect", follow_redirects=False)
    assert started.status_code in (302, 307), started.text
    return operator.get("/api/superadmin/gmail/callback", follow_redirects=False)


def outcome(res):
    where = res.headers.get("location", "")
    assert "email=" in where, where
    return where.split("email=")[1].split("&")[0]


# --- who may write a platform-wide credential -------------------------------------

def test_a_stranger_cannot_see_how_the_platform_sends(client):
    assert client.get("/api/superadmin/email-status").status_code in (401, 403)


def test_a_tenant_cannot_either(tenant):
    """Signed in, but not as the operator."""
    assert tenant.get("/api/superadmin/email-status").status_code in (401, 403)


def test_a_stranger_cannot_start_a_connection(client):
    assert client.get("/api/superadmin/gmail/connect",
                      follow_redirects=False).status_code in (401, 403)


def test_a_tenant_cannot_start_one(tenant):
    assert tenant.get("/api/superadmin/gmail/connect",
                      follow_redirects=False).status_code in (401, 403)


def test_the_marker_alone_is_not_enough_to_finish_one(superadmin, google):
    """The session has to still be an operator's when the callback lands.

    Signing out pops superadmin_id and leaves everything else on the session,
    so a browser that started a connection and then signed out still carries
    the marker. Without asking who the session belongs to as well, that
    browser could file the Google account every tenant's mail goes out
    through - as nobody in particular.
    """
    started = superadmin.get("/api/superadmin/gmail/connect", follow_redirects=False)
    assert started.status_code in (302, 307)

    assert superadmin.post("/api/superadmin/logout").status_code == 200
    assert superadmin.get("/api/superadmin/email-status").status_code in (401, 403),         "the operator session should be gone"

    res = superadmin.get("/api/superadmin/gmail/callback", follow_redirects=False)
    assert res.status_code in (401, 403), res.status_code
    assert platform_token() is None


def test_a_tenant_cannot_finish_one_either(superadmin, tenant, google):
    """A different browser entirely, carrying no marker and no operator."""
    superadmin.get("/api/superadmin/gmail/connect", follow_redirects=False)
    res = tenant.get("/api/superadmin/gmail/callback", follow_redirects=False)
    assert res.status_code in (401, 403), res.status_code
    assert platform_token() is None


def test_a_callback_nobody_started_is_refused(superadmin, google):
    """Even as the operator: without a start there is nothing to finish."""
    assert outcome(superadmin.get("/api/superadmin/gmail/callback",
                                  follow_redirects=False)) == "notlinked"
    assert platform_token() is None


def test_a_stranger_cannot_disconnect(client):
    assert client.post("/api/superadmin/gmail/disconnect").status_code in (401, 403)


# --- connecting ---------------------------------------------------------------------

def test_the_operator_connects_the_platform_not_a_tenant(superadmin, google):
    assert outcome(connect(superadmin)) == "connected"
    assert platform_token() == "platform-refresh"

    # Filed against no tenant at all, which is the whole point - a token on a
    # tenant row is that tenant's, and the platform cannot use it as its own.
    with main.SessionLocal() as db:
        rows = db.query(models.DBSettings).filter(
            models.DBSettings.key == "GOOGLE_REFRESH_TOKEN").all()
        assert [r.client_id for r in rows] == [None], [r.client_id for r in rows]


def test_connecting_is_also_choosing_to_send_that_way(superadmin, google):
    connect(superadmin)
    with main.SessionLocal() as db:
        assert main.email_transport(db) == "gmail"


def test_it_asks_for_access_that_outlives_the_visit(superadmin, google):
    connect(superadmin)
    assert google["asked_for"].get("access_type") == "offline"
    assert google["asked_for"].get("prompt") == "consent"


def test_google_comes_back_to_the_operator_route(superadmin, google):
    connect(superadmin)
    assert google["redirect_uri"].endswith("/api/superadmin/gmail/callback"), \
        google["redirect_uri"]


def test_connecting_again_replaces_the_token(superadmin, google):
    connect(superadmin)
    google["refresh_token"] = "second-platform-refresh"
    connect(superadmin)
    assert platform_token() == "second-platform-refresh"


def test_access_that_will_not_last_is_a_failure(superadmin, google):
    google["refresh_token"] = None
    assert outcome(connect(superadmin)) == "norefresh"
    assert platform_token() is None


def test_a_refusal_at_google_changes_nothing(superadmin, google):
    google["refuses"] = True
    assert outcome(connect(superadmin)) == "failed"
    assert platform_token() is None


def test_the_callback_cannot_be_replayed(superadmin, google):
    connect(superadmin)
    google["refresh_token"] = "replayed"
    again = superadmin.get("/api/superadmin/gmail/callback", follow_redirects=False)
    assert outcome(again) == "notlinked"
    assert platform_token() == "platform-refresh"


# --- what the screen says -------------------------------------------------------------

def test_it_says_plainly_when_nothing_can_be_sent(superadmin, monkeypatch):
    """The answer to "why did no code arrive" lived nowhere before this."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with main.SessionLocal() as db:
        main.set_platform_setting(db, "email.transport", "gmail")
        db.commit()

    d = superadmin.get("/api/superadmin/email-status").json()
    assert d["can_send"] is False
    assert d["blocked_reason"], d
    assert d["google_connected"] is False


def test_and_says_so_once_something_is_connected(superadmin, google):
    connect(superadmin)
    d = superadmin.get("/api/superadmin/email-status").json()
    assert d["can_send"] is True
    assert d["google_connected"] is True
    assert d["transport"] == "gmail"


def test_a_stored_token_that_no_longer_works_is_not_called_working(
        superadmin, google):
    """A dead token looks exactly like a live one until somebody needs a code.

    The google fixture makes the call to Google raise, which is what a revoked
    authorisation does.
    """
    connect(superadmin)
    d = superadmin.get("/api/superadmin/email-status").json()
    assert d["google_connected"] is True
    assert d["google_works"] is False
    assert d["connected_as"] == ""


def test_the_status_never_hands_back_the_token(superadmin, google):
    """It is read by a web page. A credential that can be read out of one is a
    credential that leaves with it."""
    connect(superadmin)
    body = superadmin.get("/api/superadmin/email-status").text
    assert "platform-refresh" not in body, body


# --- disconnecting ----------------------------------------------------------------------

def test_disconnecting_removes_it(superadmin, google):
    connect(superadmin)
    res = superadmin.post("/api/superadmin/gmail/disconnect")
    assert res.status_code == 200, res.text
    assert platform_token() is None


def test_and_says_out_loud_that_nothing_can_be_sent_now(superadmin, google,
                                                        monkeypatch):
    """A button marked Disconnect does not convey "every code in the product
    stops working"."""
    monkeypatch.delenv("SMTP_HOST", raising=False)
    connect(superadmin)
    body = superadmin.post("/api/superadmin/gmail/disconnect").json()
    assert body["can_send"] is False
    assert "no longer send" in body["message"].lower(), body["message"]
