"""Asking the cheapest thing that will answer.

Every AI feature went to one paid provider on one large model, and the same
question asked twice was paid for twice. Both are now handled inside llm.py so
that no call site had to change - which is convenient, and also means a mistake
here is invisible at every one of the thirteen places it is used. Hence these.

The rules worth holding down: free providers are asked first, a provider that
cannot answer is a reason to try the next rather than to fail, a paid provider
is only ever reached last, an identical question is not bought twice, and the
reason reported after everything has failed is the one an operator can act on.
"""
import json

import pytest
from fastapi.testclient import TestClient

import llm
import main


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Each test states its own chain, and leaves nothing behind.

    Provider keys are read from the environment at call time, so a stray one on
    the machine running the suite would otherwise join the chain and make these
    depend on who is running them.
    """
    for spec in llm.PROVIDERS:
        monkeypatch.delenv(spec["key_env"], raising=False)
        monkeypatch.delenv(spec.get("model_env", "x"), raising=False)
    monkeypatch.delenv("AI_PROVIDER_ORDER", raising=False)
    llm.cache_clear()
    llm.STATS.update({"calls": 0, "hits": 0, "by_provider": {}})
    yield
    llm.cache_clear()


class FakeResponse:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def answer(text):
    return FakeResponse(200, payload={"choices": [{"message": {"content": text}}]})


def record_calls(monkeypatch, responder):
    """Stand in for the network, and note who was asked, in order."""
    asked = []

    def fake_post(url, **kwargs):
        name = next((p["name"] for p in llm.PROVIDERS
                     if url.startswith(p["base_url"])), url)
        asked.append(name)
        return responder(name, kwargs)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    return asked


# --- The order ------------------------------------------------------------
def test_the_free_provider_is_asked_before_the_paid_one(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("OPENAI_API_KEY", "sk_paid")
    asked = record_calls(monkeypatch, lambda name, kw: answer("hello"))

    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "hello"
    assert asked == ["groq"], "the paid provider was reached with a free one working"


def test_a_paid_provider_is_only_reached_when_the_free_ones_cannot_answer(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")
    monkeypatch.setenv("OPENAI_API_KEY", "sk_paid")

    def responder(name, kw):
        if name == "openai":
            return answer("paid answer")
        return FakeResponse(429, text="rate limit exceeded")

    asked = record_calls(monkeypatch, responder)
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "paid answer"
    assert asked == ["groq", "cerebras", "openai"]


def test_being_out_of_quota_moves_on_rather_than_failing(monkeypatch):
    """The whole point of a free tier first: running out is normal, not fatal."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")

    def responder(name, kw):
        return FakeResponse(429, text="rate limit") if name == "groq" \
            else answer("second in line")

    record_calls(monkeypatch, responder)
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "second in line"
    assert llm.llm_last_provider() == "cerebras"


def test_a_retired_model_moves_on_too(monkeypatch):
    """This one took the AI down completely before there was a chain."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")

    def responder(name, kw):
        return FakeResponse(404, text="model has been decommissioned") \
            if name == "groq" else answer("still here")

    record_calls(monkeypatch, responder)
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "still here"


def test_only_providers_with_a_key_are_asked(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")
    asked = record_calls(monkeypatch, lambda name, kw: answer("ok"))
    llm.llm_chat([{"role": "user", "content": "hi"}])
    assert asked == ["cerebras"]


def test_the_order_can_be_overridden(monkeypatch):
    """For somebody whose quotas make the built-in order wrong."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "cerebras,groq")

    asked = record_calls(monkeypatch, lambda name, kw: answer("ok"))
    llm.llm_chat([{"role": "user", "content": "hi"}])
    assert asked == ["cerebras"]


def test_an_unknown_name_in_the_order_is_ignored_not_fatal(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "nonesuch,groq")
    record_calls(monkeypatch, lambda name, kw: answer("ok"))
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "ok"


