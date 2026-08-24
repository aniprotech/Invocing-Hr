"""Letting the person who worked the day say what it was.

The nightly job closes a forgotten clock-out and records no hours, on purpose:
the shift length is not knowable from the outside. That leaves the employee
holding a day worth nothing and, until this existed, no way to say so.

The rule these hold down is that a request never changes the record. The
proposed times wait until HR decides, and a rejection leaves the attendance
row exactly as it was.
"""
import pytest

import database
import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def staffer(tenant):
    return make_employee(tenant, password="EmpPass123")


@pytest.fixture
def portal(client, tenant, staffer):
    res = client.post("/api/employee/auth/login",
                      json={"email": staffer["email"], "password": "EmpPass123"})
    assert res.status_code == 200, res.text
    return client


def add_shift(tenant, emp_id, day="2026-08-06", clock_in="09:00:00",
              clock_out="", status="needs_review"):
    cid = tenant.get("/api/client/me").json()["id"]
    with database.SessionLocal() as db:
        att = models.DBAttendance(
            client_id=cid, employee_id=emp_id, date=day, clock_in=clock_in,
            clock_out=clock_out, status=status, total_hours=0.0)
        db.add(att)
        db.commit()
        return att.id


def shift(att_id):
    with database.SessionLocal() as db:
        return db.query(models.DBAttendance).filter(
            models.DBAttendance.id == att_id).first()


def raise_one(portal, att_id, **over):
    payload = {"attendance_id": att_id, "clock_in": "09:00",
               "clock_out": "17:30", "reason": "Forgot to clock out"}
    payload.update(over)
    return portal.post("/api/employee/attendance/corrections", json=payload)


# --- raising one ------------------------------------------------------------

def test_an_employee_can_ask_for_a_day_to_be_fixed(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    res = raise_one(portal, att_id)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "pending"


def test_raising_one_changes_nothing_yet(portal, tenant, staffer):
    """The whole shape of this: asking is not doing."""
    att_id = add_shift(tenant, staffer["id"])
    raise_one(portal, att_id)

    row = shift(att_id)
    assert row.clock_out == ""
    assert row.total_hours == 0.0
    assert row.status == "needs_review"


def test_the_old_values_are_kept(portal, tenant, staffer):
    """So an approval landing days later can still show what it changed."""
    att_id = add_shift(tenant, staffer["id"], clock_in="08:15:00")
    body = raise_one(portal, att_id).json()
    assert body["old_clock_in"] == "08:15:00"
    assert body["old_clock_out"] == ""


def test_a_reason_is_required(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    assert raise_one(portal, att_id, reason="").status_code == 400


def test_a_finish_before_a_start_is_refused(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    res = raise_one(portal, att_id, clock_in="17:00", clock_out="09:00")
    assert res.status_code == 400


def test_nonsense_times_are_refused(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    assert raise_one(portal, att_id, clock_in="banana").status_code == 400


def test_only_one_request_may_be_open_on_a_day(portal, tenant, staffer):
    """A second would silently replace what HR is part-way through deciding."""
    att_id = add_shift(tenant, staffer["id"])
    assert raise_one(portal, att_id).status_code == 200
    assert raise_one(portal, att_id).status_code == 409


def test_an_employee_cannot_correct_somebody_elses_day(portal, tenant):
    """The one that matters: this must be scoped to the person asking."""
    other = make_employee(tenant)
    att_id = add_shift(tenant, other["id"])
    assert raise_one(portal, att_id).status_code == 404


# --- deciding ---------------------------------------------------------------

def test_approving_writes_the_times_and_the_hours(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    cid = raise_one(portal, att_id).json()["id"]

    res = tenant.post(f"/api/hr/attendance/corrections/{cid}/decide",
                      json={"decision": "approve"})
    assert res.status_code == 200, res.text

    row = shift(att_id)
    assert row.clock_in == "09:00:00"
    assert row.clock_out == "17:30:00"
    assert row.total_hours == 8.5
    assert row.status == "completed"


def test_rejecting_leaves_the_record_untouched(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    cid = raise_one(portal, att_id).json()["id"]

    tenant.post(f"/api/hr/attendance/corrections/{cid}/decide",
                json={"decision": "reject", "note": "You were on leave"})

    row = shift(att_id)
    assert row.clock_out == ""
    assert row.total_hours == 0.0
    assert row.status == "needs_review"


def test_a_decision_cannot_be_made_twice(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    cid = raise_one(portal, att_id).json()["id"]
    tenant.post(f"/api/hr/attendance/corrections/{cid}/decide", json={"decision": "approve"})
    again = tenant.post(f"/api/hr/attendance/corrections/{cid}/decide",
                        json={"decision": "reject"})
    assert again.status_code == 409


def test_hr_sees_the_queue(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    raise_one(portal, att_id)
    rows = tenant.get("/api/hr/attendance/corrections").json()
    assert len(rows) == 1
    assert rows[0]["employee_name"]


def test_the_employee_can_see_what_they_asked_for(portal, tenant, staffer):
    att_id = add_shift(tenant, staffer["id"])
    raise_one(portal, att_id)
    rows = portal.get("/api/employee/attendance/corrections").json()
    assert [r["reason"] for r in rows] == ["Forgot to clock out"]


def test_a_stranger_cannot_reach_the_queue(client):
    assert client.get("/api/hr/attendance/corrections").status_code in (401, 403)

def test_the_portal_is_told_which_day_is_which(portal, tenant, staffer):
    """The Fix button sends an attendance id, so the dashboard has to include
    one. It did not, and the button would have posted undefined."""
    att_id = add_shift(tenant, staffer["id"])
    rows = portal.get("/api/employee/dashboard").json()["attendance"]
    assert rows, "no attendance came back"
    assert att_id in [r["id"] for r in rows]
