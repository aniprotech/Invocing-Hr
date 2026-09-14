"""A new hire is on probation until a date, and somebody has to decide.

Until now the trial period ended when somebody remembered, which is to say
it did not end. The date is set the moment they are added - the tenant's
default months after they start, unless one is given - the manager is
told a fortnight before and on the day, the dashboard counts what is due,
and the decision is written to their history and told to them.

And birthdays and work anniversaries: a day and a month to colleagues,
never an age, and only for people with a date on file.
"""
from datetime import date, datetime, timedelta

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
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def probation_of(tenant, emp_id):
    return tenant.get(f"/api/employees/{emp_id}").json()["probation"]


def run_job():
    with main.SessionLocal() as db:
        return main.job_probation_reminders(db, datetime.now())


# --- it starts when they do -------------------------------------------------------

def test_a_new_hire_is_on_probation_for_the_default_three_months(tenant):
    emp = person(tenant, start_date="2026-01-31")
    p = probation_of(tenant, emp["id"])
    assert p["status"] == "on_probation"
    assert p["end"] == "2026-04-30"          # three months on, clamped to the month's end


def test_the_tenant_sets_its_own_default(tenant):
    tenant.post("/api/settings", json={"probation_months": 6})
    emp = person(tenant, start_date="2026-03-01")
    assert probation_of(tenant, emp["id"])["end"] == "2026-09-01"
    tenant.post("/api/settings", json={"probation_months": 0})
    none = person(tenant, start_date="2026-03-01")
    assert probation_of(tenant, none["id"])["status"] == ""


def test_an_explicit_date_or_months_on_the_hire_wins(tenant):
    a = person(tenant, start_date="2026-03-01", probation_end="2026-12-24")
    assert probation_of(tenant, a["id"])["end"] == "2026-12-24"
    b = person(tenant, start_date="2026-03-01", probation_months=1)
    assert probation_of(tenant, b["id"])["end"] == "2026-04-01"
    res = tenant.post("/api/employees", json={
        "first_name": "Bad", "last_name": "Date", "email": f"bad-{a['id']}@example.com",
        "probation_end": "soonish"})
    assert res.status_code == 400


def test_days_left_due_and_overdue_are_worked_out(tenant):
    soon = person(tenant, probation_end=days(10))
    p = probation_of(tenant, soon["id"])
    assert p["days_left"] == 10 and p["due"] and not p["overdue"]
    later = person(tenant, probation_end=days(40))
    assert not probation_of(tenant, later["id"])["due"]
    past = person(tenant, probation_end=days(-3))
    p = probation_of(tenant, past["id"])
    assert p["due"] and p["overdue"] and p["days_left"] == -3


# --- the list and the dashboard ---------------------------------------------------------

def test_the_list_is_soonest_first_and_counts_due_and_overdue(tenant):
    boss = person(tenant, first_name="Bea", probation_months=0)
    person(tenant, first_name="Later", probation_end=days(60), reports_to=boss["id"])
    person(tenant, first_name="Soon", probation_end=days(5))
    person(tenant, first_name="Past", probation_end=days(-1))
    out = tenant.get("/api/probations").json()
    assert [p["employee_name"].split()[0] for p in out["probations"]] == ["Past", "Soon", "Later"]
    assert out["due"] == 2 and out["overdue"] == 1
    assert out["probations"][2]["manager_name"].startswith("Bea")
    waiting = {w["key"]: w for w in tenant.get("/api/hr/dashboard").json()["waiting_on_you"]}
    assert waiting["probations"]["count"] == 2
    coming = tenant.get("/api/hr/dashboard").json()["coming_up"]["probations"]
    assert [c["name"].split()[0] for c in coming] == ["Past", "Soon"]


def test_a_leaver_on_probation_is_nobodys_decision(tenant):
    gone = person(tenant, probation_end=days(2))
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    assert tenant.get("/api/probations").json()["probations"] == []


# --- deciding ---------------------------------------------------------------------------------

def test_confirming_tells_them_and_goes_on_their_record(tenant):
    emp = person(tenant, probation_end=days(3))
    res = tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "confirm", "note": "Great start"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "confirmed" and res.json()["days_left"] is None
    assert res.json()["decided_by"]
    hist = tenant.get(f"/api/employees/{emp['id']}/history").json()["history"]
    assert hist[0]["kind"] == "probation" and hist[0]["new_value"] == "Probation passed"
    assert hist[0]["note"] == "Great start"
    as_staff(tenant, emp)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert "Probation passed" in titles
    # Deciding twice is refused.
    main.rate_limiter._hits.clear()
    tenant.post("/api/employee/auth/logout")


def test_extending_needs_a_later_date_and_restarts_the_reminders(tenant):
    emp = person(tenant, probation_end=days(3))
    run_job()
    res = tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "extend", "until": days(1)})
    assert res.status_code == 400
    res = tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "extend", "until": days(60)})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "extended" and res.json()["end"] == days(60)
    with main.SessionLocal() as db:
        row = db.get(main.models.DBEmployee, emp["id"])
        assert row.probation_reminder_stage == 0


