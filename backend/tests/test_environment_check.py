"""Answering "did that variable actually take effect?" without reading logs.

Setting a variable on a hosting platform is easy; confirming the running
process picked it up is not, and the failure is silent - an unset SECRET_KEY
just quietly signs everybody out on the next redeploy.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


def check(body, name):
    return next(c for c in body["checks"] if c["name"] == name)


def test_it_is_superadmin_only(tenant):
    """An ordinary account must not learn how production is configured."""
    assert tenant.get("/api/superadmin/environment").status_code in (401, 403)


def test_a_stranger_is_refused(client):
    assert client.get("/api/superadmin/environment").status_code in (401, 403)


def test_it_reports_every_setting(superadmin):
    body = superadmin.get("/api/superadmin/environment").json()
    names = [c["name"] for c in body["checks"]]
    assert names == ["SECRET_KEY", "GROQ_API_KEY", "DATABASE_URL", "Payment gateways"]


def test_a_set_variable_reads_as_ok(superadmin, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    body = superadmin.get("/api/superadmin/environment").json()
    assert check(body, "SECRET_KEY")["ok"] is True
    assert "SECRET_KEY" not in body["outstanding"]


def test_an_unset_variable_explains_the_consequence(superadmin, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    body = superadmin.get("/api/superadmin/environment").json()
    entry = check(body, "SECRET_KEY")
    assert entry["ok"] is False
    assert "signed out" in entry["detail"]
    assert entry["fix"]
    assert "SECRET_KEY" in body["outstanding"]


def test_it_never_returns_the_value(superadmin, monkeypatch):
    """The whole point is that an operator can check this page safely."""
    secret = "super-secret-value-nobody-should-see"
    monkeypatch.setenv("SECRET_KEY", secret)
    monkeypatch.setenv("GROQ_API_KEY", secret)
    res = superadmin.get("/api/superadmin/environment")
    assert secret not in res.text


def test_ready_is_only_true_when_nothing_is_outstanding(superadmin, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    body = superadmin.get("/api/superadmin/environment").json()
    assert body["ready"] is False
    assert body["ready"] == (body["outstanding"] == [])
