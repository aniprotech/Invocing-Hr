"""The product talking to the tools around it.

An API key is made once and shown once; what is kept is its hash. It opens
a versioned, read-mostly API for the business it belongs to and nobody
else, with a write scope for the few that need it. A webhook is an https
URL, the events it wants, and a secret each delivery is signed with;
deliveries retry with backoff, every attempt is written down, and a
receiver that fails twenty times in a row is switched off rather than
hammered forever.
"""
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta

os.environ["WEBHOOKS_ASYNC"] = "0"          # the tests drive delivery by hand

import pytest

import main
import models
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def fake_net(monkeypatch):
    """Stand in for the network: records every POST, answers what it is told."""
    calls = []
    state = {"code": 200}

    def post(url, body, headers, timeout=6):
        calls.append({"url": url, "body": body, "headers": headers})
        return state["code"], "" if state["code"] < 400 else f"HTTP {state['code']}"
    monkeypatch.setattr(main, "_post_webhook", post)
    return calls, state


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def make_key(tenant, write=False, name="Payroll sync"):
    res = tenant.post("/api/api-keys", json={"name": name, "write": write})
    assert res.status_code == 200, res.text
    return res.json()


def with_key(client, key):
    return {"Authorization": "Bearer " + key}


def deliver():
    with main.SessionLocal() as db:
        return main.deliver_webhooks(db)


# --- keys ---------------------------------------------------------------------------------

def test_a_key_is_shown_once_and_only_its_hash_is_kept(tenant):
    k = make_key(tenant)
    assert k["key"].startswith("ak_") and k["scopes"] == "read" and k["prefix"] == k["key"][:11]
    listed = tenant.get("/api/api-keys").json()["keys"]
    assert listed[0]["id"] == k["id"] and "key" not in listed[0]
    with main.SessionLocal() as db:
        row = db.get(models.DBApiKey, k["id"])
        assert row.key_hash == hashlib.sha256(k["key"].encode()).hexdigest()
        assert k["key"] not in (row.key_hash + row.prefix)


def test_a_key_reads_this_business_and_no_other(tenant, account):
    emp = person(tenant, first_name="Ann")
    k = make_key(tenant)
    tenant.post("/api/client/logout")
    res = tenant.get("/api/v1/employees", headers=with_key(tenant, k["key"]))
    assert res.status_code == 200, res.text
    assert [e["first_name"] for e in res.json()["employees"]] == ["Ann"]
    assert tenant.get(f"/api/v1/employees/{emp['id']}", headers=with_key(tenant, k["key"])).json()["email"] == emp["email"]
    assert tenant.get("/api/v1/departments", headers=with_key(tenant, k["key"])).status_code == 200
    assert tenant.get("/api/v1/leave", headers=with_key(tenant, k["key"])).json()["leave"] == []
    assert tenant.get("/api/v1/attendance", headers=with_key(tenant, k["key"])).json()["attendance"] == []
    # Nothing without a key, nothing with a wrong one, nothing with a revoked one.
    assert tenant.get("/api/v1/employees").status_code == 401
    assert tenant.get("/api/v1/employees", headers=with_key(tenant, "ak_nonsense")).status_code == 401
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert tenant.delete(f"/api/api-keys/{k['id']}").status_code == 200
    tenant.post("/api/client/logout")
    assert tenant.get("/api/v1/employees", headers=with_key(tenant, k["key"])).status_code == 401
    # Another business's key sees its own, empty, list.
    other = f"other-{account['email']}"
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    k2 = make_key(tenant)
    tenant.post("/api/client/logout")
    assert tenant.get("/api/v1/employees", headers=with_key(tenant, k2["key"])).json()["employees"] == []
    assert tenant.get(f"/api/v1/employees/{emp['id']}", headers=with_key(tenant, k2["key"])).status_code == 404


