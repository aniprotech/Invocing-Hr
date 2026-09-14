"""A manager and one of their reports, on a date.

Either side books it and adds what they want to talk about. The notes are
shared. The actions carry over to the next one until they are ticked, so
"we said we would sort the laptop" is still there three meetings later. The
manager keeps a private note the report never receives - and neither does
HR, because a note HR could read is not a private one. HR sees which
reporting lines have gone quiet, which is the number that matters.
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
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def as_hr(client, account):
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def team(tenant):
    boss = person(tenant, first_name="Bea", last_name="Boss")
    report = person(tenant, first_name="Ravi", last_name="Kumar", reports_to=boss["id"])
    other = person(tenant, first_name="Lena", last_name="Ortiz")
    return boss, report, other


def book(client, when=None, **over):
    payload = {"scheduled_for": when or days(1)}
    payload.update(over)
    res = client.post("/api/employee/check-ins", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# --- booking one -----------------------------------------------------------------

def test_a_report_books_one_with_their_manager_and_the_manager_is_told(tenant):
    boss, report, _ = team(tenant)
    as_staff(tenant, report)
    c = book(tenant, days(2), talking_points=["Pay", "  ", "The laptop"])
    assert c["manager_id"] == boss["id"] and c["employee_id"] == report["id"]
    assert c["my_role"] == "employee" and c["status"] == "planned"
    assert [t["text"] for t in c["talking_points"]] == ["Pay", "The laptop"]
    assert all(t["by"] == report["id"] for t in c["talking_points"])
    mine = tenant.get("/api/employee/check-ins").json()
    assert [x["id"] for x in mine["with_my_manager"]] == [c["id"]]
    assert mine["manager"]["name"] == "Bea Boss"
    as_staff(tenant, boss)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert f"One-to-one on {days(2)}" in titles
    theirs = tenant.get("/api/employee/check-ins").json()
    assert [x["employee_name"] for x in theirs["with_my_reports"]] == ["Ravi Kumar"]
    assert [r["name"] for r in theirs["reports"]] == ["Ravi Kumar"]


def test_a_manager_books_one_with_a_report_but_not_with_anybody_else(tenant):
    boss, report, other = team(tenant)
    as_staff(tenant, boss)
    c = book(tenant, employee_id=report["id"])
    assert c["my_role"] == "manager"
    res = tenant.post("/api/employee/check-ins", json={"scheduled_for": days(1), "employee_id": other["id"]})
    assert res.status_code == 404
    assert "Not one of your reports" in res.json()["detail"]


def test_somebody_with_no_manager_is_told_why(tenant):
    _, _, other = team(tenant)
    as_staff(tenant, other)
    res = tenant.post("/api/employee/check-ins", json={"scheduled_for": days(1)})
    assert res.status_code == 400
    assert "no manager" in res.json()["detail"]
    res = tenant.post("/api/employee/check-ins", json={"scheduled_for": "tomorrow", "employee_id": None})
    assert res.status_code == 400


# --- in the room ---------------------------------------------------------------------

def test_both_sides_add_talking_points_and_the_notes_are_shared(tenant):
    boss, report, _ = team(tenant)
    as_staff(tenant, report)
    c = book(tenant, talking_points=["Pay"])
    as_staff(tenant, boss)
    res = tenant.put(f"/api/employee/check-ins/{c['id']}", json={
        "talking_points": c["talking_points"] + [{"text": "Q3 targets"}],
        "notes": "Agreed a pay review in October.",
        "private_note": "Flight risk if nothing moves."})
    assert res.status_code == 200, res.text
    got = res.json()
    assert [t["by"] for t in got["talking_points"]] == [report["id"], boss["id"]]
    assert got["private_note"] == "Flight risk if nothing moves."
    as_staff(tenant, report)
    seen = tenant.get(f"/api/employee/check-ins/{c['id']}").json()
    assert seen["notes"] == "Agreed a pay review in October."
    assert "private_note" not in seen, "the private note is the manager's alone"


def test_a_report_cannot_write_the_private_note(tenant):
    boss, report, _ = team(tenant)
    as_staff(tenant, report)
    c = book(tenant)
    res = tenant.put(f"/api/employee/check-ins/{c['id']}", json={"private_note": "I wrote this"})
    assert res.status_code == 200
    as_staff(tenant, boss)
    assert tenant.get(f"/api/employee/check-ins/{c['id']}").json()["private_note"] == ""


def test_actions_carry_over_until_they_are_ticked(tenant):
    boss, report, _ = team(tenant)
    as_staff(tenant, boss)
    first = book(tenant, days(-14), employee_id=report["id"])
    res = tenant.post(f"/api/employee/check-ins/{first['id']}/complete", json={
        "actions": [{"text": "Order the laptop", "owner": boss["id"]},
                    {"text": "Draft the plan", "owner": report["id"], "done": True}]})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "done" and res.json()["completed_at"]
    second = book(tenant, days(0), employee_id=report["id"])
    carried = second["carried_actions"]
    assert [a["text"] for a in carried] == ["Order the laptop"]
    assert carried[0]["from_date"] == days(-14) and carried[0]["check_in_id"] == first["id"]
    # Ticked from the meeting it came up in again, on the row it was written on.
    res = tenant.post(f"/api/employee/check-ins/{second['id']}/actions/{first['id']}/0/done")
    assert res.status_code == 200
    assert res.json()["carried_actions"] == []
    assert tenant.get(f"/api/employee/check-ins/{first['id']}").json()["actions"][0]["done"] is True


def test_completing_tells_the_other_side_how_many_actions_are_theirs(tenant):
    boss, report, _ = team(tenant)
    as_staff(tenant, boss)
    c = book(tenant, days(0), employee_id=report["id"])
    tenant.post(f"/api/employee/check-ins/{c['id']}/complete", json={
        "actions": [{"text": "A", "owner": report["id"]}, {"text": "B", "owner": report["id"]},
                    {"text": "C", "owner": boss["id"]}]})
    as_staff(tenant, report)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    mine = [n for n in notes if n["title"].startswith("One-to-one notes")]
    assert mine and "2 actions for you" in mine[0]["message"]
    assert tenant.get("/api/employee/check-ins").json()["open_actions_on_me"] == 2
    assert tenant.post(f"/api/employee/check-ins/{c['id']}/complete").status_code == 409


def test_a_planned_one_can_be_cancelled_a_held_one_cannot(tenant):
    boss, report, _ = team(tenant)
    as_staff(tenant, report)
    c = book(tenant)
    assert tenant.delete(f"/api/employee/check-ins/{c['id']}").status_code == 200
    c = book(tenant)
    as_staff(tenant, boss)
    tenant.post(f"/api/employee/check-ins/{c['id']}/complete", json={"notes": "Held"})
    res = tenant.delete(f"/api/employee/check-ins/{c['id']}")
    assert res.status_code == 409


def test_an_action_owner_must_be_one_of_the_two(tenant):
    boss, report, other = team(tenant)
    as_staff(tenant, boss)
    c = book(tenant, employee_id=report["id"])
    got = tenant.put(f"/api/employee/check-ins/{c['id']}", json={
        "actions": [{"text": "Not yours", "owner": other["id"]}, {"text": "x", "owner": "abc"}]}).json()
    assert [a["owner"] for a in got["actions"]] == [report["id"], report["id"]]


# --- who can see it --------------------------------------------------------------------

def test_nobody_else_can_see_or_touch_it(tenant, account):
    boss, report, other = team(tenant)
    as_staff(tenant, report)
    c = book(tenant)
    as_staff(tenant, other)
    assert tenant.get(f"/api/employee/check-ins/{c['id']}").status_code == 404
    assert tenant.put(f"/api/employee/check-ins/{c['id']}", json={"notes": "x"}).status_code == 404
    assert tenant.post(f"/api/employee/check-ins/{c['id']}/complete").status_code == 404
    assert tenant.delete(f"/api/employee/check-ins/{c['id']}").status_code == 404
    assert tenant.get("/api/employee/check-ins").json()["with_my_manager"] == []


def test_hr_sees_the_dates_and_notes_but_never_the_private_note(tenant, account):
    boss, report, _ = team(tenant)
    as_staff(tenant, boss)
    c = book(tenant, days(-1), employee_id=report["id"])
    tenant.post(f"/api/employee/check-ins/{c['id']}/complete", json={
        "notes": "Shared", "private_note": "Private"})
    as_hr(tenant, account)
    rows = tenant.get(f"/api/employees/{report['id']}/check-ins").json()["check_ins"]
    assert rows[0]["notes"] == "Shared"
    assert "private_note" not in rows[0]
    assert "Private" not in tenant.get(f"/api/employees/{report['id']}/check-ins").text


def test_hr_sees_which_reporting_lines_have_gone_quiet(tenant, account):
    boss, report, _ = team(tenant)
    quiet = person(tenant, first_name="Quiet", reports_to=boss["id"])
    stale = person(tenant, first_name="Stale", reports_to=boss["id"])
    as_staff(tenant, boss)
    recent = book(tenant, days(-3), employee_id=report["id"])
    tenant.post(f"/api/employee/check-ins/{recent['id']}/complete")
    old = book(tenant, days(-60), employee_id=stale["id"])
    tenant.post(f"/api/employee/check-ins/{old['id']}/complete")
    book(tenant, days(1), employee_id=quiet["id"])      # planned is not held
    as_hr(tenant, account)
    cov = tenant.get("/api/check-ins/coverage").json()
    assert cov["pairs"] == 3 and cov["recent"] == 1 and cov["quiet"] == 2
    assert cov["window_days"] == 30
    by_name = {r["employee_name"]: r for r in cov["rows"]}
    assert by_name["Ravi Kumar"]["recent"] and by_name["Ravi Kumar"]["last_held"] == days(-3)
    assert not by_name[f"Stale {stale['last_name']}"]["recent"]
    assert by_name[f"Quiet {quiet['last_name']}"]["last_held"] == ""
    # The quiet ones come first: they are the ones to do something about.
    assert not cov["rows"][0]["recent"]
    a = tenant.get("/api/hr/analytics").json()["check_ins"]
    assert a == {"pairs": 3, "recent": 1, "quiet": 2, "window_days": 30}


def test_another_business_gets_nothing(tenant, account):
    boss, report, _ = team(tenant)
    as_staff(tenant, report)
    c = book(tenant)
    other = f"other-{account['email']}"
    tenant.post("/api/employee/auth/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest",
                                              "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get(f"/api/employees/{report['id']}/check-ins").status_code == 404
    assert tenant.get("/api/check-ins/coverage").json()["pairs"] == 0
