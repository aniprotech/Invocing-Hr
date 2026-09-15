"""One email a day saying what is waiting on HR.

The same rows as the dashboard - requests to decide, probations, policy
acknowledgements - plus who starts, whose probation ends and whose
birthday it is. Sent from seven in the morning, once a day, only when
there is something in it, only to businesses that have not switched it
off, and never with somebody's markup in it.
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


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, **kw: (sent.append({"to": to, "subject": subject, "body": body, "html": html_body, "client_id": kw.get("client_id")}), (True, ""))[1])
    return sent


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def test_nothing_waiting_means_no_email(tenant, account):
    assert tenant.get("/api/hr/digest-preview").json()["digest"] is None


def test_the_digest_says_what_is_waiting_and_what_is_coming(tenant, account):
    person(tenant, first_name="Nia <b>x</b>", probation_end=days(3), start_date=days(2))
    out = tenant.get("/api/hr/digest-preview").json()
    assert out["enabled"] and out["to"] == account["email"]
    d = out["digest"]
    assert "1 probations to decide" in d["text"]
    assert "probation ends" in d["text"] and "starts" in d["text"]
    assert "<b>" not in d["html"] and "&lt;b&gt;" in d["html"], "a name is text in the email too"
    # A new hire also brings document requests, so the count is more than the probation alone.
    assert d["subject"].endswith("things waiting") and d["waiting"]


def test_it_goes_out_once_from_seven_and_not_before(tenant, account, outbox):
    person(tenant, probation_end=days(3))
    fn = next(f for n, f, _ in main.SCHEDULED_JOBS if n == "hr_digest")
    early = datetime.combine(date.today(), datetime.min.time()).replace(hour=6, minute=30)
    late = early.replace(hour=7, minute=15)
    assert fn(early) != fn(late) and fn(late) == fn(late.replace(hour=18))
    with main.SessionLocal() as db:
        assert main.job_hr_digest(db, early) == "too early"
        assert outbox == []
        result = main.job_hr_digest(db, late)
    assert result.endswith("sent") and any(m["to"] == account["email"] for m in outbox)
    mine = next(m for m in outbox if m["to"] == account["email"])
    assert "probations to decide" in mine["body"] and mine["client_id"]


def test_a_business_can_switch_it_off(tenant, account, outbox):
    person(tenant, probation_end=days(3))
    tenant.post("/api/settings", json={"hr_digest": "0"})
    assert tenant.get("/api/hr/digest-preview").json()["enabled"] is False
    with main.SessionLocal() as db:
        main.job_hr_digest(db, datetime.now().replace(hour=8))
    assert not any(m["to"] == account["email"] for m in outbox)
