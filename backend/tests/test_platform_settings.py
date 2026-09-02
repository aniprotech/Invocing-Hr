"""What the operator can change without a deploy.

The pattern already existed - collection mode is a settings row with a null
client_id - but everything else operational was an environment variable,
which makes an operator's decision into a developer's deploy.

The rules worth holding down are the ones that are easy to get wrong: what
wins when a value is set in two places, that a bad value cannot be stored,
that a half-applied theme is impossible, and that secrets are not exposed
just because a settings page exists.
"""
import pytest

from fastapi.testclient import TestClient

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture(autouse=True)
def _leave_no_settings_behind():
    """These write platform-wide rows, and the suite shares one database.

    Without this, setting a top-up floor here made a later test in another
    module fail its own amount validation before reaching the thing it was
    actually checking - which is exactly the sort of failure that gets blamed
    on the wrong file.
    """
    yield
    with main.SessionLocal() as db:
        db.query(models.DBSettings).filter(
            models.DBSettings.client_id == None,        # noqa: E711
            models.DBSettings.key.in_(list(main.SETTINGS_BY_KEY)),
        ).delete(synchronize_session=False)
        db.commit()


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


def get_all(operator):
    res = operator.get("/api/superadmin/platform-settings")
    assert res.status_code == 200, res.text
    return {s["key"]: s for s in res.json()["settings"]}


# --- who may touch it -------------------------------------------------------

def test_a_stranger_cannot_read_the_settings(client):
    assert client.get("/api/superadmin/platform-settings").status_code == 401


def test_a_tenant_cannot_change_the_platform(tenant):
    res = tenant.put("/api/superadmin/platform-settings",
                     json={"settings": {"theme.primary": "#ff0000"}})
    assert res.status_code == 401


def test_no_secret_is_offered(operator):
    """A value that can be read out of a web page leaks with the page. Keys
    and the session secret stay in the environment."""
    keys = " ".join(get_all(operator)).lower()
    for secret in ("secret", "api_key", "token", "password", "database"):
        assert secret not in keys, f"{secret} is exposed in the settings"


# --- what wins --------------------------------------------------------------

def test_the_built_in_default_applies_when_nothing_is_set(operator):
    assert get_all(operator)["billing.topup_min"]["value"] == "5"


def test_an_environment_variable_is_inherited(operator, monkeypatch):
    """Existing deployments keep what their environment says until somebody
    changes it here, so upgrading does not move anything."""
    monkeypatch.setenv("TOPUP_MIN", "12")
    row = get_all(operator)["billing.topup_min"]
    assert row["value"] == "12"
    assert row["from_env"] is True
    assert row["is_set"] is False


def test_a_stored_value_beats_the_environment(operator, monkeypatch):
    monkeypatch.setenv("TOPUP_MIN", "12")
    operator.put("/api/superadmin/platform-settings",
                 json={"settings": {"billing.topup_min": "20"}})
    row = get_all(operator)["billing.topup_min"]
    assert row["value"] == "20"
    assert row["is_set"] is True


def test_resetting_gives_the_inherited_value_back(operator, monkeypatch):
    monkeypatch.setenv("TOPUP_MIN", "12")
    operator.put("/api/superadmin/platform-settings",
                 json={"settings": {"billing.topup_min": "20"}})
    res = operator.post("/api/superadmin/platform-settings/reset",
                        json={"keys": ["billing.topup_min"]})
    assert res.status_code == 200
    assert res.json()["now"]["billing.topup_min"] == "12"


# --- what may be stored -----------------------------------------------------

def test_a_colour_must_be_a_colour(operator):
    """This one is written into a style property, so anything else here is an
    injection rather than a typo."""
    for bad in ("red", "#fff", "javascript:alert(1)", "#12345g", "'; --"):
        res = operator.put("/api/superadmin/platform-settings",
                           json={"settings": {"theme.primary": bad}})
        assert res.status_code == 400, f"{bad!r} was accepted"


def test_a_good_colour_is_stored(operator):
    res = operator.put("/api/superadmin/platform-settings",
                       json={"settings": {"theme.primary": "#1A2B3C"}})
    assert res.status_code == 200
    assert res.json()["changed"]["theme.primary"] == "#1a2b3c"


def test_a_number_is_kept_inside_its_bounds(operator):
    assert operator.put("/api/superadmin/platform-settings",
                        json={"settings": {"theme.radius": "500"}}).status_code == 400
    assert operator.put("/api/superadmin/platform-settings",
                        json={"settings": {"theme.radius": "-4"}}).status_code == 400
    assert operator.put("/api/superadmin/platform-settings",
                        json={"settings": {"theme.radius": "8"}}).status_code == 200


