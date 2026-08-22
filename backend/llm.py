import os
import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# The model is a setting, because hosted models get retired and two now have.
# Changing GROQ_MODEL in the environment is a restart; changing this constant is
# a deploy, and the difference matters when the AI is already down.
# available_models() lists what the key can actually use, so a replacement is
# picked from what exists rather than from what sounds current - which is how
# llama-3.3-70b-versatile came to be the default after it had been retired.
# This one was checked against the live API: a chat call and a JSON call, at the
# token budgets this app actually uses.
DEFAULT_MODEL = "openai/gpt-oss-120b"
MODEL = os.getenv("GROQ_MODEL", "").strip() or DEFAULT_MODEL


def available_models():
    """Model ids this key may use, newest listing first, or an empty list.

    Used by the operator page so a retired model can be replaced with one that
    exists rather than one that sounds right.
    """
    if not GROQ_API_KEY:
        return []
    try:
        resp = httpx.get(
            f"{GROQ_BASE_URL}/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        rows = resp.json().get("data", [])
        return sorted(
            [r.get("id", "") for r in rows if r.get("id")],
            key=lambda name: (not name.startswith("llama"), name))
    except Exception as exc:      # noqa: BLE001 - reported, never raised
        logger.warning("Could not list Groq models: %s", exc)
        return []


def llm_configured() -> bool:
    """Whether an API key is set at all.

    Callers use this to tell "nobody has configured this" apart from "the call
    failed", which used to look identical because both came back as None.
    """
    return bool(GROQ_API_KEY)


# Why the last call failed, for the endpoints to pass on. A single "AI
# unavailable" told the user nothing they could act on.
LAST_ERROR = {"reason": ""}


def llm_last_error() -> str:
    return LAST_ERROR["reason"]


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


def llm_chat(messages, temperature=0.3, max_tokens=1024):
    if not GROQ_API_KEY:
        LAST_ERROR["reason"] = "no_key"
        return None
    try:
        resp = httpx.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            timeout=30,
        )
        if resp.status_code == 200:
            LAST_ERROR["reason"] = ""
            answer = strip_reasoning(
                resp.json()["choices"][0]["message"]["content"])
            if not answer:
                # A 200 whose whole budget went on reasoning is a failure like
                # any other, and saying nothing is worse than saying why.
                LAST_ERROR["reason"] = "empty_answer"
                return None
            return answer
        body = (resp.text or "")[:400].lower()
        retired = (
            resp.status_code == 404
            or "decommission" in body or "deprecat" in body
            or "model_not_found" in body or "does not exist" in body
        )
        LAST_ERROR["reason"] = "model_gone" if retired else {
            401: "bad_key", 403: "bad_key", 429: "rate_limited",
        }.get(resp.status_code, "upstream_error")
        logger.error("Groq API error %d: %s", resp.status_code, resp.text[:200])
    except httpx.TimeoutException:
        LAST_ERROR["reason"] = "timeout"
        logger.error("Groq call timed out")
    except Exception as e:
        LAST_ERROR["reason"] = "network_error"
        logger.error("Groq call failed: %s", e)
    return None


# What to put in front of a person for each reason.
LLM_MESSAGES = {
    "no_key": "AI is not set up yet. Add a GROQ_API_KEY and it will switch on.",
    "bad_key": "The AI key was rejected. Check GROQ_API_KEY.",
    "rate_limited": "The AI is busy right now. Try again in a moment.",
    "timeout": "The AI took too long to answer. Try again.",
    "network_error": "Could not reach the AI service.",
    "upstream_error": "The AI service returned an error.",
    "empty_answer": ("The AI thought about it for too long and ran out of room "
                     "to answer. Try a shorter question."),
    "model_gone": ("The AI model this is set to no longer exists. Set GROQ_MODEL "
                   "to a current one - the AI status page lists what the key can use."),
}


def llm_error_message() -> str:
    return LLM_MESSAGES.get(LAST_ERROR["reason"], "The AI is unavailable right now.")


def llm_json(messages, temperature=0.2):
    text = llm_chat(messages, temperature=temperature, max_tokens=2048)
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
