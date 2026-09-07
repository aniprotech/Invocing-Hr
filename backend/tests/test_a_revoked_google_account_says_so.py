"""What a business is told when its Google access has been revoked.

Taken from a production log. Sending an invoice produced two errors, one after
the other:

    Failed to refresh Gmail credentials:
        ('invalid_grant: Token has been expired or revoked.', ...)

    Gmail API failed: Failed to retrieve
        http://metadata.google.internal/computeMetadata/v1/universe/
        universe-domain from the Google Compute Engine metadata service.
        Compute Engine Metadata server unavailable...

The first line is the truth. The second is what the business was shown.

get_gmail_credentials returns None when the refresh fails, and the send path
passed that None straight to build(). Given no credentials, the Google client
library goes looking for Application Default Credentials instead - which means
asking a GCE metadata server that does not exist on this host, waiting three
seconds for it, and failing with a message about metadata.google.internal.

Nothing in that mentions Google access, a token, or reconnecting. So the one
message that could have explained why no email was arriving instead described
a machine that was never involved, while the real reason sat one line above it
in a log nobody reads. "Emails aren't working" and no way to find out why.
"""
import pytest

import main
import models


@pytest.fixture
def gmail(monkeypatch):
    """A business sending through its own connected Google account."""
    state = {"creds": object(), "built": [], "sent": []}

    def build(name, version, credentials=None, **kw):
        state["built"].append(credentials)
        if credentials is None:
            # What the real library does: goes hunting for Application Default
            # Credentials and eventually times out against a metadata server.
            raise RuntimeError(
                "Failed to retrieve http://metadata.google.internal/"
                "computeMetadata/v1/universe/universe-domain from the Google "
                "Compute Engine metadata service.")
        class Service:
            def users(self):
                return self
            def messages(self):
                return self
            def send(self, userId=None, body=None):
                return self
            def execute(self):
                state["sent"].append(True)
                return {"id": "msg1"}
        return Service()

    monkeypatch.setattr(main, "build", build)
    monkeypatch.setattr(main, "get_gmail_credentials",
                        lambda **kw: state["creds"])
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    return state


def connected(client_id):
    with main.SessionLocal() as db:
        row = db.query(models.DBClientEmailSettings).filter(
            models.DBClientEmailSettings.client_id == client_id).first()
        if not row:
            row = models.DBClientEmailSettings(client_id=client_id)
            db.add(row)
        row.transport = "gmail"
        db.add(models.DBSettings(key="GOOGLE_REFRESH_TOKEN",
                                 value="their-token", client_id=client_id))
        db.commit()


def send_as(client_id):
    return main.send_email_background(
        "customer@example.com", "Invoice", "body", "Acme <a@b.com>",
        client_id=client_id)


@pytest.fixture
def a_business(client, tenant):
    mine = tenant.get("/api/client/me").json()["id"]
    connected(mine)
    yield mine
    with main.SessionLocal() as db:
        db.query(models.DBSettings).filter(
            models.DBSettings.key == "GOOGLE_REFRESH_TOKEN").delete()
        db.commit()


# --- the message they are actually shown ------------------------------------------

def test_a_revoked_account_is_named_as_the_problem(a_business, gmail):
    """It has to say what is wrong and what to do, in that order."""
    gmail["creds"] = None                       # the refresh failed

    ok, detail = send_as(a_business)

    assert ok is False
    assert "Google account" in detail, detail
    assert "Reconnect" in detail, detail


def test_and_never_mentions_a_metadata_server(a_business, gmail):
    """The thing the business was shown. It describes a Google Compute Engine
    host that has nothing to do with this deployment or with their account."""
    gmail["creds"] = None

    ok, detail = send_as(a_business)

    assert "metadata.google.internal" not in detail, detail
    assert "Compute Engine" not in detail, detail


def test_the_client_is_never_built_without_credentials(a_business, gmail):
    """The cause. Handing build() a None is what starts the hunt for
    Application Default Credentials, and it costs three seconds before it
    fails - on every message, for every business, while the account is
    unauthorised."""
    gmail["creds"] = None

    send_as(a_business)

    assert gmail["built"] == [], \
        "build() was called with no credentials, which is what reaches for ADC"


def test_a_deployment_with_no_google_app_says_that_instead(a_business, gmail, monkeypatch):
    """Same None, a different reason. Telling somebody to reconnect an account
    would be wrong when the deployment itself has no Google application."""
    gmail["creds"] = None
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    ok, detail = send_as(a_business)

    assert ok is False
    assert "not configured" in detail, detail
    assert "Reconnect" not in detail, detail


# --- and a working account still works ----------------------------------------------

def test_a_live_account_still_sends(a_business, gmail):
    ok, detail = send_as(a_business)
    assert ok is True, detail
    assert gmail["sent"] == [True]
    assert gmail["built"] and gmail["built"][0] is not None
