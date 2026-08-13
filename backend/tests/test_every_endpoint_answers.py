"""No signed-in page should ever hand back a 500.

Individual features have their own tests, but nothing swept the whole surface,
so an endpoint could rot for weeks - a renamed column, a field the model never
had - and only a user would find out. This walks every GET route that needs no
path parameter and insists it answers. A fresh account is the harshest case:
every list is empty, so anything that divides by a count or reads [0] falls
over here first.
"""
import pytest

import main


def parameterless_get_routes():
    seen = set()
    for route in main.app.routes:
        path = getattr(route, "path", "")
        if "GET" not in (getattr(route, "methods", None) or set()):
            continue
        if "{" in path or not path.startswith("/api"):
            continue
        seen.add(path)
    return sorted(seen)


ROUTES = parameterless_get_routes()


def test_there_are_routes_to_sweep():
    """Guards the sweep itself: a filter that matches nothing would make every
    test below pass without checking anything."""
    assert len(ROUTES) > 50, ROUTES


@pytest.mark.parametrize("path", ROUTES)
def test_a_signed_in_account_gets_an_answer(tenant, path):
    res = tenant.get(path)
    assert res.status_code < 500, f"GET {path} -> {res.status_code}: {res.text[:400]}"


@pytest.mark.parametrize("path", ROUTES)
def test_a_stranger_is_turned_away_not_crashed(client, path):
    """Signed out, the answer must be a refusal, not a traceback - reading the
    session of somebody who has none is where these break."""
    res = client.get(path)
    assert res.status_code < 500, f"GET {path} -> {res.status_code}: {res.text[:400]}"