def test_writing_needs_the_write_scope_and_goes_through_the_same_checks(tenant):
    ro = make_key(tenant)
    rw = make_key(tenant, write=True)
    tenant.post("/api/client/logout")
    body = {"first_name": "Via", "last_name": "Api", "email": f"via-{rw['id']}@example.com", "job_title": "Dev"}
    assert tenant.post("/api/v1/employees", json=body, headers=with_key(tenant, ro["key"])).status_code == 403
    res = tenant.post("/api/v1/employees", json=body, headers=with_key(tenant, rw["key"]))
    assert res.status_code == 200, res.text
    assert tenant.post("/api/v1/employees", json=body, headers=with_key(tenant, rw["key"])).status_code in (400, 409)   # same email twice
    listed = tenant.get("/api/v1/employees?status=current", headers=with_key(tenant, rw["key"])).json()["employees"]
    assert any(e["email"] == body["email"] for e in listed)


def test_a_session_works_on_the_public_api_too_and_keys_are_limited(tenant):
    assert tenant.get("/api/v1/employees").status_code == 200
    for i in range(10):
        make_key(tenant, name=f"k{i}")
    assert tenant.post("/api/api-keys", json={"name": "one too many"}).status_code == 400


# --- webhooks ---------------------------------------------------------------------------------

def test_a_webhook_needs_https_and_known_events(tenant):
    assert tenant.post("/api/webhooks", json={"url": "http://plain.example/hook"}).status_code == 400
    assert tenant.post("/api/webhooks", json={"url": "https://x.example/hook", "events": ["employee.exploded"]}).status_code == 400
    assert tenant.post("/api/webhooks", json={"url": "https://x.example/hook", "events": []}).status_code == 400
    w = tenant.post("/api/webhooks", json={"url": "https://x.example/hook"}).json()
    assert w["secret"].startswith("whsec_") and set(w["events"]) == set(main.WEBHOOK_EVENTS)
    listed = tenant.get("/api/webhooks").json()["webhooks"]
    assert listed[0]["id"] == w["id"] and "secret" not in listed[0] and listed[0]["secret_prefix"] == "whsec_"


def test_an_event_is_delivered_signed_and_only_to_hooks_that_want_it(tenant, fake_net):
    calls, _ = fake_net
    wants = tenant.post("/api/webhooks", json={"url": "https://a.example/hook", "events": ["employee.created"]}).json()
    tenant.post("/api/webhooks", json={"url": "https://b.example/hook", "events": ["leave.decided"]})
    emp = person(tenant, first_name="Nia")
    assert deliver() == 1
    assert len(calls) == 1 and calls[0]["url"] == "https://a.example/hook"
    body = json.loads(calls[0]["body"])
    assert body["event"] == "employee.created" and body["data"]["id"] == emp["id"] and body["data"]["first_name"] == "Nia"
    h = calls[0]["headers"]
    assert h["X-Aniprotech-Event"] == "employee.created"
    expected = "sha256=" + hmac.new(wants["secret"].encode(), calls[0]["body"].encode(), hashlib.sha256).hexdigest()
    assert h["X-Aniprotech-Signature"] == expected
    log = tenant.get("/api/webhooks").json()
    assert log["deliveries"][0]["ok"] and log["deliveries"][0]["status_code"] == 200 and log["deliveries"][0]["attempts"] == 1
    assert log["webhooks"][0]["last_status"] == 200


