"""A business's own Google connection that has stopped working is said, on
every screen.

Sending checked only that a token had once been stored, so a connection
Google had revoked still counted as ready: the app said nothing, and every
invoice and reminder failed until somebody reconnected it by chance. Now
readiness asks whether the token still works, and while it does not, every
screen carries a bar, the dashboard lists it, and a send is refused with
the reason instead of failing quietly.
"""
import types

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    main._GMAIL_HEALTH.clear()
    yield
    main._GMAIL_HEALTH.clear()


@pytest.fixture
def google(monkeypatch):
    """Google's answer to "does this token still work", and how often it was asked."""
    state = {"works": True, "asked": 0}

    def creds(access_token=None, refresh_token=None):
        state["asked"] += 1
        return types.SimpleNamespace(valid=True) if state["works"] else None
    monkeypatch.setattr(main, "get_gmail_credentials", creds)
    return state


def me(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(models.DBClient.email == account["email"]).first().id


def connect_own_google(account, token="tok-1", transport="gmail"):
    cid = me(account)
    with main.SessionLocal() as db:
        db.query(models.DBSettings).filter(models.DBSettings.key == "GOOGLE_REFRESH_TOKEN",
                                           models.DBSettings.client_id == cid).delete()
        db.add(models.DBSettings(client_id=cid, key="GOOGLE_REFRESH_TOKEN", value=token))
        if transport is not None:
            row = db.query(models.DBClientEmailSettings).filter(models.DBClientEmailSettings.client_id == cid).first()
            if not row:
                row = models.DBClientEmailSettings(client_id=cid)
                db.add(row)
            row.transport = transport
        db.commit()


def mine(tenant):
    return tenant.get("/api/client/account-status").json()["mine"]


def test_a_working_connection_is_ready(tenant, account, google):
    connect_own_google(account)
    assert mine(tenant) == {"can_send": True, "blocked_reason": ""}


def test_a_revoked_connection_is_not_ready_and_says_what_to_do(tenant, account, google):
    connect_own_google(account)
    google["works"] = False
    m = mine(tenant)
    assert m["can_send"] is False and "no longer authorised" in m["blocked_reason"] and "Reconnect" in m["blocked_reason"]


def test_the_dashboard_lists_it_first(tenant, account, google):
    connect_own_google(account)
    google["works"] = False
    items = tenant.get("/api/dashboard/attention").json()["items"]
    blocked = [i for i in items if i["key"] == "email_blocked"]
    assert blocked and blocked[0]["tone"] == "bad" and blocked[0]["view"] == "settings-view" and "Reconnect" in blocked[0]["hint"]


def test_a_send_through_a_dead_connection_is_refused_with_the_reason(tenant, account, google):
    from conftest import make_invoice
    connect_own_google(account)
    google["works"] = False
    inv = make_invoice(tenant, status="Awaiting Payment", contact="Acme", email="acme@example.com",
                       line_items=[{"description": "Work", "qty": 1, "price": 10, "tax_rate": "No Tax"}])
    r = tenant.post(f"/api/invoices/{inv['number']}/send", json={})
    assert r.status_code >= 400 and "no longer authorised" in r.text


def test_a_connection_saved_without_choosing_gmail_is_still_the_one_tested(tenant, account, google):
    connect_own_google(account, transport=None)          # sending picks this token first
    google["works"] = False
    assert mine(tenant)["can_send"] is False


def test_a_business_on_its_own_mail_server_is_not_judged_by_an_old_google_token(tenant, account, google):
    connect_own_google(account, transport="smtp")
    cid = me(account)
    with main.SessionLocal() as db:
        db.query(models.DBClientEmailSettings).filter(models.DBClientEmailSettings.client_id == cid).first().smtp_host = "mail.example.com"
        db.commit()
    google["works"] = False
    assert mine(tenant)["can_send"] is True and google["asked"] == 0


def test_google_is_asked_once_for_a_while_not_on_every_screen(tenant, account, google):
    connect_own_google(account)
    for _ in range(5):
        mine(tenant)
    assert google["asked"] == 1


def test_reconnecting_is_noticed_straight_away(tenant, account, google):
    connect_own_google(account, token="old")
    google["works"] = False
    assert mine(tenant)["can_send"] is False
    google["works"] = True
    connect_own_google(account, token="new")             # a new token is a new question
    assert mine(tenant)["can_send"] is True
