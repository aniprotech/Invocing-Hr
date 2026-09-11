"""Getting your money back.

Somebody paid for something out of their own pocket and wants it back - the
train to the client, the sandwich on the way, the cable the office ran out
of. Until this existed there was no way to say so inside the product, so it
went by email to whoever, and got paid or did not.

The same shape as leave, on purpose: the person asks, their manager decides,
HR can decide anything and is the only one who can say it has been paid. The
decision is written once and shared between the two routes in.

The amount is an integer in minor units, the way the wallet is. A float that
says 12.30 is not always 12.30, and a spreadsheet of reimbursements has to
add up to the penny. The tests check the penny.
"""
import base64
import uuid
from datetime import date, timedelta

import pytest

import main
import models
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
PNG = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
SVG = "data:image/svg+xml;base64," + base64.b64encode(b"<svg><script>1</script></svg>").decode()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def as_staff(client, emp):
    main.rate_limiter._hits.clear()
    client.post("/api/client/logout")
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def as_hr(client, account):
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def claim(client, **over):
    payload = {"category": "travel", "amount": "12.30", "spent_on": YESTERDAY,
               "description": "Train to the client"}
    payload.update(over)
    res = client.post("/api/employee/expenses", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# --- asking ------------------------------------------------------------------------

def test_a_claim_is_kept_to_the_penny(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant, amount="12.30")
    assert c["amount_minor"] == 1230
    assert c["amount"] == 12.30
    assert c["status"] == "pending"
    assert c["currency"] == "GBP"


def test_the_amount_survives_the_float_trap(tenant):
    """0.1 + 0.2 is not 0.3 in a float. It is in pence."""
    staff = person(tenant)
    as_staff(tenant, staff)
    a = claim(tenant, amount="0.10")
    b = claim(tenant, amount="0.20")
    assert a["amount_minor"] + b["amount_minor"] == 30
    total = tenant.get("/api/employee/expenses").json()
    assert sum(x["amount_minor"] for x in total["claims"]) == 30


def test_half_a_penny_rounds_the_way_money_does(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    assert claim(tenant, amount="1.005")["amount_minor"] == 101


def test_nothing_is_not_an_amount(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    for bad in ("0", "", "-5", "abc", None):
        res = tenant.post("/api/employee/expenses", json={
            "category": "travel", "amount": bad, "spent_on": YESTERDAY,
            "description": "x"})
        assert res.status_code == 400, (bad, res.text)


def test_a_million_is_a_typo(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    res = tenant.post("/api/employee/expenses", json={
        "category": "travel", "amount": "1000001", "spent_on": YESTERDAY,
        "description": "x"})
    assert res.status_code == 400


def test_the_category_is_one_of_the_list(tenant):
    """So "what did we spend on travel this quarter" has an answer."""
    staff = person(tenant)
    as_staff(tenant, staff)
    res = tenant.post("/api/employee/expenses", json={
        "category": "snacks", "amount": "1", "spent_on": YESTERDAY, "description": "x"})
    assert res.status_code == 400
    assert "travel" in res.json()["detail"]


def test_the_date_cannot_be_in_the_future(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    res = tenant.post("/api/employee/expenses", json={
        "category": "travel", "amount": "1", "spent_on": tomorrow, "description": "x"})
    assert res.status_code == 400


def test_it_has_to_say_what_it_was_for(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    res = tenant.post("/api/employee/expenses", json={
        "category": "travel", "amount": "1", "spent_on": YESTERDAY, "description": "  "})
    assert res.status_code == 400


def test_the_currency_is_the_businesss(tenant, account):
    with main.SessionLocal() as db:
        row = db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first()
        row.currency = "EUR"
        db.commit()
    staff = person(tenant)
    as_staff(tenant, staff)
    assert claim(tenant)["currency"] == "EUR"


def test_the_manager_is_told(tenant):
    boss = person(tenant)
    mine = person(tenant, first_name="Sam", last_name="Mine", reports_to=boss["id"])
    as_staff(tenant, mine)
    claim(tenant, amount="45.00")
    as_staff(tenant, boss)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("Sam Mine" in n["message"] and "45.00" in n["message"] for n in notes), notes


# --- the receipt ------------------------------------------------------------------------

def test_a_receipt_is_kept_and_comes_back(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant, receipt_data=PNG)
    assert c["has_receipt"] is True
    res = tenant.get(f"/api/employee/expenses/{c['id']}/receipt")
    assert res.status_code == 200
    assert res.content == PNG_BYTES
    assert res.headers["content-type"].startswith("image/png")
    assert res.headers.get("x-content-type-options") == "nosniff"


def test_a_receipt_follows_the_same_rules_as_a_picture(tenant):
    """One validator for everything a person uploads and other people's
    browsers render. The risk is the same, so the rules are."""
    staff = person(tenant)
    as_staff(tenant, staff)
    res = tenant.post("/api/employee/expenses", json={
        "category": "travel", "amount": "1", "spent_on": YESTERDAY,
        "description": "x", "receipt_data": SVG})
    assert res.status_code == 400
    assert "receipt" in res.json()["detail"]


def test_a_manager_can_read_a_reports_receipt(tenant):
    """They decide on it, so they have to be able to see it."""
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    as_staff(tenant, mine)
    c = claim(tenant, receipt_data=PNG)
    as_staff(tenant, boss)
    assert tenant.get(f"/api/employee/expenses/{c['id']}/receipt").status_code == 200


def test_but_a_colleague_cannot(tenant):
    a = person(tenant)
    b = person(tenant)
    as_staff(tenant, a)
    c = claim(tenant, receipt_data=PNG)
    as_staff(tenant, b)
    assert tenant.get(f"/api/employee/expenses/{c['id']}/receipt").status_code == 404


def test_hr_can_read_any_receipt(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant, receipt_data=PNG)
    as_hr(tenant, account)
    assert tenant.get(f"/api/expenses/{c['id']}/receipt").status_code == 200


# --- my list ------------------------------------------------------------------------------

def test_i_see_my_own_claims_and_what_i_am_owed(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    a = claim(tenant, amount="10.00")
    claim(tenant, amount="20.00")
    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{a['id']}/decide", json={"action": "approve"})

    as_staff(tenant, staff)
    mine = tenant.get("/api/employee/expenses").json()
    assert len(mine["claims"]) == 2
    # Owed is what has been agreed and not yet paid - not what is pending,
    # which may still be refused.
    assert mine["owed_minor"] == 1000
    assert mine["pending"] == 1


def test_and_not_anybody_elses(tenant):
    a = person(tenant)
    b = person(tenant)
    as_staff(tenant, a)
    claim(tenant)
    as_staff(tenant, b)
    assert tenant.get("/api/employee/expenses").json()["claims"] == []


# --- withdrawing ---------------------------------------------------------------------------

def test_a_pending_claim_can_be_withdrawn(tenant):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant)
    assert c["can_withdraw"] is True
    assert tenant.delete(f"/api/employee/expenses/{c['id']}").status_code == 200
    assert tenant.get("/api/employee/expenses").json()["claims"] == []


def test_but_not_once_decided(tenant, account):
    """A decision is a record. Withdrawing after a rejection would erase the
    rejection."""
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant)
    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{c['id']}/decide", json={"action": "reject"})
    as_staff(tenant, staff)
    assert tenant.delete(f"/api/employee/expenses/{c['id']}").status_code == 409
    assert tenant.get("/api/employee/expenses").json()["claims"][0]["can_withdraw"] is False


def test_and_not_somebody_elses(tenant):
    a = person(tenant)
    b = person(tenant)
    as_staff(tenant, a)
    c = claim(tenant)
    as_staff(tenant, b)
    assert tenant.delete(f"/api/employee/expenses/{c['id']}").status_code == 404


# --- the manager decides ---------------------------------------------------------------------

def test_it_appears_on_the_managers_list(tenant):
    boss = person(tenant)
    mine = person(tenant, first_name="Sam", last_name="Mine", reports_to=boss["id"])
    as_staff(tenant, mine)
    claim(tenant, amount="33.50", description="Taxi from the station")
    as_staff(tenant, boss)
    got = tenant.get("/api/employee/approvals").json()
    assert got["count"] == 1
    assert got["expenses"][0]["employee"] == "Sam Mine"
    assert got["expenses"][0]["amount"] == 33.5
    assert got["expenses"][0]["description"] == "Taxi from the station"


def test_the_manager_can_approve(tenant):
    boss = person(tenant, first_name="Dana", last_name="Boss")
    mine = person(tenant, reports_to=boss["id"])
    as_staff(tenant, mine)
    c = claim(tenant)
    as_staff(tenant, boss)
    res = tenant.post(f"/api/employee/approvals/expense/{c['id']}",
                      json={"action": "approve"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    with main.SessionLocal() as db:
        row = db.query(models.DBExpenseClaim).filter(models.DBExpenseClaim.id == c["id"]).first()
        assert row.decided_by == "Dana Boss"


def test_and_reject_with_a_reason(tenant):
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    as_staff(tenant, mine)
    c = claim(tenant)
    as_staff(tenant, boss)
    tenant.post(f"/api/employee/approvals/expense/{c['id']}",
                json={"action": "reject", "note": "No receipt attached"})
    as_staff(tenant, mine)
    got = tenant.get("/api/employee/expenses").json()["claims"][0]
    assert got["status"] == "rejected"
    assert got["decision_note"] == "No receipt attached"
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("No receipt attached" in n["message"] for n in notes), notes


def test_nobody_approves_their_own(tenant):
    boss = person(tenant)
    person(tenant, reports_to=boss["id"])
    as_staff(tenant, boss)
    c = claim(tenant)
    assert tenant.post(f"/api/employee/approvals/expense/{c['id']}",
                       json={"action": "approve"}).status_code == 404


def test_nor_somebody_elses_reports(tenant):
    boss = person(tenant)
    other_boss = person(tenant)
    theirs = person(tenant, reports_to=other_boss["id"])
    as_staff(tenant, theirs)
    c = claim(tenant)
    as_staff(tenant, boss)
    assert tenant.post(f"/api/employee/approvals/expense/{c['id']}",
                       json={"action": "approve"}).status_code == 404


def test_a_manager_cannot_mark_it_paid(tenant):
    """Approved is "we owe you this". Paid is "and it left the account".
    Only HR says the second, because only HR did it."""
    boss = person(tenant)
    mine = person(tenant, reports_to=boss["id"])
    as_staff(tenant, mine)
    c = claim(tenant)
    as_staff(tenant, boss)
    tenant.post(f"/api/employee/approvals/expense/{c['id']}", json={"action": "approve"})
    # There is no manager route to paid at all.
    assert tenant.post(f"/api/expenses/{c['id']}/paid").status_code == 401


# --- HR --------------------------------------------------------------------------------------------

def test_hr_sees_everything_with_the_totals(tenant, account):
    a = person(tenant)
    b = person(tenant)
    as_staff(tenant, a)
    c1 = claim(tenant, amount="10.00")
    as_staff(tenant, b)
    c2 = claim(tenant, amount="25.50")
    claim(tenant, amount="4.50")

    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{c1['id']}/decide", json={"action": "approve"})
    tenant.post(f"/api/expenses/{c2['id']}/decide", json={"action": "approve"})
    tenant.post(f"/api/expenses/{c2['id']}/paid")

    got = tenant.get("/api/expenses").json()
    assert len(got["claims"]) == 3
    assert got["totals"]["pending"] == 4.5
    assert got["totals"]["pending_count"] == 1
    assert got["totals"]["owed"] == 10.0
    assert got["totals"]["paid_this_month"] == 25.5


def test_hr_can_filter_by_status(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant)
    claim(tenant)
    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{c['id']}/decide", json={"action": "approve"})
    assert len(tenant.get("/api/expenses", params={"status": "approved"}).json()["claims"]) == 1
    assert len(tenant.get("/api/expenses", params={"status": "pending"}).json()["claims"]) == 1


def test_only_an_approved_claim_can_be_paid(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant)
    as_hr(tenant, account)
    assert tenant.post(f"/api/expenses/{c['id']}/paid").status_code == 409
    tenant.post(f"/api/expenses/{c['id']}/decide", json={"action": "reject"})
    assert tenant.post(f"/api/expenses/{c['id']}/paid").status_code == 409


def test_paying_tells_the_person(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant, amount="99.99")
    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{c['id']}/decide", json={"action": "approve"})
    tenant.post(f"/api/expenses/{c['id']}/paid")
    as_staff(tenant, staff)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("paid" in n["title"].lower() and "99.99" in n["message"] for n in notes), notes
    assert tenant.get("/api/employee/expenses").json()["owed_minor"] == 0


def test_paying_twice_is_refused(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant)
    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{c['id']}/decide", json={"action": "approve"})
    assert tenant.post(f"/api/expenses/{c['id']}/paid").status_code == 200
    assert tenant.post(f"/api/expenses/{c['id']}/paid").status_code == 409


def test_deciding_twice_is_refused(tenant, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant)
    as_hr(tenant, account)
    tenant.post(f"/api/expenses/{c['id']}/decide", json={"action": "approve"})
    assert tenant.post(f"/api/expenses/{c['id']}/decide",
                       json={"action": "reject"}).status_code == 409


# --- reaching across -------------------------------------------------------------------------------

def test_another_business_cannot_touch_a_claim(tenant, client, account):
    staff = person(tenant)
    as_staff(tenant, staff)
    c = claim(tenant, receipt_data=PNG)

    email = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/employee/auth/logout")
    client.post("/api/client/register", json={
        "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})

    assert client.get("/api/expenses").json()["claims"] == []
    assert client.get(f"/api/expenses/{c['id']}/receipt").status_code == 404
    assert client.post(f"/api/expenses/{c['id']}/decide",
                       json={"action": "approve"}).status_code == 404
    assert client.post(f"/api/expenses/{c['id']}/paid").status_code == 404
