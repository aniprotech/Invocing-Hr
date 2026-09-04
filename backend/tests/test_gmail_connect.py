"""Connecting a Google account to send from, without signing in as it.

The only way to do this was the sign-in route, and for anybody who signed up
with an email and a password that was worse than useless. If their Google
address differed from the one they signed up with - uday@company.com against
uday@gmail.com - the callback found no account with that address, made a brand
new empty one, moved their session into it, and filed the token there. They
were left in an account with none of their invoices, and their real account
still could not send.

So the test that matters is the mismatch: a different address must link to the
account already signed in, and must not create anything.
"""
import uuid

import pytest

import main
import models


@pytest.fixture
def google(monkeypatch):
    """Stand in for the round trip out to Google.

    Authlib would send a browser to Google and read the code it comes back
    with. Neither half can happen in a test, so both ends are replaced and the
    routes are left to do their own work in between.
    """
    state = {"refresh_token": "refresh-abc", "email": "someone.else@gmail.com",
             "refuses": False, "asked_for": {}, "redirect_uri": ""}

    async def fake_redirect(request, redirect_uri, **kw):
        state["redirect_uri"] = redirect_uri
        state["asked_for"] = kw
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="https://accounts.google.example/stub")

    async def fake_token(request):
        if state["refuses"]:
            raise RuntimeError("the person said no")
        out = {"userinfo": {"email": state["email"]}}
        if state["refresh_token"]:
            out["refresh_token"] = state["refresh_token"]
        return out

    monkeypatch.setattr(main.oauth.google, "authorize_redirect", fake_redirect)
    monkeypatch.setattr(main.oauth.google, "authorize_access_token", fake_token)
    return state


@pytest.fixture
def dns(monkeypatch):
    """Resolution without the network, so a test does not fail on a train."""
    import socket

    def fake_getaddrinfo(host, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def whose_session(tenant):
    return tenant.get("/api/client/me").json()["id"]


def accounts_called(email):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            main.sqlfunc.lower(models.DBClient.email) == email.lower()).count()


def token_held_by(client_id):
    with main.SessionLocal() as db:
        row = db.query(models.DBSettings).filter(
            models.DBSettings.key == "GOOGLE_REFRESH_TOKEN",
            models.DBSettings.client_id == client_id).first()
        return row.value if row else None


def connect(tenant):
    """Start the link and come back from Google, the way a browser would."""
    started = tenant.get("/api/gmail/connect", follow_redirects=False)
    assert started.status_code in (302, 307), started.text
    return tenant.get("/api/gmail/connect/callback", follow_redirects=False)


def outcome(res):
    """The word the settings page is told to report."""
    where = res.headers.get("location", "")
    assert "gmail=" in where, where
    return where.split("gmail=")[1].split("&")[0]


# --- the thing that was broken -------------------------------------------------

def test_a_different_google_address_links_rather_than_making_an_account(
        tenant, google):
    mine = whose_session(tenant)
    google["email"] = f"quite.different-{uuid.uuid4().hex[:6]}@gmail.com"
    before = accounts_called(google["email"])

    res = connect(tenant)

    assert outcome(res) == "connected"
    assert accounts_called(google["email"]) == before, \
        "it made an account out of the Google address"
    assert token_held_by(mine) == "refresh-abc", \
        "the token did not reach the account that asked for it"


def test_it_leaves_you_in_the_account_you_were_already_in(tenant, google):
    mine = whose_session(tenant)
    google["email"] = f"other-{uuid.uuid4().hex[:6]}@gmail.com"
    connect(tenant)
    assert whose_session(tenant) == mine, "it moved the session somewhere else"


def test_one_account_linking_does_not_disturb_another(client, google):
    """Two businesses, two Google accounts, one settings table."""
    def sign_up():
        email = f"user-{uuid.uuid4().hex[:10]}@example.com"
        assert client.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest",
            "company_name": "Acme Ltd"}).status_code == 200
        assert client.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"}).status_code == 200
        return client.get("/api/client/me").json()["id"]

    first = sign_up()
    connect(client)
    second = sign_up()
    google["refresh_token"] = "refresh-for-the-second"
    connect(client)

    assert first != second
    assert token_held_by(first) == "refresh-abc", "the first one's token moved"
    assert token_held_by(second) == "refresh-for-the-second"


def test_connecting_it_is_also_choosing_to_send_through_it(tenant, google):
    connect(tenant)
    assert tenant.get("/api/email-settings").json()["transport"] == "gmail"


def test_connecting_again_replaces_the_token(tenant, google):
    mine = whose_session(tenant)
    connect(tenant)
    google["refresh_token"] = "refresh-second"
    connect(tenant)
    assert token_held_by(mine) == "refresh-second"


def test_it_asks_google_for_access_that_outlives_the_visit(tenant, google):
    """Without offline access and forced consent, Google sends no refresh
    token on a repeat connection, and sending stops the moment the browser's
    own token expires."""
    connect(tenant)
    assert google["asked_for"].get("access_type") == "offline"
    assert google["asked_for"].get("prompt") == "consent"


def test_google_is_sent_back_to_the_linking_route_not_the_sign_in_one(
        tenant, google):
    connect(tenant)
    assert google["redirect_uri"].endswith("/api/gmail/connect/callback"), \
        google["redirect_uri"]


# --- when it does not work -----------------------------------------------------

def test_access_that_does_not_last_is_a_failure_not_a_success(tenant, google):
    """Without a refresh token nothing can be sent later, so calling it
    connected is a lie somebody finds out about at the worst moment."""
    mine = whose_session(tenant)
    google["refresh_token"] = None
    assert outcome(connect(tenant)) == "norefresh"
    assert token_held_by(mine) is None


def test_a_refusal_at_google_changes_nothing(tenant, google):
    mine = whose_session(tenant)
    google["refuses"] = True
    assert outcome(connect(tenant)) == "failed"
    assert token_held_by(mine) is None


def test_a_failed_link_does_not_switch_sending_over_to_gmail(tenant, google, dns):
    """Turning the transport over to an account that cannot send would stop
    the mail that was leaving perfectly well before."""
    assert tenant.put("/api/email-settings", json={
        "transport": "smtp", "smtp_host": "mail.example.com",
        "smtp_port": 587, "smtp_user": "u", "smtp_password": "p",
        "from_email": "billing@example.com"}).status_code == 200

    google["refresh_token"] = None
    connect(tenant)
    assert tenant.get("/api/email-settings").json()["transport"] == "smtp"


# --- who is allowed to ---------------------------------------------------------

def test_starting_it_needs_somebody_signed_in(client):
    assert client.get("/api/gmail/connect",
                      follow_redirects=False).status_code in (401, 403)


def test_a_callback_nobody_started_is_refused(client, google):
    """Arriving cold, there is no answer to whose account this would be - and
    guessing it from the Google address is the bug itself."""
    assert outcome(client.get("/api/gmail/connect/callback",
                              follow_redirects=False)) == "notlinked"


def test_the_callback_cannot_be_replayed(tenant, google):
    """A second visit with no fresh start must not link again."""
    connect(tenant)
    mine = whose_session(tenant)
    google["refresh_token"] = "refresh-replayed"
    again = tenant.get("/api/gmail/connect/callback", follow_redirects=False)
    assert outcome(again) == "notlinked"
    assert token_held_by(mine) == "refresh-abc"
