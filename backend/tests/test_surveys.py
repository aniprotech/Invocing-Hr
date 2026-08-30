"""Asking staff what they think, and meaning it.

The whole value of a staff survey rests on whether people believe the anonymous
one is anonymous. That cannot be a display rule: if answers carry an employee
id and the screen merely declines to show it, one query, one export or one
careless join undoes it - and the people answering were right not to trust it.

So most of this file attacks the guarantee rather than the feature: it goes
looking in the database for the link, tries to get at it through the results,
through the chase list, and through a named survey standing next to an
anonymous one. The link has to be absent, not hidden.
"""
import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def client_id(account):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id


def sign_in(client, emp, password="EmpPass123"):
    main.rate_limiter._hits.clear()
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": password})
    assert res.status_code == 200, res.text
    return client


def as_owner(client, account):
    main.rate_limiter._hits.clear()
    res = client.post("/api/client/login", json={
        "email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text
    return client


@pytest.fixture
def staff(tenant):
    return make_employee(tenant, first_name="Ada", last_name="Reid",
                         password="EmpPass123")


def make_survey(tenant, anonymous=True, questions=None):
    body = {
        "title": "How are things?", "anonymous": anonymous,
        "questions": questions or [
            {"text": "How happy are you?", "kind": "scale"},
            {"text": "Anything to add?", "kind": "text", "required": False},
        ],
    }
    res = tenant.post("/api/surveys", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def open_survey(tenant, sid):
    res = tenant.post(f"/api/surveys/{sid}/open")
    assert res.status_code == 200, res.text
    return res.json()


def answer(tenant, sid, survey, happy="4", comment="All fine"):
    qs = {q["kind"]: q["id"] for q in survey["questions"]}
    payload = {str(qs["scale"]): happy}
    if "text" in qs:
        payload[str(qs["text"])] = comment
    res = tenant.post(f"/api/employee/surveys/{sid}/respond",
                      json={"answers": payload})
    assert res.status_code == 200, res.text
    return res.json()


# --- the anonymity guarantee --------------------------------------------------

def test_an_anonymous_answer_is_stored_with_nobody_attached(tenant, staff, account):
    """Looked for in the database itself, not in the response body. A field the
    API declines to return is still a field somebody can query."""
    s = make_survey(tenant, anonymous=True)
    open_survey(tenant, s["id"])

    sign_in(tenant, staff)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail)

    with main.SessionLocal() as db:
        rows = db.query(models.DBSurveyResponse).filter(
            models.DBSurveyResponse.survey_id == s["id"]).all()
        assert len(rows) == 1
        assert rows[0].employee_id is None, "the link exists in the database"


def test_a_named_survey_does_keep_the_name(tenant, staff, account):
    """The other half: when it is not anonymous the attribution is real, so
    the anonymous case is a deliberate absence rather than a missing feature."""
    s = make_survey(tenant, anonymous=False)
    open_survey(tenant, s["id"])

    sign_in(tenant, staff)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail)

    with main.SessionLocal() as db:
        row = db.query(models.DBSurveyResponse).filter(
            models.DBSurveyResponse.survey_id == s["id"]).first()
        assert row.employee_id == staff["id"]


def test_who_answered_is_known_but_not_what_they_said(tenant, staff, account):
    """The recipient row is the only person-shaped thing on an anonymous
    survey, and it must carry no route to the answers."""
    s = make_survey(tenant, anonymous=True)
    open_survey(tenant, s["id"])
    sign_in(tenant, staff)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail, happy="1", comment="Not good at all")

    with main.SessionLocal() as db:
        rec = db.query(models.DBSurveyRecipient).filter(
            models.DBSurveyRecipient.survey_id == s["id"]).first()
        assert rec.responded is True
        assert rec.employee_id == staff["id"]
        # Nothing on the recipient points at a response.
        assert not hasattr(rec, "response_id")

        resp = db.query(models.DBSurveyResponse).filter(
            models.DBSurveyResponse.survey_id == s["id"]).first()
        assert resp.employee_id is None


def test_the_form_says_which_promise_is_being_made(tenant, staff):
    """It decides how somebody answers the next question, so it is on the form
    rather than in a policy somewhere."""
    anon = make_survey(tenant, anonymous=True)
    named = make_survey(tenant, anonymous=False)
    open_survey(tenant, anon["id"])
    open_survey(tenant, named["id"])

    sign_in(tenant, staff)
    a = tenant.get(f"/api/employee/surveys/{anon['id']}").json()
    n = tenant.get(f"/api/employee/surveys/{named['id']}").json()
    assert "anonymous" in a["promise"].lower()
    assert "cannot be traced" in a["promise"].lower()
    assert "name is recorded" in n["promise"].lower()


