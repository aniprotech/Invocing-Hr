"""Reviews: a period, some questions, two halves.

HR names a cycle and opens it. Everybody still here gets a review; they
write their half first, then whoever they report to writes theirs, and the
manager's overall rating is the one that counts. Somebody with nobody above
them is HR's to write. The person sees the manager's half only once it is
done, the manager sees the person's half only once it is sent, and nobody
sees anybody else's at all.
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


QUESTIONS = [
    {"text": "What went well?", "kind": "text"},
    {"text": "Quality of work", "kind": "rating"},
]


def cycle(client, **over):
    payload = {"name": "H1 2026", "period_start": "2026-01-01", "period_end": "2026-06-30",
               "due_on": "2026-07-15", "questions": QUESTIONS}
    payload.update(over)
    res = client.post("/api/review-cycles", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def open_cycle(client, cid):
    res = client.post(f"/api/review-cycles/{cid}/open")
    assert res.status_code == 200, res.text
    return res.json()


def review_of(client, cid, employee_id):
    detail = client.get(f"/api/review-cycles/{cid}").json()
    return next(r for r in detail["reviews"] if r["employee_id"] == employee_id)


def team(tenant):
    """A manager, a report, and somebody with nobody above them."""
    boss = person(tenant, first_name="Bea")
    report = person(tenant, first_name="Ravi", reports_to=boss["id"])
    loner = person(tenant, first_name="Lena")
    return boss, report, loner


# --- setting one up ------------------------------------------------------------------

def test_a_cycle_starts_as_a_draft_with_its_questions(tenant):
    c = cycle(tenant)
    assert c["status"] == "draft"
    assert [q["text"] for q in c["questions"]] == ["What went well?", "Quality of work"]
    assert c["counts"]["total"] == 0


def test_no_questions_means_the_default_set(tenant):
    res = tenant.post("/api/review-cycles", json={"name": "Default"})
    assert res.status_code == 200, res.text
    qs = res.json()["questions"]
    assert len(qs) == len(main.DEFAULT_REVIEW_QUESTIONS)
    assert any(q["kind"] == "rating" for q in qs)


def test_a_cycle_needs_a_name_and_a_sane_period(tenant):
    assert tenant.post("/api/review-cycles", json={"name": "  "}).status_code == 400
    res = tenant.post("/api/review-cycles", json={
        "name": "Backwards", "period_start": "2026-06-01", "period_end": "2026-01-01"})
    assert res.status_code == 400
    assert "before it starts" in res.json()["detail"]
    res = tenant.post("/api/review-cycles", json={"name": "Bad date", "due_on": "next week"})
    assert res.status_code == 400


def test_an_empty_question_list_is_refused_but_blank_lines_are_dropped(tenant):
    assert tenant.post("/api/review-cycles", json={"name": "x", "questions": []}).status_code == 400
    c = cycle(tenant, questions=["Real question", "   ", {"text": "", "kind": "rating"}])
    assert [q["text"] for q in c["questions"]] == ["Real question"]


def test_a_draft_can_be_edited_and_deleted(tenant):
    c = cycle(tenant)
    res = tenant.put(f"/api/review-cycles/{c['id']}", json={"name": "H1 renamed",
                                                            "questions": ["Only one"]})
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "H1 renamed"
    assert len(res.json()["questions"]) == 1
    assert tenant.delete(f"/api/review-cycles/{c['id']}").status_code == 200
    assert tenant.get(f"/api/review-cycles/{c['id']}").status_code == 404


# --- opening it ------------------------------------------------------------------------

def test_opening_writes_one_review_per_person_and_finds_the_reviewer(tenant):
    boss, report, loner = team(tenant)
    c = cycle(tenant)
    out = open_cycle(tenant, c["id"])
    assert out["opened"] == 3
    assert out["hr_pool"] == 2          # the boss and the loner have nobody above them
    r = review_of(tenant, c["id"], report["id"])
    assert r["reviewer_id"] == boss["id"]
    assert r["reviewer_how"] == "manager"
    assert r["status"] == "awaiting_self"
    assert review_of(tenant, c["id"], loner["id"])["reviewer_name"] == "HR"


def test_a_department_head_reviews_the_headless(tenant):
    head = person(tenant, first_name="Hana")
    dept = tenant.post("/api/departments", json={"name": "Ops"}).json()
    tenant.put(f"/api/departments/{dept['id']}/head", json={"head_id": head["id"]})
    tenant.put(f"/api/employees/{head['id']}", json={"department_id": dept["id"]})
    member = person(tenant, first_name="Mo", department_id=dept["id"])
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    assert review_of(tenant, c["id"], member["id"])["reviewer_how"] == "department_head"
    # The head does not review themselves; that one is HR's.
    assert review_of(tenant, c["id"], head["id"])["reviewer_how"] == "hr"


def test_a_cycle_can_be_for_one_department(tenant):
    dept = tenant.post("/api/departments", json={"name": "Sales"}).json()
    inside = person(tenant, department_id=dept["id"])
    person(tenant)      # outside
    c = cycle(tenant, department_id=dept["id"])
    assert open_cycle(tenant, c["id"])["opened"] == 1
    detail = tenant.get(f"/api/review-cycles/{c['id']}").json()
    assert [r["employee_id"] for r in detail["reviews"]] == [inside["id"]]
    assert detail["cycle"]["department_name"] == "Sales"


def test_leavers_are_not_reviewed(tenant):
    gone = person(tenant)
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    staying = person(tenant)
    c = cycle(tenant)
    assert open_cycle(tenant, c["id"])["opened"] == 1
    assert review_of(tenant, c["id"], staying["id"])


def test_nobody_to_review_is_said_not_silently_opened(tenant):
    c = cycle(tenant)
    res = tenant.post(f"/api/review-cycles/{c['id']}/open")
    assert res.status_code == 400
    assert tenant.get(f"/api/review-cycles/{c['id']}").json()["cycle"]["status"] == "draft"


def test_everybody_is_told_and_a_manager_is_told_how_many(tenant):
    boss, report, loner = team(tenant)
    person(tenant, first_name="Zed", reports_to=boss["id"])
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    as_staff(tenant, boss)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert "Review: H1 2026" in titles
    assert "2 reviews to write" in titles


def test_once_open_the_questions_and_audience_are_fixed(tenant):
    person(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    res = tenant.put(f"/api/review-cycles/{c['id']}", json={"questions": ["Different"]})
    assert res.status_code == 409
    assert "fixed" in res.json()["detail"]
    # The name and the due date are still theirs to change.
    res = tenant.put(f"/api/review-cycles/{c['id']}", json={"name": "H1 (final)", "due_on": "2026-08-01"})
    assert res.status_code == 200, res.text
    assert tenant.post(f"/api/review-cycles/{c['id']}/open").status_code == 409
    assert tenant.delete(f"/api/review-cycles/{c['id']}").status_code == 409


# --- the two halves -----------------------------------------------------------------------

def submit_self(client, review_id, rating=4, draft=False):
    return client.post(f"/api/employee/reviews/{review_id}/self", json={
        "answers": [{"text": "Shipped the thing"}, {"rating": rating}],
        "rating": rating, "comment": "Good half", "draft": draft})


def submit_manager(client, path, rating=5, summary="Strong period", draft=False):
    return client.post(path, json={
        "answers": [{"text": "Agreed"}, {"rating": rating}],
        "rating": rating, "summary": summary, "draft": draft})


def test_the_person_writes_first_then_the_manager_and_only_then_is_it_read(tenant, account):
    boss, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]

    as_staff(tenant, report)
    mine = tenant.get("/api/employee/reviews").json()
    assert [m["id"] for m in mine["mine"]] == [rid]
    assert mine["to_write"] == []
    assert submit_self(tenant, rid).status_code == 200
    detail = tenant.get(f"/api/employee/reviews/{rid}").json()
    assert detail["status"] == "awaiting_manager"
    assert detail["self"]["rating"] == 4
    assert "manager" not in detail, "the manager's half is not theirs to see yet"

    as_staff(tenant, boss)
    todo = tenant.get("/api/employee/reviews").json()["to_write"]
    assert [t["employee_name"] for t in todo] == ["Ravi " + report["last_name"]]
    seen = tenant.get(f"/api/employee/reviews/{rid}").json()
    assert seen["my_role"] == "reviewer"
    assert seen["self"]["answers"][0]["text"] == "Shipped the thing"
    res = submit_manager(tenant, f"/api/employee/reviews/{rid}/manager")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "complete"

    as_staff(tenant, report)
    done = tenant.get(f"/api/employee/reviews/{rid}").json()
    assert done["manager"]["rating"] == 5
    assert done["manager"]["rating_label"] == "Outstanding"
    assert done["manager"]["summary"] == "Strong period"
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert "Your review is ready" in titles

    as_hr(tenant, account)
    summary = tenant.get(f"/api/review-cycles/{c['id']}").json()["summary"]
    assert summary["rated"] == 1 and summary["average"] == 5.0
    assert summary["distribution"]["5"] == 1


def test_a_draft_keeps_the_words_and_sends_nothing(tenant):
    boss, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    as_staff(tenant, report)
    res = submit_self(tenant, rid, rating=None, draft=True)
    assert res.status_code == 200, res.text
    assert res.json()["saved"] == "draft"
    assert tenant.get(f"/api/employee/reviews/{rid}").json()["status"] == "awaiting_self"
    # The manager cannot read a draft.
    as_staff(tenant, boss)
    assert "self" not in tenant.get(f"/api/employee/reviews/{rid}").json()


def test_a_submission_needs_every_rating_and_an_overall(tenant):
    _, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    as_staff(tenant, report)
    res = tenant.post(f"/api/employee/reviews/{rid}/self", json={
        "answers": [{"text": "x"}, {}], "rating": 3})
    assert res.status_code == 400
    assert "Quality of work" in res.json()["detail"]
    res = tenant.post(f"/api/employee/reviews/{rid}/self", json={
        "answers": [{"text": "x"}, {"rating": 3}], "rating": None})
    assert res.status_code == 400
    for bad in (0, 6, "five"):
        res = tenant.post(f"/api/employee/reviews/{rid}/self", json={
            "answers": [{"text": "x"}, {"rating": bad}], "rating": 3})
        assert res.status_code == 400, bad


def test_once_sent_it_cannot_be_sent_again(tenant):
    _, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    as_staff(tenant, report)
    assert submit_self(tenant, rid).status_code == 200
    assert submit_self(tenant, rid, rating=1).status_code == 409


def test_the_manager_needs_a_summary_and_can_finish_without_the_self_half(tenant):
    boss, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    as_staff(tenant, boss)
    res = submit_manager(tenant, f"/api/employee/reviews/{rid}/manager", summary="")
    assert res.status_code == 400
    assert "summary" in res.json()["detail"].lower()
    res = submit_manager(tenant, f"/api/employee/reviews/{rid}/manager")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "complete"
    # Now the person cannot write theirs; the moment has passed.
    as_staff(tenant, report)
    assert submit_self(tenant, rid).status_code == 409


def test_hr_writes_for_those_with_nobody_above_them(tenant):
    _, _, loner = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], loner["id"])["id"]
    res = submit_manager(tenant, f"/api/reviews/{rid}/manager", rating=3)
    assert res.status_code == 200, res.text
    full = tenant.get(f"/api/reviews/{rid}").json()
    assert full["manager"]["rating"] == 3
    assert full["manager"]["by"]     # the business's name, for the record
    assert full["reviewer_name"] == "HR"


def test_the_manager_sees_the_goals_they_are_reviewing_against(tenant):
    boss, report, _ = team(tenant)
    tenant.post(f"/api/employees/{report['id']}/goals", json={
        "title": "Close five deals", "target_value": 5, "current_value": 2})
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    as_staff(tenant, boss)
    goals = tenant.get(f"/api/employee/reviews/{rid}").json()["goals"]
    assert goals and goals[0]["title"] == "Close five deals"
    assert goals[0]["progress_pct"] == 40


# --- who can see what --------------------------------------------------------------------

def test_a_review_is_invisible_to_anybody_else(tenant):
    boss, report, loner = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    as_staff(tenant, loner)
    assert tenant.get(f"/api/employee/reviews/{rid}").status_code == 404
    assert submit_self(tenant, rid).status_code == 404
    assert submit_manager(tenant, f"/api/employee/reviews/{rid}/manager").status_code == 404


def test_the_reviewer_cannot_write_the_self_half_nor_the_subject_the_managers(tenant):
    boss, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    as_staff(tenant, boss)
    assert submit_self(tenant, rid).status_code == 403
    as_staff(tenant, report)
    assert submit_manager(tenant, f"/api/employee/reviews/{rid}/manager").status_code == 403


def test_another_business_sees_none_of_it(tenant, account):
    person(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = tenant.get(f"/api/review-cycles/{c['id']}").json()["reviews"][0]["id"]
    other_email = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={
        "email": other_email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other_email, "password": "Passw0rdTest"})
    assert tenant.get("/api/review-cycles").json()["cycles"] == []
    assert tenant.get(f"/api/review-cycles/{c['id']}").status_code == 404
    assert tenant.get(f"/api/reviews/{rid}").status_code == 404
    assert tenant.post(f"/api/reviews/{rid}/manager", json={"rating": 5, "summary": "x"}).status_code == 404


# --- closing ------------------------------------------------------------------------------------

def test_a_closed_cycle_takes_no_more_answers_and_is_kept(tenant):
    boss, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    rid = review_of(tenant, c["id"], report["id"])["id"]
    res = tenant.post(f"/api/review-cycles/{c['id']}/close")
    assert res.status_code == 200 and res.json()["status"] == "closed"
    as_staff(tenant, report)
    assert submit_self(tenant, rid).status_code == 409
    assert tenant.get("/api/employee/reviews").json()["mine"][0]["cycle_status"] == "closed"
    as_staff(tenant, boss)
    assert tenant.get("/api/employee/reviews").json()["to_write"] == []


def test_a_review_goes_back_to_hr_when_its_reviewer_is_deleted(tenant):
    boss, report, _ = team(tenant)
    c = cycle(tenant)
    open_cycle(tenant, c["id"])
    assert tenant.delete(f"/api/employees/{boss['id']}").status_code == 200
    r = review_of(tenant, c["id"], report["id"])
    assert r["reviewer_id"] is None and r["reviewer_how"] == "hr"
