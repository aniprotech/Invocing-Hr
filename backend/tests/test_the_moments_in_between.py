"""Workflows fire on the moments between joining and leaving.

Passing probation, a promotion, a move between departments: each used to
be handled by remembering. Now a workflow can wait on it, and fires once
per person from the place the thing happens - the probation decision, the
profile edit, the history entry.
"""
import uuid

import pytest

import main
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", "EmpPass123")
    return make_employee(tenant, **kw)


def a_workflow(tenant, trigger, title):
    res = tenant.post("/api/workflows", json={"name": f"Flow {uuid.uuid4().hex[:6]}", "trigger": trigger,
                                              "steps": [{"title": title, "owner": "hr", "due_offset_days": 1}]})
    assert res.status_code == 200, res.text
    flow = res.json()
    assert tenant.put(f"/api/workflows/{flow['id']}/active", json={"active": True}).status_code == 200
    return flow


def tasks_for(tenant, employee_id):
    return [t["title"] for t in tenant.get("/api/workflow-tasks").json() if t["employee_id"] == employee_id]


def test_the_new_triggers_are_offered(tenant):
    assert set(main.WORKFLOW_TRIGGERS) >= {"probation_passed", "promoted", "transferred"}
    assert tenant.post("/api/workflows", json={"name": "x", "trigger": "sneezed", "steps": [{"title": "t"}]}).status_code == 400


def test_passing_probation_fires_once(tenant):
    a_workflow(tenant, "probation_passed", "Issue the permanent badge")
    emp = person(tenant, probation_end="2026-12-01")
    assert tasks_for(tenant, emp["id"]) == []
    assert tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "confirm"}).status_code == 200
    assert tasks_for(tenant, emp["id"]) == ["Issue the permanent badge"]


def test_a_promotion_fires_whether_by_level_or_by_hand(tenant):
    a_workflow(tenant, "promoted", "Update the org chart title")
    by_level = person(tenant, level="L2")
    tenant.put(f"/api/employees/{by_level['id']}", json={"level": "L3"})
    assert tasks_for(tenant, by_level["id"]) == ["Update the org chart title"]
    by_hand = person(tenant)
    tenant.post(f"/api/employees/{by_hand['id']}/history", json={"kind": "promotion", "note": "Lead"})
    assert tasks_for(tenant, by_hand["id"]) == ["Update the org chart title"]
    # Once per person: a second promotion does not make a second task.
    tenant.put(f"/api/employees/{by_level['id']}", json={"level": "L4"})
    assert tasks_for(tenant, by_level["id"]) == ["Update the org chart title"]


def test_a_move_between_departments_fires(tenant):
    a_workflow(tenant, "transferred", "Move their desk")
    a = tenant.post("/api/departments", json={"name": "A"}).json()
    b = tenant.post("/api/departments", json={"name": "B"}).json()
    emp = person(tenant, department_id=a["id"])
    tenant.put(f"/api/employees/{emp['id']}", json={"department_id": b["id"]})
    assert tasks_for(tenant, emp["id"]) == ["Move their desk"]
    same = person(tenant, department_id=a["id"])
    tenant.put(f"/api/employees/{same['id']}", json={"department_id": a["id"]})
    assert tasks_for(tenant, same["id"]) == []
