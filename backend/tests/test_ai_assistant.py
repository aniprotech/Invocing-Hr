"""The in-app assistant and the AI writing helpers.

The property that matters most: the assistant is grounded. It is given the
tenant's real figures and told to use only those, because an ungrounded model
pointed at business data will confidently invent balances and headcounts.
"""
import pytest

import main
from conftest import make_employee, make_invoice


@pytest.fixture
def superadmin(client):
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


# --- grounding --------------------------------------------------------------

def test_context_contains_the_tenants_real_figures(client, account):
    """Whatever the model does with it, the context it receives must be true."""
    tenant = account["client"]
    make_invoice(tenant, issue_date="2020-01-01", due_date="2020-01-31", status="Sent")
    make_employee(tenant, first_name="Nina", last_name="Patel")
    tenant.post("/api/departments", json={"name": "Engineering"})

    import database
    with database.SessionLocal() as db:
        cl = db.query(main.models.DBClient).filter(
            main.models.DBClient.email == account["email"]
        ).first()
        context = main.build_business_context(db, cl)

    assert "INVOICING" in context and "PEOPLE" in context and "RECRUITMENT" in context
    assert "Nina Patel" in context or "Employees: 1" in context
    assert "Outstanding:" in context
    assert "days overdue" in context, "an overdue invoice should be spelled out"


def test_context_is_scoped_to_one_tenant(client, account):
    """One company's numbers must never reach another company's assistant."""
    tenant = account["client"]
    make_employee(tenant, first_name="Secret", last_name="Person")

    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": "other-ai@example.com", "password": "Passw0rdTest"})
    client.post("/api/client/login", json={"email": "other-ai@example.com", "password": "Passw0rdTest"})

    import database
    with database.SessionLocal() as db:
        other = db.query(main.models.DBClient).filter(
            main.models.DBClient.email == "other-ai@example.com"
        ).first()
        context = main.build_business_context(db, other)
    assert "Secret Person" not in context
    assert "Employees: 0" in context


def test_assistant_answers_from_context(tenant, monkeypatch):
    seen = {}

    def fake(messages, **kwargs):
        seen["prompt"] = messages[-1]["content"]
        seen["system"] = messages[0]["content"]
        return "You are owed £1,440.00 across 1 overdue invoice."

    monkeypatch.setattr(main, "llm_chat", fake)
    res = tenant.post("/api/ai/assistant", json={"question": "How much am I owed?"})
    assert res.status_code == 200
    assert res.json()["available"] is True
    assert "CONTEXT:" in seen["prompt"], "the model must receive the real data"
    assert "ONLY the CONTEXT" in seen["system"], "and be told to use only that"


def test_assistant_degrades_when_the_model_is_down(tenant, monkeypatch):
    """A model that will not answer is not an error the caller has to handle -
    the question was valid and the app is working. So it comes back 200 with
    available false and something to read.

    What that something says is no longer fixed here. It used to be one
    sentence for all six failures, which is what made "an administrator needs
    to configure the AI key" the answer to a retired model. Which reason it was
    is checked in test_ai_says_why.
    """
    import llm

    monkeypatch.setattr(main, "llm_chat", lambda *a, **k: None)
    llm.LAST_ERROR["reason"] = "model_gone"

    res = tenant.post("/api/ai/assistant", json={"question": "How much am I owed?"})
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body["answer"].strip(), "silence is the one thing it must not do"
    llm.LAST_ERROR["reason"] = ""


@pytest.mark.parametrize("question,code", [
    ("", 400),
    ("x" * 600, 400),
])
def test_assistant_validates_the_question(tenant, question, code):
    assert tenant.post("/api/ai/assistant", json={"question": question}).status_code == code


def test_assistant_requires_a_session(client):
    client.post("/api/client/logout")
    assert client.post("/api/ai/assistant", json={"question": "hi"}).status_code == 401


# --- suggestions ------------------------------------------------------------

def test_suggestions_reflect_what_is_actually_happening(tenant):
    plain = tenant.get("/api/ai/suggestions").json()["suggestions"]
    assert "Summarise where the business stands today" in plain

    make_invoice(tenant, issue_date="2020-01-01", due_date="2020-01-31", status="Sent")
    with_overdue = tenant.get("/api/ai/suggestions").json()["suggestions"]
    assert any("overdue" in s.lower() for s in with_overdue)


