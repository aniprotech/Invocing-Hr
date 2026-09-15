"""Who can do what, at what level, and who else.

A catalogue that grows from use - a skill typed on a profile that did not
exist yet is created, matched without regard to case. A person adds their
own and HR or their manager confirms; what HR adds is confirmed. The
question this exists to answer is the one asked the day somebody resigns:
who else can do what they did - so the skills only one person holds well
are named as single points of failure.
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
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def as_hr(client, account):
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def give(tenant, emp_id, skills):
    res = tenant.put(f"/api/employees/{emp_id}/skills", json={"skills": skills})
    assert res.status_code == 200, res.text
    return res.json()["skills"]


def test_the_catalogue_grows_from_use_without_regard_to_case(tenant):
    a = person(tenant)
    b = person(tenant)
    give(tenant, a["id"], [{"name": "Python", "level": 4}, {"name": "  SQL  ", "level": 2}])
    give(tenant, b["id"], [{"name": "python", "level": 3}, "Excel"])
    names = sorted(s["name"] for s in tenant.get("/api/skills").json()["skills"])
    assert names == ["Excel", "Python", "SQL"]
    py = next(s for s in tenant.get("/api/skills").json()["skills"] if s["name"] == "Python")
    assert py["people"] == 2 and py["strong"] == 2 and py["average_level"] == 3.5
    ex = next(s for s in tenant.get("/api/skills").json()["skills"] if s["name"] == "Excel")
    assert ex["average_level"] == 2.0          # a bare name is a working level


def test_hr_written_skills_are_confirmed_and_levels_are_one_to_four(tenant):
    a = person(tenant)
    skills = give(tenant, a["id"], [{"name": "Python", "level": 4}])
    assert skills[0]["verified"] and skills[0]["level_word"] == "Expert" and skills[0]["added_by"] == "hr"
    assert tenant.put(f"/api/employees/{a['id']}/skills", json={"skills": [{"name": "X", "level": 5}]}).status_code == 400
    assert tenant.put(f"/api/employees/{a['id']}/skills", json={"skills": [{"name": "  ", "level": 2}]}).status_code == 400
    assert tenant.put(f"/api/employees/{a['id']}/skills", json={"skills": "python"}).status_code == 400


def test_single_points_of_failure_are_named(tenant):
    a = person(tenant, first_name="Only")
    b = person(tenant, first_name="Also")
    give(tenant, a["id"], [{"name": "Payroll run", "level": 4}, {"name": "Python", "level": 3}])
    give(tenant, b["id"], [{"name": "Python", "level": 3}, {"name": "Payroll run", "level": 1}])   # learning does not count
    out = tenant.get("/api/skills").json()
    assert [s["name"] for s in out["single_points_of_failure"]] == ["Payroll run"]
    give(tenant, b["id"], [{"name": "Python", "level": 3}, {"name": "Payroll run", "level": 2}])
    assert tenant.get("/api/skills").json()["single_points_of_failure"] == []
    # A leaver's skills do not cover anything.
    tenant.put(f"/api/employees/{b['id']}", json={"status": "terminated"})
    assert [s["name"] for s in tenant.get("/api/skills").json()["single_points_of_failure"]] == ["Payroll run", "Python"]


def test_search_finds_who_can_do_it_strongest_first(tenant):
    a = person(tenant, first_name="Ann")
    b = person(tenant, first_name="Bob")
    give(tenant, a["id"], [{"name": "React", "level": 2}])
    give(tenant, b["id"], [{"name": "React Native", "level": 4}])
    people = tenant.get("/api/skills/search?q=react").json()["people"]
    assert [p["name"].split()[0] for p in people] == ["Bob", "Ann"]
    assert people[0]["skill"] == "React Native" and people[0]["level_word"] == "Expert"
    assert tenant.get("/api/skills/search?q=").json()["people"] == []


def test_the_matrix_is_people_by_skills_for_a_department(tenant):
    dept = tenant.post("/api/departments", json={"name": "Data"}).json()
    a = person(tenant, first_name="Ann", department_id=dept["id"])
    b = person(tenant, first_name="Bob", department_id=dept["id"])
    person(tenant, first_name="Out")
    give(tenant, a["id"], [{"name": "SQL", "level": 4}, {"name": "Python", "level": 2}])
    give(tenant, b["id"], [{"name": "SQL", "level": 1}])
    m = tenant.get(f"/api/skills/matrix?department_id={dept['id']}").json()
    assert [s["name"] for s in m["skills"]] == ["Python", "SQL"]
    assert [p["name"].split()[0] for p in m["people"]] == ["Ann", "Bob"]
    assert m["people"][0]["levels"] == [2, 4] and m["people"][1]["levels"] == [0, 1]
    assert {c["name"]: c["strong"] for c in m["coverage"]} == {"Python": 0, "SQL": 1}
    everyone = tenant.get("/api/skills/matrix").json()
    assert len(everyone["people"]) == 3


def test_renaming_merging_and_deleting_in_the_catalogue(tenant):
    a = person(tenant)
    give(tenant, a["id"], [{"name": "Postgres", "level": 3}, {"name": "MySQL", "level": 2}])
    ids = {s["name"]: s["id"] for s in tenant.get("/api/skills").json()["skills"]}
    assert tenant.put(f"/api/skills/{ids['MySQL']}", json={"name": "postgres"}).status_code == 409
    assert tenant.put(f"/api/skills/{ids['Postgres']}", json={"name": "PostgreSQL", "category": "Databases"}).json()["name"] == "PostgreSQL"
    assert tenant.delete(f"/api/skills/{ids['MySQL']}").status_code == 200
    names = [s["name"] for s in tenant.get(f"/api/employees/{a['id']}/skills").json()["skills"]]
    assert names == ["PostgreSQL"]
    assert tenant.post("/api/skills", json={"name": "Go", "category": "Languages"}).json()["category"] == "Languages"


# --- the person's own and the manager's confirmation ----------------------------------------

def test_a_person_adds_their_own_and_hr_or_the_manager_confirms(tenant, account):
    boss = person(tenant, first_name="Bea")
    emp = person(tenant, reports_to=boss["id"])
    other = person(tenant)
    as_staff(tenant, emp)
    res = tenant.put("/api/employee/skills", json={"skills": [{"name": "Python", "level": 3}, {"name": "Figma", "level": 2}]})
    assert res.status_code == 200, res.text
    mine = res.json()["skills"]
    assert all(not s["verified"] and s["added_by"] == "employee" for s in mine)
    assert "Python" in tenant.get("/api/employee/skills").json()["catalogue"]
    py = next(s for s in mine if s["name"] == "Python")
    as_staff(tenant, boss)
    team = tenant.get("/api/employee/team-skills").json()["reports"]
    assert team[0]["employee_id"] == emp["id"] and len(team[0]["skills"]) == 2
    assert tenant.post(f"/api/employee/team/{emp['id']}/skills/{py['skill_id']}/verify").status_code == 200
    as_staff(tenant, other)
    assert tenant.post(f"/api/employee/team/{emp['id']}/skills/{py['skill_id']}/verify").status_code == 404
    as_staff(tenant, emp)
    mine = tenant.get("/api/employee/skills").json()["skills"]
    assert next(s for s in mine if s["name"] == "Python")["verified_by"].startswith("Bea")
    # The same level again keeps the confirmation; a new level loses it.
    tenant.put("/api/employee/skills", json={"skills": [{"name": "Python", "level": 3}]})
    assert tenant.get("/api/employee/skills").json()["skills"][0]["verified"]
    tenant.put("/api/employee/skills", json={"skills": [{"name": "Python", "level": 4}]})
    assert not tenant.get("/api/employee/skills").json()["skills"][0]["verified"]
    as_hr(tenant, account)
    sid = tenant.get(f"/api/employees/{emp['id']}/skills").json()["skills"][0]["skill_id"]
    assert tenant.post(f"/api/employees/{emp['id']}/skills/{sid}/verify").status_code == 200
    assert tenant.get(f"/api/employees/{emp['id']}/skills").json()["skills"][0]["verified"]


def test_there_is_a_limit(tenant):
    a = person(tenant)
    res = tenant.put(f"/api/employees/{a['id']}/skills", json={"skills": [f"Skill {i}" for i in range(41)]})
    assert res.status_code == 400 and "40 skills" in res.json()["detail"]


def test_another_business_has_its_own_catalogue(tenant, account):
    a = person(tenant)
    give(tenant, a["id"], [{"name": "Python", "level": 4}])
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/skills").json()["skills"] == []
    assert tenant.get("/api/skills/search?q=python").json()["people"] == []
    assert tenant.get(f"/api/employees/{a['id']}/skills").status_code == 404
    # The same name here is this business's own entry, not the other one's.
    b = person(tenant)
    give(tenant, b["id"], [{"name": "Python", "level": 2}])
    mine = tenant.get("/api/skills").json()["skills"]
    assert [x["name"] for x in mine] == ["Python"] and mine[0]["people"] == 1


def test_analytics_carries_the_skills_block(tenant):
    a = person(tenant)
    person(tenant)
    give(tenant, a["id"], [{"name": "Payroll run", "level": 4}])
    s = tenant.get("/api/hr/analytics").json()["skills"]
    assert s["skills"] == 1 and s["single_points_of_failure"] == 1 and s["people_with_none"] == 1
    assert s["top"][0]["name"] == "Payroll run"
