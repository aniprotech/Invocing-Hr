"""Which address the platform's own mail claims to come from.

Sign-in codes, verification codes, password resets and team invites all leave
on the platform transport - whichever Google account the operator connected.
They said they came from hello@keyroutes.co, a different company's domain left
over from somewhere else, hardcoded as the default in thirteen places.

That is worse than untidy. Gmail sends as the account that authenticated,
whatever the header claims, so the message went out saying one domain while
being sent by another - which is exactly what SPF and DMARC exist to catch.
The mild outcome is a sign-in code in a spam folder. The less mild one is a
receiving server rejecting it, which from this end looks identical to a code
that was sent and simply never arrived.

So the address is now the account actually doing the sending, then whatever
the operator set deliberately, then the old constant for a deployment that has
neither.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("FROM_EMAIL", raising=False)
    def clear():
        with main.SessionLocal() as db:
            db.query(models.DBSettings).filter(
                models.DBSettings.key == "GOOGLE_SENDER_EMAIL",
                models.DBSettings.client_id == None).delete(  # noqa: E711
                    synchronize_session=False)
            db.commit()
    clear()
    yield
    clear()


def platform_connected_as(address):
    with main.SessionLocal() as db:
        db.add(models.DBSettings(key="GOOGLE_SENDER_EMAIL", value=address,
                                 client_id=None))
        db.commit()


# --- what it resolves to ---------------------------------------------------------

def test_it_uses_the_account_that_is_actually_sending(client):
    """The whole point. Gmail sends as the authenticated account regardless,
    so this is the only header that is not a contradiction."""
    platform_connected_as("info@aniprotech.com")
    assert main.platform_from_address() == "info@aniprotech.com"


def test_an_address_the_operator_set_is_used_when_none_is_connected(client, monkeypatch):
    """An SMTP deployment has no Google account to read this from."""
    monkeypatch.setenv("FROM_EMAIL", "billing@theirs.test")
    assert main.platform_from_address() == "billing@theirs.test"


def test_the_connected_account_wins_over_the_variable(client, monkeypatch):
    """Because the variable cannot change who Gmail sends as, and a header
    that disagrees with the sender is the thing being fixed."""
    monkeypatch.setenv("FROM_EMAIL", "something@else.test")
    platform_connected_as("info@aniprotech.com")
    assert main.platform_from_address() == "info@aniprotech.com"


def test_a_blank_setting_is_not_treated_as_an_address(client, monkeypatch):
    platform_connected_as("   ")
    monkeypatch.setenv("FROM_EMAIL", "billing@theirs.test")
    assert main.platform_from_address() == "billing@theirs.test"


def test_it_never_returns_nothing(client):
    """Every caller puts this straight into a From header."""
    assert "@" in main.platform_from_address()


# --- and nothing hardcodes the old domain any more --------------------------------

def test_no_send_path_still_names_the_other_company(client):
    """Thirteen call sites had it as their default. One left is the helper's
    own last resort; one is who operator accounts are seeded for, which is a
    recipient rather than a sender."""
    import pathlib
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    lines = [f"{i}: {l.strip()}" for i, l in enumerate(src.split("\n"), 1)
             if "hello@keyroutes.co" in l
             and "SUPERADMIN_EMAILS" not in l
             and not l.strip().startswith(("#", "or ", "operator connected"))]
    assert not lines, "\n".join(lines)


def test_every_from_email_read_goes_through_the_helper(client):
    """Otherwise a new send path picks the old default up again."""
    import pathlib
    src = pathlib.Path(main.__file__).read_text(encoding="utf-8")
    reads = [f"{i}: {l.strip()}" for i, l in enumerate(src.split("\n"), 1)
             if 'getenv("FROM_EMAIL"' in l]
    assert len(reads) == 1, "\n".join(reads)


# --- end to end, on the message that matters most -------------------------------------

def test_an_operator_sign_in_code_is_sent_from_the_connected_account(client, monkeypatch):
    """The one message where landing in spam locks somebody out of everything."""
    platform_connected_as("info@aniprotech.com")
    seen = {}

    def capture(to_email, subject, body, from_email, *a, **k):
        seen.update(to_email=to_email, from_email=from_email)
        return True, "sent"

    monkeypatch.setattr(main, "send_email_background", capture)
    monkeypatch.setattr(main, "email_delivery_ready", lambda db, cid=None: (True, ""))

    with main.SessionLocal() as db:
        who = db.query(models.DBSuperAdmin).first()
        address = who.email

    res = client.post("/api/superadmin/request-otp", json={"identifier": address})
    assert res.status_code == 200, res.text
    assert seen.get("from_email") == "info@aniprotech.com", seen
