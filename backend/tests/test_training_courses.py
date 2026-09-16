"""Training courses: what people are asked to learn, and whether they did.

A course is a title, a link, how long it takes, whether it is mandatory
and whether it must be done again. HR assigns it to people, a department
or everybody; each person sees it in their portal and marks it done, or
HR does; a course that renews comes due again; reminders go out a week
before, on the day and once when late; the dashboard counts what is
overdue. Nothing crosses a business.
"""
from datetime import date, datetime, timedelta

import pytest

import main
import models
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
    assert client.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD}).status_code == 200


def as_hr(client, account):
    main.rate_limiter._hits.clear()
    client.post("/api/employee/auth/logout")
    assert client.post("/api/client/login", json={"email": account["email"], "password": account["password"]}).status_code == 200


def course(tenant, **kw):
    res = tenant.post("/api/courses", json=dict({"title": "Fire safety", "link": "https://learn.example/fire", "due_days": 14}, **kw))
    assert res.status_code == 200, res.text
    return res.json()


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def test_a_course_is_made_assigned_and_seen_by_the_person(tenant, account):
    c = course(tenant, mandatory=True, duration_hours=1.5, provider="Safety Co")
    assert c["mandatory"] and c["due_days"] == 14 and c["assigned"] == 0
    ann = person(tenant, first_name="Ann", last_name="Lee")
    bo = person(tenant, first_name="Bo")
    res = tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"], bo["id"]]})
    assert res.json() == {"assigned": 2, "already": 0}
    assert tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"]]}).json() == {"assigned": 0, "already": 1}
    listed = tenant.get("/api/courses").json()["courses"][0]
    assert listed["assigned"] == 2 and listed["done"] == 0
    rows = tenant.get(f"/api/courses/{c['id']}/assignments").json()["assignments"]
    assert {r["employee"] for r in rows} == {"Ann Lee", "Bo " + bo["last_name"]} and all(r["status"] == "assigned" and r["due_on"] == d(14) for r in rows)
    as_staff(tenant, ann)
    mine = tenant.get("/api/employee/courses").json()["courses"]
    assert len(mine) == 1 and mine[0]["course"]["title"] == "Fire safety" and mine[0]["course"]["link"] == "https://learn.example/fire" and mine[0]["status"] == "assigned"
    notes = tenant.get("/api/employee/notifications").json()
    titles = [n["title"] for n in (notes if isinstance(notes, list) else notes.get("notifications", []))]
    assert "Training: Fire safety" in titles
    items = {i["key"]: i for i in tenant.get("/api/employee/todo").json()["items"]}
    assert items["training"]["count"] == 1
    # Done, from the portal.
    res = tenant.post(f"/api/employee/courses/{c['id']}/complete", json={"note": "Passed the quiz"})
    assert res.status_code == 200 and res.json()["status"] == "done" and res.json()["completed_by"] == "employee" and res.json()["completed_on"] == d(0)
    assert "training" not in {i["key"] for i in tenant.get("/api/employee/todo").json()["items"]}
    as_hr(tenant, account)
    prof = tenant.get(f"/api/employees/{ann['id']}/courses").json()["courses"]
    assert prof[0]["status"] == "done" and prof[0]["note"] == "Passed the quiz"
    assert tenant.get("/api/courses").json()["courses"][0]["done"] == 1


def test_what_a_course_must_be(tenant):
    assert tenant.post("/api/courses", json={"title": " "}).status_code == 400
    assert tenant.post("/api/courses", json={"title": "x", "link": "ftp://nope"}).status_code == 400
    assert tenant.post("/api/courses", json={"title": "x", "due_days": -1}).status_code == 400
    assert tenant.post("/api/courses", json={"title": "x", "renew_months": "soon"}).status_code == 400
    c = course(tenant)
    up = tenant.put(f"/api/courses/{c['id']}", json={"renew_months": 12, "self_complete": False}).json()
    assert up["renew_months"] == 12 and up["self_complete"] is False and up["title"] == "Fire safety", "only what was sent changes"


def test_hr_marks_it_done_when_the_person_may_not(tenant, account):
    c = course(tenant, self_complete=False)
    ann = person(tenant, first_name="Ann")
    tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"]]})
    as_staff(tenant, ann)
    assert tenant.post(f"/api/employee/courses/{c['id']}/complete", json={}).status_code == 403
    as_hr(tenant, account)
    res = tenant.post(f"/api/courses/{c['id']}/assignments/{ann['id']}/complete", json={"completed_on": d(-3), "note": "Seen the certificate"})
    assert res.status_code == 200 and res.json()["status"] == "done" and res.json()["completed_by"] == "hr" and res.json()["completed_on"] == d(-3)
    assert tenant.post(f"/api/courses/{c['id']}/assignments/{ann['id']}/complete", json={"completed_on": "soon"}).status_code == 400


def test_a_course_that_renews_comes_due_again(tenant, account):
    c = course(tenant, renew_months=12)
    ann = person(tenant, first_name="Ann")
    tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"]]})
    long_ago = (date.today() - timedelta(days=400)).isoformat()
    res = tenant.post(f"/api/courses/{c['id']}/assignments/{ann['id']}/complete", json={"completed_on": long_ago})
    assert res.json()["expires_on"] == main._add_months(main._parse_date(long_ago), 12).isoformat()
    rows = tenant.get(f"/api/courses/{c['id']}/assignments").json()["assignments"]
    assert rows[0]["status"] == "due_again"
    assert main.training_summary(main.SessionLocal(), tenant.get("/api/client/me").json()["id"])["overdue_count"] == 1
    # Assigning again gives a fresh due date rather than refusing.
    assert tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"]]}).json() == {"assigned": 1, "already": 0}
    rows = tenant.get(f"/api/courses/{c['id']}/assignments").json()["assignments"]
    assert rows[0]["status"] == "assigned" and rows[0]["due_on"] == d(14) and rows[0]["completed_on"] == ""


