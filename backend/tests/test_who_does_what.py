"""Working out who a workflow task actually belongs to.

A step could be owned by "hr", "manager" or "employee". That string was
written onto the task and left there, and nothing ever turned it into a
person. For "manager" the consequence was total: the portal asked for tasks
where owner='employee', and no manager-facing list existed anywhere in the
application, so a task aimed at somebody's manager was returned by no query at
all. It sat in HR's list looking like HR's job.

Nothing about it looked broken. The task existed, the workflow had run, the
count was right. It was simply addressed to a role that no screen resolved.

So the role is turned into a person when the workflow fires, and written down.
Two reasons it happens then and not when somebody looks:

  - It is a fact about the moment. Who your manager was when you joined is
    what the checklist meant, and it stays true after you change team.
  - Something has to happen when there is no answer. Resolving late means a
    person with no manager makes a task no query returns, which is the same
    disappearance in a new place. Resolving early forces the fallback to be
    written down, and a null assignee is the HR pool on purpose.
"""
import uuid

import pytest

import main
import models
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def sign_in(tenant, emp):
    main.rate_limiter._hits.clear()
    res = tenant.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text
    return res


def other_business(client):
    """A second business on the same test client, signed in. There is no
    two-tenant fixture; this is how the rest of the suite does it."""
    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={
        "email": email, "password": "Passw0rdTest"})
    return client


def a_workflow(tenant, steps, trigger="employee_joins", name=None):
    res = tenant.post("/api/workflows", json={
        "name": name or f"Flow {uuid.uuid4().hex[:6]}",
        "trigger": trigger, "steps": steps})
    assert res.status_code == 200, res.text
    flow = res.json()
    assert tenant.put(f"/api/workflows/{flow['id']}/active",
                      json={"active": True}).status_code == 200
    return flow


def hire(tenant, **kw):
    """Somebody joining, which is what fires an employee_joins workflow."""
    return person(tenant, **kw)


def tasks_for(tenant, employee_id):
    rows = tenant.get("/api/workflow-tasks").json()
    return [t for t in rows if t["employee_id"] == employee_id]


# --- the one that was invisible -------------------------------------------------

def test_a_step_owned_by_manager_lands_on_the_actual_manager(tenant):
    boss = person(tenant, first_name="Dana", last_name="Boss")
    a_workflow(tenant, [{"title": "Book a first-week catch-up",
                         "owner": "manager", "due_offset_days": 2}])
    joiner = hire(tenant, first_name="Sam", last_name="New",
                  reports_to=boss["id"])

    got = tasks_for(tenant, joiner["id"])
    assert len(got) == 1, got
    assert got[0]["assignee_id"] == boss["id"], got[0]
    assert got[0]["assigned_how"] == "manager"
    assert got[0]["assignee"] == "Dana Boss"


def test_and_that_manager_can_actually_see_it(tenant):
    """The whole point. Before this there was no query that returned it."""
    boss = person(tenant, first_name="Dana", last_name="Boss")
    a_workflow(tenant, [{"title": "Book a first-week catch-up", "owner": "manager"}])
    joiner = hire(tenant, first_name="Sam", last_name="New", reports_to=boss["id"])

    sign_in(tenant, boss)
    mine = tenant.get("/api/employee/team-tasks").json()
    assert [t["title"] for t in mine] == ["Book a first-week catch-up"], mine
    assert mine[0]["about"] == "Sam New"


def test_the_manager_can_tick_it_off(tenant):
    boss = person(tenant)
    a_workflow(tenant, [{"title": "Order a laptop", "owner": "manager"}])
    hire(tenant, reports_to=boss["id"])

    sign_in(tenant, boss)
    task = tenant.get("/api/employee/team-tasks").json()[0]
    assert tenant.post(f"/api/employee/team-tasks/{task['id']}/done").status_code == 200
    assert tenant.get("/api/employee/team-tasks").json()[0]["done"] is True


def test_it_is_not_mixed_into_the_persons_own_list(tenant):
    """Things you owe about other people are a different list from things
    asked of you. Merging them means a manager's own induction is buried in
    other people's paperwork."""
    boss = person(tenant)
    a_workflow(tenant, [{"title": "Meet your new report", "owner": "manager"}])
    hire(tenant, reports_to=boss["id"])

    sign_in(tenant, boss)
    assert tenant.get("/api/employee/tasks").json() == []
    assert len(tenant.get("/api/employee/team-tasks").json()) == 1


# --- when there is no answer ----------------------------------------------------

def test_somebody_with_no_manager_does_not_make_a_task_for_nobody(tenant):
    """The failure that has to be loud. A null assignee is the HR pool, and
    saying which fallback it was is the difference between "HR owns this" and
    "this was meant for a manager who does not exist"."""
    a_workflow(tenant, [{"title": "Book a first-week catch-up", "owner": "manager"}])
    joiner = hire(tenant, first_name="Alone", last_name="Here")

    got = tasks_for(tenant, joiner["id"])
    assert len(got) == 1
    assert got[0]["assignee_id"] is None
    assert got[0]["assigned_how"] == "no_manager"
    # Picked out of a list of three hundred, because it is a workflow that
    # meant to reach somebody and could not.
    assert got[0]["unrouted"] is True
    assert "no manager" in got[0]["assigned_how_label"]