# --- response shape tolerance ----------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("one line", "one line"),
    (["para one", "para two"], "para one\n\npara two"),
    (None, ""),
    ([], ""),
])
def test_as_text_accepts_string_or_list(value, expected):
    """The model returns multi-paragraph fields either way; dropping one shape
    silently produced an empty job advert."""
    assert main.as_text(value) == expected


@pytest.mark.parametrize("value,expected", [
    (["a", "b"], ["a", "b"]),
    ("- a\n- b", ["a", "b"]),
    (None, []),
])
def test_as_list_accepts_list_or_text(value, expected):
    assert main.as_list(value) == expected


def test_job_description_handles_a_list_description(tenant, monkeypatch):
    monkeypatch.setattr(main, "llm_json", lambda *a, **k: {
        "description": ["First paragraph.", "Second paragraph."],
        "requirements": ["Python", "SQL"],
    })
    res = tenant.post("/api/ai/job-description", json={"title": "Backend Engineer"})
    assert res.status_code == 200
    body = res.json()
    assert "First paragraph." in body["description"]
    assert "Second paragraph." in body["description"]
    assert body["requirements"] == ["Python", "SQL"]


def test_job_description_needs_a_title(tenant):
    assert tenant.post("/api/ai/job-description", json={}).status_code == 400


def test_interview_questions_normalise_bare_strings(tenant, monkeypatch):
    monkeypatch.setattr(main, "llm_json", lambda *a, **k: {
        "questions": ["Tell me about a hard bug.", {"question": "Why us?", "area": "role fit"}],
    })
    res = tenant.post("/api/ai/interview-questions", json={"job_title": "Engineer"})
    assert res.status_code == 200
    qs = res.json()["questions"]
    assert qs[0]["question"] == "Tell me about a hard bug."
    assert qs[1]["area"] == "role fit"


def test_describe_item_needs_input(tenant):
    assert tenant.post("/api/ai/describe-item", json={"text": "   "}).status_code == 400


def test_describe_item_strips_model_quoting(tenant, monkeypatch):
    monkeypatch.setattr(main, "llm_chat", lambda *a, **k: '"Website bug fixing over three days."')
    res = tenant.post("/api/ai/describe-item", json={"text": "fixed bugs 3 days"})
    assert res.json()["description"] == "Website bug fixing over three days."


# --- billing ----------------------------------------------------------------

def test_assistant_is_billed_only_on_a_real_answer(client, account, superadmin, monkeypatch):
    rows = superadmin.get("/api/superadmin/clients").json()
    cid = next(r["id"] for r in rows if r["email"] == account["email"])
    superadmin.post(f"/api/superadmin/wallets/{cid}/adjust",
                    json={"amount": 5, "reason": "seed"})
    rules = superadmin.get("/api/superadmin/pricing").json()
    rule = next(r for r in rules if r["action_key"] == "ai_assistant")
    superadmin.put(f"/api/superadmin/pricing/{rule['id']}",
                   json={"unit_price": 0.10, "free_allowance": 0})
    superadmin.post("/api/superadmin/logout")

    tenant = account["client"]
    tenant.post("/api/client/login", json={
        "email": account["email"], "password": account["password"],
    })

    monkeypatch.setattr(main, "llm_chat", lambda *a, **k: None)
    before = tenant.get("/api/wallet").json()["balance"]
    tenant.post("/api/ai/assistant", json={"question": "anything"})
    assert tenant.get("/api/wallet").json()["balance"] == before, "no answer, no charge"

    monkeypatch.setattr(main, "llm_chat", lambda *a, **k: "You have 3 employees.")
    tenant.post("/api/ai/assistant", json={"question": "how many staff?"})
    after = tenant.get("/api/wallet").json()["balance"]
    assert round(before - after, 2) == 0.10, "a real answer is billed"


def test_all_ai_actions_have_a_price(tenant):
    pricing = {p["action_key"] for p in tenant.get("/api/wallet").json()["pricing"]}
    for key in ("ai_assistant", "ai_insights", "ai_job_description",
                "ai_interview_questions", "ai_describe_item"):
        assert key in pricing, f"{key} would be silently free"
