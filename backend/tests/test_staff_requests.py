"""Employees being able to answer back, and to ask for anything.

Two gaps with one shape. The portal only talked at people - they could read
that a document had been returned but not ask why. And leave was the only thing
they could raise, so a payslip query or a broken laptop happened over email
where this system never saw it.

A reply is a message on a thread; anything new is a thread of its own.
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


def as_employee(client, emp, password="EmpPass123"):
    main.rate_limiter._hits.clear()
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": password})
    assert res.status_code == 200, res.text


def as_owner(client, account):
    main.rate_limiter._hits.clear()
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


@pytest.fixture
def staff(tenant):
    return make_employee(tenant, first_name="Sarah", last_name="Daley",
                         password="EmpPass123")


def raise_request(client, **body):
    body.setdefault("subject", "My payslip looks wrong")
    body.setdefault("message", "August tax looks higher than July.")
    res = client.post("/api/employee/requests", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# --- raising something that is not leave --------------------------------------

def test_an_employee_can_raise_a_request(client, tenant, staff, account):
    as_employee(client, staff)
    req = raise_request(client)
    assert req["status"] == "open"
    assert req["subject"] == "My payslip looks wrong"
    assert len(req["messages"]) == 1
    assert req["messages"][0]["author"] == "employee"
    assert "August tax" in req["messages"][0]["body"]
    as_owner(client, account)


def test_a_request_needs_a_subject_and_a_body(client, tenant, staff, account):
    as_employee(client, staff)
    assert client.post("/api/employee/requests",
                       json={"message": "x"}).status_code == 400
    assert client.post("/api/employee/requests",
                       json={"subject": "x"}).status_code == 400
    as_owner(client, account)


def test_an_unknown_category_becomes_other(client, tenant, staff, account):
    """Rather than refusing a request over a dropdown value."""
    as_employee(client, staff)
    req = raise_request(client, category="something-else")
    assert req["category"] == "other"
    as_owner(client, account)


def test_they_see_their_own_requests(client, tenant, staff, account):
    as_employee(client, staff)
    raise_request(client, subject="First")
    raise_request(client, subject="Second")
    listing = client.get("/api/employee/requests").json()
    assert {r["subject"] for r in listing["requests"]} == {"First", "Second"}
    as_owner(client, account)


def test_a_request_can_point_at_a_document(client, tenant, staff, account):
    """So HR can see what they were looking at when they asked."""
    with main.SessionLocal() as db:
        doc = db.query(models.DBDocumentRequest).filter(
            models.DBDocumentRequest.employee_id == staff["id"]).first()
        doc_id = doc.id

    as_employee(client, staff)
    req = raise_request(client, subject="Which passport page?",
                        about_document_id=doc_id)
    assert req["about_document_id"] == doc_id
    as_owner(client, account)


def test_it_will_not_attach_to_somebody_elses_document(client, tenant, staff, account):
    """A guessed id must not hang a thread off another person's paperwork."""
    other = make_employee(tenant, password="EmpPass123")
    with main.SessionLocal() as db:
        theirs = db.query(models.DBDocumentRequest).filter(
            models.DBDocumentRequest.employee_id == other["id"]).first()
        theirs_id = theirs.id

    as_employee(client, staff)
    req = raise_request(client, about_document_id=theirs_id)
    assert req["about_document_id"] is None
    as_owner(client, account)


# --- the conversation ---------------------------------------------------------

def test_hr_sees_it_in_the_queue(client, tenant, staff, account):
    as_employee(client, staff)
    raise_request(client)
    as_owner(client, account)

    queue = tenant.get("/api/hr/requests").json()
    assert queue["open_count"] == 1
    row = queue["requests"][0]
    assert row["employee"]["name"] == "Sarah Daley"
    assert row["last_message"]["author"] == "employee"


