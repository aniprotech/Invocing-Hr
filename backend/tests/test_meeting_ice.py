"""What the browser is told about reaching the other side of a call.

STUN alone only finds a path when both ends are directly reachable. Behind
symmetric NAT, a corporate firewall, or some mobile carriers it cannot - and
the failure is the worst kind available: the call looks connected, the tile
appears, and no audio or video ever arrives. Our users are office staff, which
is precisely the population sitting behind restrictive firewalls.

So the relay has to be configurable, its credentials must not be baked into a
static page anyone can read, and the app has to know whether one exists so it
can say something useful when a connection fails.
"""
import importlib
import os

import pytest

import main


@pytest.fixture
def relay(monkeypatch):
    monkeypatch.setenv("TURN_URLS", "turn:relay.example.com:3478,turns:relay.example.com:5349")
    monkeypatch.setenv("TURN_USERNAME", "demo")
    monkeypatch.setenv("TURN_PASSWORD", "s3cret")
    yield


@pytest.fixture
def no_relay(monkeypatch):
    for key in ("TURN_URLS", "TURN_USERNAME", "TURN_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    yield


def test_stun_is_always_offered(client, no_relay):
    """With nothing configured the call still works for everyone whose
    network allows a direct path. It just cannot rescue those it does not."""
    body = client.get("/api/meet/ice").json()
    urls = [u for s in body["iceServers"] for u in s["urls"]]
    assert any(u.startswith("stun:") for u in urls)
    assert body["relay_configured"] is False


def test_a_configured_relay_is_passed_through(client, relay):
    body = client.get("/api/meet/ice").json()
    turn = [s for s in body["iceServers"] if any(u.startswith(("turn:", "turns:"))
                                                 for u in s["urls"])]
    assert turn, body
    assert turn[0]["username"] == "demo"
    assert turn[0]["credential"] == "s3cret"
    assert body["relay_configured"] is True


def test_several_relay_urls_are_kept(client, relay):
    """A TLS one alongside the plain one is how you get through a firewall
    that only lets 443 out."""
    body = client.get("/api/meet/ice").json()
    urls = [u for s in body["iceServers"] for u in s["urls"]]
    assert "turn:relay.example.com:3478" in urls
    assert "turns:relay.example.com:5349" in urls


def test_a_half_configured_relay_is_not_offered(client, monkeypatch):
    """A URL with no credentials cannot authenticate, and offering it would
    make the app claim a relay it has not got - so failures would be reported
    as a network problem rather than as the missing configuration they are."""
    monkeypatch.setenv("TURN_URLS", "turn:relay.example.com:3478")
    monkeypatch.delenv("TURN_USERNAME", raising=False)
    monkeypatch.delenv("TURN_PASSWORD", raising=False)

    body = client.get("/api/meet/ice").json()
    assert body["relay_configured"] is False
    urls = [u for s in body["iceServers"] for u in s["urls"]]
    assert not any(u.startswith(("turn:", "turns:")) for u in urls)


def test_the_page_does_not_carry_the_credentials(no_relay):
    """The whole reason this is an endpoint. A password in a static file is
    readable by anyone who opens the page, and rotating it is a deploy."""
    with open("../frontend/meeting.html", encoding="utf-8") as f:
        page = f.read()
    assert "TURN_PASSWORD" not in page
    assert "credential" not in page.lower().replace("credentials", "")
