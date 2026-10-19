"""A person updating progress on their own goal from the staff portal.

The endpoint existed with no screen, stored whatever it was sent, and then
compared it with the target - so a word, or nothing, was a server error.
"""
import pytest

import main
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def staff(tenant, account):
    emp = make_employee(tenant, password=EMP_PASSWORD)
    r = tenant.post(f"/api/employees/{emp['id']}/goals", json={"title": "Close 10 deals", "target_value": 10, "unit": "deals"})
    assert r.status_code == 200, r.text
    goal_id = r.json()["id"]
    tenant.post("/api/client/logout")
    assert tenant.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD}).status_code == 200
    return tenant, goal_id


def goal(client, goal_id):
    return next(g for g in client.get("/api/employee/goals").json() if g["id"] == goal_id)


def test_progress_is_saved_and_reaching_the_target_completes_it(staff):
    client, gid = staff
    r = client.post(f"/api/employee/goals/{gid}/update", json={"current_value": 4})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    assert goal(client, gid)["current_value"] == 4
    r = client.post(f"/api/employee/goals/{gid}/update", json={"current_value": "10"})
    assert r.status_code == 200 and r.json()["status"] == "completed"


def test_a_completed_goal_taken_back_below_target_is_in_progress_again(staff):
    client, gid = staff
    client.post(f"/api/employee/goals/{gid}/update", json={"current_value": 10})
    r = client.post(f"/api/employee/goals/{gid}/update", json={"current_value": 9})
    assert r.json()["status"] == "in_progress"


@pytest.mark.parametrize("bad", ["lots", None, -1, "nan", "inf", 10 ** 12, [], {}])
def test_progress_that_is_not_a_number_from_zero_up_is_refused(staff, bad):
    client, gid = staff
    r = client.post(f"/api/employee/goals/{gid}/update", json={"current_value": bad})
    assert r.status_code == 400, r.text
    assert goal(client, gid)["current_value"] == 0


def test_only_your_own_goal_and_only_when_signed_in(staff, tenant):
    client, gid = staff
    assert client.post(f"/api/employee/goals/{gid + 999}/update", json={"current_value": 1}).status_code == 404
    client.post("/api/employee/auth/logout")
    assert client.post(f"/api/employee/goals/{gid}/update", json={"current_value": 1}).status_code == 401