def test_an_hr_step_is_not_reported_as_a_routing_failure(tenant):
    """HR owning something is the intention, not a fallback. Flagging it would
    make the warning meaningless by making it universal."""
    a_workflow(tenant, [{"title": "File the contract", "owner": "hr"}])
    joiner = hire(tenant)

    got = tasks_for(tenant, joiner["id"])
    assert got[0]["assignee_id"] is None
    assert got[0]["unrouted"] is False


# --- the department head --------------------------------------------------------

def department(tenant, name=None):
    res = tenant.post("/api/departments",
                      json={"name": name or f"Dept {uuid.uuid4().hex[:6]}"})
    assert res.status_code == 200, res.text
    return res.json()


def test_a_step_can_be_aimed_at_the_head_of_their_department(tenant):
    dept = department(tenant)
    head = person(tenant, first_name="Ravi", last_name="Head",
                  department_id=dept["id"])
    assert tenant.put(f"/api/departments/{dept['id']}/head",
                      json={"head_id": head["id"]}).status_code == 200

    a_workflow(tenant, [{"title": "Approve the tools budget",
                         "owner": "department_head"}])
    joiner = hire(tenant, department_id=dept["id"])

    got = tasks_for(tenant, joiner["id"])
    assert got[0]["assignee_id"] == head["id"]
    assert got[0]["assigned_how"] == "department_head"


def test_a_department_with_no_head_falls_back_and_says_so(tenant):
    dept = department(tenant)
    a_workflow(tenant, [{"title": "Approve the tools budget",
                         "owner": "department_head"}])
    joiner = hire(tenant, department_id=dept["id"])

    got = tasks_for(tenant, joiner["id"])
    assert got[0]["assignee_id"] is None
    assert got[0]["assigned_how"] == "no_department_head"
    assert got[0]["unrouted"] is True


def test_the_head_is_not_asked_to_sign_off_their_own_arrival(tenant):
    """A rubber stamp is not a control. If the person the task is about is the
    one who would approve it, it goes to HR instead."""
    dept = department(tenant)
    head = person(tenant, department_id=dept["id"])
    tenant.put(f"/api/departments/{dept['id']}/head", json={"head_id": head["id"]})

    a_workflow(tenant, [{"title": "Approve the tools budget",
                         "owner": "department_head"},
                        {"title": "Say hello", "owner": "employee"}],
               trigger="employee_leaves")
    # This is what fires a leaver workflow - a status edit does not.
    assert tenant.post(f"/api/employees/{head['id']}/offboard").status_code == 200

    got = [t for t in tasks_for(tenant, head["id"])
           if t["title"] == "Approve the tools budget"]
    assert got, tasks_for(tenant, head["id"])
    assert got[0]["assignee_id"] is None
    assert got[0]["assigned_how"] == "head_is_the_subject"


# --- a named person -------------------------------------------------------------

def test_a_step_can_name_one_person(tenant):
    it = person(tenant, first_name="Jo", last_name="Tech")
    a_workflow(tenant, [{"title": "Set up the laptop", "owner": "person",
                         "owner_employee_id": it["id"]}])
    joiner = hire(tenant)

    got = tasks_for(tenant, joiner["id"])
    assert got[0]["assignee_id"] == it["id"]
    assert got[0]["assigned_how"] == "person"


def test_naming_nobody_is_stored_as_an_hr_step(tenant):
    """Rejecting it outright would lose the rest of the workflow over one
    empty dropdown; keeping owner='person' with no person would make unowned
    tasks every time it ran. Saying now that it is HR's is the honest option."""
    flow = a_workflow(tenant, [{"title": "Set up the laptop", "owner": "person"}])
    steps = tenant.get(f"/api/workflows/{flow['id']}").json()["steps"]
    assert steps[0]["owner"] == "hr"
    assert steps[0]["owner_employee_id"] is None


def test_a_step_cannot_name_another_businesss_employee(client, tenant, account):
    """The step is saved by one business and would otherwise put a task on
    somebody else's staff list."""
    outsider = person(other_business(client), first_name="Not", last_name="Yours")
    # The two businesses share one TestClient, so signing the second one in
    # signed the first one out. Back to the business under test.
    assert client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]
    }).status_code == 200
    flow = a_workflow(tenant, [{"title": "Set up the laptop", "owner": "person",
                                "owner_employee_id": outsider["id"]}])
    steps = tenant.get(f"/api/workflows/{flow['id']}").json()["steps"]
    assert steps[0]["owner"] == "hr"
    assert steps[0]["owner_employee_id"] is None


def test_when_the_named_person_has_left_it_goes_to_hr(tenant):
    """The common way a template rots. Without this the task lands on a leaver
    whose list nobody opens again."""
    it = person(tenant, first_name="Jo", last_name="Tech")
    a_workflow(tenant, [{"title": "Set up the laptop", "owner": "person",
                         "owner_employee_id": it["id"]}])
    tenant.put(f"/api/employees/{it['id']}", json={"status": "terminated"})

    joiner = hire(tenant)
    got = tasks_for(tenant, joiner["id"])
    assert got[0]["assignee_id"] is None
    assert got[0]["assigned_how"] == "person_gone"
    assert got[0]["unrouted"] is True


