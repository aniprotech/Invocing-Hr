"""The things that should happen every time, without anybody remembering.

A new starter needs a laptop, a contract, an induction and a check-in. None of
it is hard; it is just easy to forget one, and the one forgotten is discovered
on the person's first morning.

Three properties carry the weight here, and each has a way of going wrong that
is worse than the feature not existing:

  - Turning a workflow on must not fire it at people already here. An
    automation whose first act is two hundred tasks for staff who joined years
    ago is one nobody trusts again.
  - A run copies its steps. Editing the template next month must not rewrite
    what was asked of somebody last month.
  - A workflow that fails must not stop somebody being hired. The hire is the
    real work; the checklist is the convenience.
"""
from datetime import datetime, timedelta

import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


TODAY = datetime.now().date()


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


def make_workflow(tenant, trigger="employee_joins", steps=None, name="New starter"):
    res = tenant.post("/api/workflows", json={
        "name": name, "trigger": trigger,
        "steps": steps if steps is not None else [
            {"title": "Order a laptop", "owner": "hr", "due_offset_days": -3},
            {"title": "Book the induction", "owner": "manager", "due_offset_days": 1},
            {"title": "Read the handbook", "owner": "employee", "due_offset_days": 5},
        ],
    })
    assert res.status_code == 200, res.text
    return res.json()


def turn_on(tenant, wid):
    res = tenant.put(f"/api/workflows/{wid}/active", json={"active": True})
    assert res.status_code == 200, res.text
    return res.json()


def tasks(tenant, **params):
    res = tenant.get("/api/workflow-tasks", params=params)
    assert res.status_code == 200, res.text
    return res.json()


# --- turning one on -----------------------------------------------------------

def test_a_new_workflow_starts_switched_off(tenant):
    """Nobody wants it running before they have read the steps back."""
    w = make_workflow(tenant)
    assert w["active"] is False
    assert w["step_count"] == 3


def test_one_with_no_steps_cannot_be_turned_on(tenant):
    w = make_workflow(tenant, steps=[])
    res = tenant.put(f"/api/workflows/{w['id']}/active", json={"active": True})
    assert res.status_code == 400


def test_turning_it_on_does_not_reach_back_over_people_already_here(tenant):
    """The property that decides whether anybody trusts it. Enabling "when
    somebody joins" must not manufacture tasks for staff who joined years
    ago."""
    make_employee(tenant, first_name="Already", last_name="Here")
    make_employee(tenant, first_name="Also", last_name="Here")

    w = make_workflow(tenant)
    body = turn_on(tenant, w["id"])

    assert tasks(tenant) == []
    assert "nobody already here" in body["note"]


def test_it_runs_for_the_next_person_who_joins(tenant):
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])

    make_employee(tenant, first_name="Nia", last_name="Okoro")
    rows = tasks(tenant)
    assert len(rows) == 3
    assert {r["title"] for r in rows} == {
        "Order a laptop", "Book the induction", "Read the handbook"}
    assert all(r["employee"] == "Nia Okoro" for r in rows)


def test_a_workflow_left_off_does_nothing(tenant):
    make_workflow(tenant)
    make_employee(tenant)
    assert tasks(tenant) == []


def test_only_the_matching_trigger_fires(tenant):
    joins = make_workflow(tenant, trigger="employee_joins", name="Joining")
    leaves = make_workflow(tenant, trigger="employee_leaves", name="Leaving")
    turn_on(tenant, joins["id"])
    turn_on(tenant, leaves["id"])

    make_employee(tenant)
    assert {r["workflow"] for r in tasks(tenant)} == {"Joining"}


def test_leaving_fires_its_own(tenant):
    leaves = make_workflow(tenant, trigger="employee_leaves", name="Leaving",
                           steps=[{"title": "Take the laptop back", "owner": "hr"}])
    turn_on(tenant, leaves["id"])

    emp = make_employee(tenant)
    res = tenant.post(f"/api/employees/{emp['id']}/offboard")
    assert res.status_code == 200, res.text

    rows = tasks(tenant)
    assert [r["title"] for r in rows] == ["Take the laptop back"]


