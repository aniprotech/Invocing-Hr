"""One app, and a plan that decides what is in it.

Invoicing and HR used to be two pages with two logins. Which one a business
got was answered by which URL they opened - so the same account saw a
different product at a different address, anybody with both signed in twice,
and every endpoint stayed open to whoever typed the path regardless.

They are one app now. These check the part that actually matters: that the
plan is enforced where it decides something, not only where it is drawn.
"""
import pytest

import database
import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def superadmin(client):
    """Signs in as the operator on the same client the tenant uses. The
    session carries both ids at once, so the two do not evict each other
    and a test can act as each in turn."""
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    return client


def set_modules(tenant, value):
    cid = tenant.get("/api/client/me").json()["id"]
    with database.SessionLocal() as db:
        row = db.query(models.DBClient).filter(models.DBClient.id == cid).first()
        row.modules = value
        db.commit()
    return cid


# --- what a business is told it has ----------------------------------------

def test_an_account_has_everything_by_default(tenant):
    """Nobody who could reach both should lose one on upgrade."""
    assert set(tenant.get("/api/client/me").json()["modules"]) == {"invoicing", "hr"}


def test_a_blank_plan_still_means_everything(tenant):
    """Rows that predate the column read as empty, and empty must not be
    read as "no modules" - that would lock out every existing account."""
    set_modules(tenant, "")
    assert set(tenant.get("/api/client/me").json()["modules"]) == {"invoicing", "hr"}


def test_nonsense_in_the_column_is_ignored_not_trusted(tenant):
    set_modules(tenant, "hr,teleportation")
    assert tenant.get("/api/client/me").json()["modules"] == ["hr"]


# --- and what it can actually reach ----------------------------------------

def test_an_invoicing_only_business_is_refused_hr(tenant):
    """The whole point. Hiding the menu item leaves the URL working, so this
    is checked where it decides something."""
    set_modules(tenant, "invoicing")
    assert tenant.get("/api/employees").status_code == 403
    assert tenant.get("/api/departments").status_code == 403
    assert tenant.get("/api/payslips").status_code == 403


def test_an_invoicing_only_business_is_refused_the_calendar(tenant):
    """Every leave request, goal deadline and document expiry the calendar
    reads back is HR data, so the whole thing gates with the rest of HR."""
    set_modules(tenant, "invoicing")
    assert tenant.get("/api/hr/calendar").status_code == 403
    assert tenant.post("/api/hr/calendar-events",
                       json={"date": "2026-09-01", "title": "X"}).status_code == 403
    assert tenant.get("/api/hr/holidays").status_code == 403


def test_but_keeps_its_own_module(tenant):
    set_modules(tenant, "invoicing")
    assert tenant.get("/api/invoices").status_code == 200


def test_an_hr_only_business_is_refused_invoicing(tenant):
    set_modules(tenant, "hr")
    assert tenant.get("/api/invoices").status_code == 403
    assert tenant.get("/api/quotes").status_code == 403


def test_but_keeps_its_own(tenant):
    set_modules(tenant, "hr")
    assert tenant.get("/api/employees").status_code == 200


def test_the_shared_parts_stay_reachable_either_way(tenant):
    """Settings, the wallet and contacts belong to the account rather than to
    a module. Refusing those would break the half they do have."""
    for plan in ("invoicing", "hr"):
        set_modules(tenant, plan)
        assert tenant.get("/api/settings").status_code == 200, plan
        assert tenant.get("/api/wallet").status_code == 200, plan


def test_the_refusal_says_what_to_do(tenant):
    set_modules(tenant, "invoicing")
    detail = tenant.get("/api/employees").json()["detail"].lower()
    assert "plan" in detail and "hr" in detail


# --- the operator sets it ---------------------------------------------------

def test_an_operator_can_change_a_plan(superadmin, tenant):
    cid = tenant.get("/api/client/me").json()["id"]
    res = superadmin.put(f"/api/superadmin/clients/{cid}/modules",
                         json={"modules": ["hr"]})
    assert res.status_code == 200, res.text
    assert res.json()["modules"] == ["hr"]
    assert tenant.get("/api/invoices").status_code == 403


def test_a_plan_cannot_be_emptied(superadmin, tenant):
    """An account with no modules is an account that can do nothing, which is
    a disable rather than a plan - and there is already a switch for that."""
    cid = tenant.get("/api/client/me").json()["id"]
    assert superadmin.put(f"/api/superadmin/clients/{cid}/modules",
                          json={"modules": []}).status_code == 400


def test_an_invented_module_is_refused(superadmin, tenant):
    cid = tenant.get("/api/client/me").json()["id"]
    res = superadmin.put(f"/api/superadmin/clients/{cid}/modules",
                         json={"modules": ["hr", "payroll-plus"]})
    assert res.status_code == 400
    assert "payroll-plus" in res.json()["detail"]


def test_a_tenant_cannot_grant_itself_a_module(tenant):
    cid = tenant.get("/api/client/me").json()["id"]
    assert tenant.put(f"/api/superadmin/clients/{cid}/modules",
                      json={"modules": ["invoicing", "hr"]}).status_code == 401


def test_the_stored_order_does_not_depend_on_the_request(superadmin, tenant):
    cid = tenant.get("/api/client/me").json()["id"]
    a = superadmin.put(f"/api/superadmin/clients/{cid}/modules",
                       json={"modules": ["hr", "invoicing"]}).json()["modules"]
    b = superadmin.put(f"/api/superadmin/clients/{cid}/modules",
                       json={"modules": ["invoicing", "hr"]}).json()["modules"]
    assert a == b
