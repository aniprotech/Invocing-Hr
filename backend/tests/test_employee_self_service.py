"""What a person can find out and change about themselves.

Four things the portal could not do. Payslips could be seen as a figure but not
taken away - and a payslip is what a landlord or a lender asks for. Leave was
requested by people who could not see what they had left. A phone number could
only be corrected by asking HR, which is why the numbers on file go stale. And
every AI feature pointed at the owner's side, so the people with the most
routine questions had nobody to ask but HR.

The property that matters most here is containment: everything an employee can
reach is their own. One person reading another's pay would be the worst bug in
the application, so it is asserted from several directions.
"""
import uuid

import pytest

import llm
import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    llm.LAST_ERROR["reason"] = ""
    yield
    llm.LAST_ERROR["reason"] = ""


def sign_in(client, emp, password="EmpPass123"):
    main.rate_limiter._hits.clear()
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": password})
    assert res.status_code == 200, res.text
    return client


def as_owner(client, account):
    main.rate_limiter._hits.clear()
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text
    return client


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


@pytest.fixture
def staff(tenant):
    return make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")


@pytest.fixture
def credit(account):
    """Wallet credit, so nothing here turns on the pricing table.

    Pricing is global and other tests edit it - one drops a free allowance to
    zero to prove billing works. Without credit the assistant is refused before
    the model is reached, and a 402 is not the failure these tests are about.
    """
    with main.SessionLocal() as db:
        main.get_wallet(db, client_id(account)).balance_minor = 500_00
        db.commit()


def add_payslip(account, emp_id, **kw):
    fields = dict(number=f"PS-{uuid.uuid4().hex[:6]}", period_start="2026-07-01",
                  period_end="2026-07-31", pay_date="2026-08-01",
                  gross_pay=3000.0, tax_amount=600.0, total_deductions=750.0,
                  net_pay=2250.0, status="Paid")
    fields.update(kw)
    with main.SessionLocal() as db:
        ps = models.DBPayslip(client_id=client_id(account), employee_id=emp_id, **fields)
        db.add(ps)
        db.commit()
        return ps.id


def set_fields(emp_id, **kw):
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp_id).first()
        for k, v in kw.items():
            setattr(row, k, v)
        db.commit()


def read(emp_id, field):
    with main.SessionLocal() as db:
        return getattr(db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp_id).first(), field)


# --- leave balance ------------------------------------------------------------

def test_a_person_can_see_what_leave_they_have_left(tenant, staff):
    """It was on the HR record only, so leave was requested blind and refused
    for a reason the form could have shown first."""
    sign_in(tenant, staff)
    body = tenant.get("/api/employee/leave-balance").json()
    assert body["annual_total"] > 0
    assert body["annual_remaining"] == body["annual_total"]


def test_an_undecided_request_is_already_held_back(tenant, staff, account):
    """Otherwise somebody books the same fortnight twice while the first is
    still waiting."""
    sign_in(tenant, staff)
    res = tenant.post("/api/employee/leave", json={
        "leave_type": "annual", "start_date": "2026-09-01",
        "end_date": "2026-09-03", "reason": "Away"})
    assert res.status_code == 200, res.text

    body = tenant.get("/api/employee/leave-balance").json()
    assert body["annual_pending"] > 0
    assert body["annual_remaining"] == round(
        body["annual_total"] - body["annual_taken"] - body["annual_pending"], 2)


def test_leave_balance_needs_a_session(client):
    assert client.get("/api/employee/leave-balance").status_code == 401


# --- payslips -----------------------------------------------------------------

def test_a_person_can_list_their_own_payslips(tenant, staff, account):
    add_payslip(account, staff["id"], number="PS-0001")
    sign_in(tenant, staff)
    rows = tenant.get("/api/employee/payslips").json()
    assert [r["number"] for r in rows] == ["PS-0001"]
    assert rows[0]["net_pay"] == 2250.0


