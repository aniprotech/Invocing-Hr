"""Equipment, and getting it back.

The thing HR loses is not the laptop; it is the laptop that walked out with
somebody who left three months ago. So most of this is about the assignment
rather than the asset.

The property worth pinning hardest: who holds a thing is never stored on the
thing. It is read from the assignment with nothing in returned_at, so a list
and a detail view cannot disagree, and no update can leave the two out of step.
"""
import uuid

import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


@pytest.fixture
def staff(tenant):
    return make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")


def new_asset(tenant, **kw):
    body = {"tag": f"LAP-{uuid.uuid4().hex[:5]}", "name": "MacBook Air",
            "category": "laptop"}
    body.update(kw)
    res = tenant.post("/api/assets", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def set_status(emp_id, status):
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp_id).first()
        row.status = status
        db.commit()


# --- keeping a list -----------------------------------------------------------

def test_an_asset_starts_available_and_held_by_nobody(tenant):
    a = new_asset(tenant, tag="LAP-001", name="MacBook Air 13")
    assert a["status"] == "available"
    assert a["held_by"] is None
    assert a["tag"] == "LAP-001"


def test_a_tag_cannot_be_used_twice(tenant):
    """A tag is how somebody identifies the thing in their hands, so two
    assets sharing one identifies nothing."""
    new_asset(tenant, tag="LAP-DUP")
    res = tenant.post("/api/assets", json={"tag": "LAP-DUP", "name": "Another"})
    assert res.status_code == 409
    assert "LAP-DUP" in res.json()["detail"]


@pytest.mark.parametrize("body", [
    {"name": "No tag"},
    {"tag": "T-1"},
    {"tag": "   ", "name": "Blank tag"},
])
def test_a_tag_and_a_name_are_both_required(tenant, body):
    assert tenant.post("/api/assets", json=body).status_code == 400


def test_an_unknown_category_falls_back_rather_than_failing(tenant):
    a = new_asset(tenant, category="spaceship")
    assert a["category"] == "other"


def test_assets_are_the_tenants_own(tenant, account):
    from fastapi.testclient import TestClient
    new_asset(tenant, tag="MINE-1")

    with TestClient(main.app) as other:
        main.rate_limiter._hits.clear()
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"})
        assert other.get("/api/assets").json() == []


def test_assets_need_a_session(client):
    assert client.get("/api/assets").status_code in (401, 403)


# --- issuing and taking back --------------------------------------------------

def test_issuing_records_who_has_it(tenant, staff):
    a = new_asset(tenant)
    res = tenant.post(f"/api/assets/{a['id']}/assign",
                      json={"employee_id": staff["id"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "assigned"
    assert body["held_by"]["name"] == "Ada Reid"


def test_who_holds_it_is_never_stored_on_the_asset(tenant, staff):
    """The whole design. An asset carrying its own holder would eventually
    disagree with the history - the cupboard, while somebody is typing on it."""
    a = new_asset(tenant)
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})

    with main.SessionLocal() as db:
        row = db.query(models.DBAsset).filter(
            models.DBAsset.id == a["id"]).first()
        # Nothing on the asset says who has it, and its own state is untouched.
        assert row.state == "available"
        assert not hasattr(row, "employee_id")
        assert main.open_assignment(db, a["id"]).employee_id == staff["id"]


def test_the_same_thing_cannot_be_in_two_hands(tenant, staff):
    other = make_employee(tenant, first_name="Sam", last_name="Ali")
    a = new_asset(tenant, tag="LAP-ONE")
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})

    res = tenant.post(f"/api/assets/{a['id']}/assign",
                      json={"employee_id": other["id"]})
    assert res.status_code == 409
    assert "Ada Reid" in res.json()["detail"]


def test_taking_it_back_frees_it(tenant, staff):
    a = new_asset(tenant)
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    res = tenant.post(f"/api/assets/{a['id']}/return", json={"condition": "good"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "available"
    assert res.json()["held_by"] is None


def test_something_returned_damaged_does_not_go_straight_back_out(tenant, staff):
    """Available means somebody can be given it, and a broken laptop is not
    that."""
    a = new_asset(tenant)
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    body = tenant.post(f"/api/assets/{a['id']}/return",
                       json={"condition": "damaged"}).json()
    assert body["state"] == "repair"
    assert body["condition"] == "damaged"


def test_taking_back_what_nobody_has_is_refused(tenant):
    a = new_asset(tenant)
    res = tenant.post(f"/api/assets/{a['id']}/return", json={})
    assert res.status_code == 409


def test_a_retired_asset_is_not_issued(tenant, staff):
    a = new_asset(tenant)
    tenant.put(f"/api/assets/{a['id']}", json={"state": "retired"})
    res = tenant.post(f"/api/assets/{a['id']}/assign",
                      json={"employee_id": staff["id"]})
    assert res.status_code == 409


def test_something_in_somebodys_hands_cannot_be_retired(tenant, staff):
    """Retiring it while it is out is how it stops being tracked at all."""
    a = new_asset(tenant)
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    res = tenant.put(f"/api/assets/{a['id']}", json={"state": "retired"})
    assert res.status_code == 409
    assert "back" in res.json()["detail"].lower()


def test_issuing_to_somebody_who_is_not_staff_is_refused(tenant):
    a = new_asset(tenant)
    assert tenant.post(f"/api/assets/{a['id']}/assign",
                       json={"employee_id": 999999}).status_code == 404


def test_the_person_is_told_what_they_now_have(tenant, staff):
    a = new_asset(tenant, tag="LAP-TOLD", name="MacBook Air")
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})

    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": staff["email"], "password": "EmpPass123"})
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("LAP-TOLD" in (n["title"] + n["message"]) for n in notes), notes


