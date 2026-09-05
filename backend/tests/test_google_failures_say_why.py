"""When Google refuses, say which refusal it was.

Every failure arrived as "Google authentication failed. Please try again."
and trying again fixes none of them - a redirect URI that is not registered,
a client id that does not match the project, a scope the consent screen does
not declare. The reason existed only in the server log, so anybody who was
not reading the log had nothing to work with at all.

Google's own codes are public and say what is misconfigured rather than who
by, so they travel with the redirect. The exception text does not: it can
carry the client id and the request parameters, and those have no business in
a URL.
"""
import pytest

import main


@pytest.fixture
def google_refuses(monkeypatch):
    """Make the token exchange fail with whatever Google would have said."""
    said = {"text": "boom"}

    async def refuse(request):
        raise RuntimeError(said["text"])

    monkeypatch.setattr(main.oauth.google, "authorize_access_token", refuse)
    return said


def where(res):
    return res.headers.get("location", "")


@pytest.mark.parametrize("said,code", [
    ("Error: redirect_uri_mismatch", "redirect_uri_mismatch"),
    ("invalid_client: Unauthorized", "invalid_client"),
    ("access_denied", "access_denied"),
    ("invalid_scope: bad scope", "invalid_scope"),
    ("unauthorized_client", "unauthorized_client"),
    ("admin_policy_enforced", "admin_policy_enforced"),
    ("org_internal", "org_internal"),
    ("invalid_grant: code already redeemed", "invalid_grant"),
])
def test_the_reason_travels_with_the_failure(client, google_refuses, said, code):
    google_refuses["text"] = said
    res = client.get("/api/auth/callback", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert f"why={code}" in where(res), where(res)


def test_something_unrecognised_is_not_guessed_at(client, google_refuses):
    google_refuses["text"] = "the datacentre fell over"
    assert "why=unknown" in where(
        client.get("/api/auth/callback", follow_redirects=False))


def test_it_still_lands_on_the_sign_in_page(client, google_refuses):
    """The reason is extra. Somebody still has to end up somewhere they can
    try again from."""
    got = where(client.get("/api/auth/callback", follow_redirects=False))
    assert got.startswith("/login.html?error=auth_failed"), got


def test_the_exception_itself_is_never_passed_on(client, google_refuses):
    """It can carry the client id and the request parameters, and a URL is
    read by browsers, proxies and anything keeping history."""
    google_refuses["text"] = (
        "invalid_client: no client 8675309-secret.apps.googleusercontent.com "
        "with code 4/0AY0e-g7 and state abc123")
    got = where(client.get("/api/auth/callback", follow_redirects=False))
    assert got == "/login.html?error=auth_failed&why=invalid_client", got
    for leak in ("8675309", "googleusercontent", "4/0AY0e-g7", "abc123"):
        assert leak not in got, f"{leak!r} reached the URL: {got}"


def test_every_code_is_one_the_page_can_say_something_about(client):
    """A code the sign-in page does not recognise falls back to the wording
    that was there before, which is the thing this exists to replace."""
    import pathlib
    page = (pathlib.Path(__file__).resolve().parents[2]
            / "frontend" / "login.html").read_text(encoding="utf-8")
    for code in main.GOOGLE_FAILURES:
        assert code in page, f"{code} has no message on the sign-in page"