def test_a_payslip_carries_everything_the_document_needs(tenant, staff, account):
    ps_id = add_payslip(account, staff["id"])
    sign_in(tenant, staff)
    body = tenant.get(f"/api/employee/payslips/{ps_id}").json()

    for field in ("number", "period_start", "period_end", "pay_date", "gross_pay",
                  "tax_amount", "total_deductions", "net_pay", "currency"):
        assert field in body, field
    assert body["employee"]["name"] == "Ada Reid"
    assert body["company"]["name"]


def test_the_bank_account_on_a_payslip_is_masked(tenant, staff, account):
    """Enough to recognise which account, never enough to use it - a payslip
    gets forwarded to landlords and lenders."""
    set_fields(staff["id"], bank_account="12345678")
    ps_id = add_payslip(account, staff["id"])
    sign_in(tenant, staff)
    shown = tenant.get(f"/api/employee/payslips/{ps_id}").json()["employee"]["bank_account"]
    assert shown.endswith("5678")
    assert "1234" not in shown


def test_one_employee_cannot_read_anothers_payslip(tenant, account):
    """The worst bug this application could have."""
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    theirs = make_employee(tenant, first_name="Sam", last_name="Ali",
                           password="EmpPass123")
    other_ps = add_payslip(account, theirs["id"], net_pay=9999.0)

    sign_in(tenant, mine)
    assert tenant.get(f"/api/employee/payslips/{other_ps}").status_code == 404
    assert tenant.get("/api/employee/payslips").json() == []


def test_payslips_need_a_session(client):
    assert client.get("/api/employee/payslips").status_code == 401


# --- correcting your own record -----------------------------------------------

def test_contact_details_change_without_asking_anybody(tenant, staff):
    """A new phone number is nobody's decision but the person's own."""
    sign_in(tenant, staff)
    res = tenant.put("/api/employee/profile", json={
        "phone": "07700 900123", "address": "12 New Street",
        "emergency_contact": "Jo Reid", "emergency_phone": "07700 900999"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body["applied"]) == {"phone", "address",
                                    "emergency_contact", "emergency_phone"}
    assert body["awaiting_approval"] == []
    assert read(staff["id"], "phone") == "07700 900123"


def test_bank_details_are_proposed_rather_than_applied(tenant, staff):
    """Whatever is stored there is where the wages go."""
    set_fields(staff["id"], bank_account="11112222")
    sign_in(tenant, staff)

    body = tenant.put("/api/employee/profile",
                      json={"bank_account": "99998888"}).json()
    assert body["awaiting_approval"] == ["bank_account"]
    assert body["applied"] == []
    assert read(staff["id"], "bank_account") == "11112222", "not applied yet"


def test_asking_twice_revises_the_ask_rather_than_queueing_two(tenant, staff):
    """HR should not have to work out which of two rows came last."""
    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "1111"})
    tenant.put("/api/employee/profile", json={"bank_account": "2222"})

    pending = [r for r in tenant.get("/api/employee/profile-changes").json()
               if r["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["new_value"] == "2222"


def test_setting_a_field_to_what_it_already_is_changes_nothing(tenant, staff):
    set_fields(staff["id"], phone="07700 900123", bank_account="1111")
    sign_in(tenant, staff)
    body = tenant.put("/api/employee/profile", json={
        "phone": "07700 900123", "bank_account": "1111"}).json()
    assert body["applied"] == []
    assert body["awaiting_approval"] == []


def test_a_field_nobody_offered_is_ignored(tenant, staff):
    """Salary is not on either list, and a request naming it must not take."""
    set_fields(staff["id"], salary=3000.0)
    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"salary": 999999, "status": "active"})
    assert read(staff["id"], "salary") == 3000.0


def test_profile_updates_need_a_session(client):
    assert client.put("/api/employee/profile", json={"phone": "1"}).status_code == 401


# --- HR deciding --------------------------------------------------------------