# --- the history --------------------------------------------------------------

def test_the_history_is_kept_rather_than_overwritten(tenant, staff):
    """Who had it when it was damaged is asked after the fact."""
    other = make_employee(tenant, first_name="Sam", last_name="Ali")
    a = new_asset(tenant)

    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    tenant.post(f"/api/assets/{a['id']}/return", json={"condition": "fair"})
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": other["id"]})

    rows = tenant.get(f"/api/assets/{a['id']}/history").json()
    assert len(rows) == 2
    assert rows[0]["employee"] == "Sam Ali" and rows[0]["open"] is True
    assert rows[1]["employee"] == "Ada Reid" and rows[1]["open"] is False
    assert rows[1]["condition_in"] == "fair"


def test_something_with_a_history_is_not_deleted(tenant, staff):
    a = new_asset(tenant)
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    tenant.post(f"/api/assets/{a['id']}/return", json={})

    res = tenant.delete(f"/api/assets/{a['id']}")
    assert res.status_code == 409
    assert "retire" in res.json()["detail"].lower()


def test_something_that_was_never_issued_can_be_deleted(tenant):
    """A typo should not have to be retired forever."""
    a = new_asset(tenant)
    assert tenant.delete(f"/api/assets/{a['id']}").status_code == 200
    assert tenant.get("/api/assets").json() == []


# --- what is still out --------------------------------------------------------

def test_the_summary_counts_what_is_where(tenant, staff):
    new_asset(tenant)
    held = new_asset(tenant)
    tenant.post(f"/api/assets/{held['id']}/assign", json={"employee_id": staff["id"]})

    counts = tenant.get("/api/assets/summary").json()["counts"]
    assert counts["total"] == 2
    assert counts["assigned"] == 1
    assert counts["available"] == 1


def test_a_leaver_still_holding_something_is_the_headline(tenant, staff):
    """The one figure here that is a problem rather than a fact."""
    a = new_asset(tenant, tag="LAP-GONE", name="MacBook Air")
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    set_status(staff["id"], "terminated")

    out = tenant.get("/api/assets/summary").json()["still_out_with_leavers"]
    assert len(out) == 1
    assert out[0]["tag"] == "LAP-GONE"
    assert out[0]["employee"] == "Ada Reid"


def test_somebody_still_working_here_is_not_flagged(tenant, staff):
    a = new_asset(tenant)
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    assert tenant.get("/api/assets/summary").json()["still_out_with_leavers"] == []


def test_offboarding_can_ask_what_they_are_holding(tenant, staff):
    a = new_asset(tenant, tag="LAP-OFF")
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})

    rows = tenant.get(f"/api/employees/{staff['id']}/assets").json()
    assert [r["tag"] for r in rows] == ["LAP-OFF"]


def test_what_has_come_back_is_no_longer_theirs(tenant, staff):
    a = new_asset(tenant)
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})
    tenant.post(f"/api/assets/{a['id']}/return", json={})
    assert tenant.get(f"/api/employees/{staff['id']}/assets").json() == []


# --- the employee's own view --------------------------------------------------

def test_a_person_can_see_what_they_are_holding(tenant, staff):
    """The first anybody hears of a laptop they were never given is usually the
    day they are asked to hand it back."""
    a = new_asset(tenant, tag="LAP-MINE", name="MacBook Air")
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": staff["id"]})

    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": staff["email"], "password": "EmpPass123"})
    rows = tenant.get("/api/employee/assets").json()
    assert [r["tag"] for r in rows] == ["LAP-MINE"]


def test_a_person_sees_nothing_of_a_colleagues_kit(tenant, account):
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    theirs = make_employee(tenant, first_name="Sam", last_name="Ali")
    a = new_asset(tenant, tag="LAP-THEIRS")
    tenant.post(f"/api/assets/{a['id']}/assign", json={"employee_id": theirs["id"]})

    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": mine["email"], "password": "EmpPass123"})
    assert tenant.get("/api/employee/assets").json() == []


def test_the_employee_view_needs_a_session(client):
    assert client.get("/api/employee/assets").status_code == 401