def test_an_unknown_trigger_is_refused(tenant):
    res = tenant.post("/api/workflows", json={
        "name": "Nonsense", "trigger": "when_the_moon_is_full", "steps": []})
    assert res.status_code == 400


def test_a_workflow_needs_a_name(tenant):
    assert tenant.post("/api/workflows", json={"steps": []}).status_code == 400


# --- what a run remembers -----------------------------------------------------

def test_a_task_keeps_what_was_asked_even_after_the_template_changes(tenant):
    """Editing the template next month must not rewrite what was asked of
    somebody last month."""
    w = make_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    turn_on(tenant, w["id"])
    make_employee(tenant, first_name="Nia", last_name="Okoro")

    with main.SessionLocal() as db:
        step = db.query(models.DBWorkflowStep).filter(
            models.DBWorkflowStep.workflow_id == w["id"]).first()
        step.title = "Order a desktop instead"
        db.commit()

    assert [r["title"] for r in tasks(tenant)] == ["Order a laptop"]


def test_the_run_remembers_the_name_it_ran_under(tenant):
    w = make_workflow(tenant, name="Original name",
                      steps=[{"title": "Do a thing", "owner": "hr"}])
    turn_on(tenant, w["id"])
    make_employee(tenant)

    with main.SessionLocal() as db:
        flow = db.query(models.DBWorkflow).filter(
            models.DBWorkflow.id == w["id"]).first()
        flow.name = "Renamed later"
        db.commit()

    assert tasks(tenant)[0]["workflow"] == "Original name"


def test_the_same_workflow_does_not_run_twice_for_one_person(tenant):
    """A status corrected twice would otherwise make two identical sets."""
    w = make_workflow(tenant, trigger="employee_leaves",
                      steps=[{"title": "Collect the pass", "owner": "hr"}])
    turn_on(tenant, w["id"])
    emp = make_employee(tenant)

    tenant.post(f"/api/employees/{emp['id']}/offboard")
    tenant.post(f"/api/employees/{emp['id']}/offboard")
    assert len(tasks(tenant)) == 1


# --- dates --------------------------------------------------------------------

def test_a_negative_offset_puts_the_task_before_the_start(tenant):
    """A laptop ordered on somebody's first morning arrives in their second
    week, which is the whole reason the offset can be negative."""
    w = make_workflow(tenant, steps=[
        {"title": "Order a laptop", "owner": "hr", "due_offset_days": -3}])
    turn_on(tenant, w["id"])
    make_employee(tenant)

    due = tasks(tenant)[0]["due_date"]
    assert due == (TODAY - timedelta(days=3)).strftime("%Y-%m-%d")


def test_something_past_its_date_is_marked_late(tenant):
    w = make_workflow(tenant, steps=[
        {"title": "Order a laptop", "owner": "hr", "due_offset_days": -3}])
    turn_on(tenant, w["id"])
    make_employee(tenant)
    assert tasks(tenant)[0]["overdue"] is True


def test_something_due_later_is_not(tenant):
    w = make_workflow(tenant, steps=[
        {"title": "Check in", "owner": "hr", "due_offset_days": 30}])
    turn_on(tenant, w["id"])
    make_employee(tenant)
    assert tasks(tenant)[0]["overdue"] is False


# --- working through them -----------------------------------------------------

def test_a_task_can_be_ticked_off(tenant):
    w = make_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    turn_on(tenant, w["id"])
    make_employee(tenant)

    tid = tasks(tenant)[0]["id"]
    res = tenant.post(f"/api/workflow-tasks/{tid}/done")
    assert res.status_code == 200
    assert res.json()["done"] is True
    assert tasks(tenant, done="open") == []


def test_ticking_it_off_can_be_undone(tenant):
    w = make_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    turn_on(tenant, w["id"])
    make_employee(tenant)
    tid = tasks(tenant)[0]["id"]

    tenant.post(f"/api/workflow-tasks/{tid}/done")
    tenant.post(f"/api/workflow-tasks/{tid}/done", json={"done": False})
    assert len(tasks(tenant, done="open")) == 1