def test_ending_needs_a_reason(tenant):
    emp = person(tenant, probation_end=days(3))
    assert tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "end"}).status_code == 400
    res = tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "end", "note": "Not the right fit"})
    assert res.status_code == 200 and res.json()["status"] == "ended"
    assert tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "confirm"}).status_code == 409


def test_hr_can_put_somebody_on_probation_by_hand(tenant):
    emp = person(tenant, probation_months=0)
    assert probation_of(tenant, emp["id"])["status"] == ""
    res = tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "start", "months": 2})
    assert res.status_code == 200 and res.json()["status"] == "on_probation"
    res = tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "sideways"})
    assert res.status_code == 400
    # Typing a date onto the profile does the same.
    other = person(tenant, probation_months=0)
    tenant.put(f"/api/employees/{other['id']}", json={"probation_end": days(30)})
    assert probation_of(tenant, other["id"])["status"] == "on_probation"


# --- the manager is told ----------------------------------------------------------------------

def test_the_manager_is_told_a_fortnight_out_and_on_the_day_once_each(tenant):
    boss = person(tenant, first_name="Bea", probation_months=0)
    emp = person(tenant, first_name="Nia", probation_end=days(10), reports_to=boss["id"])
    assert run_job() == "1 told"
    assert run_job() == "0 told"
    with main.SessionLocal() as db:
        db.get(main.models.DBEmployee, emp["id"]).probation_end = days(0)
        db.commit()
    assert run_job() == "1 told"
    as_staff(tenant, boss)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert any(t.startswith("Nia") and "ends in 10 days" in t for t in titles), titles
    assert any(t.startswith("Nia") and "ends today" in t for t in titles), titles


def test_nobody_is_told_about_somebody_with_no_manager_but_the_stage_still_moves(tenant):
    emp = person(tenant, probation_end=days(2))
    assert run_job() == "0 told"
    with main.SessionLocal() as db:
        assert db.get(main.models.DBEmployee, emp["id"]).probation_reminder_stage == 1


# --- celebrations -----------------------------------------------------------------------------

def test_birthdays_and_anniversaries_in_the_next_month(tenant):
    today = date.today()
    in_5 = today + timedelta(days=5)
    in_50 = today + timedelta(days=50)
    person(tenant, first_name="Bday", date_of_birth=f"1990-{in_5.month:02d}-{in_5.day:02d}")
    person(tenant, first_name="Later", date_of_birth=f"1990-{in_50.month:02d}-{in_50.day:02d}")
    person(tenant, first_name="Anni", start_date=f"{today.year - 3}-{in_5.month:02d}-{in_5.day:02d}")
    person(tenant, first_name="New", start_date=today.isoformat())         # no anniversary yet
    out = tenant.get("/api/hr/celebrations?days=30").json()["celebrations"]
    kinds = [(c["name"].split()[0], c["kind"], c["years"]) for c in out]
    assert ("Bday", "birthday", None) in kinds
    assert ("Anni", "anniversary", 3) in kinds
    assert not any(k[0] in ("Later", "New") for k in kinds)
    bday = next(c for c in out if c["kind"] == "birthday")
    assert bday["in_days"] == 5 and "1990" not in str(bday)


def test_colleagues_see_them_too_but_never_a_year(tenant):
    today = date.today()
    soon = today + timedelta(days=2)
    emp = person(tenant, date_of_birth=f"1985-{soon.month:02d}-{soon.day:02d}")
    other = person(tenant)
    as_staff(tenant, other)
    out = tenant.get("/api/employee/celebrations").json()["celebrations"]
    assert out and out[0]["employee_id"] == emp["id"]
    assert "1985" not in tenant.get("/api/employee/celebrations").text


def test_a_bad_date_of_birth_is_refused(tenant):
    emp = person(tenant)
    assert tenant.put(f"/api/employees/{emp['id']}", json={"date_of_birth": "yesterday"}).status_code == 400
    assert tenant.put(f"/api/employees/{emp['id']}", json={"date_of_birth": "1990-05-05"}).status_code == 200
    assert tenant.get(f"/api/employees/{emp['id']}").json()["date_of_birth"] == "1990-05-05"


def test_analytics_counts_ages_and_probations(tenant):
    person(tenant, date_of_birth="2004-01-01", probation_end=days(30))
    person(tenant, date_of_birth="1980-01-01", probation_months=0)
    person(tenant, probation_months=0)
    h = tenant.get("/api/hr/analytics").json()["headcount"]
    assert h["age_bands"]["under_25"] == 1 and h["age_bands"]["45_54"] == 1 and h["age_bands"]["unknown"] == 1
    assert h["on_probation"] == 1
