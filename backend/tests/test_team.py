"""More than one person per business.

Until now a company had exactly one login, so an owner and their bookkeeper
shared a password. Most of this is about what each role must *not* be able to
do, because that is where a permission model goes wrong.
"""
import uuid
from datetime import datetime, timedelta

import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def invite(tenant, email=None, role="admin"):
    email = email or f"mate-{uuid.uuid4().hex[:8]}@example.com"
    res = tenant.post("/api/team/invite", json={"email": email, "role": role, "name": "Colleague"})
    assert res.status_code == 200, res.text
    return res.json(), email


def set_their_password(member_id, password="Colleague123"):
    """Accept the invite the way the emailed link does."""
    raw = uuid.uuid4().hex
    with main.SessionLocal() as db:
        db.add(models.DBPasswordReset(
            user_type="member", member_id=member_id,
            token_hash=main.hash_reset_token(raw),
            expires_at=(datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    return raw


def sign_in_as(client, email, password="Colleague123"):
    return client.post("/api/client/login", json={"email": email, "password": password})


# --- the team list ------------------------------------------------------------

def test_a_new_account_is_a_team_of_one(tenant):
    body = tenant.get("/api/team").json()
    assert len(body["members"]) == 1
    assert body["members"][0]["role"] == "owner"
    assert body["members"][0]["is_account_owner"] is True
    assert body["your_role"] == "owner"


def test_inviting_adds_them_to_the_list(tenant):
    _, email = invite(tenant)
    members = tenant.get("/api/team").json()["members"]
    assert [m["email"] for m in members if not m["is_account_owner"]] == [email]


def test_an_invite_starts_unaccepted_and_with_no_password(tenant):
    member, _ = invite(tenant)
    assert member["accepted"] is False
    with main.SessionLocal() as db:
        row = db.query(models.DBTeamMember).filter(
            models.DBTeamMember.id == member["id"]).first()
        assert row.password_hash == "", "an invite must not carry a password"


# --- accepting and signing in -------------------------------------------------

def test_a_colleague_can_set_a_password_and_sign_in(client, tenant):
    member, email = invite(tenant)
    raw = set_their_password(member["id"])

    res = client.post("/api/client/reset-password",
                      json={"token": raw, "password": "Colleague123"})
    assert res.status_code == 200, res.text

    res = sign_in_as(client, email)
    assert res.status_code == 200, res.text
    assert res.json()["role"] == "admin"


def test_accepting_marks_the_invite_accepted(client, tenant):
    member, _ = invite(tenant)
    raw = set_their_password(member["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "Colleague123"})

    row = next(m for m in tenant.get("/api/team").json()["members"]
               if m["id"] == member["id"])
    assert row["accepted"] is True


def test_a_colleague_sees_the_same_company(client, tenant):
    tenant.post("/api/invoices", json={
        "contact": "Shared Customer", "email": "s@example.com",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "line_items": [{"description": "w", "qty": 1, "price": 10.0}]})

    member, email = invite(tenant)
    raw = set_their_password(member["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "Colleague123"})
    sign_in_as(client, email)

    assert [i["to"] for i in client.get("/api/invoices").json()] == ["Shared Customer"]


def test_a_deactivated_colleague_cannot_sign_in(client, tenant):
    member, email = invite(tenant)
    raw = set_their_password(member["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "Colleague123"})
    tenant.put(f"/api/team/{member['id']}", json={"is_active": False})

    assert sign_in_as(client, email).status_code == 401


def test_a_removed_colleague_cannot_sign_in(client, tenant):
    member, email = invite(tenant)
    raw = set_their_password(member["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "Colleague123"})
    tenant.delete(f"/api/team/{member['id']}")

    assert sign_in_as(client, email).status_code == 401


def test_removing_someone_kills_their_outstanding_invite(client, tenant):
    member, _ = invite(tenant)
    raw = set_their_password(member["id"])
    tenant.delete(f"/api/team/{member['id']}")

    res = client.post("/api/client/reset-password",
                      json={"token": raw, "password": "Colleague123"})
    assert res.status_code == 400


# --- what a viewer may not do -------------------------------------------------

@pytest.fixture
def viewer(client, tenant):
    member, email = invite(tenant, role="viewer")
    raw = set_their_password(member["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "Colleague123"})
    sign_in_as(client, email)
    return {"client": client, "member": member, "email": email}


def test_a_viewer_can_read(viewer):
    assert viewer["client"].get("/api/invoices").status_code == 200
    assert viewer["client"].get("/api/sales/pipeline").status_code == 200


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/invoices", {"contact": "X", "issue_date": "2026-01-01",
                               "due_date": "2026-01-31",
                               "line_items": [{"description": "x", "qty": 1, "price": 1.0}]}),
    ("post", "/api/quotes", {"contact": "X", "issue_date": "2026-01-01",
                             "expiry_date": "2026-01-31",
                             "line_items": [{"description": "x", "qty": 1, "price": 1.0}]}),
    ("post", "/api/employees", {"first_name": "A", "last_name": "B",
                                "email": "ab@example.com"}),
    ("post", "/api/settings", {"company_name": "Renamed"}),
    ("put", "/api/tax-rates", {"tax_rates": [{"name": "X", "percent": 1}]}),
])
def test_a_viewer_cannot_write(viewer, method, path, body):
    res = getattr(viewer["client"], method)(path, json=body)
    assert res.status_code == 403, f"{method.upper()} {path} should be refused"
    assert "read-only" in res.json()["detail"].lower()


def test_a_viewer_cannot_delete(viewer, account):
    """The fixtures share one HTTP client, so the owner has to sign back in to
    create the invoice, then the viewer signs in again to try deleting it."""
    c = viewer["client"]
    c.post("/api/client/login", json={"email": account["email"],
                                      "password": account["password"]})
    inv = c.post("/api/invoices", json={
        "contact": "X", "email": "x@example.com", "issue_date": "2026-01-01",
        "due_date": "2026-01-31",
        "line_items": [{"description": "x", "qty": 1, "price": 1.0}]}).json()
    assert "number" in inv, inv

    main.rate_limiter._hits.clear()
    sign_in_as(c, viewer["email"])
    assert c.delete(f"/api/invoices/{inv['number']}").status_code == 403


def test_a_viewer_can_still_sign_out(viewer):
    """The guard must not lock somebody into a session they cannot leave."""
    assert viewer["client"].post("/api/client/logout").status_code == 200


# --- what an admin may not do -------------------------------------------------

@pytest.fixture
def admin(client, tenant):
    member, email = invite(tenant, role="admin")
    raw = set_their_password(member["id"])
    client.post("/api/client/reset-password", json={"token": raw, "password": "Colleague123"})
    sign_in_as(client, email)
    return {"client": client, "member": member}


def test_an_admin_can_write(admin):
    res = admin["client"].post("/api/invoices", json={
        "contact": "Made by admin", "email": "a@example.com",
        "issue_date": "2026-01-01", "due_date": "2026-01-31",
        "line_items": [{"description": "x", "qty": 1, "price": 1.0}]})
    assert res.status_code == 200, res.text


def test_an_admin_cannot_manage_the_team(admin):
    c = admin["client"]
    assert c.post("/api/team/invite", json={"email": "new@example.com"}).status_code == 403
    assert c.put(f"/api/team/{admin['member']['id']}", json={"role": "viewer"}).status_code == 403
    assert c.delete(f"/api/team/{admin['member']['id']}").status_code == 403


def test_an_admin_sees_their_own_role(admin):
    assert admin["client"].get("/api/team").json()["your_role"] == "admin"


# --- validation ---------------------------------------------------------------

def test_you_cannot_invite_a_second_owner(tenant):
    res = tenant.post("/api/team/invite", json={"email": "x@example.com", "role": "owner"})
    assert res.status_code == 400


def test_you_cannot_invite_the_same_person_twice(tenant):
    _, email = invite(tenant)
    res = tenant.post("/api/team/invite", json={"email": email})
    assert res.status_code == 400


def test_you_cannot_invite_the_owner(tenant, account):
    res = tenant.post("/api/team/invite", json={"email": account["email"]})
    assert res.status_code == 400


def test_a_bad_address_is_refused(tenant):
    assert tenant.post("/api/team/invite", json={"email": "not-an-email"}).status_code == 400


# --- isolation ----------------------------------------------------------------

def test_one_company_cannot_touch_another_s_team(client, tenant):
    member, _ = invite(tenant)

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    assert client.get("/api/team").json()["members"] == [
        m for m in client.get("/api/team").json()["members"] if m["is_account_owner"]]
    assert client.put(f"/api/team/{member['id']}", json={"role": "viewer"}).status_code == 404
    assert client.delete(f"/api/team/{member['id']}").status_code == 404


def test_the_team_needs_a_session(client):
    assert client.get("/api/team").status_code == 401
