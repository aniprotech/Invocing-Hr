"""AI features are metered, and the rules around that are easy to get wrong.

A tenant must not be billed when the model is unavailable or the request is
invalid, must be refused before the upstream call when out of credit, and must
actually be billed when the model does produce something.
"""
import pytest

import main
from conftest import past_trial


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


@pytest.fixture
def priced_account(client, account, superadmin):
    """A funded tenant with AI screening priced and no free allowance.

    Past its free month as well: for the first thirty days nothing is charged
    at all, so a fixture called "priced" that left the account inside one would
    be describing something that cannot happen.
    """
    rows = superadmin.get("/api/superadmin/clients").json()
    cid = next(r["id"] for r in rows if r["email"] == account["email"])
    past_trial(cid)
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust",
                    json={"amount": 10, "reason": "test credit"})
    rules = superadmin.get("/api/superadmin/pricing").json()
    rule = next(r for r in rules if r["action_key"] == "ai_resume_screen")
    superadmin.put(f"/api/superadmin/pricing/{rule['id']}",
                   json={"unit_price": 0.40, "free_allowance": 0})
    superadmin.post("/api/superadmin/logout")

    tenant = account["client"]
    tenant.post("/api/client/login", json={
        "email": account["email"], "password": account["password"],
    })
    return {"client": tenant, "client_id": cid}


def balance(tenant):
    return tenant.get("/api/wallet").json()["balance"]


SCREEN_PAYLOAD = {
    "job_title": "Engineer",
    "resume_text": "Python developer with five years of experience.",
    "candidate_name": "Test Person",
}


def test_no_charge_when_the_model_is_unavailable(priced_account, monkeypatch):
    """With no API key llm_json returns None. The endpoint still answers, but
    nothing was produced, so nothing is billed."""
    monkeypatch.setattr(main, "llm_json", lambda *a, **k: None)
    tenant = priced_account["client"]
    before = balance(tenant)
    res = tenant.post("/api/ai/screen-resume", json=SCREEN_PAYLOAD)
    assert res.status_code == 200
    assert "unavailable" in res.json()["summary"].lower()
    assert balance(tenant) == before


def test_no_charge_for_an_invalid_request(priced_account):
    tenant = priced_account["client"]
    before = balance(tenant)
    assert tenant.post("/api/ai/screen-resume", json={}).status_code == 400
    assert balance(tenant) == before


def test_no_charge_when_there_is_nothing_to_screen(priced_account, monkeypatch):
    monkeypatch.setattr(main, "llm_json", lambda *a, **k: {"score": 90})
    tenant = priced_account["client"]
    before = balance(tenant)
    res = tenant.post("/api/ai/screen-resume", json={"job_title": "Engineer"})
    assert res.status_code == 200
    assert balance(tenant) == before


def test_charge_lands_when_the_model_answers(priced_account, monkeypatch):
    """The positive case: a real result is billed, and the debit persists."""
    monkeypatch.setattr(main, "llm_json", lambda *a, **k: {
        "score": 82, "summary": "Strong match", "strengths": ["Python"],
        "weaknesses": [], "recommendation": "Interview",
    })
    tenant = priced_account["client"]
    before = balance(tenant)
    res = tenant.post("/api/ai/screen-resume", json=SCREEN_PAYLOAD)
    assert res.status_code == 200
    assert res.json()["score"] == 82

    after = balance(tenant)
    assert round(before - after, 2) == 0.40, "a successful AI call must be billed"

    tx = tenant.get("/api/wallet/transactions?direction=debit").json()[0]
    assert tx["action_key"] == "ai_resume_screen"
    assert tx["amount"] == 0.40
    assert tx["balance_after"] == after


def test_refused_before_the_upstream_call_when_out_of_credit(client, account, superadmin, monkeypatch):
    """Affordability is checked first, so an unfunded tenant cannot burn an
    upstream API call."""
    rows = superadmin.get("/api/superadmin/clients").json()
    cid = next(r["id"] for r in rows if r["email"] == account["email"])
    rules = superadmin.get("/api/superadmin/pricing").json()
    rule = next(r for r in rules if r["action_key"] == "ai_resume_screen")
    superadmin.put(f"/api/superadmin/pricing/{rule['id']}",
                   json={"unit_price": 0.40, "free_allowance": 0})
    superadmin.post("/api/superadmin/logout")

    called = {"n": 0}

    def spy(*a, **k):
        called["n"] += 1
        return {"score": 50}

    monkeypatch.setattr(main, "llm_json", spy)

    tenant = account["client"]
    tenant.post("/api/client/login", json={
        "email": account["email"], "password": account["password"],
    })
    res = tenant.post("/api/ai/screen-resume", json=SCREEN_PAYLOAD)
    assert res.status_code == 402
    assert called["n"] == 0, "the model must not be called when the tenant cannot pay"


def test_free_allowance_means_no_charge(client, account, superadmin, monkeypatch):
    rows = superadmin.get("/api/superadmin/clients").json()
    cid = next(r["id"] for r in rows if r["email"] == account["email"])
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust",
                    json={"amount": 5, "reason": "seed"})
    rules = superadmin.get("/api/superadmin/pricing").json()
    rule = next(r for r in rules if r["action_key"] == "ai_resume_screen")
    superadmin.put(f"/api/superadmin/pricing/{rule['id']}",
                   json={"unit_price": 0.40, "free_allowance": 5})
    superadmin.post("/api/superadmin/logout")

    monkeypatch.setattr(main, "llm_json", lambda *a, **k: {"score": 70})
    tenant = account["client"]
    tenant.post("/api/client/login", json={
        "email": account["email"], "password": account["password"],
    })
    before = balance(tenant)
    assert tenant.post("/api/ai/screen-resume", json=SCREEN_PAYLOAD).status_code == 200
    assert balance(tenant) == before, "the first call is inside the free allowance"


def test_llm_returns_none_without_a_key():
    """The guard that makes every AI feature degrade instead of erroring."""
    import llm
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) is None or llm.GROQ_API_KEY
