"""The test-email button, which anybody on the internet could press.

/api/send-test-email took a recipient, a subject and a body and sent them.
There was no get_client_user, no require_superadmin, no dependency of any
kind - and no auth middleware behind it either, since security_middleware
only sets headers. It then sent through the platform's own Gmail account,
because send_email_background falls back to that when client_id is None.

So: an unauthenticated open relay, on the public internet, wearing our own
sending identity, on a domain going through Google verification. Anything sent
through it would have been sent by us, and the bill for that is the sending
reputation of the address every tenant without their own account relies on.

Confirmed live before this was written - an anonymous POST with a malformed
body returned 422, which means the request reached the handler and was
validated rather than being turned away for having no session.
"""
import pytest

import main


BODY = {"to_email": "somebody@example.com", "subject": "hi", "body": "there"}


# --- the hole ------------------------------------------------------------------

def test_a_stranger_cannot_send_anything(client):
    """The whole finding, in one line."""
    res = client.post("/api/send-test-email", json=BODY)
    assert res.status_code in (401, 403), \
        f"anyone on the internet can send mail as us ({res.status_code})"


def test_and_not_by_supplying_their_own_recipient_and_body(client):
    """The parameters are entirely caller-controlled, which is what makes it a
    relay rather than a fixed-content ping."""
    res = client.post("/api/send-test-email", json={
        "to_email": "victim@example.com",
        "subject": "Your invoice is overdue",
        "body": "Pay here: http://not-us.example",
    })
    assert res.status_code in (401, 403), res.status_code


def test_nothing_leaves_however_the_anonymous_request_is_shaped(client, monkeypatch):
    """A malformed anonymous body still answers 422 rather than 401, because
    the auth call is in the handler and FastAPI validates the body first. That
    is worth knowing and is not the hole - it reveals the route exists and
    nothing more. The property that matters is this one: no shape of
    unauthenticated request results in a message."""
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda *a, **k: sent.append(a) or (True, "sent"))

    for shape in ({}, BODY, {"to_email": "x@y.z"},
                  {"to_email": "x@y.z", "subject": "", "body": ""}):
        client.post("/api/send-test-email", json=shape)

    assert not sent, f"an unauthenticated request sent {len(sent)} message(s)"


# --- and it sends through their account, not ours ----------------------------------

def test_a_signed_in_business_sends_through_its_own_transport(tenant, monkeypatch):
    """The point of the button. Sending through the platform account would
    make the test pass while telling them nothing about their own setup."""
    seen = {}

    def capture(*args, **kwargs):
        seen.update(kwargs)
        return True, "sent"

    monkeypatch.setattr(main, "send_email_background", capture)
    monkeypatch.setattr(main, "email_delivery_ready", lambda db, cid: (True, ""))

    res = tenant.post("/api/send-test-email", json=BODY)
    assert res.status_code == 200, res.text
    assert seen.get("client_id"), \
        "sent with no client_id, which is the platform's account"


def test_a_business_that_cannot_send_is_told_so(tenant, monkeypatch):
    """Rather than borrowing our account to produce a passing test for a setup
    that does not work."""
    monkeypatch.setattr(main, "email_delivery_ready",
                        lambda db, cid: (False, "no Google account is connected"))
    res = tenant.post("/api/send-test-email", json=BODY)
    assert res.status_code == 503, res.status_code
    assert "no Google account is connected" in res.json()["detail"]


def test_the_route_still_exists_for_the_button_that_calls_it(client):
    """frontend/app.js calls this from the email settings screen. Removing it
    would have been the other way to close the hole, and would have taken the
    feature with it."""
    assert any(getattr(r, "path", "") == "/api/send-test-email"
               for r in main.app.routes)
