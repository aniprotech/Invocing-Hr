"""The handful of things the portal wants from a person, as counts that
jump to the tab; and, for the operator, which businesses use which parts
of the HR side. The operator's view is guarded like every operator view.
"""
from datetime import date, timedelta

import pytest

import main
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


def days(n):
    return (date.today() + timedelta(days=n)).isoformat()


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


def test_an_empty_slate_is_an_empty_list(tenant):
    emp = person(tenant, probation_months=0)
    as_staff(tenant, emp)
    out = tenant.get("/api/employee/todo").json()
    assert out["items"] == [] and out["total"] == 0


def test_the_list_gathers_what_is_waiting(tenant):
    boss = person(tenant, first_name="Bea", probation_months=0, start_date=days(-400))
    emp = person(tenant, reports_to=boss["id"], probation_end=days(10))
    tenant.post("/api/policies", json={"title": "Handbook", "body": "Read me"})
    tenant.post(f"/api/employees/{emp['id']}/certifications", json={"name": "Lapsed", "expires_on": days(-1)})
    tenant.post(f"/api/employees/{emp['id']}/goals", json={"title": "Late", "target_value": 5, "current_value": 0, "due_date": days(-1)})
    c = tenant.post("/api/review-cycles", json={"name": "H1"}).json()
    tenant.post(f"/api/review-cycles/{c['id']}/open")
    as_staff(tenant, emp)
    items = {i["key"]: i for i in tenant.get("/api/employee/todo").json()["items"]}
    assert items["self_review"]["count"] == 1 and items["self_review"]["tab"] == "reviews"
    assert items["policies"]["count"] == 1 and items["policies"]["tab"] == "documents"
    assert items["certifications"]["count"] == 1 and items["goals"]["count"] == 1
    assert items["one_to_one"]["count"] == 1 and items["probation"]["label"] == f"Probation ends {days(10)}"
    assert "reviews" not in items, "they review nobody"
    as_staff(tenant, boss)
    items = {i["key"]: i for i in tenant.get("/api/employee/todo").json()["items"]}
    assert items["reviews"]["count"] == 1 and "one_to_one" not in items, "the boss has no manager to meet"


def test_the_adoption_report_is_the_operators_and_counts_per_business(tenant, account):
    emp = person(tenant)
    tenant.post("/api/policies", json={"title": "Handbook", "body": "x"})
    tenant.put(f"/api/employees/{emp['id']}/skills", json={"skills": [{"name": "SQL", "level": 2}]})
    assert tenant.get("/api/superadmin/hr-adoption").status_code in (401, 403)
    with main.SessionLocal() as db:
        cid = db.query(main.models.DBClient).filter(main.models.DBClient.email == account["email"]).first().id
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    res = tenant.post("/api/superadmin/login", json={"identifier": "hello@keyroutes.co", "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    out = tenant.get("/api/superadmin/hr-adoption").json()
    mine = next(b for b in out["businesses"] if b["client_id"] == cid)
    assert mine["employees"] == 1 and mine["features"]["policies"] == 1 and mine["features"]["skills"] == 1
    assert mine["features_used"] >= 2 and "webhooks" in out["feature_keys"]