def test_tasks_can_be_read_for_one_person(tenant):
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])
    emp = make_employee(tenant, first_name="Nia", last_name="Okoro")
    make_employee(tenant, first_name="Someone", last_name="Else")

    rows = tenant.get(f"/api/employees/{emp['id']}/workflow-tasks").json()
    assert len(rows) == 3


# --- the employee's own list --------------------------------------------------

def test_a_person_sees_only_what_was_asked_of_them(tenant):
    """Three steps, one of them theirs. The other two are HR's business."""
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])
    emp = make_employee(tenant, first_name="Nia", last_name="Okoro",
                        password="EmpPass123")

    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": emp["email"], "password": "EmpPass123"})
    rows = tenant.get("/api/employee/tasks").json()
    assert [r["title"] for r in rows] == ["Read the handbook"]


def test_a_person_can_tick_off_their_own(tenant):
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])
    emp = make_employee(tenant, first_name="Nia", last_name="Okoro",
                        password="EmpPass123")

    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": emp["email"], "password": "EmpPass123"})
    tid = tenant.get("/api/employee/tasks").json()[0]["id"]
    assert tenant.post(f"/api/employee/tasks/{tid}/done").status_code == 200


def test_a_person_cannot_tick_off_hrs_task(tenant):
    """Ordering the laptop is not theirs to declare done."""
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])
    emp = make_employee(tenant, first_name="Nia", last_name="Okoro",
                        password="EmpPass123")

    hr_task = next(t for t in tasks(tenant) if t["owner"] == "hr")

    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": emp["email"], "password": "EmpPass123"})
    assert tenant.post(f"/api/employee/tasks/{hr_task['id']}/done").status_code == 404


def test_a_person_cannot_reach_a_colleagues_task(tenant):
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    theirs = make_employee(tenant, first_name="Sam", last_name="Ali",
                           password="EmpPass123")

    their_task = next(t for t in tasks(tenant)
                      if t["employee"] == "Sam Ali" and t["owner"] == "employee")

    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/login",
                json={"email": mine["email"], "password": "EmpPass123"})
    assert tenant.get("/api/employee/tasks").json()[0]["title"] == "Read the handbook"
    assert len(tenant.get("/api/employee/tasks").json()) == 1
    assert tenant.post(f"/api/employee/tasks/{their_task['id']}/done").status_code == 404


# --- deleting -----------------------------------------------------------------

def test_one_that_never_ran_can_be_deleted(tenant):
    w = make_workflow(tenant)
    assert tenant.delete(f"/api/workflows/{w['id']}").status_code == 200


def test_one_that_has_run_is_turned_off_rather_than_deleted(tenant):
    """Deleting it would take somebody's outstanding tasks with it."""
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])
    make_employee(tenant)

    res = tenant.delete(f"/api/workflows/{w['id']}")
    assert res.status_code == 409
    assert "off" in res.json()["detail"].lower()


# --- it must not get in the way -----------------------------------------------

def test_a_broken_workflow_does_not_stop_somebody_being_hired(tenant, monkeypatch):
    """The hire is the real work. A checklist that refuses to be written is a
    reason to log something, not a reason to fail the hire."""
    w = make_workflow(tenant)
    turn_on(tenant, w["id"])

    def explode(*a, **k):
        raise RuntimeError("workflow engine fell over")

    monkeypatch.setattr(main.models, "DBWorkflowRun", explode)

    emp = make_employee(tenant, first_name="Still", last_name="Hired")
    assert emp["id"]
    with main.SessionLocal() as db:
        assert db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp["id"]).first() is not None


# --- who can see what ---------------------------------------------------------

def test_workflows_are_the_tenants_own(tenant):
    import uuid
    from fastapi.testclient import TestClient
    make_workflow(tenant)

    with TestClient(main.app) as other:
        main.rate_limiter._hits.clear()
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"})
        assert other.get("/api/workflows").json() == []
        assert other.get("/api/workflow-tasks").json() == []


def test_workflows_need_a_session(client):
    assert client.get("/api/workflows").status_code in (401, 403)
    assert client.get("/api/workflow-tasks").status_code in (401, 403)
    assert client.get("/api/employee/tasks").status_code == 401