def test_free_text_is_held_back_until_enough_people_have_written(tenant, account):
    """One written answer among two is not anonymous - the voice identifies
    the person as surely as a name would."""
    people = [make_employee(tenant, first_name=f"P{i}", last_name="X",
                            password="EmpPass123") for i in range(4)]
    s = make_survey(tenant, anonymous=True)
    open_survey(tenant, s["id"])

    sign_in(tenant, people[0])
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail, comment="I am unhappy about the rota")

    as_owner(tenant, account)
    body = tenant.get(f"/api/surveys/{s['id']}/results").json()
    assert body["withholding_detail"] is True
    text_q = next(r for r in body["results"] if r["kind"] == "text")
    assert text_q["comments"] == []
    assert text_q["withheld"] is True
    assert "I am unhappy" not in str(body)


def test_once_enough_have_answered_the_comments_come_through(tenant, account):
    people = [make_employee(tenant, first_name=f"Q{i}", last_name="X",
                            password="EmpPass123") for i in range(3)]
    s = make_survey(tenant, anonymous=True)
    open_survey(tenant, s["id"])

    for i, p in enumerate(people):
        sign_in(tenant, p)
        detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
        answer(tenant, s["id"], detail, comment=f"Comment {i}")

    as_owner(tenant, account)
    body = tenant.get(f"/api/surveys/{s['id']}/results").json()
    assert body["withholding_detail"] is False
    text_q = next(r for r in body["results"] if r["kind"] == "text")
    assert len(text_q["comments"]) == 3


def test_a_named_survey_shows_its_comments_straight_away(tenant, staff, account):
    """Nothing to protect: everyone answering knew their name was on it."""
    s = make_survey(tenant, anonymous=False)
    open_survey(tenant, s["id"])
    sign_in(tenant, staff)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail, comment="Happy to be named")

    as_owner(tenant, account)
    body = tenant.get(f"/api/surveys/{s['id']}/results").json()
    assert body["withholding_detail"] is False
    text_q = next(r for r in body["results"] if r["kind"] == "text")
    assert text_q["comments"] == ["Happy to be named"]


def test_the_results_never_carry_a_person(tenant, staff, account):
    s = make_survey(tenant, anonymous=True)
    open_survey(tenant, s["id"])
    sign_in(tenant, staff)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail)

    as_owner(tenant, account)
    body = tenant.get(f"/api/surveys/{s['id']}/results").json()
    assert "Ada" not in str(body)
    assert "employee_id" not in str(body["results"])


# --- chasing the people who have not replied ---------------------------------

def test_hr_can_chase_without_knowing_what_anybody_said(tenant, account):
    keen = make_employee(tenant, first_name="Keen", last_name="One",
                         password="EmpPass123")
    quiet = make_employee(tenant, first_name="Quiet", last_name="Two",
                          password="EmpPass123")
    s = make_survey(tenant, anonymous=True)
    open_survey(tenant, s["id"])

    sign_in(tenant, keen)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail)

    as_owner(tenant, account)
    body = tenant.get(f"/api/surveys/{s['id']}/chase").json()
    assert body["asked"] == 2
    assert body["answered"] == 1
    assert [p["name"] for p in body["outstanding"]] == ["Quiet Two"]


# --- running one --------------------------------------------------------------

def test_a_survey_with_no_questions_asks_nothing(tenant):
    res = tenant.post("/api/surveys", json={"title": "Empty", "questions": []})
    sid = res.json()["id"]
    out = tenant.post(f"/api/surveys/{sid}/open")
    assert out.status_code == 400


def test_a_survey_needs_a_title(tenant):
    assert tenant.post("/api/surveys", json={"questions": []}).status_code == 400


def test_opening_it_asks_the_staff(tenant, staff):
    s = make_survey(tenant)
    body = open_survey(tenant, s["id"])
    assert body["status"] == "open"
    assert body["asked"] == 1


def test_everybody_asked_is_told(tenant, staff):
    s = make_survey(tenant)
    open_survey(tenant, s["id"])
    sign_in(tenant, staff)
    notes = tenant.get("/api/employee/notifications").json()["notifications"]
    assert any("How are things?" in n["title"] for n in notes), notes


def test_it_cannot_be_opened_twice(tenant, staff):
    s = make_survey(tenant)
    open_survey(tenant, s["id"])
    assert tenant.post(f"/api/surveys/{s['id']}/open").status_code == 409


def test_nobody_answers_a_draft(tenant, staff):
    s = make_survey(tenant)
    sign_in(tenant, staff)
    assert tenant.get(f"/api/employee/surveys/{s['id']}").status_code == 404


