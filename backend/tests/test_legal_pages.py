"""The privacy policy and terms, at addresses that cannot move.

Google records the privacy policy URL when an app is verified and rechecks it
afterwards. The operator-managed policies live at /policy.html?id=N, which is
right for anything the operator adds and wrong for this one: the address is
built from a database row id, so deleting and re-adding the policy - which
happens while it is being drafted - changes it. The old URL then 404s and
verification fails weeks later with nothing to point at.

So these two are files in the repository at fixed paths, and most of what is
checked here is that they stay reachable, stay public, and keep saying the
things Google's review actually looks for.
"""
import pathlib

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parents[2] / "frontend"


@pytest.mark.parametrize("path", ["/privacy", "/terms"])
def test_a_stranger_can_read_them(client, path):
    """Behind a login they are no use to anybody, least of all a reviewer."""
    res = client.get(path)
    assert res.status_code == 200, res.status_code
    assert "text/html" in res.headers.get("content-type", "")


@pytest.mark.parametrize("path", ["/privacy", "/terms"])
def test_they_do_not_start_a_session(client, path):
    """A public page that sets a cookie is a public page that tracks people."""
    res = client.get(path)
    assert "set-cookie" not in {k.lower() for k in res.headers}, dict(res.headers)


def test_the_address_does_not_depend_on_a_database_row(client):
    """The whole reason these are not operator-managed items. Nothing about
    the URL may come from a row that can be deleted."""
    res = client.get("/privacy")
    assert res.status_code == 200
    # Reachable with an empty database and no operator having done anything.
    assert "Privacy Policy" in res.text


# --- what Google's review looks for ---------------------------------------------

def test_the_privacy_policy_carries_the_limited_use_words(client):
    """Sensitive scopes are reviewed against this. Without the sentence, in
    close to these words, the app is rejected."""
    text = client.get("/privacy").text
    assert "Google API Services User Data Policy" in text
    assert "Limited Use" in text


def test_it_names_the_google_permissions_and_what_each_is_for(client):
    """A reviewer checks the policy describes the scopes actually requested."""
    text = client.get("/privacy").text
    assert "gmail.send" in text
    for word in ("openid", "email", "profile"):
        assert word in text


def test_it_says_plainly_that_mail_is_never_read(client):
    """The single question a reviewer has about a Gmail scope."""
    text = client.get("/privacy").text.lower()
    assert "cannot read your email" in text or "only allows sending" in text


def test_it_rules_out_the_uses_google_asks_about(client):
    """Advertising, sale, human reading and model training - the four the
    Limited Use policy names. Matched on the commitment rather than one exact
    sentence, since the same promise is worded differently in each case."""
    text = client.get("/privacy").text.lower()
    for what, promise in (
        ("advertising", "not used for advertising"),
        ("selling it", "not sold"),
        ("people reading it", "not read by any person"),
        ("training a model", "used to train any machine learning"),
    ):
        assert promise in text, f"nothing rules out {what}"


def test_it_says_how_to_take_the_access_back(client):
    text = client.get("/privacy").text
    assert "myaccount.google.com/permissions" in text


# --- the ordinary things a privacy policy has to have -----------------------------

def test_it_says_what_is_stored_and_who_it_reaches(client):
    text = client.get("/privacy").text
    for third_party in ("Railway", "Groq", "Stripe", "Razorpay", "GoCardless"):
        assert third_party in text, third_party


def test_it_says_there_is_no_tracking(client):
    """True of this app - there is no analytics or advertising script on any
    page - and worth stating, because it is the first thing people assume."""
    text = client.get("/privacy").text.lower()
    assert "no advertising, tracking or analytics" in text


def test_no_page_actually_loads_a_tracker(client):
    """The claim above has to keep being true. A tag added to any page would
    turn a plain statement into a false one."""
    trackers = ("google-analytics.com", "googletagmanager.com", "gtag(",
                "connect.facebook.net", "hotjar", "mixpanel", "segment.com")
    for page in FRONTEND.glob("*.html"):
        body = page.read_text(encoding="utf-8", errors="ignore").lower()
        for tracker in trackers:
            assert tracker not in body, f"{page.name} loads {tracker}"


def test_the_two_link_to_each_other(client):
    assert "/terms" in client.get("/privacy").text
    assert "/privacy" in client.get("/terms").text


def test_the_front_page_links_to_both(client):
    """Google checks the homepage for a link to the policy."""
    home = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert 'href="/privacy"' in home
    assert 'href="/terms"' in home


# --- the parts only the operator can fill in ----------------------------------------

@pytest.mark.parametrize("path", ["/privacy", "/terms"])
def test_the_gaps_are_marked_rather_than_invented(client, path):
    """A registered company name, a postal address, a retention period and a
    governing law are facts about the business, not about the code. Guessing
    them would put false statements in a legal document, so they are left as
    marked gaps that are impossible to miss.

    This test is expected to be deleted once they are filled in.
    """
    text = client.get(path).text
    assert "Before publishing" in text, (
        f"{path} no longer marks its gaps - if they are filled in, delete this test")