def test_a_configured_provider_left_out_of_the_order_still_gets_a_turn(monkeypatch):
    """Naming one provider must not silently disable the rest."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")
    monkeypatch.setenv("AI_PROVIDER_ORDER", "cerebras")

    def responder(name, kw):
        return FakeResponse(500, text="boom") if name == "cerebras" \
            else answer("groq still asked")

    asked = record_calls(monkeypatch, responder)
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "groq still asked"
    assert asked == ["cerebras", "groq"]


# --- The cache ------------------------------------------------------------
def test_the_same_question_is_not_bought_twice(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    asked = record_calls(monkeypatch, lambda name, kw: answer("cached answer"))

    msgs = [{"role": "user", "content": "what is my outstanding total?"}]
    first = llm.llm_chat(msgs)
    second = llm.llm_chat(msgs)

    assert first == second == "cached answer"
    assert len(asked) == 1, "the second identical question went to the network"
    assert llm.cache_stats()["hits"] == 1


def test_a_different_question_is_a_different_answer(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    asked = record_calls(monkeypatch, lambda name, kw: answer("x"))

    llm.llm_chat([{"role": "user", "content": "one"}])
    llm.llm_chat([{"role": "user", "content": "two"}])
    assert len(asked) == 2


def test_the_settings_are_part_of_the_key(monkeypatch):
    """Same words, different temperature, is a different request."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    asked = record_calls(monkeypatch, lambda name, kw: answer("x"))

    msgs = [{"role": "user", "content": "same"}]
    llm.llm_chat(msgs, temperature=0.1)
    llm.llm_chat(msgs, temperature=0.9)
    assert len(asked) == 2


def test_a_failure_is_never_cached(monkeypatch):
    """Otherwise one bad minute is an hour of not trying."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    state = {"fail": True}

    def responder(name, kw):
        return FakeResponse(500, text="boom") if state["fail"] else answer("recovered")

    asked = record_calls(monkeypatch, responder)
    msgs = [{"role": "user", "content": "hi"}]
    assert llm.llm_chat(msgs) is None
    state["fail"] = False
    assert llm.llm_chat(msgs) == "recovered"
    assert len(asked) == 2


def test_a_caller_can_opt_out(monkeypatch):
    """The status probe does, or it would report a chain that had since died."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    asked = record_calls(monkeypatch, lambda name, kw: answer("pong"))

    msgs = [{"role": "user", "content": "ping"}]
    llm.llm_chat(msgs, use_cache=False)
    llm.llm_chat(msgs, use_cache=False)
    assert len(asked) == 2


def test_the_cache_does_not_grow_without_end(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setattr(llm, "CACHE_MAX", 5)
    record_calls(monkeypatch, lambda name, kw: answer("x"))
    for i in range(25):
        llm.llm_chat([{"role": "user", "content": f"q{i}"}])
    assert llm.cache_stats()["entries"] <= 5


def test_an_expired_entry_is_asked_again(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setattr(llm, "CACHE_TTL", 60)
    asked = record_calls(monkeypatch, lambda name, kw: answer("x"))

    msgs = [{"role": "user", "content": "hi"}]
    llm.llm_chat(msgs)
    # Push what is stored back beyond the window rather than sleeping.
    key = next(iter(llm._cache))
    value, _ = llm._cache[key]
    llm._cache[key] = (value, 0)
    llm.llm_chat(msgs)
    assert len(asked) == 2


# --- What is reported when it all fails ------------------------------------
def test_with_no_keys_at_all_it_says_so(monkeypatch):
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) is None
    assert llm.llm_last_error() == "no_key"
    assert not llm.llm_configured()


def test_the_reported_reason_is_the_actionable_one(monkeypatch):
    """A rejected key is something to go and fix; a 500 elsewhere is not."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_bad")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")

    def responder(name, kw):
        return FakeResponse(401, text="invalid api key") if name == "groq" \
            else FakeResponse(500, text="boom")

    record_calls(monkeypatch, responder)
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) is None
    assert llm.llm_last_error() == "bad_key"
    assert "key" in llm.llm_error_message().lower()


def test_a_provider_that_answers_with_nothing_is_a_failure(monkeypatch):
    """A 200 whose whole budget went on reasoning used to read as success."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")

    def responder(name, kw):
        return answer("<think>still going") if name == "groq" else answer("a real answer")

    record_calls(monkeypatch, responder)
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "a real answer"


def test_a_local_model_needs_no_key_but_must_be_opted_into(monkeypatch):
    asked = record_calls(monkeypatch, lambda name, kw: answer("local"))
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) is None

    monkeypatch.setenv("OLLAMA_ENABLED", "true")
    assert llm.llm_chat([{"role": "user", "content": "hi"}]) == "local"
    assert asked == ["ollama"]


