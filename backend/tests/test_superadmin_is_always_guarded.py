"""Every operator endpoint must refuse a stranger.

A superadmin route reaches across every tenant at once, so one route that
forgets its check is not a leak of one account's data but of all of them.
The guard used to be three lines pasted into each handler, which is exactly
the kind of thing that gets left out of the thirty-fifth one.

This sweeps the routes themselves rather than a list someone has to remember
to update, so a new /api/superadmin/... endpoint is covered the moment it is
written, and fails here if it is not guarded.
"""
import pytest

import main

SAFE_WITHOUT_A_SESSION = {
    # These are how a session is obtained or discarded in the first place.
    "/api/superadmin/login",
    "/api/superadmin/logout",
}


def superadmin_routes():
    found = []
    for route in main.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/superadmin"):
            continue
        if path in SAFE_WITHOUT_A_SESSION:
            continue
        for method in (getattr(route, "methods", None) or set()):
            if method in ("HEAD", "OPTIONS"):
                continue
            found.append((method, path))
    return sorted(set(found))


ROUTES = superadmin_routes()


def test_there_are_operator_routes_to_sweep():
    """Guards the sweep itself: if the filter stopped matching, every test
    below would pass while checking nothing."""
    assert len(ROUTES) > 25, ROUTES


@pytest.mark.parametrize("method,path", ROUTES)
def test_a_stranger_is_refused(client, method, path):
    """No session at all: the answer must be 401, not data and not a crash."""
    res = client.request(method, _fill(path))
    assert res.status_code == 401, (
        f"{method} {path} -> {res.status_code} for a signed-out stranger. "
        f"Call require_superadmin(request) in the handler. Body: {res.text[:300]}"
    )


@pytest.mark.parametrize("method,path", ROUTES)
def test_a_signed_in_tenant_is_not_an_operator(tenant, method, path):
    """A perfectly valid client session is still not an operator session.
    This is the one that catches a guard checking merely 'is logged in'."""
    res = tenant.request(method, _fill(path))
    assert res.status_code == 401, (
        f"{method} {path} -> {res.status_code} for an ordinary tenant. "
        f"A client session must never reach an operator endpoint. "
        f"Body: {res.text[:300]}"
    )


def _fill(path):
    """Path params get a plausible id. The guard runs before the handler
    looks anything up, so the row need not exist - a 404 here would mean
    the request got past the gate, which is what we are testing for."""
    out = []
    for part in path.split("/"):
        out.append("1" if part.startswith("{") and part.endswith("}") else part)
    return "/".join(out)
