"""The AI model is a setting, because hosted models get retired.

One already did, and every AI feature went down with it. Changing an
environment variable is a restart; changing a constant is a deploy, and the
difference matters when the thing is already broken.
"""
import importlib
import os

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


def reloaded(monkeypatch, value=None):
    """llm reads the environment at import, so reload it to change the model."""
    import llm
    if value is None:
        monkeypatch.delenv("GROQ_MODEL", raising=False)
    else:
        monkeypatch.setenv("GROQ_MODEL", value)
    return importlib.reload(llm)


# --- the setting --------------------------------------------------------------

def test_the_model_can_be_set_without_a_deploy(monkeypatch):
    llm = reloaded(monkeypatch, "some-newer-model")
    assert llm.MODEL == "some-newer-model"
    reloaded(monkeypatch)      # leave it as it was


def test_there_is_a_default_when_nothing_is_set(monkeypatch):
    llm = reloaded(monkeypatch)
    assert llm.MODEL == llm.DEFAULT_MODEL
    assert llm.MODEL, "something has to be asked for"


# Two have now been retired under this app. Both are named, because the second
# one became the default as the fix for the first.
RETIRED = ("llama-3.1-8b-instant", "llama-3.3-70b-versatile")


@pytest.mark.parametrize("gone", RETIRED)
def test_a_retired_model_is_not_the_default(monkeypatch, gone):
    """The whole point of this change, twice over."""
    llm = reloaded(monkeypatch)
    assert llm.DEFAULT_MODEL != gone


def test_blank_falls_back_rather_than_asking_for_nothing(monkeypatch):
    llm = reloaded(monkeypatch, "   ")
    assert llm.MODEL == llm.DEFAULT_MODEL
    reloaded(monkeypatch)


# --- saying which failure it was ----------------------------------------------

def test_a_retired_model_reads_as_a_retired_model():
    """A 404 from the model endpoint used to be reported as a generic upstream
    error, which tells an operator nothing they can act on."""
    import llm
    assert "model_gone" in llm.LLM_MESSAGES
    message = llm.LLM_MESSAGES["model_gone"]
    assert "GROQ_MODEL" in message, "it should name the thing to change"


# --- what the operator page shows ---------------------------------------------

def test_the_status_page_names_the_model(superadmin):
    body = superadmin.get("/api/superadmin/ai-status").json()
    assert body["model"]
    assert body["model_env_var"] == "GROQ_MODEL"
    assert "model_default" in body


def test_the_status_page_offers_the_alternatives(superadmin):
    """Without a key there is nothing to list, but the field must exist so the
    page can render the same either way."""
    body = superadmin.get("/api/superadmin/ai-status").json()
    assert isinstance(body["available_models"], list)


def test_the_status_page_is_superadmin_only(tenant):
    assert tenant.get("/api/superadmin/ai-status").status_code in (401, 403)


def test_listing_models_without_a_key_is_empty_not_an_error(monkeypatch):
    import llm
    monkeypatch.setattr(llm, "GROQ_API_KEY", "")
    assert llm.available_models() == []

# --- reasoning traces are not the answer --------------------------------------
# Everything Groq still offers is a reasoning model, and several wrap the answer
# in a <think> block. One of them put a trace straight into a chat reply while
# the replacement model was being chosen.

def test_a_reasoning_trace_is_not_shown_to_anybody():
    import llm
    assert llm.strip_reasoning(
        "<think>weighing it up</think>Two are overdue.") == "Two are overdue."


def test_the_tags_are_matched_whatever_they_are_called():
    import llm
    for tag in ("think", "thinking", "reasoning"):
        assert llm.strip_reasoning(f"<{tag}>x</{tag}>Answer.") == "Answer."


def test_the_case_of_the_tag_does_not_matter():
    import llm
    assert llm.strip_reasoning("<THINK>x</THINK> Answer.") == "Answer."


def test_an_answer_with_no_trace_is_left_alone():
    import llm
    for text in ("Two are overdue.", '{"ok": true}', ""):
        assert llm.strip_reasoning(text) == text.strip()


def test_a_trace_cut_off_by_the_token_budget_leaves_nothing():
    """No closing tag means the budget ran out mid-thought, so there is no
    answer after it to keep - and half a thought is not an answer."""
    import llm
    assert llm.strip_reasoning("<think>ran out of room mid-thou") == ""


def test_a_brace_inside_the_reasoning_does_not_become_the_json():
    """llm_json falls back to the first { it finds. Before stripping, that was
    whichever one the model mentioned while thinking."""
    import llm
    cleaned = llm.strip_reasoning(
        '<think>maybe {"wrong": 1} would do</think>{"right": 2}')
    assert cleaned == '{"right": 2}'


def test_thinking_the_whole_budget_away_is_reported_not_swallowed():
    """A 200 with nothing left to say is a failure like any other, and it used
    to come back as a silent None."""
    import llm
    assert "empty_answer" in llm.LLM_MESSAGES
    assert llm.LLM_MESSAGES["empty_answer"]