def test_the_authorization_header_is_the_right_key_for_each_provider(monkeypatch):
    """Sending Groq's key to Cerebras would fail in a way that reads as quota."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_one")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_two")
    seen = {}

    def responder(name, kw):
        seen[name] = kw["headers"].get("Authorization")
        return FakeResponse(500, text="boom") if name == "groq" else answer("ok")

    record_calls(monkeypatch, responder)
    llm.llm_chat([{"role": "user", "content": "hi"}])
    assert seen["groq"] == "Bearer gsk_one"
    assert seen["cerebras"] == "Bearer csk_two"


def test_each_provider_is_asked_for_its_own_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_one")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_two")
    seen = {}

    def responder(name, kw):
        seen[name] = kw["json"]["model"]
        return FakeResponse(500, text="boom") if name == "groq" else answer("ok")

    record_calls(monkeypatch, responder)
    llm.llm_chat([{"role": "user", "content": "hi"}])
    assert seen["groq"] == llm.PROVIDERS_BY_NAME["groq"]["default_model"]
    assert seen["cerebras"] == llm.PROVIDERS_BY_NAME["cerebras"]["default_model"]


def test_json_answers_go_through_the_same_chain(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("CEREBRAS_API_KEY", "csk_free")

    def responder(name, kw):
        return FakeResponse(429, text="busy") if name == "groq" \
            else answer(json.dumps({"score": 7}))

    record_calls(monkeypatch, responder)
    assert llm.llm_json([{"role": "user", "content": "rate this"}]) == {"score": 7}


def test_the_free_tier_is_the_default_arrangement():
    """If the built-in order ever put a billed provider first, every install
    that had not thought about it would start paying."""
    names = [p["name"] for p in llm.PROVIDERS]
    first_paid = next(i for i, p in enumerate(llm.PROVIDERS) if not p["free"])
    assert all(llm.PROVIDERS[i]["free"] for i in range(first_paid)), names


# --- What the operator is shown -------------------------------------------
# The panel used to say "is the key good". With a chain the useful questions
# are which links are live, which one did the work, and what the cache saved.

@pytest.fixture
def operator():
    """The operator in a session of its own.

    It used to sign in on the same TestClient a tenant was using, so one
    session held both identities at once. Signing in now starts a fresh
    session - which is the point of it - so sharing a client would simply
    log the tenant out. In production these are two different sign-ins
    anyway, and a browser that is both a customer and the platform operator
    is the privilege mixing that clearing exists to prevent.
    """
    with TestClient(main.app) as own:
        res = own.post("/api/superadmin/login", json={
            "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
        assert res.status_code == 200, res.text
        yield own


def test_the_status_page_lists_the_whole_chain(operator, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("OPENAI_API_KEY", "sk_paid")
    monkeypatch.setattr(llm.httpx, "post",
                        lambda url, **kw: answer("pong"))
    monkeypatch.setattr(llm.httpx, "get",
                        lambda *a, **k: FakeResponse(200, payload={"data": []}))

    d = operator.get("/api/superadmin/ai-status").json()

    listed = {p["name"] for p in d["providers"]}
    assert listed == {p["name"] for p in llm.PROVIDERS}, \
        "a provider missing from the panel is one nobody knows they could add"

    # Position is what says who is asked first, and it has to agree with what
    # the chain will actually do.
    ordered = [p["name"] for p in sorted(
        [p for p in d["providers"] if p["position"]], key=lambda p: p["position"])]
    assert ordered == d["free_first"] == ["groq", "openai"]


def test_the_status_page_says_which_provider_answered(operator, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setenv("OPENAI_API_KEY", "sk_paid")

    def responder(url, **kw):
        if url.startswith(llm.PROVIDERS_BY_NAME["groq"]["base_url"]):
            return FakeResponse(429, text="busy")
        return answer("paid pong")

    monkeypatch.setattr(llm.httpx, "post", responder)
    monkeypatch.setattr(llm.httpx, "get",
                        lambda *a, **k: FakeResponse(200, payload={"data": []}))

    d = operator.get("/api/superadmin/ai-status").json()
    assert d["reachable"] is True
    assert d["answered_by"] == "openai"
    assert "openai" in d["detail"]


def test_the_status_probe_is_never_answered_from_cache(operator, monkeypatch):
    """A cached probe would report the chain healthy long after it had died."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    monkeypatch.setattr(llm.httpx, "get",
                        lambda *a, **k: FakeResponse(200, payload={"data": []}))

    calls = []

    def responder(url, **kw):
        calls.append(url)
        return answer("pong")

    monkeypatch.setattr(llm.httpx, "post", responder)
    operator.get("/api/superadmin/ai-status")
    operator.get("/api/superadmin/ai-status")
    assert len(calls) == 2


def test_the_status_page_never_shows_a_key(operator, monkeypatch):
    """It reports on keys, which is exactly when one gets printed by accident."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_hunter2_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk_also_secret")
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: answer("pong"))
    monkeypatch.setattr(llm.httpx, "get",
                        lambda *a, **k: FakeResponse(200, payload={"data": []}))

    body = operator.get("/api/superadmin/ai-status").text
    assert "hunter2" not in body
    assert "also_secret" not in body


def test_the_status_page_is_the_operators_alone(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_free")
    assert client.get("/api/superadmin/ai-status").status_code in (401, 403)
