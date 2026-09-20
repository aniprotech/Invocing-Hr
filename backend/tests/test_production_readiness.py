"""The things that are fine on a laptop and not fine with customers on it.

Each of these was true in production when it was found:

  - /docs, /redoc and /openapi.json were served to anybody. The complete
    map of every endpoint and parameter of a multi-tenant product.
  - An employee's password could be a single character. The business's own
    password needed eight, a capital and a digit; the login in front of
    somebody's payslips and bank details needed nothing.
  - With DATABASE_URL unset the app fell back to a local SQLite file and came
    up healthy - every table present, nothing in any of them. On a container
    that is a fresh empty database on every deploy, and it presents as "all
    my data is gone" while being nearly impossible to tell from real loss.
  - The platform's own mail - sign-in codes, resets - was written down
    nowhere but the log. A transport that had been failing for weeks looked,
    from every screen the operator has, like nothing at all.
"""
import os
import subprocess
import sys

import pytest

import main
import models
from conftest import make_employee

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


# --- the API is not a public map -----------------------------------------------------

def test_the_interactive_docs_are_off(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path


def test_but_can_be_asked_for():
    """On a machine somebody controls. The switch exists so it is a decision,
    not a thing that happens to be on."""
    code = (
        "import os; os.environ['EXPOSE_API_DOCS']='true'; "
        "os.environ['DATABASE_URL']='sqlite:///./docs-probe.db'; "
        "import main; print(main.app.docs_url, main.app.openapi_url)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND,
                         capture_output=True, text=True, timeout=120)
    try:
        os.remove(os.path.join(BACKEND, "docs-probe.db"))
    except OSError:
        pass
    assert "/docs /openapi.json" in out.stdout, out.stdout + out.stderr


# --- an employee's password is a password ----------------------------------------------

def test_hr_cannot_set_a_one_character_password(tenant):
    emp = make_employee(tenant)
    res = tenant.put(f"/api/employees/{emp['id']}/set-password", json={"password": "a"})
    assert res.status_code == 400, res.text
    assert "8 characters" in res.json()["detail"]


def test_nor_reset_to_a_four_character_one(tenant):
    emp = make_employee(tenant)
    res = tenant.post(f"/api/employees/{emp['id']}/reset-password", json={"password": "abcd"})
    assert res.status_code == 400, res.text


def test_the_rule_is_the_same_one_a_business_gets(tenant):
    """Eight characters, a capital and a digit. Not a separate, weaker rule
    for the people with the least say in it."""
    emp = make_employee(tenant)
    assert tenant.put(f"/api/employees/{emp['id']}/set-password",
                      json={"password": "alllowercase1"}).status_code == 400
    assert tenant.put(f"/api/employees/{emp['id']}/set-password",
                      json={"password": "NoDigitsHere"}).status_code == 400
    assert tenant.put(f"/api/employees/{emp['id']}/set-password",
                      json={"password": "Proper1Password"}).status_code == 200


# --- no empty database by accident ------------------------------------------------------

def _bare_env(**extra):
    """No DATABASE_URL from anywhere. load_dotenv() reads the nearest .env
    upward from the working directory, and a developer's machine has one
    with the real URL in it - so the subprocess runs from an empty temp dir,
    where there is nothing to find."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "ALLOW_SQLITE_FALLBACK")}
    env["PYTHONPATH"] = BACKEND
    env.update(extra)
    return env


def test_the_app_refuses_to_start_without_a_database_url(tmp_path):
    """Not a warning in a log nobody reads. A stop, with the variable named."""
    out = subprocess.run([sys.executable, "-c", "import database"], cwd=str(tmp_path),
                         capture_output=True, text=True, timeout=60, env=_bare_env())
    assert out.returncode != 0, "it started with no database"
    assert "DATABASE_URL is not set" in (out.stderr + out.stdout)


def test_unless_a_throwaway_is_asked_for_by_name(tmp_path):
    out = subprocess.run([sys.executable, "-c", "import database; print(database.DATABASE_URL)"],
                         cwd=str(tmp_path), capture_output=True, text=True, timeout=60,
                         env=_bare_env(ALLOW_SQLITE_FALLBACK="true"))
    assert out.returncode == 0, out.stderr
    assert "sqlite" in out.stdout


def test_a_url_that_is_set_is_used_as_given(tmp_path):
    out = subprocess.run([sys.executable, "-c", "import database; print(database.DATABASE_URL)"],
                         cwd=str(tmp_path), capture_output=True, text=True, timeout=60,
                         env=_bare_env(DATABASE_URL="sqlite:///./given-probe.db"))
    assert out.returncode == 0, out.stderr
    assert "given-probe" in out.stdout


# --- the platform's own mail is on the record ---------------------------------------------

def _platform_rows():
    with main.SessionLocal() as db:
        return db.query(models.DBEmailDelivery).filter(
            models.DBEmailDelivery.client_id == None,          # noqa: E711
            models.DBEmailDelivery.kind == "platform").all()


def test_a_platform_send_is_written_down(monkeypatch):
    before = len(_platform_rows())
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (False, "SMTP error: no route to host"))
    ok, why = main.send_email_background("somebody@example.com", "Your sign-in code: 123456",
                                         "body", "hello@example.com")
    assert ok is False
    rows = _platform_rows()
    assert len(rows) == before + 1
    row = rows[-1]
    assert row.status == "failed"
    assert "no route to host" in row.error
    assert row.to_email == "somebody@example.com"


def test_and_the_record_does_not_carry_the_code(monkeypatch):
    """The subject of a sign-in mail has the code in it. What went wrong is
    worth keeping; what would have let somebody in is not."""
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (False, "nope"))
    main.send_email_background("x@example.com", "Your sign-in code: 987654", "b", "f@example.com")
    row = _platform_rows()[-1]
    assert "987654" not in (row.reference or "")
    assert "987654" not in (row.error or "")
    assert row.reference == "Your sign-in code"


def test_a_business_send_is_not_double_counted(monkeypatch, tenant):
    """Those are recorded by deliver_and_record around this. Recording them
    here too would show every invoice twice."""
    with main.SessionLocal() as db:
        cid = db.query(models.DBClient).first().id
    before = len(_platform_rows())
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (True, "sent"))
    main.send_email_background("x@example.com", "Invoice INV-1", "b", "f@example.com", client_id=cid)
    assert len(_platform_rows()) == before


def test_the_operator_can_see_what_failed(client, monkeypatch):
    """The screen that did not exist."""
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (False, "SMTP error: [Errno 111] refused"))
    main.send_email_background("a@example.com", "Your sign-in code: 1", "b", "f@example.com")
    main.send_email_background("b@example.com", "Reset your password", "b", "f@example.com")
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (True, "sent"))
    main.send_email_background("c@example.com", "Verify your address", "b", "f@example.com")

    # signed in as the operator, the way the authenticator tests do it
    from fastapi.testclient import TestClient
    main.rate_limiter._hits.clear()
    with TestClient(main.app) as op:
        res = op.post("/api/superadmin/login", json={
            "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
        assert res.status_code == 200, res.text
        got = op.get("/api/superadmin/email-failures").json()
    assert got["failed_7d"] >= 2
    assert got["sent_7d"] >= 1
    assert got["last_failure"]
    assert any("refused" in r["reason"] for r in got["reasons"]), got["reasons"]
    whats = [f["what"] for f in got["failures"]]
    assert "Your sign-in code" in whats and "Reset your password" in whats


def test_and_nobody_else_can(client, tenant):
    assert tenant.get("/api/superadmin/email-failures").status_code in (401, 403)


# --- and the health check says so ------------------------------------------------------------

def test_health_reports_whether_mail_can_leave(client):
    body = client.get("/api/health").json()
    assert body.get("email") in ("ready", "not_configured"), body


def test_health_counts_recent_failures(client, monkeypatch):
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (False, "down"))
    main.send_email_background("a@example.com", "Your sign-in code: 1", "b", "f@example.com")
    body = client.get("/api/health").json()
    assert body.get("email_failures_24h", 0) >= 1, body
    # And status is left alone: it is about the database and the schema, and
    # is what the platform restarts on.
    assert body["status"] in ("ok", "ok_with_warnings")
