"""Talking to a model, cheaply.

Every AI feature went to one paid provider on one large model, and the same
question asked twice was paid for twice. Two changes here, and neither touches
a single call site - llm_chat and llm_json keep their signatures:

  Free first. Providers are tried in order, cheapest to dearest, and the first
  one that answers wins. Only those with a key set are tried at all, so this is
  configuration rather than a code change: add a key and that provider joins
  the chain; remove it and the chain closes over the gap. A paid provider is
  the last resort rather than the only one.

  Ask once. Identical requests are answered from a short-lived cache. The key
  is a hash of the exact messages and settings, so a hit means the input was
  the same in every character and the answer would have been bought twice.

Everything here speaks the OpenAI chat-completions shape, which is why one code
path covers all of them.
"""
import hashlib
import json
import logging
import os
import re
import threading
import time

import httpx

logger = logging.getLogger(__name__)


# --- Who we ask, and in what order -----------------------------------------
# Ordered deliberately: free tiers first, then paid. Within the free tier the
# faster ones come first, because the whole chain sits in front of a user
# waiting for an answer.
#
# `free` is about what the provider charges on its own free tier, not a promise
# - a provider that starts billing is still one key removal away from being cut
# out of the chain.
PROVIDERS = [
    {
        "name": "groq",
        "label": "Groq",
        "key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "model_env": "GROQ_MODEL",
        "default_model": "openai/gpt-oss-120b",
        "free": True,
        "key_hint": "Groq keys begin with gsk_ and are issued at console.groq.com/keys",
    },
    {
        "name": "cerebras",
        "label": "Cerebras",
        "key_env": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
        "model_env": "CEREBRAS_MODEL",
        "default_model": "llama-3.3-70b",
        "free": True,
        "key_hint": "Issued at cloud.cerebras.ai",
    },
    {
        "name": "openrouter",
        "label": "OpenRouter",
        "key_env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "model_env": "OPENROUTER_MODEL",
        # OpenRouter marks its no-cost models with a :free suffix. Naming one
        # explicitly keeps a default from quietly becoming a billed model.
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "free": True,
        "key_hint": "Issued at openrouter.ai/keys. Models ending :free cost nothing.",
    },
    {
        "name": "gemini",
        "label": "Google Gemini",
        "key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-2.0-flash",
        "free": True,
        "key_hint": "Issued at aistudio.google.com/apikey. Has a free tier.",
    },
    {
        "name": "ollama",
        "label": "Ollama (local)",
        # Local, so there is no key to check - its presence is the base URL
        # being set, which is why this one is opted into explicitly.
        "key_env": "OLLAMA_ENABLED",
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "model_env": "OLLAMA_MODEL",
        "default_model": "llama3.1",
        "free": True,
        "needs_no_key": True,
        "key_hint": "Set OLLAMA_ENABLED=true to use a model running on this host.",
    },
    {
        "name": "openai",
        "label": "OpenAI",
        "key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "free": False,
        "key_hint": "Billed per token. Only reached when every free provider above has failed.",
    },
]

PROVIDERS_BY_NAME = {p["name"]: p for p in PROVIDERS}


def provider_key(spec) -> str:
    return os.getenv(spec["key_env"], "").strip()


def provider_configured(spec) -> bool:
    raw = provider_key(spec)
    if spec.get("needs_no_key"):
        return raw.lower() in ("1", "true", "yes", "on")
    return bool(raw)


def provider_model(spec) -> str:
    return os.getenv(spec.get("model_env", ""), "").strip() or spec["default_model"]


def active_providers():
    """The chain as it stands, in the order it will be tried.

    Order can be overridden with AI_PROVIDER_ORDER - a comma-separated list of
    names - for the case where the built-in order is wrong for somebody's
    quotas. Names it does not know are ignored rather than fatal, and a
    provider left out of the list still gets a turn after the named ones:
    naming one must not silently switch the others off.
    """
    configured = [p for p in PROVIDERS if provider_configured(p)]

    raw = os.getenv("AI_PROVIDER_ORDER", "").strip()
    if not raw:
        return configured

    wanted = [n.strip().lower() for n in raw.split(",") if n.strip()]
    ranked = [p for n in wanted for p in configured if p["name"] == n]
    return ranked + [p for p in configured if p not in ranked]


# --- Kept for the callers that still name Groq directly ---------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = PROVIDERS_BY_NAME["groq"]["base_url"]
DEFAULT_MODEL = PROVIDERS_BY_NAME["groq"]["default_model"]
MODEL = os.getenv("GROQ_MODEL", "").strip() or DEFAULT_MODEL


