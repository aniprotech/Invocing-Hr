"""An address on an employee record is the whole enrolment.

HR types the employee's email and saves. From then on, that address signing in
with Google lands in the employee portal - no password to set, no invitation to
accept, no second account. Whichever sign-in page they started from.

The Google exchange itself is not reachable from a test, so these cover the two
pieces the routing is built from: which record an address resolves to, and what
a session becomes once it does. Both are where this would go wrong.
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


class FakeRequest:
    """Only the session, which is all start_employee_session touches."""

    def __init__(self, session=None):
        self.session = session if session is not None else {}
        self.client = None


def db_employee(emp_id):
    with main.SessionLocal() as db:
        return db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp_id).first()


def lookup(email):
    with main.SessionLocal() as db:
        return main.employee_by_email(db, email)


# --- which record an address resolves to --------------------------------------

def test_the_address_hr_saved_finds_that_employee(tenant):
    emp = make_employee(tenant, first_name="Sarah", last_name="Daley")
    found = lookup(emp["email"])
    assert found is not None
    assert found.id == emp["id"]


def test_case_and_spacing_do_not_matter(tenant):
    """Nobody types their own address the same way twice."""
    emp = make_employee(tenant)
    assert lookup("  " + emp["email"].upper() + "  ").id == emp["id"]


def test_an_unknown_address_matches_nothing(tenant):
    make_employee(tenant)
    assert lookup(f"stranger-{uuid.uuid4().hex[:8]}@example.com") is None


def test_an_empty_address_matches_nothing(tenant):
    make_employee(tenant)
    assert lookup("") is None
    assert lookup(None) is None


def test_a_terminated_employee_is_not_a_match(tenant):
    """Access ends when the employment does. Otherwise anyone who has ever
    worked here keeps a way in for as long as their Google account exists."""
    emp = make_employee(tenant)
    res = tenant.put(f"/api/employees/{emp['id']}", json={"status": "terminated"})
    assert res.status_code == 200, res.text
    assert lookup(emp["email"]) is None


def test_someone_still_onboarding_can_sign_in(tenant):
    """They are exactly who needs the portal - it is where their documents go."""
    emp = make_employee(tenant)
    assert db_employee(emp["id"]).status == "onboarding"
    assert lookup(emp["email"]) is not None


# --- what the session becomes -------------------------------------------------

def test_signing_in_makes_the_request_that_employee(tenant):
    emp = make_employee(tenant)
    req = FakeRequest()
    main.start_employee_session(req, db_employee(emp["id"]))
    assert req.session["employee_id"] == emp["id"]
    assert req.session["employee_client_id"]


def test_it_drops_any_admin_rights_left_on_the_browser(tenant):
    """The dangerous case: somebody signs in as the business owner, then an
    employee signs in on the same browser. A staff session must not inherit
    the account holder's access."""
    emp = make_employee(tenant)
    req = FakeRequest({"client_id": 999, "member_id": 42, "superadmin_id": 7})
    # Google says who this is, so it replaces whatever was here.
    main.start_employee_session(req, db_employee(emp["id"]),
                                replace_other_sessions=True)

    assert "client_id" not in req.session
    assert "member_id" not in req.session
    assert "superadmin_id" not in req.session
    assert req.session["employee_id"] == emp["id"]


def test_an_employee_belongs_to_their_own_employer(client, tenant):
    """Two businesses, one address each. The session must carry the right
    employer or the portal shows another company's payslips."""
    mine = make_employee(tenant)

    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    theirs = make_employee(client)

    req = FakeRequest()
    main.start_employee_session(req, db_employee(mine["id"]))
    mine_client = req.session["employee_client_id"]

    req2 = FakeRequest()
    main.start_employee_session(req2, db_employee(theirs["id"]))
    assert req2.session["employee_client_id"] != mine_client


# --- no password needed, and none implied -------------------------------------

def test_no_password_is_needed_on_the_record(client, tenant):
    """The point of the feature: HR saves an address and that is the enrolment.
    A record with no password still resolves for Google, while password
    sign-in for the same record is refused - so nothing here has quietly
    become a way in without credentials."""
    emp = make_employee(tenant)
    with main.SessionLocal() as db:
        row = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == emp["id"]).first()
        row.password_hash = ""      # nobody set one; Google is the way in
        db.commit()

    assert lookup(emp["email"]).id == emp["id"], (
        "the address must still resolve with no password on the record")

    main.rate_limiter._hits.clear()
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": "anything"})
    assert res.status_code == 401, (
        "a record with no password must not accept one")


# --- when one address is both an owner and an employee ------------------------

def target(email, portal):
    with main.SessionLocal() as db:
        return main.employee_signing_in(db, email, portal)


def test_a_plain_employee_lands_in_the_portal_from_any_page(tenant):
    """The requirement: HR saves the address, and it works wherever they
    start."""
    emp = make_employee(tenant)
    for portal in ("employee", "hr", "invoicing", "", None):
        assert target(emp["email"], portal) is not None, portal


def test_an_owner_who_is_also_an_employee_keeps_their_business(client, account):
    """Adding yourself as an employee must not shut you out of your own
    account. Signing in from the business pages goes to the business."""
    main.rate_limiter._hits.clear()
    emp = make_employee(client, email=account["email"])
    assert emp["email"].lower() == account["email"].lower()

    assert target(account["email"], "invoicing") is None
    assert target(account["email"], "hr") is None


def test_and_can_still_reach_their_own_employee_portal(client, account):
    """From the employee page, the same person is an employee - so an owner who
    keeps a record for their own payslips can still read them."""
    main.rate_limiter._hits.clear()
    make_employee(client, email=account["email"])
    found = target(account["email"], "employee")
    assert found is not None
    assert found.email.lower() == account["email"].lower()


def test_an_employee_address_that_owns_nothing_is_unaffected(tenant):
    """The tie-break must only apply to the person who is genuinely both."""
    emp = make_employee(tenant)
    assert target(emp["email"], "invoicing") is not None
