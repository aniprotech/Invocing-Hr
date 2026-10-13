"""HMRC and Salt Edge are set on the operator's settings screen, with the
environment variable they used to live in as the fallback."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import main
import saltedge

NAMES = [n for n in (list(main.SALTEDGE_SETTING_FOR) + [
    "HMRC_VENDOR_ID", "HMRC_RTI_ENDPOINT", "HMRC_RTI_MODE", "HMRC_RTI_IRMARK"])]


@pytest.fixture
def operator_client(client, monkeypatch):
    for n in NAMES:
        monkeypatch.delenv(n, raising=False)
    with main.SessionLocal() as db:       # the test database outlives a test
        db.query(main.models.DBSettings).filter(
            main.models.DBSettings.client_id == None,        # noqa: E711
            main.models.DBSettings.key.like("hmrc.%") | main.models.DBSettings.key.like("saltedge.%"),
        ).delete(synchronize_session=False)
        db.commit()
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    return client


def save(c, **values):
    res = c.put("/api/superadmin/platform-settings", json={"settings": values})
    assert res.status_code == 200, res.text
    return res.json()


def pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def test_the_settings_screen_lists_hmrc_and_salt_edge(operator_client):
    groups = operator_client.get("/api/superadmin/platform-settings").json()["groups"]
    assert "HMRC" in groups and "Salt Edge" in groups


def test_hmrc_values_saved_on_the_screen_are_the_ones_used(operator_client):
    assert main.rti_cfg()["vendor_id"] == "" and main.rti_cfg()["mode"] == "test"
    save(operator_client, **{"hmrc.vendor_id": "1234", "hmrc.endpoint": "https://gw.example/rti",
                             "hmrc.mode": "live", "hmrc.irmark": "true"})
    cfg = main.rti_cfg()
    assert (cfg["vendor_id"], cfg["endpoint"], cfg["mode"], cfg["irmark"]) == (
        "1234", "https://gw.example/rti", "live", True)


def test_the_environment_variable_still_works_until_something_is_saved(operator_client, monkeypatch):
    monkeypatch.setenv("HMRC_VENDOR_ID", "from-env")
    assert main.rti_cfg()["vendor_id"] == "from-env"
    save(operator_client, **{"hmrc.vendor_id": "from-screen"})
    assert main.rti_cfg()["vendor_id"] == "from-screen"


def test_mode_only_accepts_test_or_live(operator_client):
    res = operator_client.put("/api/superadmin/platform-settings",
                              json={"settings": {"hmrc.mode": "yes"}})
    assert res.status_code == 400


def test_salt_edge_keys_saved_on_the_screen_switch_it_on(operator_client):
    assert not saltedge.is_configured(main.saltedge_cfg())
    save(operator_client, **{
        "saltedge.app_id": "app", "saltedge.secret": "sec",
        "saltedge.creditor_name": "Aniprotech Ltd",
        "saltedge.creditor_sort_code": "12-34-56", "saltedge.creditor_account_number": "12345678"})
    cfg = main.saltedge_cfg()
    assert saltedge.is_configured(cfg) and saltedge.can_take(cfg, "GBP")


def test_a_secret_is_never_sent_back_and_blank_keeps_it(operator_client):
    save(operator_client, **{"saltedge.secret": "topsecret"})
    rows = {r["key"]: r for r in operator_client.get("/api/superadmin/platform-settings").json()["settings"]}
    assert rows["saltedge.secret"]["value"] == "" and rows["saltedge.secret"]["is_set"] is True
    save(operator_client, **{"saltedge.secret": ""})
    assert main.saltedge_cfg()["secret"] == "topsecret"


def test_a_whole_private_key_survives_being_saved_and_can_sign(operator_client):
    key = pem()
    save(operator_client, **{"saltedge.private_key": key})
    assert saltedge.sign(main.saltedge_cfg()["private_key"], "x")


def test_a_key_pasted_into_a_one_line_box_is_rebuilt():
    key = pem()
    one_line = " ".join(key.split())             # newlines lost, as a one-line field does
    assert saltedge.sign(saltedge._pem(one_line), "x")
    assert saltedge.sign(saltedge._pem(key.replace("\n", "\\n")), "x")
    assert saltedge.sign(saltedge._pem(key), "x")


@pytest.fixture(autouse=True)
def _tidy_after(request):
    yield
    if "operator_client" in request.fixturenames:
        with main.SessionLocal() as db:
            db.query(main.models.DBSettings).filter(
                main.models.DBSettings.client_id == None,        # noqa: E711
                main.models.DBSettings.key.like("hmrc.%") | main.models.DBSettings.key.like("saltedge.%"),
            ).delete(synchronize_session=False)
            db.commit()


def test_the_screen_is_operator_only(client):
    assert client.put("/api/superadmin/platform-settings",
                      json={"settings": {"hmrc.vendor_id": "x"}}).status_code == 401