def llm_configured() -> bool:
    """Whether anything at all can answer.

    Callers use this to tell "nobody has configured this" apart from "the call
    failed", which used to look identical because both came back as None.
    """
    return bool(active_providers())


# --- The cache --------------------------------------------------------------
# The same question asked twice was answered twice and billed twice. The key is
# a digest of the exact request, so a hit means every character of the input
# matched and the second answer would have been bought for nothing.
#
# In process and not shared between workers: a warm cache per worker is most of
# the saving, and a shared one would be a database round-trip to avoid an API
# call the free tier was going to serve anyway.
CACHE_TTL = int(os.getenv("AI_CACHE_TTL", "3600"))       # seconds; 0 disables
CACHE_MAX = int(os.getenv("AI_CACHE_MAX", "500"))        # entries

_cache = {}
_cache_lock = threading.Lock()
STATS = {"calls": 0, "hits": 0, "by_provider": {}}


def _cache_key(messages, temperature, max_tokens):
    payload = json.dumps(
        {"m": messages, "t": temperature, "n": max_tokens},
        sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_get(key):
    if CACHE_TTL <= 0:
        return None
    with _cache_lock:
        hit = _cache.get(key)
        if not hit:
            return None
        value, stored_at = hit
        if time.time() - stored_at > CACHE_TTL:
            _cache.pop(key, None)
            return None
        return value


def _cache_put(key, value):
    if CACHE_TTL <= 0 or not value:
        return
    with _cache_lock:
        if len(_cache) >= CACHE_MAX:
            # Oldest out. Cheap, and a wrong eviction costs one API call.
            oldest = min(_cache, key=lambda k: _cache[k][1])
            _cache.pop(oldest, None)
        _cache[key] = (value, time.time())


def cache_clear():
    with _cache_lock:
        _cache.clear()


def cache_stats():
    with _cache_lock:
        size = len(_cache)
    calls = STATS["calls"]
    return {
        "entries": size,
        "calls": calls,
        "hits": STATS["hits"],
        "hit_rate": round(STATS["hits"] / calls, 3) if calls else 0.0,
        "by_provider": dict(STATS["by_provider"]),
        "ttl_seconds": CACHE_TTL,
    }


# --- Errors -----------------------------------------------------------------
# Why the last call failed, for the endpoints to pass on. A single "AI
# unavailable" told the user nothing they could act on.
LAST_ERROR = {"reason": ""}
LAST_PROVIDER = {"name": ""}


def llm_last_error() -> str:
    return LAST_ERROR["reason"]


def llm_last_provider() -> str:
    """Which provider answered, or tried last. Shown on the status page so an
    operator can see the free tier doing the work."""
    return LAST_PROVIDER["name"]


# Everything Groq still offers is a reasoning model, and several wrap the
# answer in a <think> block. Left in, it reaches the customer - one of them put
# a reasoning trace straight into a chat reply in testing - and it breaks the
# JSON parse, because the first { the parser meets is inside the reasoning
# rather than in the answer.
THINK_BLOCK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>",
                         re.DOTALL | re.IGNORECASE)
