"""What colleagues say, and where somebody sits.

A reviewer or HR asks a few colleagues what it is like to work with the
person; each answers strengths, what to work on and a rating, or declines.
The reviewer reads it with names. The person reads it afterwards without
them, and in no particular order, so two answers cannot be told apart by
when they came in. The manager's half also carries a view of potential,
and performance against potential is the nine-box grid HR looks at when
asking who is next - with the unplaced counted, so the grid cannot pass
for the whole company.
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
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def open_cycle(tenant, **over):
    payload = {"name": "H1", "questions": [{"text": "Quality of work", "kind": "rating"}]}
    payload.update(over)
    c = tenant.post("/api/review-cycles", json=payload).json()
    res = tenant.post(f"/api/review-cycles/{c['id']}/open")
    assert res.status_code == 200, res.text
    return c


def review_of(tenant, cid, employee_id):
    detail = tenant.get(f"/api/review-cycles/{cid}").json()
    return next(r for r in detail["reviews"] if r["employee_id"] == employee_id)


def team(tenant):
    boss = person(tenant, first_name="Bea", last_name="Boss")
    subject = person(tenant, first_name="Ravi", last_name="Kumar", reports_to=boss["id"])
    peer_a = person(tenant, first_name="Ann", last_name="Peer")
    peer_b = person(tenant, first_name="Bob", last_name="Peer")
    return boss, subject, peer_a, peer_b


def answer(client, fid, strengths="Calm under pressure", improvements="Writes less", rating=4):
    return client.post(f"/api/employee/feedback-requests/{fid}",
                       json={"strengths": strengths, "improvements": improvements, "rating": rating})


# --- asking --------------------------------------------------------------------------

def test_the_reviewer_asks_colleagues_and_they_are_told(tenant):
    boss, subject, a, b = team(tenant)
    c = open_cycle(tenant)
    rid = review_of(tenant, c["id"], subject["id"])["id"]
    as_staff(tenant, boss)
    res = tenant.post(f"/api/employee/reviews/{rid}/peers", json={"peer_ids": [a["id"], b["id"], subject["id"], boss["id"]]})
    assert res.status_code == 200, res.text
    assert res.json()["asked"] == 2         # not the subject, not the reviewer
    as_staff(tenant, a)
    mine = tenant.get("/api/employee/feedback-requests").json()
    assert mine["open"] == 1 and mine["requests"][0]["employee_name"] == "Ravi Kumar"
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert "Feedback on Ravi Kumar" in titles
    assert tenant.get("/api/employee/reviews").json()["feedback_open"] == 1


def test_only_the_reviewer_or_hr_asks_and_only_while_open(tenant, account):
    boss, subject, a, b = team(tenant)
    c = open_cycle(tenant)
    rid = review_of(tenant, c["id"], subject["id"])["id"]
    as_staff(tenant, subject)
    assert tenant.post(f"/api/employee/reviews/{rid}/peers", json={"peer_ids": [a["id"]]}).status_code == 403
    as_staff(tenant, a)
    assert tenant.post(f"/api/employee/reviews/{rid}/peers", json={"peer_ids": [b["id"]]}).status_code == 404
    as_hr(tenant, account)
    assert tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": [a["id"]]}).json()["asked"] == 1
    assert tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": [a["id"]]}).json()["asked"] == 0   # once each
    tenant.post(f"/api/review-cycles/{c['id']}/close")
    assert tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": [b["id"]]}).status_code == 409


def test_there_is_a_limit_and_leavers_are_skipped(tenant, account):
    boss, subject, a, b = team(tenant)
    gone = person(tenant)
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    c = open_cycle(tenant)
    rid = review_of(tenant, c["id"], subject["id"])["id"]
    assert tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": [gone["id"]]}).json()["asked"] == 0
    many = [person(tenant)["id"] for _ in range(7)]
    res = tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": many})
    assert res.status_code == 400 and "6 colleagues" in res.json()["detail"]
    assert tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": []}).status_code == 400


# --- answering ------------------------------------------------------------------------

def test_a_peer_answers_or_declines_once(tenant, account):
    boss, subject, a, b = team(tenant)
    c = open_cycle(tenant)
    rid = review_of(tenant, c["id"], subject["id"])["id"]
    tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": [a["id"], b["id"]]})
    as_staff(tenant, a)
    fid = tenant.get("/api/employee/feedback-requests").json()["requests"][0]["id"]
    assert answer(tenant, fid, strengths="", improvements="", rating=None).status_code == 400
    assert answer(tenant, fid, rating=7).status_code == 400
    assert answer(tenant, fid).status_code == 200
    assert answer(tenant, fid).status_code == 409
    as_staff(tenant, b)
    fid_b = tenant.get("/api/employee/feedback-requests").json()["requests"][0]["id"]
    assert tenant.post(f"/api/employee/feedback-requests/{fid_b}", json={"decline": True}).json()["status"] == "declined"
    # Somebody else's request is not mine to answer.
    assert answer(tenant, fid).status_code == 404
    as_staff(tenant, boss)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert "Feedback in on Ravi Kumar" in titles
    fb = tenant.get(f"/api/employee/reviews/{rid}").json()["peer_feedback"]
    assert fb["asked"] == 2 and fb["submitted"] == 1 and fb["declined"] == 1 and fb["average"] == 4.0
    assert fb["items"][0]["peer_name"] == "Ann Peer"


def test_the_person_reads_it_afterwards_without_names_or_order(tenant, account):
    boss, subject, a, b = team(tenant)
    c = open_cycle(tenant)
    rid = review_of(tenant, c["id"], subject["id"])["id"]
    tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": [a["id"], b["id"]]})
    as_staff(tenant, a)
    answer(tenant, tenant.get("/api/employee/feedback-requests").json()["requests"][0]["id"], strengths="Zeal")
    as_staff(tenant, b)
    answer(tenant, tenant.get("/api/employee/feedback-requests").json()["requests"][0]["id"], strengths="Accuracy")
    as_staff(tenant, subject)
    before = tenant.get(f"/api/employee/reviews/{rid}").json()["peer_feedback"]
    assert before["items"] == [] and before["submitted"] == 2       # counts yes, words not yet
    as_hr(tenant, account)
    tenant.post(f"/api/reviews/{rid}/manager", json={"answers": [{"rating": 4}], "rating": 4, "summary": "Good", "potential": 2})
    as_staff(tenant, subject)
    after = tenant.get(f"/api/employee/reviews/{rid}").json()
    items = after["peer_feedback"]["items"]
    assert [i["strengths"] for i in items] == ["Accuracy", "Zeal"]     # alphabetical, not by who or when
    assert all("peer_name" not in i and "peer_id" not in i and "submitted_at" not in i for i in items)
    assert "Ann" not in tenant.get(f"/api/employee/reviews/{rid}").text
    assert after["manager"]["potential"] is None, "potential is the manager's and HR's, not theirs"


# --- potential and the grid -------------------------------------------------------------

def test_potential_is_one_to_three_on_the_managers_half(tenant):
    boss, subject, a, b = team(tenant)
    c = open_cycle(tenant)
    rid = review_of(tenant, c["id"], subject["id"])["id"]
    res = tenant.post(f"/api/reviews/{rid}/manager", json={"answers": [{"rating": 5}], "rating": 5, "summary": "x", "potential": 4})
    assert res.status_code == 400
    res = tenant.post(f"/api/reviews/{rid}/manager", json={"answers": [{"rating": 5}], "rating": 5, "summary": "x", "potential": 3})
    assert res.status_code == 200, res.text
    assert tenant.get(f"/api/reviews/{rid}").json()["manager"]["potential"] == 3
    assert review_of(tenant, c["id"], subject["id"])["potential"] == 3


def test_the_grid_places_the_rated_and_counts_the_rest(tenant):
    boss, subject, a, b = team(tenant)
    c = open_cycle(tenant)
    def finish(emp_id, rating, potential):
        rid = review_of(tenant, c["id"], emp_id)["id"]
        body = {"answers": [{"rating": rating}], "rating": rating, "summary": "x"}
        if potential:
            body["potential"] = potential
        assert tenant.post(f"/api/reviews/{rid}/manager", json=body).status_code == 200
    finish(subject["id"], 5, 3)       # future leader
    finish(a["id"], 3, 2)             # core team
    finish(b["id"], 2, 1)             # at risk
    finish(boss["id"], 4, None)       # rated, no potential: unplaced
    g = tenant.get("/api/talent-grid").json()
    assert g["cycle"]["name"] == "H1"
    assert g["placed"] == 3 and g["unplaced"] == 1 and g["pending"] == 0
    box = {(bx["performance"], bx["potential"]): bx for bx in g["boxes"]}
    assert len(box) == 9
    assert [p["name"] for p in box[(3, 3)]["people"]] == ["Ravi Kumar"] and box[(3, 3)]["label"] == "Future leaders"
    assert [p["name"] for p in box[(2, 2)]["people"]] == ["Ann Peer"]
    assert [p["name"] for p in box[(1, 1)]["people"]] == ["Bob Peer"] and box[(1, 1)]["label"] == "At risk"
    assert g["potential_words"]["3"] == "Could go a long way"


def test_the_grid_is_empty_with_no_cycle_and_is_hr_only(tenant):
    g = tenant.get("/api/talent-grid").json()
    assert g["cycle"] is None and g["boxes"] == []
    emp = person(tenant)
    as_staff(tenant, emp)
    assert tenant.get("/api/talent-grid").status_code in (401, 403)
    assert tenant.get("/api/employee/feedback-requests").json()["requests"] == []


def test_another_business_sees_none_of_it(tenant, account):
    boss, subject, a, b = team(tenant)
    c = open_cycle(tenant)
    rid = review_of(tenant, c["id"], subject["id"])["id"]
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.post(f"/api/reviews/{rid}/peers", json={"peer_ids": [a["id"]]}).status_code == 404
    assert tenant.get("/api/talent-grid").json()["cycle"] is None
