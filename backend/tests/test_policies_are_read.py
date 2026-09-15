"""The handbook, and who has read it.

A policy is published to everybody or to one department, and each person
acknowledges each version - so a change is a fresh round, HR can see who
has not, and remind them. A typo fix keeps the version and the
acknowledgements; a republish does not. Nobody acknowledges a policy that
is not theirs to read.
"""
import pytest

import main
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


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
    res = client.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def as_hr(client, account):
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def publish(tenant, **over):
    payload = {"title": "Expenses policy", "body": "Keep receipts."}
    payload.update(over)
    res = tenant.post("/api/policies", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def test_publishing_tells_everybody_and_shows_the_coverage(tenant):
    a = person(tenant, first_name="Ann")
    b = person(tenant, first_name="Bob")
    p = publish(tenant)
    assert p["version"] == 1 and p["coverage"] == {"audience": 2, "acknowledged": 0, "outstanding": 2, "pct": 0,
                                                   "outstanding_people": [{"employee_id": a["id"], "name": f"Ann {a['last_name']}"},
                                                                          {"employee_id": b["id"], "name": f"Bob {b['last_name']}"}]}
    as_staff(tenant, a)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert "Policy to read: Expenses policy" in titles
    mine = tenant.get("/api/employee/policies").json()
    assert mine["to_read"] == 1 and mine["policies"][0]["to_read"] and mine["policies"][0]["body"] == "Keep receipts."


def test_a_policy_needs_a_title_and_words_or_a_link(tenant):
    assert tenant.post("/api/policies", json={"title": " ", "body": "x"}).status_code == 400
    assert tenant.post("/api/policies", json={"title": "Empty"}).status_code == 400
    assert tenant.post("/api/policies", json={"title": "Bad link", "url": "http://plain.example"}).status_code == 400
    assert publish(tenant, title="Linked", body="", url="https://docs.example/handbook")["url"] == "https://docs.example/handbook"


def test_acknowledging_is_per_version_and_a_republish_starts_again(tenant, account):
    a = person(tenant, first_name="Ann")
    p = publish(tenant)
    as_staff(tenant, a)
    res = tenant.post(f"/api/employee/policies/{p['id']}/acknowledge")
    assert res.status_code == 200 and res.json()["version"] == 1
    again = tenant.post(f"/api/employee/policies/{p['id']}/acknowledge").json()
    assert again["acknowledged_at"] == res.json()["acknowledged_at"], "once is once"
    assert tenant.get("/api/employee/policies").json()["to_read"] == 0
    as_hr(tenant, account)
    listed = tenant.get("/api/policies").json()
    assert listed["policies"][0]["coverage"]["pct"] == 100 and listed["outstanding_total"] == 0
    # A typo fix keeps the version and the acknowledgement.
    tenant.put(f"/api/policies/{p['id']}", json={"body": "Keep receipts!"})
    assert tenant.get("/api/policies").json()["policies"][0]["coverage"]["pct"] == 100
    # A republish is a new version everybody must read again.
    res = tenant.put(f"/api/policies/{p['id']}", json={"body": "Keep receipts and submit within 30 days.", "republish": True})
    assert res.json()["version"] == 2 and res.json()["coverage"]["outstanding"] == 1
    acks = tenant.get(f"/api/policies/{p['id']}/acks").json()["acks"]
    assert [x["version"] for x in acks] == [1]
    as_staff(tenant, a)
    mine = tenant.get("/api/employee/policies").json()
    assert mine["to_read"] == 1 and mine["policies"][0]["version"] == 2
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert titles.count("Policy to read: Expenses policy") == 2


def test_a_department_policy_is_only_that_departments(tenant):
    ops = tenant.post("/api/departments", json={"name": "Ops"}).json()
    inside = person(tenant, department_id=ops["id"])
    outside = person(tenant)
    p = publish(tenant, title="Ops handbook", department_id=ops["id"])
    assert p["coverage"]["audience"] == 1 and p["department_name"] == "Ops"
    as_staff(tenant, outside)
    assert tenant.get("/api/employee/policies").json()["policies"] == []
    assert tenant.post(f"/api/employee/policies/{p['id']}/acknowledge").status_code == 404
    as_staff(tenant, inside)
    assert tenant.get("/api/employee/policies").json()["to_read"] == 1


def test_reminders_go_only_to_those_outstanding_and_the_dashboard_counts_them(tenant, account):
    a = person(tenant, first_name="Ann")
    b = person(tenant, first_name="Bob")
    p = publish(tenant)
    as_staff(tenant, a)
    tenant.post(f"/api/employee/policies/{p['id']}/acknowledge")
    as_hr(tenant, account)
    assert tenant.post(f"/api/policies/{p['id']}/remind").json()["reminded"] == 1
    waiting = {w["key"]: w for w in tenant.get("/api/hr/dashboard").json()["waiting_on_you"]}
    assert waiting["policies"]["count"] == 1 and waiting["policies"]["view"] == "policies-view"
    as_staff(tenant, b)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert titles.count("Policy to read: Expenses policy") == 2
    as_staff(tenant, a)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert titles.count("Policy to read: Expenses policy") == 1


def test_one_that_needs_no_acknowledgement_and_one_switched_off(tenant):
    a = person(tenant)
    info = publish(tenant, title="Office map", requires_ack=False)
    assert info["coverage"] is None
    off = publish(tenant, title="Old rules")
    tenant.put(f"/api/policies/{off['id']}", json={"active": False})
    as_staff(tenant, a)
    mine = tenant.get("/api/employee/policies").json()
    assert [x["title"] for x in mine["policies"]] == ["Office map"] and mine["to_read"] == 0
    assert tenant.post(f"/api/employee/policies/{off['id']}/acknowledge").status_code == 404


def test_leavers_are_not_outstanding(tenant):
    gone = person(tenant)
    p = publish(tenant)
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    assert tenant.get("/api/policies").json()["policies"][0]["coverage"]["outstanding"] == 0


def test_another_business_sees_nothing(tenant, account):
    person(tenant)
    p = publish(tenant)
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/policies").json()["policies"] == []
    assert tenant.put(f"/api/policies/{p['id']}", json={"title": "Stolen"}).status_code == 404
    assert tenant.delete(f"/api/policies/{p['id']}").status_code == 404
