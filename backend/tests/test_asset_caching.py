"""A stale script is indistinguishable from the app reverting.

Pages carried no-store already, but app.js and styles.css carried no cache
policy at all, so each browser applied its own guess. That is how a fixed
header can keep coming back looking like old code.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def cache_header(client, path):
    return client.get(path).headers.get("cache-control", "")


def test_pages_are_never_stored(client):
    """The page names the asset versions, so a cached page pins old scripts."""
    for path in ("/app.html", "/hr.html", "/"):
        assert "no-store" in cache_header(client, path), path


def test_a_versioned_script_can_be_kept_forever(client):
    """The ?v= changes whenever the file does, so the old URL is never asked
    for again and the new one is never served from cache."""
    header = cache_header(client, "/app.js?v=99")
    assert "immutable" in header
    assert "max-age=31536000" in header


def test_a_versioned_stylesheet_too(client):
    assert "immutable" in cache_header(client, "/styles.css?v=99")


def test_an_unversioned_script_is_always_revalidated(client):
    """Without a version there is nothing to tell a browser the file changed,
    so it has to ask every time rather than guess."""
    header = cache_header(client, "/app.js")
    assert "no-cache" in header
    assert "immutable" not in header


def test_an_unversioned_stylesheet_too(client):
    assert "no-cache" in cache_header(client, "/styles.css")