# --- the person themselves still works ------------------------------------------

def test_their_own_tasks_are_still_theirs(tenant):
    a_workflow(tenant, [{"title": "Read the handbook", "owner": "employee"}])
    joiner = hire(tenant)

    sign_in(tenant, joiner)
    mine = tenant.get("/api/employee/tasks").json()
    assert [t["title"] for t in mine] == ["Read the handbook"]
    assert tenant.get("/api/employee/team-tasks").json() == []


def test_and_they_can_still_tick_them_off(tenant):
    a_workflow(tenant, [{"title": "Read the handbook", "owner": "employee"}])
    joiner = hire(tenant)

    sign_in(tenant, joiner)
    task = tenant.get("/api/employee/tasks").json()[0]
    assert tenant.post(f"/api/employee/tasks/{task['id']}/done").status_code == 200
    assert tenant.get("/api/employee/tasks").json()[0]["done"] is True


# --- who may not touch it -------------------------------------------------------

def test_somebody_elses_manager_cannot_see_the_task(client, tenant):
    boss = person(tenant)
    a_workflow(tenant, [{"title": "Book a catch-up", "owner": "manager"}])
    hire(tenant, reports_to=boss["id"])

    other = other_business(client)
    outsider = person(other)
    sign_in(other, outsider)
    assert other.get("/api/employee/team-tasks").json() == []


def test_a_colleague_cannot_tick_off_a_task_that_is_not_theirs(tenant):
    """It is addressed to one person. Anybody signed in could otherwise close
    somebody else's obligation and the record would say they did it."""
    boss = person(tenant)
    bystander = person(tenant)
    a_workflow(tenant, [{"title": "Book a catch-up", "owner": "manager"}])
    joiner = hire(tenant, reports_to=boss["id"])

    task = tasks_for(tenant, joiner["id"])[0]
    sign_in(tenant, bystander)
    assert tenant.post(
        f"/api/employee/team-tasks/{task['id']}/done").status_code == 404
    assert tenant.post(
        f"/api/employee/tasks/{task['id']}/done").status_code == 404


def test_the_subject_cannot_close_their_own_managers_task(tenant):
    """A joiner ticking off "check their right to work" is the control
    defeating itself."""
    boss = person(tenant)
    a_workflow(tenant, [{"title": "Check right to work", "owner": "manager"}])
    joiner = hire(tenant, reports_to=boss["id"])

    task = tasks_for(tenant, joiner["id"])[0]
    sign_in(tenant, joiner)
    assert tenant.post(
        f"/api/employee/team-tasks/{task['id']}/done").status_code == 404
    assert tenant.post(
        f"/api/employee/tasks/{task['id']}/done").status_code == 404


# --- being told ------------------------------------------------------------------

def test_the_manager_hears_about_it(tenant):
    """Otherwise they find out by happening to look, which for a joiner
    checklist is usually after the joiner has arrived."""
    boss = person(tenant, first_name="Dana", last_name="Boss")
    a_workflow(tenant, [{"title": "Book a first-week catch-up", "owner": "manager"}],
               name="New starter")
    hire(tenant, first_name="Sam", last_name="New", reports_to=boss["id"])

    sign_in(tenant, boss)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("Sam New" in (n["title"] + n["message"]) for n in notes), notes


def test_two_tasks_for_one_manager_are_one_notification(tenant):
    """Three steps for the same person is one arrival, not three alerts."""
    boss = person(tenant)
    a_workflow(tenant, [
        {"title": "Book a catch-up", "owner": "manager"},
        {"title": "Order a laptop", "owner": "manager"},
        {"title": "Set objectives", "owner": "manager"},
    ], name="New starter")
    hire(tenant, reports_to=boss["id"])

    sign_in(tenant, boss)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    mine = [n for n in notes if "New starter" in n["message"]]
    assert len(mine) == 1, mine
    assert "3 things" in mine[0]["title"], mine[0]


# --- the team list ----------------------------------------------------------------

def test_a_manager_can_see_who_reports_to_them(tenant):
    """The hierarchy was only ever read by HR's org chart. Somebody with
    reports had no way to see them from their own portal."""
    boss = person(tenant)
    person(tenant, first_name="One", last_name="Report", reports_to=boss["id"])
    person(tenant, first_name="Two", last_name="Report", reports_to=boss["id"])
    person(tenant, first_name="Not", last_name="Mine")

    sign_in(tenant, boss)
    team = tenant.get("/api/employee/my-team").json()
    assert team["count"] == 2, team
    assert sorted(t["name"] for t in team["team"]) == ["One Report", "Two Report"]


def test_somebody_with_no_reports_gets_an_empty_team(tenant):
    lone = person(tenant)
    sign_in(tenant, lone)
    team = tenant.get("/api/employee/my-team").json()
    assert team["count"] == 0
    assert team["team"] == []
