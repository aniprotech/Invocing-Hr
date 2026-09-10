"""Changing a checklist after you have written it.

There was no way to do this. A workflow could be created, switched on and off,
and deleted - and deleting is refused once it has run for somebody, because
the tasks it made are still theirs. So the first version anybody wrote was the
one they were stuck with for good: a typo in a step, or a checklist that
turned out to need one more line, meant leaving it wrong or switching the
whole thing off and starting again under a new name.

The rule that makes editing safe was already in the model. A task copies its
title and owner when it is made and holds no reference back to the step it
came from, so nothing points at the old rows. Editing changes what the next
person gets and cannot reach back into what was asked of somebody last month.

The one thing it will not do is move an already-run workflow to a different
trigger. A workflow fires once per person ever - that is what stops a
corrected status producing two sets of tasks - so re-pointing it would leave
it permanently dead for everybody it had already run for. They would reach the
new trigger and be skipped, and nothing would say so.
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


def a_workflow(tenant, steps=None, trigger="employee_joins", name=None):
    res = tenant.post("/api/workflows", json={
        "name": name or f"Flow {uuid.uuid4().hex[:6]}",
        "trigger": trigger,
        "steps": steps if steps is not None else [
            {"title": "Order a laptop", "owner": "hr", "due_offset_days": -3}]})
    assert res.status_code == 200, res.text
    return res.json()


def turn_on(tenant, flow_id):
    assert tenant.put(f"/api/workflows/{flow_id}/active",
                      json={"active": True}).status_code == 200


def steps_of(tenant, flow_id):
    return tenant.get(f"/api/workflows/{flow_id}").json()["steps"]


def tasks(tenant):
    return tenant.get("/api/workflow-tasks").json()


# --- the thing that was impossible ------------------------------------------------

def test_a_step_can_be_reworded(tenant):
    flow = a_workflow(tenant, steps=[{"title": "Oder a laptop", "owner": "hr"}])
    res = tenant.put(f"/api/workflows/{flow['id']}", json={
        "steps": [{"title": "Order a laptop", "owner": "hr"}]})
    assert res.status_code == 200, res.text
    assert [st["title"] for st in steps_of(tenant, flow["id"])] == ["Order a laptop"]


def test_a_step_can_be_added(tenant):
    flow = a_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    tenant.put(f"/api/workflows/{flow['id']}", json={"steps": [
        {"title": "Order a laptop", "owner": "hr"},
        {"title": "Book an induction", "owner": "manager", "due_offset_days": 1}]})
    got = steps_of(tenant, flow["id"])
    assert [st["title"] for st in got] == ["Order a laptop", "Book an induction"]
    assert got[1]["owner"] == "manager"
    assert got[1]["due_offset_days"] == 1


def test_a_step_can_be_removed(tenant):
    flow = a_workflow(tenant, steps=[
        {"title": "Order a laptop", "owner": "hr"},
        {"title": "Book an induction", "owner": "hr"}])
    tenant.put(f"/api/workflows/{flow['id']}", json={
        "steps": [{"title": "Book an induction", "owner": "hr"}]})
    assert [st["title"] for st in steps_of(tenant, flow["id"])] == ["Book an induction"]


def test_steps_can_be_reordered(tenant):
    flow = a_workflow(tenant, steps=[
        {"title": "First", "owner": "hr"},
        {"title": "Second", "owner": "hr"}])
    tenant.put(f"/api/workflows/{flow['id']}", json={"steps": [
        {"title": "Second", "owner": "hr"},
        {"title": "First", "owner": "hr"}]})
    got = steps_of(tenant, flow["id"])
    assert [st["title"] for st in got] == ["Second", "First"]
    # Position is what the order is read back by, so it has to be rewritten
    # rather than left as it was.
    assert [st["position"] for st in got] == [0, 1]


def test_the_old_rows_are_gone_rather_than_piling_up(tenant):
    """Replaced, not appended. A checklist that grew a second copy of every
    step each time it was saved would be worse than not being editable."""
    flow = a_workflow(tenant, steps=[{"title": "One", "owner": "hr"}])
    for _ in range(3):
        tenant.put(f"/api/workflows/{flow['id']}",
                   json={"steps": [{"title": "One", "owner": "hr"}]})
    with main.SessionLocal() as db:
        rows = db.query(models.DBWorkflowStep).filter(
            models.DBWorkflowStep.workflow_id == flow["id"]).count()
    assert rows == 1, rows


def test_the_name_and_description_can_be_changed(tenant):
    flow = a_workflow(tenant, name="New staretr")
    res = tenant.put(f"/api/workflows/{flow['id']}", json={
        "name": "New starter", "description": "What happens on day one"})
    assert res.status_code == 200
    got = tenant.get(f"/api/workflows/{flow['id']}").json()
    assert got["name"] == "New starter"
    assert got["description"] == "What happens on day one"


def test_editing_one_thing_leaves_the_rest_alone(tenant):
    """A rename must not blank the steps just because it did not mention
    them."""
    flow = a_workflow(tenant, name="Before",
                      steps=[{"title": "Order a laptop", "owner": "manager"}])
    tenant.put(f"/api/workflows/{flow['id']}", json={"name": "After"})
    got = tenant.get(f"/api/workflows/{flow['id']}").json()
    assert got["name"] == "After"
    assert [st["title"] for st in got["steps"]] == ["Order a laptop"]
    assert got["steps"][0]["owner"] == "manager"


# --- and what it must not touch ----------------------------------------------------

def test_a_task_already_issued_does_not_change(tenant):
    """The invariant the whole design rests on. Somebody was asked to order a
    laptop; editing the template next month must not rewrite their list."""
    flow = a_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    turn_on(tenant, flow["id"])
    make_employee(tenant, first_name="Nia", last_name="Okoro")

    tenant.put(f"/api/workflows/{flow['id']}", json={
        "steps": [{"title": "Order a desktop instead", "owner": "hr"}]})

    assert [t["title"] for t in tasks(tenant)] == ["Order a laptop"]


def test_removing_a_step_does_not_remove_the_task_it_made(tenant):
    """Deleting the row a task came from must not delete the task. Somebody
    may already have done it, and the record of that is the point."""
    flow = a_workflow(tenant, steps=[
        {"title": "Order a laptop", "owner": "hr"},
        {"title": "Book an induction", "owner": "hr"}])
    turn_on(tenant, flow["id"])
    make_employee(tenant)
    assert len(tasks(tenant)) == 2

    tenant.put(f"/api/workflows/{flow['id']}", json={
        "steps": [{"title": "Book an induction", "owner": "hr"}]})

    assert sorted(t["title"] for t in tasks(tenant)) == [
        "Book an induction", "Order a laptop"]


def test_the_next_person_gets_the_new_version(tenant):
    """The reason to edit at all."""
    flow = a_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    turn_on(tenant, flow["id"])
    first = make_employee(tenant, first_name="First", last_name="In")

    tenant.put(f"/api/workflows/{flow['id']}", json={"steps": [
        {"title": "Order a laptop", "owner": "hr"},
        {"title": "Order a chair", "owner": "hr"}]})
    second = make_employee(tenant, first_name="Second", last_name="In")

    mine = [t["title"] for t in tasks(tenant) if t["employee_id"] == first["id"]]
    theirs = [t["title"] for t in tasks(tenant) if t["employee_id"] == second["id"]]
    assert mine == ["Order a laptop"]
    assert sorted(theirs) == ["Order a chair", "Order a laptop"]


# --- the trigger ---------------------------------------------------------------------

def test_the_trigger_can_be_changed_before_it_has_run(tenant):
    flow = a_workflow(tenant, trigger="employee_joins")
    res = tenant.put(f"/api/workflows/{flow['id']}",
                     json={"trigger": "employee_leaves"})
    assert res.status_code == 200, res.text
    assert tenant.get(f"/api/workflows/{flow['id']}").json()["trigger"] == "employee_leaves"


def test_but_not_after(tenant):
    """It fires once per person ever. Re-pointing it would leave it silently
    dead for everybody it had already run for - they reach the new trigger and
    are skipped, and nothing says so."""
    flow = a_workflow(tenant, trigger="employee_joins")
    turn_on(tenant, flow["id"])
    make_employee(tenant)

    res = tenant.put(f"/api/workflows/{flow['id']}",
                     json={"trigger": "employee_leaves"})
    assert res.status_code == 409, res.text
    assert "never fire again" in res.json()["detail"]
    assert tenant.get(f"/api/workflows/{flow['id']}").json()["trigger"] == "employee_joins"


def test_saying_the_same_trigger_is_not_a_change(tenant):
    """Re-saving an unedited form sends every field back. Refusing that would
    make an already-run workflow uneditable again, which is the problem this
    exists to fix."""
    flow = a_workflow(tenant, trigger="employee_joins")
    turn_on(tenant, flow["id"])
    make_employee(tenant)

    res = tenant.put(f"/api/workflows/{flow['id']}", json={
        "name": "Renamed", "trigger": "employee_joins",
        "steps": [{"title": "Order a laptop", "owner": "hr"}]})
    assert res.status_code == 200, res.text
    assert tenant.get(f"/api/workflows/{flow['id']}").json()["name"] == "Renamed"


def test_a_trigger_that_does_not_exist_is_refused(tenant):
    flow = a_workflow(tenant)
    assert tenant.put(f"/api/workflows/{flow['id']}",
                      json={"trigger": "when_i_feel_like_it"}).status_code == 400


# --- what cannot be saved ------------------------------------------------------------

def test_a_workflow_cannot_be_emptied_of_steps(tenant):
    """A workflow with no steps is switched on, fires, and does nothing. There
    is no state it could be in where that is what somebody meant."""
    flow = a_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    res = tenant.put(f"/api/workflows/{flow['id']}", json={"steps": []})
    assert res.status_code == 400, res.text
    assert [st["title"] for st in steps_of(tenant, flow["id"])] == ["Order a laptop"]


def test_blank_titles_do_not_count_as_steps(tenant):
    flow = a_workflow(tenant, steps=[{"title": "Order a laptop", "owner": "hr"}])
    res = tenant.put(f"/api/workflows/{flow['id']}", json={
        "steps": [{"title": "   ", "owner": "hr"}]})
    assert res.status_code == 400, res.text
    assert [st["title"] for st in steps_of(tenant, flow["id"])] == ["Order a laptop"]


def test_a_blank_name_is_refused(tenant):
    flow = a_workflow(tenant, name="Has a name")
    assert tenant.put(f"/api/workflows/{flow['id']}",
                      json={"name": "  "}).status_code == 400
    assert tenant.get(f"/api/workflows/{flow['id']}").json()["name"] == "Has a name"


def test_an_unknown_owner_falls_back_to_hr_rather_than_failing(tenant):
    """Same as creating. Losing the whole edit over one bad dropdown value is
    worse than the step being HR's."""
    flow = a_workflow(tenant)
    tenant.put(f"/api/workflows/{flow['id']}", json={
        "steps": [{"title": "Order a laptop", "owner": "the_ceo"}]})
    assert steps_of(tenant, flow["id"])[0]["owner"] == "hr"


