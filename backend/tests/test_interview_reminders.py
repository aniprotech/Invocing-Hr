"""Nobody was reminded about an interview.

One was booked and then nothing happened until it either did or did not.
Candidates no-show when nothing nudges them.
"""
from datetime import datetime, timedelta

import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    yield


def booked(tenant, client, hours_ahead=20, status="scheduled", interviewer_id=None,
           candidate_email="casey@example.com"):
    """A candidate with an interview at a given distance from now."""
    main.rate_limiter._hits.clear()
    form = tenant.post("/api/recruitment/forms", json={
        "title": "Engineer", "description": "Join us",
        "fields": '[{"label":"Full name","type":"text"}]',
        "pipeline_stages": '["Applied","Interview","Hired"]'}).json()
    client.post(f"/api/recruitment/form/{form['form_token']}/submit", json={
        "answers": '{"Full name":"Casey"}', "candidate_name": "Casey Candidate",
        "candidate_email": candidate_email})
    sub = tenant.get(f"/api/recruitment/forms/{form['id']}/submissions").json()[0]

    when = (datetime.now() + timedelta(hours=hours_ahead)).strftime("%Y-%m-%d %H:%M")
    res = tenant.post(f"/api/recruitment/submissions/{sub['id']}/interviews", json={
        "round_name": "First interview", "scheduled_at": when,
        "duration_minutes": 45, "mode": "video",
        "meeting_link": "https://meet.example/abc",
        "interviewer_id": interviewer_id})
    assert res.status_code == 200, res.text
    iv = res.json()
    if status != "scheduled":
        with main.SessionLocal() as db:
            row = db.query(models.DBInterview).filter(
                models.DBInterview.id == iv["id"]).first()
            row.status = status
            db.commit()
    return iv


def reminders(tenant, interview_id):
    res = tenant.get(f"/api/recruitment/interviews/{interview_id}/reminders")
    assert res.status_code == 200, res.text
    return res.json()


def test_a_candidate_is_reminded_the_day_before(client, tenant):
    iv = booked(tenant, client, hours_ahead=20)
    main.run_due_jobs(only="interview_reminders")

    sent = reminders(tenant, iv["id"])
    assert [r["recipient"] for r in sent] == ["candidate"]
    assert sent[0]["sent_to"] == "casey@example.com"


def test_the_interviewer_is_reminded_too(client, tenant):
    emp = make_employee(tenant)
    iv = booked(tenant, client, hours_ahead=20, interviewer_id=emp["id"])
    main.run_due_jobs(only="interview_reminders")

    assert {r["recipient"] for r in reminders(tenant, iv["id"])} == {
        "candidate", "interviewer"}


def test_nobody_is_reminded_twice(client, tenant):
    iv = booked(tenant, client, hours_ahead=20)
    main.run_due_jobs(only="interview_reminders")
    with main.SessionLocal() as db:
        db.query(models.DBJobRun).delete()
        db.commit()
    main.run_due_jobs(only="interview_reminders")

    assert len(reminders(tenant, iv["id"])) == 1


def test_an_interview_further_out_waits(client, tenant):
    iv = booked(tenant, client, hours_ahead=72)
    main.run_due_jobs(only="interview_reminders")
    assert reminders(tenant, iv["id"]) == []


def test_an_interview_already_past_is_not_chased(client, tenant):
    iv = booked(tenant, client, hours_ahead=-5)
    main.run_due_jobs(only="interview_reminders")
    assert reminders(tenant, iv["id"]) == []


def test_a_cancelled_interview_is_not_chased(client, tenant):
    iv = booked(tenant, client, hours_ahead=20, status="cancelled")
    main.run_due_jobs(only="interview_reminders")
    assert reminders(tenant, iv["id"]) == []


def test_a_completed_interview_is_not_chased(client, tenant):
    iv = booked(tenant, client, hours_ahead=20, status="completed")
    main.run_due_jobs(only="interview_reminders")
    assert reminders(tenant, iv["id"]) == []


def test_a_candidate_with_no_email_is_skipped(client, tenant):
    iv = booked(tenant, client, hours_ahead=20, candidate_email="")
    main.run_due_jobs(only="interview_reminders")
    assert reminders(tenant, iv["id"]) == []


def test_the_job_is_registered_with_the_scheduler():
    assert "interview_reminders" in [j[0] for j in main.SCHEDULED_JOBS]


def test_reminders_need_a_session(client):
    assert client.get("/api/recruitment/interviews/1/reminders").status_code == 401


def test_another_tenant_cannot_read_them(client, tenant):
    import uuid
    iv = booked(tenant, client, hours_ahead=20)
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get(
        f"/api/recruitment/interviews/{iv['id']}/reminders").status_code == 404