def test_assigning_to_a_department_or_everybody_and_leavers_are_left_out(tenant):
    ops = tenant.post("/api/departments", json={"name": "Ops"}).json()
    a = person(tenant, first_name="A", department_id=ops["id"])
    b = person(tenant, first_name="B", department_id=ops["id"])
    c_ = person(tenant, first_name="C")
    gone = person(tenant, first_name="Gone", department_id=ops["id"])
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "left"})
    c = course(tenant)
    assert tenant.post(f"/api/courses/{c['id']}/assign", json={"department_id": ops["id"]}).json() == {"assigned": 2, "already": 0}
    assert tenant.post(f"/api/courses/{c['id']}/assign", json={"everyone": True}).json() == {"assigned": 1, "already": 2}
    assert {r["employee_id"] for r in tenant.get(f"/api/courses/{c['id']}/assignments").json()["assignments"]} == {a["id"], b["id"], c_["id"]}
    assert tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": []}).status_code == 400
    assert tenant.delete(f"/api/courses/{c['id']}/assignments/{c_['id']}").status_code == 200
    assert len(tenant.get(f"/api/courses/{c['id']}/assignments").json()["assignments"]) == 2


def test_overdue_is_counted_on_the_dashboard_and_in_analytics(tenant):
    c = course(tenant, due_days=0)
    ann = person(tenant, first_name="Ann")
    tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"]]})
    with main.SessionLocal() as db:
        a = db.query(models.DBCourseAssignment).filter(models.DBCourseAssignment.employee_id == ann["id"]).first()
        a.due_on = d(-2)
        db.commit()
    dash = tenant.get("/api/hr/dashboard").json()
    row = next(w for w in dash["waiting_on_you"] if w["key"] == "training")
    assert row["count"] == 1 and row["view"] == "training-view"
    t = tenant.get("/api/hr/analytics").json()["training"]
    assert t["overdue_count"] == 1 and t["overdue"][0]["course"] == "Fire safety" and t["completion_pct"] == 0
    assert tenant.get("/api/courses").json()["courses"][0]["overdue"] == 1


def test_reminders_go_a_week_before_on_the_day_and_once_when_late(tenant):
    c = course(tenant, due_days=7)
    ann = person(tenant, first_name="Ann")
    tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"]]})
    with main.SessionLocal() as db:
        db.query(models.DBNotification).filter(models.DBNotification.employee_id == ann["id"]).delete()
        db.commit()

    def run(days_from_now):
        """Ann's notifications after the job runs on that day. The job is
        platform-wide, so other tests' assignments are not counted here."""
        with main.SessionLocal() as db:
            out = main.job_training_reminders(db, datetime.combine(date.today() + timedelta(days=days_from_now), datetime.min.time()).replace(hour=8))
            assert out.endswith("sent")
            return db.query(models.DBNotification).filter(models.DBNotification.employee_id == ann["id"]).count()
    assert run(0) == 1, "due in a week"
    assert run(0) == 1, "not twice"
    assert run(3) == 1
    assert run(7) == 2, "on the day"
    assert run(8) == 3, "late, once"
    assert run(20) == 3
    with main.SessionLocal() as db:
        last = db.query(models.DBNotification).filter(models.DBNotification.employee_id == ann["id"]).order_by(models.DBNotification.id.desc()).first()
        assert "overdue" in last.message and last.type == "warning"


def test_closing_and_removing_a_course(tenant):
    c = course(tenant)
    assert tenant.delete(f"/api/courses/{c['id']}").json()["closed"] is False
    c2 = course(tenant, title="Again")
    ann = person(tenant, first_name="Ann")
    tenant.post(f"/api/courses/{c2['id']}/assign", json={"employee_ids": [ann["id"]]})
    assert tenant.delete(f"/api/courses/{c2['id']}").json()["closed"] is True
    assert tenant.get("/api/courses").json()["courses"][0]["active"] is False
    assert tenant.post(f"/api/courses/{c2['id']}/assign", json={"employee_ids": [ann["id"]]}).status_code == 400
    assert tenant.delete(f"/api/employees/{ann['id']}").status_code == 200, "a leaver's assignments go with them"


def test_nothing_crosses_a_business(tenant, account):
    c = course(tenant)
    ann = person(tenant, first_name="Ann")
    tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [ann["id"]]})
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/courses").json()["courses"] == []
    assert tenant.get(f"/api/courses/{c['id']}/assignments").status_code == 404
    assert tenant.put(f"/api/courses/{c['id']}", json={"title": "Stolen"}).status_code == 404
    theirs = person(tenant, first_name="Their")
    assert tenant.post(f"/api/courses/{c['id']}/assign", json={"employee_ids": [theirs["id"]]}).status_code == 404
    as_staff(tenant, theirs)
    assert tenant.post(f"/api/employee/courses/{c['id']}/complete", json={}).status_code == 404
