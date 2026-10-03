"""Hire -> credentials -> sandbox -> submit -> verify -> offer letter -> full access."""
import re

import pytest

import main
from conftest import make_employee
from test_onboarding_pipeline import hire_a_candidate


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "email_delivery_ready", lambda db, client_id=None: (True, ""))
    monkeypatch.setattr(
        main, "send_email_background",
        lambda to, subject, body, frm, html=None, pdf_b64=None, pdf_name="", *a, **k:
        sent.append({"to": to, "subject": subject, "body": body, "pdf": pdf_b64}))
    main.rate_limiter._hits.clear()
    return sent


def sign_in_as_hire(client, outbox, hired_email):
    welcome = next(m for m in outbox if m["to"] == hired_email and "Congratulations" in m["subject"])
    password = re.search(r"Temporary password: (\S+)", welcome["body"]).group(1)
    res = client.post("/api/employee/auth/login", json={"email": hired_email, "password": password})
    assert res.status_code == 200, res.text
    return password, res.json()


def hire(client, tenant):
    email = "newhire@example.com"
    hired = hire_a_candidate(client, tenant, email=email)
    return hired, email


def upload_all(client):
    for row in client.get("/api/employee/document-requests").json()["requests"]:
        res = client.post(f"/api/employee/document-requests/{row['id']}/upload", json={
            "file_name": "d.pdf", "file_type": "application/pdf", "file_data": "JVBERi0xLjQK",
            "expires_on": "2099-01-01"})
        assert res.status_code == 200, res.text


def test_hire_sends_credentials_and_locks_the_account(client, tenant, outbox):
    hired, email = hire(client, tenant)
    assert hired["welcome_email"] == "queued"
    _, login = sign_in_as_hire(client, outbox, email)
    assert login["portal_stage"] == "initiated" and login["must_change_password"]
    assert login["clock_in"] == "" and login["auto_clock_in"] is False


def test_nothing_opens_until_the_password_is_changed(client, tenant, outbox):
    _, email = hire(client, tenant)
    password, _ = sign_in_as_hire(client, outbox, email)
    assert client.get("/api/employee/document-requests").status_code == 403
    bad = client.post("/api/employee/preboarding/change-password",
                      json={"current_password": "wrong", "new_password": "Brand-New-Pass1"})
    assert bad.status_code == 400
    ok = client.post("/api/employee/preboarding/change-password",
                     json={"current_password": password, "new_password": "Brand-New-Pass1"})
    assert ok.status_code == 200, ok.text
    assert client.get("/api/employee/document-requests").status_code == 200


def test_the_sandbox_is_uploads_only(client, tenant, outbox):
    _, email = hire(client, tenant)
    password, _ = sign_in_as_hire(client, outbox, email)
    client.post("/api/employee/preboarding/change-password",
                json={"current_password": password, "new_password": "Brand-New-Pass1"})
    for path in ("/api/employee/profile", "/api/employee/payslips", "/api/employee/colleagues",
                 "/api/employee/leave", "/api/feed"):
        assert client.get(path).status_code == 403, path


def test_submit_needs_every_document(client, tenant, outbox):
    _, email = hire(client, tenant)
    password, _ = sign_in_as_hire(client, outbox, email)
    client.post("/api/employee/preboarding/change-password",
                json={"current_password": password, "new_password": "Brand-New-Pass1"})
    assert client.post("/api/employee/preboarding/submit").status_code == 400
    upload_all(client)
    assert client.post("/api/employee/preboarding/submit").status_code == 200
    assert any("ready for review" in m["subject"] for m in outbox)
    # Submitted means read-only: no more uploads while HR is looking.
    first = client.get("/api/employee/document-requests").json()["requests"][0]
    assert client.post(f"/api/employee/document-requests/{first['id']}/upload", json={
        "file_name": "d.pdf", "file_type": "application/pdf",
        "file_data": "JVBERi0xLjQK"}).status_code == 403


def test_reject_reopens_upload_and_approve_opens_everything(client, tenant, outbox):
    hired, email = hire(client, tenant)
    emp_id = hired["employee_id"]
    password, _ = sign_in_as_hire(client, outbox, email)
    client.post("/api/employee/preboarding/change-password",
                json={"current_password": password, "new_password": "Brand-New-Pass1"})
    upload_all(client)
    client.post("/api/employee/preboarding/submit")
    reqs = tenant.get(f"/api/employees/{emp_id}/document-requests").json()

    # Reject one: back to uploading, told by email.
    res = tenant.post(f"/api/onboarding/document-requests/{reqs[0]['id']}/review",
                      json={"decision": "reject", "note": "Blurry"})
    assert res.status_code == 200, res.text
    assert any("re-upload" in m["subject"].lower() for m in outbox)
    assert client.get("/api/employee/preboarding/status").json()["portal_stage"] == "initiated"
    client.post(f"/api/employee/document-requests/{reqs[0]['id']}/upload", json={
        "file_name": "d.pdf", "file_type": "application/pdf", "file_data": "JVBERi0xLjQK",
        "expires_on": "2099-01-01"})
    client.post("/api/employee/preboarding/submit")

    # Approve everything: portal opens and the offer letter goes out together.
    for r in reqs:
        res = tenant.post(f"/api/onboarding/document-requests/{r['id']}/review",
                          json={"decision": "approve"})
        assert res.status_code == 200, res.text
    offer = [m for m in outbox if "offer of employment" in m["subject"].lower()]
    assert len(offer) == 1 and offer[0]["to"] == email and offer[0]["pdf"]
    assert client.get("/api/employee/preboarding/status").json()["portal_stage"] == "active"
    assert client.get("/api/employee/document-requests").status_code == 200
    assert client.get("/api/employee/profile").status_code == 200


def test_an_existing_employee_is_never_locked_out(client, tenant, outbox):
    emp = make_employee(tenant, password="EmpPass123")
    res = client.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"})
    assert res.status_code == 200
    assert client.get("/api/employee/profile").status_code == 200


def test_a_password_hr_sets_is_not_temporary(client, tenant, outbox):
    hired, email = hire(client, tenant)
    res = tenant.put(f"/api/employees/{hired['employee_id']}/set-password",
                     json={"password": "Chosen-By-HR-9x"})
    assert res.status_code == 200, res.text
    login = client.post("/api/employee/auth/login",
                        json={"email": email, "password": "Chosen-By-HR-9x"}).json()
    assert login["must_change_password"] is False
    assert client.get("/api/employee/document-requests").status_code == 200


def test_an_expired_temporary_password_is_refused(client, tenant, outbox):
    hired, email = hire(client, tenant)
    welcome = next(m for m in outbox if "Congratulations" in m["subject"])
    password = re.search(r"Temporary password: (\S+)", welcome["body"]).group(1)
    with main.SessionLocal() as db:
        emp = db.query(main.models.DBEmployee).get(hired["employee_id"])
        emp.temp_password_expires_at = "2000-01-01 00:00:00"
        db.commit()
    res = client.post("/api/employee/auth/login", json={"email": email, "password": password})
    assert res.status_code == 401 and "expired" in res.json()["detail"]
    assert tenant.post(f"/api/employees/{hired['employee_id']}/resend-credentials").status_code == 200
