"""A qualification with a date it stops being one.

A forklift licence, a first-aid certificate, a data-protection course: HR
records them, or the person does and HR confirms. The date is the point. A
month out the person is told, a week out they are told again, and the day
it lapses once more - and HR's dashboard counts what has lapsed and what is
waiting to be looked at, because a lapsed one is a compliance problem today.
"""
import base64
from datetime import date, datetime, timedelta

import pytest

import main
import models
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"
PNG = "data:image/png;base64," + base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")).decode()
SVG = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)/>").decode()


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
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def as_hr(client, account):
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def add(client, emp_id, **over):
    payload = {"name": "Forklift licence", "issuer": "RTITB", "issued_on": days(-300),
               "expires_on": days(65)}
    payload.update(over)
    res = client.post(f"/api/employees/{emp_id}/certifications", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# --- recording one ------------------------------------------------------------------

def test_hr_records_one_and_it_is_verified_by_them(tenant):
    emp = person(tenant)
    c = add(tenant, emp["id"])
    assert c["status"] == "valid" and c["days_left"] == 65
    assert c["verified"] and c["added_by"] == "hr"
    assert c["verified_by"]     # the business's name


def test_it_needs_a_name_and_dates_in_order(tenant):
    emp = person(tenant)
    res = tenant.post(f"/api/employees/{emp['id']}/certifications", json={"name": " "})
    assert res.status_code == 400
    res = tenant.post(f"/api/employees/{emp['id']}/certifications", json={
        "name": "x", "issued_on": days(10), "expires_on": days(-10)})
    assert res.status_code == 400
    assert "before it was issued" in res.json()["detail"]
    res = tenant.post(f"/api/employees/{emp['id']}/certifications", json={
        "name": "x", "expires_on": "soon"})
    assert res.status_code == 400


def test_one_that_never_expires_is_always_valid(tenant):
    emp = person(tenant)
    c = add(tenant, emp["id"], expires_on="")
    assert c["status"] == "valid" and c["days_left"] is None


def test_the_status_follows_the_date(tenant):
    emp = person(tenant)
    assert add(tenant, emp["id"], expires_on=days(31))["status"] == "valid"
    assert add(tenant, emp["id"], expires_on=days(30))["status"] == "expiring"
    assert add(tenant, emp["id"], expires_on=days(0))["status"] == "expiring"
    lapsed = add(tenant, emp["id"], expires_on=days(-1))
    assert lapsed["status"] == "expired" and lapsed["days_left"] == -1


def test_the_certificate_picture_is_kept_and_served_but_never_svg(tenant):
    emp = person(tenant)
    c = add(tenant, emp["id"], document_data=PNG)
    assert c["has_document"]
    res = tenant.get(f"/api/certifications/{c['id']}/document")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/png")
    res = tenant.post(f"/api/employees/{emp['id']}/certifications", json={
        "name": "x", "document_data": SVG})
    assert res.status_code == 400


def test_editing_keeps_what_was_not_sent(tenant):
    emp = person(tenant)
    c = add(tenant, emp["id"], reference="RT-123")
    res = tenant.put(f"/api/certifications/{c['id']}", json={"notes": "Renewal booked"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["reference"] == "RT-123" and out["notes"] == "Renewal booked"
    assert out["name"] == "Forklift licence"


# --- the company list --------------------------------------------------------------------

def test_the_list_counts_and_filters_and_puts_the_soonest_first(tenant):
    a = person(tenant, first_name="Ann")
    b = person(tenant, first_name="Bob")
    add(tenant, a["id"], name="Later", expires_on=days(200))
    add(tenant, b["id"], name="Lapsed", expires_on=days(-5))
    add(tenant, a["id"], name="Soon", expires_on=days(10))
    add(tenant, b["id"], name="Forever", expires_on="")
    out = tenant.get("/api/certifications").json()
    assert out["counts"] == {"valid": 2, "expiring": 1, "expired": 1, "unverified": 0, "total": 4}
    assert [c["name"] for c in out["certifications"]] == ["Lapsed", "Soon", "Later", "Forever"]
    assert out["certifications"][0]["employee_name"].startswith("Bob")
    assert [c["name"] for c in tenant.get("/api/certifications?status=expiring").json()["certifications"]] == ["Soon"]


def test_a_leavers_certifications_are_not_a_compliance_problem(tenant):
    gone = person(tenant)
    add(tenant, gone["id"], expires_on=days(-5))
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    assert tenant.get("/api/certifications").json()["counts"]["expired"] == 0


def test_the_dashboard_rows_exist_with_the_right_counts(tenant, account):
    emp = person(tenant)
    add(tenant, emp["id"], expires_on=days(3))
    add(tenant, emp["id"], expires_on=days(-3))
    as_staff(tenant, emp)
    tenant.post("/api/employee/certifications", json={"name": "Mine", "expires_on": days(400)})
    as_hr(tenant, account)
    waiting = {w["key"]: w for w in tenant.get("/api/hr/dashboard").json()["waiting_on_you"]}
    assert waiting["certifications"]["count"] == 2
    assert waiting["verify"]["count"] == 1
    assert waiting["verify"]["view"] == "training-view"


# --- the person's own ---------------------------------------------------------------------

def test_a_person_adds_their_own_and_it_waits_for_hr(tenant, account):
    emp = person(tenant)
    as_staff(tenant, emp)
    res = tenant.post("/api/employee/certifications", json={
        "name": "First aid", "issuer": "St John", "expires_on": days(500), "document_data": PNG})
    assert res.status_code == 200, res.text
    c = res.json()
    assert c["added_by"] == "employee" and not c["verified"]
    mine = tenant.get("/api/employee/certifications").json()
    assert [x["name"] for x in mine["certifications"]] == ["First aid"]
    assert tenant.get(f"/api/employee/certifications/{c['id']}/document").status_code == 200
    as_hr(tenant, account)
    assert tenant.get("/api/certifications?status=unverified").json()["certifications"][0]["name"] == "First aid"
    res = tenant.put(f"/api/certifications/{c['id']}", json={"verified": True})
    assert res.json()["verified"] and res.json()["verified_by"]


def test_a_person_can_remove_their_own_until_hr_has_verified_it(tenant, account):
    emp = person(tenant)
    as_staff(tenant, emp)
    c = tenant.post("/api/employee/certifications", json={"name": "Typo"}).json()
    assert tenant.delete(f"/api/employee/certifications/{c['id']}").status_code == 200
    c = tenant.post("/api/employee/certifications", json={"name": "Real"}).json()
    as_hr(tenant, account)
    tenant.put(f"/api/certifications/{c['id']}", json={"verified": True})
    as_staff(tenant, emp)
    res = tenant.delete(f"/api/employee/certifications/{c['id']}")
    assert res.status_code == 409
    assert "HR has verified" in res.json()["detail"]


def test_a_person_sees_only_their_own(tenant, account):
    a = person(tenant)
    b = person(tenant)
    c = add(tenant, a["id"], document_data=PNG)
    as_staff(tenant, b)
    assert tenant.get("/api/employee/certifications").json()["certifications"] == []
    assert tenant.get(f"/api/employee/certifications/{c['id']}/document").status_code == 404
    assert tenant.delete(f"/api/employee/certifications/{c['id']}").status_code == 404


def test_another_business_cannot_touch_it(tenant, account):
    emp = person(tenant)
    c = add(tenant, emp["id"])
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest",
                                              "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/certifications").json()["certifications"] == []
    assert tenant.put(f"/api/certifications/{c['id']}", json={"name": "Stolen"}).status_code == 404
    assert tenant.delete(f"/api/certifications/{c['id']}").status_code == 404
    assert tenant.get(f"/api/employees/{emp['id']}/certifications").status_code == 404


# --- being told ----------------------------------------------------------------------------

def run_job(now=None):
    """The job itself, not the scheduler: the scheduler claims a day once per
    process, and these tests need to run it several times in one."""
    with main.SessionLocal() as db:
        return main.job_certification_expiry(db, now or datetime.now())


def titles_for(client):
    return [n["title"] for n in client.get("/api/employee/notifications").json()["notifications"]]


def test_the_job_is_on_the_daily_schedule(tenant):
    assert "certification_expiry" in [name for name, _, _ in main.SCHEDULED_JOBS]
    out = main.run_due_jobs(datetime.now(), only="certification_expiry")
    assert out and out[0]["status"] in ("done", "already_done"), out


def test_the_daily_job_tells_the_person_once_per_stage(tenant):
    emp = person(tenant)
    c = add(tenant, emp["id"], name="Forklift licence", expires_on=days(20))
    assert run_job() == "1 told"
    as_staff(tenant, emp)
    assert any(t.startswith("Forklift licence expires on") for t in titles_for(tenant))
    # The same morning again says nothing new.
    assert run_job() == "0 told"
    with main.SessionLocal() as db:
        row = db.get(models.DBCertification, c["id"])
        assert row.reminder_stage == 1
        row.expires_on = days(5)          # a week out now
        db.commit()
    assert run_job() == "1 told"
    assert any(t == "Forklift licence expires in 5 days" for t in titles_for(tenant)), titles_for(tenant)
    with main.SessionLocal() as db:
        db.get(models.DBCertification, c["id"]).expires_on = days(-1)
        db.commit()
    assert run_job() == "1 told"
    assert "Forklift licence has expired" in titles_for(tenant)
    assert run_job() == "0 told"


def test_a_new_expiry_date_starts_the_reminders_again(tenant):
    emp = person(tenant)
    c = add(tenant, emp["id"], expires_on=days(10))
    run_job()
    with main.SessionLocal() as db:
        assert db.get(models.DBCertification, c["id"]).reminder_stage == 1
    tenant.put(f"/api/certifications/{c['id']}", json={"expires_on": days(400)})
    with main.SessionLocal() as db:
        assert db.get(models.DBCertification, c["id"]).reminder_stage == 0


def test_a_leaver_is_not_told(tenant):
    emp = person(tenant)
    add(tenant, emp["id"], expires_on=days(-2))
    tenant.put(f"/api/employees/{emp['id']}", json={"status": "terminated"})
    assert run_job() == "0 told"


def test_deleting_the_person_takes_their_certifications_with_them(tenant):
    emp = person(tenant)
    c = add(tenant, emp["id"])
    assert tenant.delete(f"/api/employees/{emp['id']}").status_code == 200
    with main.SessionLocal() as db:
        assert db.get(models.DBCertification, c["id"]) is None