def test_approving_writes_the_value_across(tenant, staff, account):
    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "99998888"})

    as_owner(tenant, account)
    queued = tenant.get("/api/hr/profile-changes").json()
    assert len(queued) == 1
    assert queued[0]["employee"]["name"] == "Ada Reid"

    res = tenant.post(f"/api/hr/profile-changes/{queued[0]['id']}/decide",
                      json={"decision": "approve"})
    assert res.status_code == 200, res.text
    assert read(staff["id"], "bank_account") == "99998888"


def test_rejecting_leaves_the_record_exactly_as_it_was(tenant, staff, account):
    set_fields(staff["id"], bank_account="11112222")
    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "99998888"})

    as_owner(tenant, account)
    change_id = tenant.get("/api/hr/profile-changes").json()[0]["id"]
    tenant.post(f"/api/hr/profile-changes/{change_id}/decide",
                json={"decision": "reject", "note": "Send a bank statement first"})

    assert read(staff["id"], "bank_account") == "11112222"


def test_the_employee_is_told_either_way(tenant, staff, account):
    """A change to where their wages land is not something they should have to
    come back and check on."""
    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "99998888"})

    as_owner(tenant, account)
    change_id = tenant.get("/api/hr/profile-changes").json()[0]["id"]
    tenant.post(f"/api/hr/profile-changes/{change_id}/decide",
                json={"decision": "reject", "note": "Send a bank statement first"})

    sign_in(tenant, staff)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("bank account" in (n["title"] + n["message"]).lower()
               for n in notes), notes
    assert any("bank statement" in n["message"] for n in notes)


def test_the_same_request_cannot_be_decided_twice(tenant, staff, account):
    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "99998888"})

    as_owner(tenant, account)
    change_id = tenant.get("/api/hr/profile-changes").json()[0]["id"]
    first = tenant.post(f"/api/hr/profile-changes/{change_id}/decide",
                        json={"decision": "approve"})
    assert first.status_code == 200
    again = tenant.post(f"/api/hr/profile-changes/{change_id}/decide",
                        json={"decision": "reject"})
    assert again.status_code == 409


def test_a_decision_has_to_be_one_of_the_two(tenant, staff, account):
    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "9999"})
    as_owner(tenant, account)
    change_id = tenant.get("/api/hr/profile-changes").json()[0]["id"]
    assert tenant.post(f"/api/hr/profile-changes/{change_id}/decide",
                       json={"decision": "maybe"}).status_code == 400


def test_the_queue_is_the_tenants_own(tenant, staff, account, client):
    from fastapi.testclient import TestClient

    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "9999"})

    with TestClient(main.app) as other:
        main.rate_limiter._hits.clear()
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"})
        assert other.get("/api/hr/profile-changes").json() == []


def test_an_employee_cannot_approve_their_own_change(tenant, staff):
    """On a session that is only an employee.

    A password sign-in deliberately leaves an account holder's session alone,
    so the fixture's own client is somebody who is both - an owner who also
    keeps an employee record for their payslips - and that person may of course
    approve. The case worth proving is the ordinary one: an employee, and
    nothing else, on a browser of their own.
    """
    from fastapi.testclient import TestClient

    sign_in(tenant, staff)
    tenant.put("/api/employee/profile", json={"bank_account": "9999"})
    change_id = tenant.get("/api/employee/profile-changes").json()[0]["id"]

    with TestClient(main.app) as staff_only:
        main.rate_limiter._hits.clear()
        res = staff_only.post("/api/employee/auth/login", json={
            "email": staff["email"], "password": "EmpPass123"})
        assert res.status_code == 200, res.text

        assert staff_only.get("/api/employee/leave-balance").status_code == 200, \
            "the employee session is real"
        assert staff_only.post(f"/api/hr/profile-changes/{change_id}/decide",
                               json={"decision": "approve"}).status_code in (401, 403)

    assert read(staff["id"], "bank_account") != "9999"