# --- whose workflow it is --------------------------------------------------------------

def test_another_business_cannot_edit_it(tenant, client, account):
    flow = a_workflow(tenant, name="Mine")

    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={
        "email": email, "password": "Passw0rdTest"})

    assert client.put(f"/api/workflows/{flow['id']}",
                      json={"name": "Theirs now"}).status_code == 404

    client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert tenant.get(f"/api/workflows/{flow['id']}").json()["name"] == "Mine"


def test_editing_a_workflow_that_does_not_exist_is_a_404(tenant):
    assert tenant.put("/api/workflows/999999",
                      json={"name": "Nope"}).status_code == 404


# --- the named person survives an edit ---------------------------------------------------

def test_a_named_person_is_kept_through_an_edit(tenant):
    it = make_employee(tenant, first_name="Jo", last_name="Tech")
    flow = a_workflow(tenant)
    tenant.put(f"/api/workflows/{flow['id']}", json={"steps": [
        {"title": "Set up the laptop", "owner": "person",
         "owner_employee_id": it["id"]}]})
    got = steps_of(tenant, flow["id"])[0]
    assert got["owner"] == "person"
    assert got["owner_employee_id"] == it["id"]


def test_an_edit_cannot_name_another_businesss_employee(tenant, client, account):
    flow = a_workflow(tenant)

    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={
        "email": email, "password": "Passw0rdTest"})
    outsider = make_employee(client, first_name="Not", last_name="Yours")
    client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})

    tenant.put(f"/api/workflows/{flow['id']}", json={"steps": [
        {"title": "Set up the laptop", "owner": "person",
         "owner_employee_id": outsider["id"]}]})
    got = steps_of(tenant, flow["id"])[0]
    assert got["owner"] == "hr"
    assert got["owner_employee_id"] is None


def test_notes_on_a_step_survive_an_edit(tenant):
    """There is no field for notes on the form, so an edit rebuilds each step
    without them. Carried through rather than read back, or renaming a
    workflow would blank the notes on every step of it."""
    flow = a_workflow(tenant, steps=[
        {"title": "Order a laptop", "owner": "hr", "notes": "16GB, not 8"}])
    tenant.put(f"/api/workflows/{flow['id']}", json={"steps": [
        {"title": "Order a laptop", "owner": "hr", "notes": "16GB, not 8"}]})
    assert steps_of(tenant, flow["id"])[0]["notes"] == "16GB, not 8"


def test_a_step_created_with_a_named_person_keeps_them(tenant):
    """The create path dropped owner_employee_id on the way to the server, so
    choosing a named person stored an HR step and the dropdown looked like it
    had worked."""
    it = make_employee(tenant, first_name="Jo", last_name="Tech")
    flow = a_workflow(tenant, steps=[
        {"title": "Set up the laptop", "owner": "person",
         "owner_employee_id": it["id"]}])
    got = steps_of(tenant, flow["id"])[0]
    assert got["owner"] == "person", got
    assert got["owner_employee_id"] == it["id"], got
