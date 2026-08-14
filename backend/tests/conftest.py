"""Test fixtures.

Each test module gets a throwaway SQLite database so tests never touch the
real one and can run in any order.
"""
import os
import sys
import tempfile
import uuid

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Must be set before `database` is imported, since it reads the env at import.
_TMP_DB = os.path.join(tempfile.gettempdir(), f"invoicing_test_{uuid.uuid4().hex}.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SUPERADMIN_PASSWORD", "TestSuper123")
# Tests drive run_due_jobs() directly; a loop ticking in the background would
# race them and claim periods out from under the assertions.
os.environ.setdefault("SCHEDULER_ENABLED", "0")

from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
import main  # noqa: E402
import models  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    models.Base.metadata.create_all(bind=database.engine)
    yield
    database.engine.dispose()
    try:
        os.remove(_TMP_DB)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Registration/login are deliberately rate limited per IP. Every test comes
    from the same testserver address, so clear the window between tests instead
    of weakening the limit itself."""
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def account(client):
    """A registered, logged-in tenant. Returns the TestClient with its session
    cookie already set, plus the credentials used."""
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    password = "Passw0rdTest"
    res = client.post("/api/client/register", json={
        "email": email, "password": password, "company_name": "Acme Ltd",
    })
    assert res.status_code == 200, res.text
    res = client.post("/api/client/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"client": client, "email": email, "password": password}


@pytest.fixture
def tenant(account):
    return account["client"]


def make_employee(tenant, **overrides):
    """Create an employee and return its API representation."""
    payload = {
        "first_name": "Test", "last_name": f"Person{uuid.uuid4().hex[:6]}",
        "email": f"emp-{uuid.uuid4().hex[:10]}@example.com",
        "salary": 3000.0, "tax_rate": 20.0, "status": "active",
    }
    payload.update(overrides)
    res = tenant.post("/api/employees", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def make_invoice(tenant, line_items=None, **overrides):
    payload = {
        "contact": "Customer Ltd",
        "email": "customer@example.com",
        "issue_date": "2026-01-01",
        "due_date": "2026-01-31",
        "tax_type": "exclusive",
        "line_items": line_items or [
            {"description": "Consulting", "qty": 1, "price": 100.0, "tax_rate": "20% VAT"},
        ],
    }
    payload.update(overrides)
    res = tenant.post("/api/invoices", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def work_every_day(tenant):
    """Treat every day as a working day for this tenant.

    Signing in only starts a shift on a working day, which is the intended
    behaviour - somebody opening the portal on a Sunday to check a document is
    not at work. A test about the clock-in mechanics must not also depend on
    which day the suite happens to run, or it goes red every weekend.
    """
    res = tenant.put("/api/attendance/settings", json={"working_days": "1,2,3,4,5,6,7"})
    assert res.status_code == 200, res.text
