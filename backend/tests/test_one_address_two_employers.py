"""Signing in when two businesses employ the same person.

An employee's address is unique inside one business - clean_employee_email
enforces that - and deliberately not across the platform, because the same
person really can work for two of them. Contractors, agency staff, shared
operations people.

Three separate lookups took .first() on a platform-wide match, so which
business you reached depended on which record happened to be created first.
Somebody signing in landed in a stranger's HR portal: their colleagues, their
payslips, their leave, with no route to their own. Nothing rejected the
password, because the password checked was whichever account came first.

It gets likelier with every tenant added, which is the worst shape for a
latent bug - it activates as the platform fills up rather than while it is
small enough to notice.
"""
import uuid

import pytest

import main
import models


PASSWORD = "TheirPassword1"
OTHER = "ADifferentOne2"


def employ(email, company, password=PASSWORD, status="active"):
    """A business, with its own employee at the given address.

    The owner address is made unique per call: clients.email is unique and the
    whole suite shares one database, so a fixed one collides with an earlier
    test's business rather than making a new one.
    """
    with main.SessionLocal() as db:
        owner = models.DBClient(
            email=f"owner-{company}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="", company_name=company, is_active=True)
        db.add(owner)
        db.flush()
        emp = models.DBEmployee(
            client_id=owner.id, first_name="Jane", last_name=company,
            email=email, status=status,
            password_hash=models.hash_password(password) if password else "")
        db.add(emp)
        db.commit()
        return owner.id, emp.id


def whose_portal(client):
    """Which business the signed-in session actually reaches.

    Asked of a real endpoint rather than by unpacking the cookie: what matters
    is the tenant whose data this session is served, and that is the thing
    that was wrong - somebody landed in a stranger's portal, not merely with a
    stranger's id in a cookie.
    """
    res = client.get("/api/employee/profile")
    assert res.status_code == 200, res.text
    # Each employee is surnamed after their employer, so the portal names the
    # business it belongs to.
    return res.json()["full_name"].split()[-1]


def sign_in(client, email, password):
    return client.post("/api/employee/auth/login",
                       json={"email": email, "password": password})


@pytest.fixture
def two_employers():
    # Unique per test: the suite shares one database, so a fixed address
    # accumulates employers across tests and every later sign-in is ambiguous.
    email = f"jane-{uuid.uuid4().hex[:8]}@contractor.test"
    first = employ(email, "FirstCo", PASSWORD)
    second = employ(email, "SecondCo", OTHER)
    return email, first, second


# --- the fault -------------------------------------------------------------------

def test_the_password_decides_which_business_you_reach(client, two_employers):
    """Not the order the records were created in. This is the whole finding:
    Jane knows one password at each employer, and each one has to take her to
    that employer."""
    email, _, _ = two_employers

    res = sign_in(client, email, OTHER)
    assert res.status_code == 200, res.text
    assert whose_portal(client) == "SecondCo", "signed into the wrong business"


def test_and_the_other_password_reaches_the_other_one(client, two_employers):
    email, _, _ = two_employers

    assert sign_in(client, email, PASSWORD).status_code == 200
    assert whose_portal(client) == "FirstCo"


def test_a_wrong_password_still_gets_in_nowhere(client, two_employers):
    email, _, _ = two_employers
    assert sign_in(client, email, "neither-of-them").status_code == 401


def test_the_same_password_at_both_is_refused_rather_than_guessed(client):
    """Nothing can tell these apart, and picking one would be the original bug
    with extra steps."""
    email = f"twin-{uuid.uuid4().hex[:8]}@contractor.test"
    employ(email, "TwinA", PASSWORD)
    employ(email, "TwinB", PASSWORD)

    res = sign_in(client, email, PASSWORD)
    assert res.status_code == 409, res.status_code
    assert "more than one business" in res.json()["detail"]


# --- Google sign-in, where there is no password to tell them apart ------------------

def test_google_sign_in_refuses_when_it_cannot_know(client):
    """It carries no password, so an ambiguous address has no answer. Handing
    back the lowest id was dropping somebody into a stranger's account."""
    email = f"shared-{uuid.uuid4().hex[:8]}@contractor.test"
    employ(email, "GoogleA")
    employ(email, "GoogleB")

    with main.SessionLocal() as db:
        assert main.employee_by_email(db, email) is None


def test_google_sign_in_still_works_for_one(client):
    email = f"solo-{uuid.uuid4().hex[:8]}@contractor.test"
    owner_id, _ = employ(email, "SoloCo")

    with main.SessionLocal() as db:
        found = main.employee_by_email(db, email)
    assert found is not None and found.client_id == owner_id


def test_a_terminated_record_does_not_make_it_ambiguous(client):
    """Somebody who left one employer and joined another is one live account,
    not two."""
    email = f"moved-{uuid.uuid4().hex[:8]}@contractor.test"
    employ(email, "OldCo", PASSWORD, status="terminated")
    new_client, _ = employ(email, "NewCo", OTHER)

    with main.SessionLocal() as db:
        found = main.employee_by_email(db, email)
    assert found is not None and found.client_id == new_client

    assert sign_in(client, email, OTHER).status_code == 200


# --- resetting a password you cannot remember -----------------------------------------

def test_a_reset_is_offered_for_every_account_at_that_address(client, two_employers):
    """It used to reset whichever record came first, so the contractor locked
    out of the second employer was sent a link for the first and stayed locked
    out. They hold the mailbox; each link names the one account it is for."""
    email, (_, first_emp), (_, second_emp) = two_employers

    res = client.post("/api/employee/forgot-password", json={"email": email})
    assert res.status_code == 200, res.text

    with main.SessionLocal() as db:
        issued = {t.employee_id for t in db.query(models.DBPasswordReset).filter(
            models.DBPasswordReset.user_type == "employee",
            models.DBPasswordReset.used_at == "").all()}
    assert {first_emp, second_emp} <= issued, issued


def test_an_address_nobody_uses_still_says_nothing(client):
    """The generic answer is what stops this being a way to ask which
    addresses exist."""
    res = client.post("/api/employee/forgot-password",
                      json={"email": "nobody@nowhere.test"})
    assert res.status_code == 200, res.text