# An unclosed one means the token budget ran out mid-thought; there is no answer
# after it to keep.
OPEN_THINK = re.compile(r"<(think|thinking|reasoning)>.*\Z",
                        re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    return OPEN_THINK.sub("", THINK_BLOCK.sub("", text or "")).strip()


def available_models(provider="groq"):
    """Model ids a provider's key may use, or an empty list.

    Used by the operator page so a retired model can be replaced with one that
    exists rather than one that sounds right - which is how a default came to
    name a model that had already been decommissioned.
    """
    spec = PROVIDERS_BY_NAME.get(provider)
    if not spec or not provider_configured(spec):
        return []
    try:
        headers = {}
        if not spec.get("needs_no_key"):
            headers["Authorization"] = f"Bearer {provider_key(spec)}"
        resp = httpx.get(f"{spec['base_url']}/models", headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        rows = resp.json().get("data", [])
        return sorted([r.get("id", "") for r in rows if r.get("id")],
                      key=lambda name: (not name.startswith("llama"), name))
    except Exception as exc:      # noqa: BLE001 - reported, never raised
        logger.warning("Could not list %s models: %s", provider, exc)
        return []


# Ranked least to most actionable, so the reason reported after every provider
# has failed is the one worth acting on rather than whichever happened to be
# last in the chain.
REASON_RANK = ["upstream_error", "network_error", "timeout", "rate_limited",
               "empty_answer", "model_gone", "bad_key", "no_key"]


def _ask(spec, messages, temperature, max_tokens):
    """One provider. Returns (answer, reason); exactly one is set."""
    headers = {"Content-Type": "application/json"}
    if not spec.get("needs_no_key"):
        headers["Authorization"] = f"Bearer {provider_key(spec)}"

    try:
        resp = httpx.post(
            f"{spec['base_url']}/chat/completions",
            headers=headers,
            json={"model": provider_model(spec), "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=30,
        )
    except httpx.TimeoutException:
        logger.error("%s call timed out", spec["name"])
        return None, "timeout"
    except Exception as e:        # noqa: BLE001
        logger.error("%s call failed: %s", spec["name"], e)
        return None, "network_error"

    if resp.status_code == 200:
        try:
            answer = strip_reasoning(
                resp.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, ValueError, TypeError):
            logger.error("%s returned an unexpected shape", spec["name"])
            return None, "upstream_error"
        if not answer:
            # A 200 whose whole budget went on reasoning is a failure like any
            # other, and saying nothing is worse than saying why.
            return None, "empty_answer"
        return answer, ""

    body = (resp.text or "")[:400].lower()
    retired = (resp.status_code == 404
               or "decommission" in body or "deprecat" in body
               or "model_not_found" in body or "does not exist" in body)
    reason = "model_gone" if retired else {
        401: "bad_key", 403: "bad_key", 429: "rate_limited",
    }.get(resp.status_code, "upstream_error")
    logger.error("%s API error %d: %s", spec["name"], resp.status_code,
                 resp.text[:200])
    return None, reason


def llm_chat(messages, temperature=0.3, max_tokens=1024, use_cache=True):
    """Ask the chain, cheapest first, and return the first real answer.

    A provider that is rate limited, out of quota, or serving a retired model
    is a reason to try the next one rather than to fail - which is the whole
    point of a free tier being first.
    """
    providers = active_providers()
    if not providers:
        LAST_ERROR["reason"] = "no_key"
        LAST_PROVIDER["name"] = ""
        return None

    key = _cache_key(messages, temperature, max_tokens) if use_cache else None
    if key:
        cached = _cache_get(key)
        if cached is not None:
            STATS["calls"] += 1
            STATS["hits"] += 1
            LAST_ERROR["reason"] = ""
            LAST_PROVIDER["name"] = "cache"
            return cached

    STATS["calls"] += 1
    reasons = []
    for spec in providers:
        answer, reason = _ask(spec, messages, temperature, max_tokens)
        if answer:
            LAST_ERROR["reason"] = ""
            LAST_PROVIDER["name"] = spec["name"]
            STATS["by_provider"][spec["name"]] = \
                STATS["by_provider"].get(spec["name"], 0) + 1
            if key:
                _cache_put(key, answer)
            return answer
        reasons.append(reason)
        logger.info("%s could not answer (%s); trying the next provider",
                    spec["name"], reason)

    # Everything failed. Report the reason an operator can act on. A failure is
    # deliberately never cached: one bad minute would otherwise be an hour of
    # not trying.
    LAST_ERROR["reason"] = max(
        reasons, key=lambda r: REASON_RANK.index(r) if r in REASON_RANK else -1)
    LAST_PROVIDER["name"] = providers[-1]["name"]
    return None


# What to put in front of a person for each reason.
LLM_MESSAGES = {
    "no_key": "AI is not set up yet. Add a key for any provider and it will switch on.",
    "bad_key": "An AI key was rejected. Check the keys on the AI status page.",
    "rate_limited": "Every AI provider is busy or out of quota right now. Try again in a moment.",
    "timeout": "The AI took too long to answer. Try again.",
    "network_error": "Could not reach any AI service.",
    "upstream_error": "Every AI provider returned an error.",
    "empty_answer": ("The AI thought about it for too long and ran out of room "
                     "to answer. Try a shorter question."),
    "model_gone": ("The AI model this is set to no longer exists. The AI status "
                   "page lists what each key can actually use."),
}


def llm_error_message() -> str:
    return LLM_MESSAGES.get(LAST_ERROR["reason"], "The AI is unavailable right now.")


def llm_json(messages, temperature=0.2, use_cache=True):
    text = llm_chat(messages, temperature=temperature, max_tokens=2048,
                    use_cache=use_cache)
    if not text:
        return None
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())
    except json.JSONDecodeError:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            logger.error("Failed to parse LLM JSON: %s", text[:200])
            return None
