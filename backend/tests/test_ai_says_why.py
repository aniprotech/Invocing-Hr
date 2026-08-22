"""When the AI does not answer, say which of the six reasons it was.

llm_error_message() has told them apart for a while - no key, a rejected key, a
retired model, a rate limit, a timeout, an unreachable service - and the
endpoints people actually use threw it away. The assistant said "an
administrator needs to configure the AI key" every time, which is wrong five
times out of six and sends somebody to check a setting that was never the
problem. A retired model is the case that produced it here, and it is the one
that message describes worst.
"""
import pytest

import llm
import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    llm.LAST_ERROR["reason"] = ""
    yield
    llm.LAST_ERROR["reason"] = ""


@pytest.fixture
def funded(tenant, account):
    """Credit, so nothing here turns on the pricing table.

    Pricing is global and other tests edit it - one drops a free allowance to
    zero to prove billing works. Without credit the affordability check refuses
    the call before the model is reached, and a 402 is not the failure these
    tests are about.
    """
    with main.SessionLocal() as db:
        cid = db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id
        wallet = main.get_wallet(db, cid)
        wallet.balance_minor = 500_00
        db.commit()
    return tenant


@pytest.fixture
def dead_model(monkeypatch):
    """Every model call fails the way a retired model fails."""
    def gone(*a, **k):
        llm.LAST_ERROR["reason"] = "model_gone"
        return None

    monkeypatch.setattr(main, "llm_chat", gone)
    monkeypatch.setattr(main, "llm_json", gone)
    monkeypatch.setattr(main, "llm_configured", lambda: True)
    yield


@pytest.fixture
def rate_limited(monkeypatch):
    def busy(*a, **k):
        llm.LAST_ERROR["reason"] = "rate_limited"
        return None

    monkeypatch.setattr(main, "llm_chat", busy)
    monkeypatch.setattr(main, "llm_json", busy)
    monkeypatch.setattr(main, "llm_configured", lambda: True)
    yield


def ask(tenant, question="How many invoices are overdue?"):
    return tenant.post("/api/ai/assistant", json={"question": question})


# --- the assistant ------------------------------------------------------------

def test_a_retired_model_is_not_reported_as_a_missing_key(funded, dead_model):
    """The bug outright: the key was set the whole time."""
    body = ask(funded).json()
    assert body["available"] is False
    assert "configure the AI key" not in body["answer"]
    assert "GROQ_MODEL" in body["answer"]


def test_it_says_the_model_is_the_problem(funded, dead_model):
    body = ask(funded).json()
    assert "no longer exists" in body["answer"]
    assert body["reason"] == "model_gone"


def test_a_busy_service_reads_as_temporary_not_broken(funded, rate_limited):
    """One is worth waiting out; the other needs somebody to go and fix it.
    They used to be the same sentence."""
    body = ask(funded).json()
    assert body["reason"] == "rate_limited"
    assert "busy" in body["answer"].lower()
    assert "GROQ" not in body["answer"], "nothing for the tenant to configure here"


def test_the_two_reasons_do_not_share_a_message(funded, dead_model, monkeypatch):
    gone = ask(funded).json()["answer"]
    llm.LAST_ERROR["reason"] = "rate_limited"

    def busy(*a, **k):
        llm.LAST_ERROR["reason"] = "rate_limited"
        return None

    monkeypatch.setattr(main, "llm_chat", busy)
    assert ask(funded).json()["answer"] != gone


def test_an_answer_still_comes_back_when_it_works(funded, monkeypatch):
    monkeypatch.setattr(main, "llm_chat", lambda *a, **k: "Two invoices are overdue.")
    monkeypatch.setattr(main, "llm_configured", lambda: True)
    body = ask(funded).json()
    assert body["available"] is True
    assert body["answer"] == "Two invoices are overdue."


# --- the other features fail the same way -------------------------------------

def test_resume_screening_says_why(funded, dead_model):
    res = funded.post("/api/ai/screen-resume", json={
        "job_title": "Analyst", "resume_text": "Ten years of analysis."})
    body = res.json()
    assert body["available"] is False
    assert body["reason"] == "model_gone"
    assert "GROQ_MODEL" in body["summary"], "'AI service unavailable' told nobody anything"


def test_insights_says_why(funded, dead_model):
    body = funded.get("/api/ai/insights").json()
    assert body["available"] is False
    assert body["reason"] == "model_gone"
    assert "GROQ_MODEL" in body["message"]


def test_a_failed_call_is_never_charged_for(funded, dead_model, account):
    """The wallet check runs before the model call, and the debit after it, so
    a failure has to leave the balance alone."""
    import models

    with main.SessionLocal() as db:
        cid = db.query(models.DBClient).filter(
            models.DBClient.email == account["email"]).first().id
        before = main.get_wallet(db, cid).balance_minor

    ask(funded)

    with main.SessionLocal() as db:
        assert main.get_wallet(db, cid).balance_minor == before


# --- the status the page asks on load -----------------------------------------

def test_status_carries_the_last_reason(funded, dead_model):
    """A key being set is not the same as the AI working, and a retired model
    is invisible to a check that only looks for a key."""
    ask(funded)
    body = funded.get("/api/ai/status").json()
    assert body["configured"] is True
    assert body["last_error"] == "model_gone"
    assert "GROQ_MODEL" in body["last_error_message"]


def test_status_is_quiet_when_nothing_has_failed(tenant, monkeypatch):
    monkeypatch.setattr(main, "llm_configured", lambda: True)
    llm.LAST_ERROR["reason"] = ""
    body = tenant.get("/api/ai/status").json()
    assert body["last_error"] == ""
    assert body["last_error_message"] == ""


def test_status_still_reports_a_missing_key_plainly(tenant, monkeypatch):
    monkeypatch.setattr(main, "llm_configured", lambda: False)
    llm.LAST_ERROR["reason"] = "no_key"
    body = tenant.get("/api/ai/status").json()
    assert body["configured"] is False
    assert body["message"]


def test_status_needs_a_session(client):
    assert client.get("/api/ai/status").status_code in (401, 403)


# --- every reason has something to say ----------------------------------------

def test_no_reason_falls_through_to_silence():
    for reason in ("no_key", "bad_key", "rate_limited", "timeout",
                   "network_error", "upstream_error", "model_gone"):
        llm.LAST_ERROR["reason"] = reason
        assert llm.llm_error_message(), reason


def test_an_unknown_reason_still_says_something():
    llm.LAST_ERROR["reason"] = "something_new"
    assert llm.llm_error_message()


def test_the_messages_are_distinct():
    """Six reasons sharing one sentence is how this went unnoticed."""
    seen = set()
    for reason in ("no_key", "bad_key", "rate_limited", "timeout",
                   "network_error", "upstream_error", "model_gone"):
        llm.LAST_ERROR["reason"] = reason
        seen.add(llm.llm_error_message())
    assert len(seen) == 7