def test_an_unknown_setting_is_refused(operator):
    res = operator.put("/api/superadmin/platform-settings",
                       json={"settings": {"theme.nonsense": "#000000"}})
    assert res.status_code == 404


def test_nothing_is_written_when_any_value_is_bad(operator):
    """A half-applied theme is worse than none, so one bad colour rejects the
    whole save rather than leaving the product half-changed."""
    before = get_all(operator)["theme.background"]["value"]
    res = operator.put("/api/superadmin/platform-settings", json={"settings": {
        "theme.background": "#101010",     # fine
        "theme.primary": "not-a-colour",   # not
    }})
    assert res.status_code == 400
    assert get_all(operator)["theme.background"]["value"] == before


# --- the theme reaches the page --------------------------------------------

def test_the_theme_is_readable_without_signing_in(client, operator):
    """The sign-in pages need the colours before anybody has a session."""
    operator.put("/api/superadmin/platform-settings",
                 json={"settings": {"theme.primary": "#123456"}})
    body = client.get("/api/platform/theme").json()["theme"]
    assert body["primary"] == "#123456"


def test_the_public_theme_carries_nothing_but_the_theme(client):
    body = client.get("/api/platform/theme").json()["theme"]
    for key in body:
        assert "billing" not in key and "policy" not in key and "ai" not in key


# --- a setting that does something ------------------------------------------

def test_the_topup_floor_is_enforced_from_the_setting(tenant, operator):
    operator.put("/api/superadmin/platform-settings",
                 json={"settings": {"billing.topup_min": "50"}})
    res = tenant.post("/api/wallet/topup",
                      json={"amount": 20, "provider": "gocardless"})
    assert res.status_code == 400
    assert "50" in res.json()["detail"]


def test_turning_ai_off_stops_it_before_the_wallet_is_touched(tenant, operator):
    """Withdrawing a feature must not bill anybody for it, and must not need
    the API key pulled - which would also break the page that explains why."""
    operator.put("/api/superadmin/platform-settings",
                 json={"settings": {"ai.enabled": "false"}})
    res = tenant.post("/api/ai/describe-item", json={"text": "a chair"})
    assert res.status_code == 503
    assert "switched off" in res.json()["detail"].lower()


# --- The front page -------------------------------------------------------
# The words on the landing page were a code change and a deploy until now.
# They are settings like any other, with one extra rule: the page that reads
# them is the one page nobody has signed in to see.

def test_the_landing_copy_is_public(client):
    """It is the page a visitor reads before they have a session at all."""
    res = client.get("/api/platform/landing")
    assert res.status_code == 200, res.text
    assert res.json()["landing"]["headline"]


def test_only_the_copy_is_public(client):
    """A public endpoint on the settings table is worth being exact about.

    Every key here is landing copy. Nothing from Money, Policy, AI or anywhere
    else may arrive through it, whatever gets added to PLATFORM_SETTINGS later.
    """
    landing = client.get("/api/platform/landing").json()["landing"]
    expected = {s.key.split(".", 1)[1] for s in main.PLATFORM_SETTINGS
                if s.group == "Landing"}
    assert set(landing) == expected

    other = {s.key.split(".", 1)[1] for s in main.PLATFORM_SETTINGS
             if s.group not in ("Landing", "Theme")}
    assert not (set(landing) & other)


def test_the_operator_can_rewrite_the_front_page(operator, client):
    res = operator.put("/api/superadmin/platform-settings", json={
        "settings": {"landing.headline": "Run your whole company here."}})
    assert res.status_code == 200, res.text
    assert client.get("/api/platform/landing").json()["landing"]["headline"] \
        == "Run your whole company here."


def test_an_empty_value_falls_back_to_what_the_page_ships(operator, client):
    """Clearing the box must not blank the headline on the live site."""
    operator.put("/api/superadmin/platform-settings",
                 json={"settings": {"landing.headline": ""}})
    assert client.get("/api/platform/landing").json()["landing"]["headline"] \
        == "Everything Your Business Needs."


def test_the_notice_bar_is_off_until_it_is_written(client):
    assert client.get("/api/platform/landing").json()["landing"]["notice"] == ""


def test_copy_is_stored_as_typed(operator, client):
    """The page sets these with textContent, so markup is inert by the time it
    is rendered. Storing it verbatim is what lets an ampersand or a quote in a
    headline survive - escaping here would double-escape there."""
    operator.put("/api/superadmin/platform-settings", json={
        "settings": {"landing.headline": "Payroll & HR <together>"}})
    assert client.get("/api/platform/landing").json()["landing"]["headline"] \
        == "Payroll & HR <together>"


def test_a_headline_cannot_be_a_wall_of_text(operator):
    res = operator.put("/api/superadmin/platform-settings",
                       json={"settings": {"landing.headline": "x" * 600}})
    assert res.status_code == 400, res.text
