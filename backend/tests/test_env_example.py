"""The setup file has to stay true.

.env.example is the only place that says what this app needs to run. Nothing
enforced that, so it would have been accurate on the day it was written and
wrong by the next feature - which is worse than having no file, because
somebody setting up an environment would trust it and then debug a missing
variable that was never mentioned.

So it is checked against the code rather than maintained by memory: every
variable the backend reads is named here, and nothing is named that the
backend does not read.
"""
import pathlib
import re

import pytest

import llm

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / ".env.example"


def documented():
    """Names on the left of an = in .env.example, ignoring comments."""
    names = set()
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.add(line.partition("=")[0].strip())
    return names


def read_by_the_code():
    """Every variable the backend actually looks up.

    Three ways it does that: os.getenv, the _env_key helper the payment
    gateways use, and the provider table in llm.py, which builds its names
    from data rather than writing them out.
    """
    names = set()
    for path in (ROOT / "backend").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        names |= set(re.findall(r"os\.getenv\(\s*[\"']([A-Z0-9_]+)", src))
        names |= set(re.findall(r"_env_key\(\s*[\"']([A-Z0-9_]+)", src))

    for spec in llm.PROVIDERS:
        names.add(spec["key_env"])
        if spec.get("model_env"):
            names.add(spec["model_env"])
    return names


def test_the_setup_file_exists():
    assert EXAMPLE.exists(), "the only description of what this app needs to run"


def test_every_variable_the_code_reads_is_written_down():
    """A variable nobody documented is one somebody has to find by reading
    gateway_config() at the point they most need the app working."""
    missing = read_by_the_code() - documented()
    assert not missing, (
        "read by the backend but absent from .env.example: "
        + ", ".join(sorted(missing)))


def test_nothing_is_written_down_that_the_code_ignores():
    """A name that does nothing is worse than no name: somebody sets it, the
    behaviour does not change, and they go looking for the bug elsewhere."""
    stale = documented() - read_by_the_code()
    assert not stale, (
        "named in .env.example but read by nothing: " + ", ".join(sorted(stale)))


def test_no_value_is_filled_in():
    """It is copied to .env and committed to git. A real key in here is a
    leaked key, and a plausible-looking placeholder gets deployed as one."""
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        if not any(word in name for word in
                   ("KEY", "SECRET", "TOKEN", "PASSWORD", "CLIENT_ID")):
            continue          # defaults like PORT=8000 are settings, not secrets
        assert not value.strip(), f"{name} has a value in .env.example"


@pytest.mark.parametrize("name", [
    "GOCARDLESS_ACCESS_TOKEN", "GOCARDLESS_WEBHOOK_SECRET",
    "GOCARDLESS_ENVIRONMENT",
])
def test_the_gateway_that_takes_the_money_is_covered(name):
    """GoCardless is the only way a tenant can pay, and none of these three
    was mentioned anywhere before this file."""
    assert name in documented()


def test_the_free_ai_providers_are_all_offered():
    """The chain is only cheap if somebody knows the free keys exist to add."""
    for spec in llm.PROVIDERS:
        if spec["free"]:
            assert spec["key_env"] in documented(), spec["name"]