def test_every_kind_of_event_goes_out(tenant, account, fake_net):
    calls, _ = fake_net
    tenant.post("/api/webhooks", json={"url": "https://a.example/hook"})
    boss = person(tenant, first_name="Bea", probation_months=0)
    emp = person(tenant, first_name="Ravi", reports_to=boss["id"], probation_end="2026-12-01", salary=3000.0)
    tenant.put(f"/api/employees/{emp['id']}", json={"job_title": "Lead"})
    tenant.post(f"/api/employees/{emp['id']}/probation", json={"decision": "confirm"})
    tenant.post("/api/pay-review", json={"changes": [{"employee_id": emp["id"], "salary": 3300}]})
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/logout")
    tenant.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD})
    res = tenant.post("/api/employee/leave", json={"leave_type": "annual", "start_date": "2026-11-02", "end_date": "2026-11-03", "reason": "x"})
    assert res.status_code == 200, res.text
    tenant.post("/api/employee/auth/logout")
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    with main.SessionLocal() as db:
        leave = db.query(models.DBLeaveRequest).filter(models.DBLeaveRequest.employee_id == emp["id"]).first()
    tenant.post(f"/api/leave-requests/{leave.id}/approve") if False else None
    # Decide through the shared function, the way both screens do.
    with main.SessionLocal() as db:
        row = db.query(models.DBLeaveRequest).filter(models.DBLeaveRequest.employee_id == emp["id"]).first()
        main.decide_leave(db, row, "approve", "HR")
        db.commit()
    deliver()
    events = sorted(json.loads(c["body"])["event"] for c in calls)
    for wanted in ("employee.created", "employee.updated", "probation.decided", "pay.changed", "leave.requested", "leave.decided"):
        assert wanted in events, events
    updated = next(json.loads(c["body"]) for c in calls if json.loads(c["body"])["event"] == "employee.updated")
    assert "bank_account" not in updated["data"]["fields"]


def test_failures_retry_with_backoff_and_a_dead_receiver_is_switched_off(tenant, fake_net):
    calls, state = fake_net
    w = tenant.post("/api/webhooks", json={"url": "https://down.example/hook", "events": ["employee.created"]}).json()
    state["code"] = 500
    person(tenant)
    assert deliver() == 0
    with main.SessionLocal() as db:
        d = db.query(models.DBWebhookDelivery).filter(models.DBWebhookDelivery.webhook_id == w["id"]).first()
        assert d.attempts == 1 and not d.ok and d.next_attempt_at   # due again in a minute
        first_due = d.next_attempt_at
    assert deliver() == 0 and len(calls) == 1, "not due yet, so not tried again"
    with main.SessionLocal() as db:
        d = db.query(models.DBWebhookDelivery).filter(models.DBWebhookDelivery.webhook_id == w["id"]).first()
        d.next_attempt_at = ""
        db.commit()
    state["code"] = 200
    assert deliver() == 1
    with main.SessionLocal() as db:
        d = db.query(models.DBWebhookDelivery).filter(models.DBWebhookDelivery.webhook_id == w["id"]).first()
        assert d.ok and d.attempts == 2
        hook = db.get(models.DBWebhook, w["id"])
        assert hook.failures == 0 and hook.active
    # Twenty failures in a row and it is switched off; the log says so.
    state["code"] = 503
    with main.SessionLocal() as db:
        hook = db.get(models.DBWebhook, w["id"])
        hook.failures = 19
        db.commit()
    person(tenant)
    deliver()
    listed = tenant.get("/api/webhooks").json()["webhooks"][0]
    assert listed["active"] is False and listed["failures"] == 20
    # Switching it back on resets the count.
    assert tenant.put(f"/api/webhooks/{w['id']}", json={"active": True}).json()["failures"] == 0


def test_a_ping_and_the_delivery_log_are_per_business(tenant, account, fake_net):
    calls, _ = fake_net
    w = tenant.post("/api/webhooks", json={"url": "https://a.example/hook"}).json()
    assert tenant.post(f"/api/webhooks/{w['id']}/test").json()["queued"]
    deliver()
    assert json.loads(calls[0]["body"])["event"] == "ping"
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/webhooks").json() == {"webhooks": [], "events": list(main.WEBHOOK_EVENTS), "deliveries": []}
    assert tenant.post(f"/api/webhooks/{w['id']}/test").status_code == 404
    assert tenant.delete(f"/api/webhooks/{w['id']}").status_code == 404


def test_the_sweep_is_on_the_schedule_every_minute(tenant):
    assert "webhook_deliveries" in [n for n, _, _ in main.SCHEDULED_JOBS]
    fn = next(f for n, f, _ in main.SCHEDULED_JOBS if n == "webhook_deliveries")
    now = datetime(2026, 9, 15, 10, 30, 5)
    assert fn(now) != fn(now + timedelta(minutes=1)) and fn(now) == fn(now + timedelta(seconds=30))
