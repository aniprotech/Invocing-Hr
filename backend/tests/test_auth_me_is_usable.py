"""Being signed in is not the same as being able to use the app.

Seen in production: the dashboard rendered, the invoice form filled itself
in, and every save came back "Failed: Not logged in" while the person was
plainly looking at their own account.

The cause is that two different questions were being answered as one.
session['user'] is set for anyone who completes Google sign-in - a superadmin
and a member of staff included - but every endpoint that touches tenant data
resolves the tenant through session['client_id']. A session holding the first
and not the second got past the gate on app.html and then failed everything
behind it.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def test_a_client_session_can_use_the_app(tenant):
    body = tenant.get("/api/auth/me").json()
    assert body["user"]["email"]
    assert body["client_id"], "a signed-in business must carry its tenant id"


def test_a_stranger_is_refused(client):
    assert client.get("/api/auth/me").status_code == 401


def test_a_google_identity_alone_does_not_claim_a_tenant(client):
    """The exact shape that broke. A user in the session with no client_id
    must not report one, because the caller uses it to decide whether the
    app is usable at all."""
    with client as c:
        # Stand in for the state the OAuth callback leaves when it hands off
        # to the superadmin or employee portal: a user, and no client.
        res = c.post("/api/superadmin/login", json={
            "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
        assert res.status_code == 200, res.text

        body = c.get("/api/auth/me")
        # Either refused outright, or admitted with no tenant - never a
        # tenant it does not have.
        if body.status_code == 200:
            assert not body.json().get("client_id")


def test_the_app_endpoints_agree_with_the_gate(tenant):
    """Whatever /api/auth/me says is usable, an actual data call must accept.
    These two drifting apart is the whole bug."""
    me = tenant.get("/api/auth/me").json()
    assert me.get("client_id")
    # A representative tenant-scoped endpoint.
    assert tenant.get("/api/invoices").status_code == 200


def test_a_session_without_a_tenant_is_refused_by_the_data_endpoints(client):
    """The other half of the pair: no client_id means no data, which is what
    the gate now checks for rather than discovering on the first save."""
    assert client.get("/api/invoices").status_code == 401
