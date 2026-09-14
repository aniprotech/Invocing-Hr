"""What changed about somebody's job, and when.

HR edits a title, moves somebody to another department, gives them a rise,
points them at a new manager - and until now the old value was simply gone.
A profile said what somebody is and nothing about what they were. The
timeline is written by the same update that changes the field, so it cannot
be forgotten, and says 'Sales' rather than '7'. Joining and leaving are read
off the employee row rather than copied.
"""
import pytest

import main
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def as_staff(client, emp):
    main.rate_limiter._hits.clear()
    client.post("/api/client/logout")
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def history(client, emp_id):
    res = client.get(f"/api/employees/{emp_id}/history")
    assert res.status_code == 200, res.text
    return res.json()["history"]


def test_a_new_title_is_written_down_with_the_old_one(tenant):
    emp = person(tenant, job_title="Analyst", start_date="2024-03-01")
    res = tenant.put(f"/api/employees/{emp['id']}", json={"job_title": "Senior Analyst",
                                                          "effective_on": "2026-04-01"})
    assert res.status_code == 200, res.text
    rows = history(tenant, emp["id"])
    assert [r["kind"] for r in rows] == ["title_change", "joined"]
    change = rows[0]
    assert change["old_value"] == "Analyst" and change["new_value"] == "Senior Analyst"
    assert change["effective_on"] == "2026-04-01"
    assert change["label"] == "New title"
    assert change["recorded_by"]
    assert rows[1]["effective_on"] == "2024-03-01" and rows[1]["new_value"] == "Analyst"


def test_the_same_value_again_is_not_a_change(tenant):
    emp = person(tenant, job_title="Analyst", salary=3000.0)
    tenant.put(f"/api/employees/{emp['id']}", json={"job_title": "Analyst", "salary": 3000})
    tenant.put(f"/api/employees/{emp['id']}", json={"phone": "0123"})
    assert [r["kind"] for r in history(tenant, emp["id"])] == ["joined"]


def test_a_move_says_the_department_by_name(tenant):
    sales = tenant.post("/api/departments", json={"name": "Sales"}).json()
    ops = tenant.post("/api/departments", json={"name": "Ops"}).json()
    emp = person(tenant, department_id=sales["id"])
    tenant.put(f"/api/employees/{emp['id']}", json={"department_id": ops["id"]})
    move = history(tenant, emp["id"])[0]
    assert move["kind"] == "transfer"
    assert move["old_value"] == "Sales" and move["new_value"] == "Ops"


def test_a_new_manager_is_named(tenant):
    boss = person(tenant, first_name="Bea", last_name="Boss")
    emp = person(tenant)
    tenant.put(f"/api/employees/{emp['id']}", json={"reports_to": boss["id"]})
    row = history(tenant, emp["id"])[0]
    assert row["kind"] == "manager_change"
    assert row["old_value"] == "" and row["new_value"] == "Bea Boss"


def test_a_rise_keeps_both_numbers_and_the_note(tenant):
    emp = person(tenant, salary=3000.0)
    tenant.put(f"/api/employees/{emp['id']}", json={"salary": 3300,
                                                    "change_note": "Annual review"})
    row = history(tenant, emp["id"])[0]
    assert row["kind"] == "pay_change" and row["label"] == "Pay change"
    assert row["old_value"] == "3000" and row["new_value"] == "3300"
    assert row["note"] == "Annual review"


def test_several_fields_at_once_are_several_rows_on_the_same_day(tenant):
    emp = person(tenant, job_title="Analyst", salary=3000.0, level="L2")
    res = tenant.put(f"/api/employees/{emp['id']}", json={
        "job_title": "Lead", "salary": 4000, "level": "L4", "effective_on": "2026-05-01"})
    assert res.status_code == 200, res.text
    rows = [r for r in history(tenant, emp["id"]) if r["kind"] != "joined"]
    assert {r["kind"] for r in rows} == {"title_change", "pay_change", "level_change"}
    assert {r["effective_on"] for r in rows} == {"2026-05-01"}


def test_a_bad_effective_date_is_refused_before_anything_changes(tenant):
    emp = person(tenant, job_title="Analyst")
    res = tenant.put(f"/api/employees/{emp['id']}", json={"job_title": "Lead",
                                                          "effective_on": "last spring"})
    assert res.status_code == 400
    assert [r["kind"] for r in history(tenant, emp["id"])] == ["joined"]


def test_hr_adds_a_promotion_by_hand_and_can_take_it_back(tenant):
    emp = person(tenant)
    res = tenant.post(f"/api/employees/{emp['id']}/history", json={
        "kind": "promotion", "effective_on": "2026-01-15", "new_value": "Team lead",
        "note": "Took over the night shift"})
    assert res.status_code == 200, res.text
    row = res.json()
    assert row["label"] == "Promotion" and row["effective_on"] == "2026-01-15"
    assert tenant.post(f"/api/employees/{emp['id']}/history", json={"kind": "promotion"}).status_code == 400
    assert tenant.post(f"/api/employees/{emp['id']}/history", json={
        "kind": "sideways", "note": "x"}).status_code == 400
    assert tenant.delete(f"/api/employment-changes/{row['id']}").status_code == 200
    assert [r["kind"] for r in history(tenant, emp["id"])] == ["joined"]


def test_newest_first_with_leaving_at_the_top(tenant):
    emp = person(tenant, job_title="Analyst", start_date="2024-01-01")
    tenant.put(f"/api/employees/{emp['id']}", json={"job_title": "Lead", "effective_on": "2025-01-01"})
    tenant.put(f"/api/employees/{emp['id']}", json={"end_date": "2026-01-31", "status": "terminated"})
    kinds = [r["kind"] for r in history(tenant, emp["id"])]
    assert kinds == ["left", "title_change", "joined"]


def test_the_person_sees_their_own_timeline_pay_included(tenant):
    emp = person(tenant, salary=3000.0)
    tenant.put(f"/api/employees/{emp['id']}", json={"salary": 3300})
    as_staff(tenant, emp)
    res = tenant.get("/api/employee/history")
    assert res.status_code == 200
    mine = res.json()["history"]
    assert mine[0]["kind"] == "pay_change" and mine[0]["new_value"] == "3300"


def test_another_business_gets_nothing(tenant, account):
    emp = person(tenant)
    row = tenant.post(f"/api/employees/{emp['id']}/history", json={"kind": "note", "note": "x"}).json()
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest",
                                              "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get(f"/api/employees/{emp['id']}/history").status_code == 404
    assert tenant.delete(f"/api/employment-changes/{row['id']}").status_code == 404