def test_hr_can_reply_and_the_employee_reads_it(client, tenant, staff, account):
    as_employee(client, staff)
    req = raise_request(client)
    as_owner(client, account)

    res = tenant.post(f"/api/hr/requests/{req['id']}/reply",
                      json={"message": "Your tax code changed in August."})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "answered"

    as_employee(client, staff)
    thread = client.get(f"/api/employee/requests/{req['id']}").json()
    bodies = [m["body"] for m in thread["messages"]]
    assert "Your tax code changed in August." in bodies
    assert thread["messages"][-1]["author"] == "hr"
    as_owner(client, account)


def test_a_reply_is_notified_so_nobody_has_to_go_looking(client, tenant, staff, account):
    as_employee(client, staff)
    req = raise_request(client)
    as_owner(client, account)
    tenant.post(f"/api/hr/requests/{req['id']}/reply", json={"message": "Answered."})

    as_employee(client, staff)
    notes = client.get("/api/employee/notifications").json()["notifications"]
    assert any(n["title"].startswith("Reply:") for n in notes)
    as_owner(client, account)


def test_the_employee_can_answer_back(client, tenant, staff, account):
    """The half that did not exist: the thread goes both ways."""
    as_employee(client, staff)
    req = raise_request(client)
    as_owner(client, account)
    tenant.post(f"/api/hr/requests/{req['id']}/reply", json={"message": "Have a look."})

    as_employee(client, staff)
    res = client.post(f"/api/employee/requests/{req['id']}/reply",
                      json={"message": "That still does not match."})
    assert res.status_code == 200, res.text
    thread = res.json()
    assert thread["messages"][-1]["author"] == "employee"
    assert thread["status"] == "open", "their reply should put it back in the queue"
    as_owner(client, account)


def test_an_empty_reply_is_refused(client, tenant, staff, account):
    as_employee(client, staff)
    req = raise_request(client)
    res = client.post(f"/api/employee/requests/{req['id']}/reply",
                      json={"message": "   "})
    assert res.status_code == 400
    as_owner(client, account)


def test_closing_ends_the_thread(client, tenant, staff, account):
    as_employee(client, staff)
    req = raise_request(client)
    as_owner(client, account)

    tenant.post(f"/api/hr/requests/{req['id']}/reply",
                json={"message": "Sorted.", "close": True})

    as_employee(client, staff)
    res = client.post(f"/api/employee/requests/{req['id']}/reply",
                      json={"message": "one more thing"})
    assert res.status_code == 409
    assert "closed" in res.json()["detail"].lower()
    as_owner(client, account)


def test_the_queue_can_be_filtered(client, tenant, staff, account):
    as_employee(client, staff)
    a = raise_request(client, subject="Still open")
    b = raise_request(client, subject="Will be answered")
    as_owner(client, account)
    tenant.post(f"/api/hr/requests/{b['id']}/reply", json={"message": "Done."})

    open_only = tenant.get("/api/hr/requests?status=open").json()["requests"]
    assert [r["subject"] for r in open_only] == ["Still open"]


# --- isolation ----------------------------------------------------------------

def test_an_employee_cannot_read_another_thread(client, tenant, staff, account):
    other = make_employee(tenant, password="EmpPass123")
    as_employee(client, other)
    theirs = raise_request(client, subject="Private matter")

    as_employee(client, staff)
    assert client.get(f"/api/employee/requests/{theirs['id']}").status_code == 404
    assert client.post(f"/api/employee/requests/{theirs['id']}/reply",
                       json={"message": "hello"}).status_code == 404
    as_owner(client, account)


def test_hr_cannot_read_another_business_thread(client, tenant, staff, account):
    as_employee(client, staff)
    mine = raise_request(client, subject="Ours")
    as_owner(client, account)

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    assert client.get(f"/api/hr/requests/{mine['id']}").status_code == 404
    assert client.post(f"/api/hr/requests/{mine['id']}/reply",
                       json={"message": "peeking"}).status_code == 404
    assert client.get("/api/hr/requests").json()["requests"] == []


def test_it_needs_a_session(client):
    assert client.get("/api/employee/requests").status_code == 401
    assert client.post("/api/employee/requests",
                       json={"subject": "x", "message": "y"}).status_code == 401