def test_the_hr_queue_is_shut_to_a_plain_employee(tenant, staff):
    from fastapi.testclient import TestClient

    with TestClient(main.app) as staff_only:
        main.rate_limiter._hits.clear()
        staff_only.post("/api/employee/auth/login", json={
            "email": staff["email"], "password": "EmpPass123"})
        assert staff_only.get("/api/hr/profile-changes").status_code in (401, 403)


# --- the assistant ------------------------------------------------------------

def test_the_context_is_this_persons_own_record(tenant, staff, account):
    add_payslip(account, staff["id"], number="PS-MINE", net_pay=2250.0)
    with main.SessionLocal() as db:
        emp = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == staff["id"]).first()
        context = main.build_employee_context(db, emp)

    assert "Ada Reid" in context
    assert "PS-MINE" in context
    assert "YOUR LEAVE" in context and "YOUR PAY" in context


def test_the_context_holds_nothing_about_a_colleague(tenant, account):
    """build_business_context carries every salary in the company. This one
    must never reach for it."""
    mine = make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")
    make_employee(tenant, first_name="Sam", last_name="Ali", salary=99999.0)
    add_payslip(account, mine["id"], number="PS-MINE")

    with main.SessionLocal() as db:
        emp = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == mine["id"]).first()
        context = main.build_employee_context(db, emp)

    assert "Sam Ali" not in context
    assert "99999" not in context


def test_the_assistant_answers_from_that_context(tenant, staff, credit, monkeypatch):
    seen = {}

    def fake(messages, **kw):
        seen["system"] = messages[0]["content"]
        seen["prompt"] = messages[-1]["content"]
        return "You have 25 days of annual leave left."

    monkeypatch.setattr(main, "llm_chat", fake)
    sign_in(tenant, staff)
    body = tenant.post("/api/employee/assistant",
                       json={"question": "How much leave do I have?"}).json()

    assert body["available"] is True
    assert body["answer"] == "You have 25 days of annual leave left."
    assert "CONTEXT:" in seen["prompt"]
    assert "Ada Reid" in seen["prompt"]
    assert "ONLY the CONTEXT" in seen["system"]
    assert "colleagues" in seen["system"], "it must be told it knows nothing of others"


def test_the_assistant_says_why_when_the_model_is_down(tenant, staff, credit,
                                                      monkeypatch):
    def gone(*a, **k):
        llm.LAST_ERROR["reason"] = "model_gone"
        return None

    monkeypatch.setattr(main, "llm_chat", gone)
    sign_in(tenant, staff)
    body = tenant.post("/api/employee/assistant",
                       json={"question": "How much leave?"}).json()
    assert body["available"] is False
    assert body["reason"] == "model_gone"


def test_a_failed_answer_is_not_charged_for(tenant, staff, account, monkeypatch):
    monkeypatch.setattr(main, "llm_chat", lambda *a, **k: None)
    cid = client_id(account)
    with main.SessionLocal() as db:
        main.get_wallet(db, cid).balance_minor = 500_00
        db.commit()
        before = main.get_wallet(db, cid).balance_minor

    sign_in(tenant, staff)
    tenant.post("/api/employee/assistant", json={"question": "How much leave?"})

    with main.SessionLocal() as db:
        assert main.get_wallet(db, cid).balance_minor == before


@pytest.mark.parametrize("question,code", [("", 400), ("x" * 600, 400)])
def test_the_question_is_checked(tenant, staff, question, code):
    sign_in(tenant, staff)
    assert tenant.post("/api/employee/assistant",
                       json={"question": question}).status_code == code


def test_the_assistant_needs_a_session(client):
    assert client.post("/api/employee/assistant",
                       json={"question": "hi"}).status_code == 401


def test_the_openers_are_things_this_person_can_be_told(tenant, staff, credit):
    sign_in(tenant, staff)
    body = tenant.get("/api/employee/assistant/suggestions").json()
    assert body["suggestions"]
    assert all(s.strip().endswith("?") for s in body["suggestions"])
    assert any("leave" in s.lower() for s in body["suggestions"])