def test_a_closed_survey_takes_no_more_answers(tenant, staff):
    s = make_survey(tenant)
    open_survey(tenant, s["id"])
    sign_in(tenant, staff)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()

    main.rate_limiter._hits.clear()
    tenant.post("/api/client/login", json={"email": "x", "password": "y"})
    # Close as the owner, then try again as the employee.
    with main.SessionLocal() as db:
        row = db.query(models.DBSurvey).filter(
            models.DBSurvey.id == s["id"]).first()
        row.status = "closed"
        db.commit()

    sign_in(tenant, staff)
    qs = {q["kind"]: q["id"] for q in detail["questions"]}
    res = tenant.post(f"/api/employee/surveys/{s['id']}/respond",
                      json={"answers": {str(qs["scale"]): "5"}})
    assert res.status_code == 409


def test_nobody_answers_twice(tenant, staff):
    s = make_survey(tenant)
    open_survey(tenant, s["id"])
    sign_in(tenant, staff)
    detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
    answer(tenant, s["id"], detail)

    qs = {q["kind"]: q["id"] for q in detail["questions"]}
    again = tenant.post(f"/api/employee/surveys/{s['id']}/respond",
                        json={"answers": {str(qs["scale"]): "1"}})
    assert again.status_code == 409


def test_a_required_question_has_to_be_answered(tenant, staff):
    s = make_survey(tenant)
    open_survey(tenant, s["id"])
    sign_in(tenant, staff)
    res = tenant.post(f"/api/employee/surveys/{s['id']}/respond",
                      json={"answers": {}})
    assert res.status_code == 400
    assert "How happy" in res.json()["detail"]


def test_somebody_not_asked_cannot_answer(tenant, account):
    asked = make_employee(tenant, first_name="Asked", last_name="One",
                          password="EmpPass123")
    s = make_survey(tenant)
    open_survey(tenant, s["id"])

    # Hired after the survey went out, so never a recipient.
    later = make_employee(tenant, first_name="Later", last_name="Two",
                          password="EmpPass123")
    sign_in(tenant, later)
    assert tenant.get(f"/api/employee/surveys/{s['id']}").status_code == 404
    assert tenant.post(f"/api/employee/surveys/{s['id']}/respond",
                       json={"answers": {}}).status_code == 404


# --- the numbers --------------------------------------------------------------

def test_a_scale_question_is_averaged(tenant, account):
    people = [make_employee(tenant, first_name=f"S{i}", last_name="X",
                            password="EmpPass123") for i in range(3)]
    s = make_survey(tenant, anonymous=True)
    open_survey(tenant, s["id"])

    for p, score in zip(people, ["5", "3", "4"]):
        sign_in(tenant, p)
        detail = tenant.get(f"/api/employee/surveys/{s['id']}").json()
        answer(tenant, s["id"], detail, happy=score, comment="x")

    as_owner(tenant, account)
    body = tenant.get(f"/api/surveys/{s['id']}/results").json()
    scale = next(r for r in body["results"] if r["kind"] == "scale")
    assert scale["average"] == 4.0
    assert scale["answered"] == 3


def test_an_unanswered_survey_reports_nothing_rather_than_failing(tenant, staff):
    s = make_survey(tenant)
    open_survey(tenant, s["id"])
    body = tenant.get(f"/api/surveys/{s['id']}/results").json()
    assert body["responses"] == 0
    scale = next(r for r in body["results"] if r["kind"] == "scale")
    assert scale["average"] is None


# --- deleting -----------------------------------------------------------------

def test_a_draft_can_be_deleted(tenant):
    s = make_survey(tenant)
    assert tenant.delete(f"/api/surveys/{s['id']}").status_code == 200


def test_one_people_have_answered_is_closed_not_deleted(tenant, staff):
    """On an anonymous survey there is no way to ask them again."""
    s = make_survey(tenant)
    open_survey(tenant, s["id"])
    res = tenant.delete(f"/api/surveys/{s['id']}")
    assert res.status_code == 409
    assert "close" in res.json()["detail"].lower()


# --- who can see what ---------------------------------------------------------

def test_surveys_are_the_tenants_own(tenant, account):
    import uuid
    from fastapi.testclient import TestClient
    make_survey(tenant)

    with TestClient(main.app) as other:
        main.rate_limiter._hits.clear()
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={
            "email": email, "password": "Passw0rdTest"})
        assert other.get("/api/surveys").json() == []


def test_an_employee_cannot_read_the_results(tenant, staff):
    from fastapi.testclient import TestClient
    s = make_survey(tenant)
    open_survey(tenant, s["id"])

    with TestClient(main.app) as staff_only:
        main.rate_limiter._hits.clear()
        staff_only.post("/api/employee/auth/login", json={
            "email": staff["email"], "password": "EmpPass123"})
        assert staff_only.get(f"/api/surveys/{s['id']}/results").status_code in (401, 403)
        assert staff_only.get(f"/api/surveys/{s['id']}/chase").status_code in (401, 403)


def test_surveys_need_a_session(client):
    assert client.get("/api/surveys").status_code in (401, 403)
    assert client.get("/api/employee/surveys").status_code == 401
