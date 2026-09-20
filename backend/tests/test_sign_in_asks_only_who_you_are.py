"""Signing in with Google asks who you are, and nothing else.

It used to ask for permission to send mail too, with the consent screen forced
on every visit. So every sign-in showed "aniprotech wants to send email on
your behalf" behind Google's unverified-app warning, and Google mailed a
"security alert: aniprotech was granted access" each time. Sending is a
separate act, granted once from Settings, and that is the only place the
mail permission is asked for.
"""
import pytest

import main


@pytest.fixture
def google(monkeypatch):
    asked = {}

    async def fake_redirect(request, redirect_uri, **kw):
        asked.clear()
        asked.update(kw)
        asked["redirect_uri"] = redirect_uri
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="https://accounts.google.example/stub")

    monkeypatch.setattr(main.oauth.google, "authorize_redirect", fake_redirect)
    return asked


def test_sign_in_asks_for_identity_only_and_forces_no_consent(client, google):
    r = client.get("/api/auth/login?portal=invoicing", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert google["scope"] == "openid email profile"
    assert "gmail" not in google["scope"]
    assert google.get("prompt") != "consent"
    assert google.get("access_type") != "offline"


def test_the_superadmin_and_the_employee_doors_are_the_same(client, google):
    for query in ("?role=superadmin", "?portal=employee", ""):
        client.get("/api/auth/login" + query, follow_redirects=False)
        assert google["scope"] == "openid email profile" and google.get("prompt") != "consent", query


def test_connecting_an_account_to_send_from_is_where_the_mail_permission_is_asked(tenant, google):
    tenant.get("/api/gmail/connect", follow_redirects=False)
    # The registered scope carries gmail.send; the connect flow does not
    # narrow it, and it does force consent so a refresh token comes back.
    assert "scope" not in google or "gmail.send" in google["scope"]
    assert google.get("prompt") == "consent" and google.get("access_type") == "offline"
    assert "https://www.googleapis.com/auth/gmail.send" in main.oauth.google.client_kwargs["scope"]


def test_the_sign_in_callback_keeps_no_google_tokens(client, monkeypatch):
    """Even if Google handed tokens back, the session keeps who they are and
    not what could be done as them."""
    async def fake_token(request):
        return {"userinfo": {"email": "someone@example.com", "name": "Some One"},
                "access_token": "at-123", "refresh_token": "rt-123"}
    monkeypatch.setattr(main.oauth.google, "authorize_access_token", fake_token)
    r = client.get("/api/auth/callback?code=x&state=y", follow_redirects=False)
    assert r.status_code in (302, 307), r.text
    me = client.get("/api/auth/me").json()
    assert me["user"]["email"] == "someone@example.com"
    with main.SessionLocal() as db:
        saved = db.query(main.models.DBSettings).filter(
            main.models.DBSettings.key == "GOOGLE_REFRESH_TOKEN",
            main.models.DBSettings.value == "rt-123").count()
    assert saved == 0, "a sign-in filed a send token against the account"
