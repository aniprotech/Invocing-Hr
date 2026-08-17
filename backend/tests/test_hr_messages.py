"""HR being able to say something.

Every notification an employee saw was raised by the system - a goal assigned,
a document reviewed, leave actioned. Anything that did not fit one of those
happened over email and left no trace in the portal.

The chase is the one that matters for onboarding: instead of "please send your
documents", it names them, says which are required, and repeats why anything
was returned.
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


def inbox(client, emp, password="EmpPass123"):
    """What this employee sees in their portal."""
    main.rate_limiter._hits.clear()
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": password})
    assert res.status_code == 200, res.text
    notes = client.get("/api/employee/notifications").json()
    client.post("/api/employee/auth/logout")
    return notes


def back_as_owner(client, account):
    main.rate_limiter._hits.clear()
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


# --- announcements ------------------------------------------------------------

def test_a_message_to_everyone_reaches_everyone(tenant):
    make_employee(tenant)
    make_employee(tenant)
    res = tenant.post("/api/hr/announcements", json={
        "title": "Office closed Friday", "message": "Enjoy the long weekend."})
    assert res.status_code == 200, res.text
    assert res.json()["sent"] == 2


def test_it_arrives_in_the_employee_portal(client, tenant, account):
    emp = make_employee(tenant, password="EmpPass123")
    tenant.post("/api/hr/announcements", json={
        "title": "Office closed Friday", "message": "Enjoy the long weekend."})

    notes = inbox(client, emp)
    titles = [n["title"] for n in notes["notifications"]]
    assert "Office closed Friday" in titles
    mine = next(n for n in notes["notifications"] if n["title"] == "Office closed Friday")
    assert mine["message"] == "Enjoy the long weekend."
    assert mine["sent_by"], "the employee should see who it came from"
    assert notes["unread_count"] >= 1
    back_as_owner(client, account)


def test_one_employee_can_be_written_to_alone(client, tenant, account):
    target = make_employee(tenant, password="EmpPass123")
    other = make_employee(tenant, password="EmpPass123")

    res = tenant.post("/api/hr/announcements", json={
        "title": "About your start date", "message": "Come in at 10.",
        "audience": "employee", "employee_id": target["id"]})
    assert res.json()["sent"] == 1

    assert any(n["title"] == "About your start date"
               for n in inbox(client, target)["notifications"])
    back_as_owner(client, account)
    assert not any(n["title"] == "About your start date"
                   for n in inbox(client, other)["notifications"])
    back_as_owner(client, account)


def test_those_still_onboarding_can_be_addressed_together(tenant):
    make_employee(tenant)
    make_employee(tenant)
    res = tenant.post("/api/hr/announcements", json={
        "title": "Welcome", "message": "Please finish your paperwork.",
        "audience": "onboarding"})
    assert res.status_code == 200, res.text
    assert res.json()["sent"] == 2


def test_a_message_needs_a_subject_and_a_body(tenant):
    make_employee(tenant)
    assert tenant.post("/api/hr/announcements", json={"message": "x"}).status_code == 400
    assert tenant.post("/api/hr/announcements", json={"title": "x"}).status_code == 400


def test_choosing_one_employee_without_saying_who_is_refused(tenant):
    make_employee(tenant)
    res = tenant.post("/api/hr/announcements", json={
        "title": "x", "message": "y", "audience": "employee"})
    assert res.status_code == 400


def test_sending_to_nobody_says_so(tenant):
    """Rather than reporting a successful send to an empty room."""
    res = tenant.post("/api/hr/announcements", json={
        "title": "x", "message": "y"})
    assert res.status_code == 400
    assert "Nobody matches" in res.json()["detail"]


def test_a_terminated_employee_is_not_written_to(tenant):
    staying = make_employee(tenant)
    leaving = make_employee(tenant)
    tenant.put(f"/api/employees/{leaving['id']}", json={"status": "terminated"})

    res = tenant.post("/api/hr/announcements", json={
        "title": "Team lunch", "message": "Thursday."})
    assert res.json()["sent"] == 1


def test_announcements_do_not_cross_between_businesses(client, tenant):
    make_employee(tenant)

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    make_employee(client)

    res = client.post("/api/hr/announcements", json={
        "title": "Ours only", "message": "internal"})
    assert res.json()["sent"] == 1, "it reached another company's staff"


# --- chasing the paperwork ----------------------------------------------------

def document_requests_for(tenant, emp_id):
    """The obligations, which is not the same list as the files uploaded."""
    with main.SessionLocal() as db:
        return [r.id for r in db.query(models.DBDocumentRequest).filter(
            models.DBDocumentRequest.employee_id == emp_id).all()]


def test_the_chase_names_the_documents(client, tenant, account):
    emp = make_employee(tenant, password="EmpPass123")
    res = tenant.post(f"/api/hr/employees/{emp['id']}/chase-documents", json={})
    assert res.status_code == 200, res.text
    assert res.json()["outstanding"] >= 1

    notes = inbox(client, emp)["notifications"]
    chase = next(n for n in notes if "still needed" in n["title"])
    # Every outstanding document is listed by name, not summarised as a count.
    for name in res.json()["documents"]:
        assert name in chase["message"], name
    back_as_owner(client, account)


def test_the_chase_repeats_why_something_was_returned(client, tenant, account):
    """The employee should not have to go and look up why it came back."""
    emp = make_employee(tenant, password="EmpPass123")
    req_id = document_requests_for(tenant, emp["id"])[0]

    main.rate_limiter._hits.clear()
    client.post("/api/employee/auth/login",
                json={"email": emp["email"], "password": "EmpPass123"})
    client.post(f"/api/employee/document-requests/{req_id}/upload", json={
        "file_name": "passport.pdf", "file_type": "application/pdf",
        "file_data": "data:application/pdf;base64,JVBERi0xLjQK"})
    client.post("/api/employee/auth/logout")
    back_as_owner(client, account)

    tenant.post(f"/api/onboarding/document-requests/{req_id}/review", json={
        "decision": "reject", "note": "The photo page is cut off"})

    tenant.post(f"/api/hr/employees/{emp['id']}/chase-documents", json={})
    notes = inbox(client, emp)["notifications"]
    chase = [n for n in notes if "still needed" in n["title"]][0]
    assert "The photo page is cut off" in chase["message"]
    back_as_owner(client, account)


def test_a_note_can_be_added_to_the_chase(client, tenant, account):
    emp = make_employee(tenant, password="EmpPass123")
    tenant.post(f"/api/hr/employees/{emp['id']}/chase-documents",
                json={"note": "Needed before your first day."})
    notes = inbox(client, emp)["notifications"]
    chase = [n for n in notes if "still needed" in n["title"]][0]
    assert "Needed before your first day." in chase["message"]
    back_as_owner(client, account)


def test_chasing_somebody_with_nothing_outstanding_is_refused(tenant):
    """Otherwise HR sends a demand for nothing and looks careless."""
    emp = make_employee(tenant)
    with main.SessionLocal() as db:
        for r in db.query(models.DBDocumentRequest).filter(
                models.DBDocumentRequest.employee_id == emp["id"]).all():
            r.status = "approved"
        db.commit()

    res = tenant.post(f"/api/hr/employees/{emp['id']}/chase-documents", json={})
    assert res.status_code == 400
    assert "Nothing is outstanding" in res.json()["detail"]


def test_you_cannot_chase_another_business_employee(client, tenant):
    mine = make_employee(tenant)

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    res = client.post(f"/api/hr/employees/{mine['id']}/chase-documents", json={})
    assert res.status_code == 404
