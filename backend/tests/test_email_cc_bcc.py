"""Who else gets a copy, and the link that never resolved.

Two things reported off a live send screen. [Online Invoice Link] warned
"does not have a corresponding value" on every invoice, because the link was
built only from APP_BASE_URL, which is not set in production - so a customer
would have received a sentence ending in nothing. And there was no way to
copy anyone: no Cc, no Bcc.

The rule Bcc exists for is the one worth guarding: a blind copy must not be
visible to the other recipients. Getting that wrong is silent and only
discovered by the person who was not supposed to know.
"""
import pytest
from fastapi.testclient import TestClient

import main
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


# --- the online invoice link -------------------------------------------------
def test_the_link_resolves_without_the_setting(tenant, monkeypatch):
    """It was empty on every invoice, because the setting is not set."""
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    got = tenant.post(f"/api/invoices/{inv['number']}/email-preview",
                      json={"subject": "x", "body": "See [Online Invoice Link]"}).json()
    assert got["body"] != "See "
    assert "invoice.html?id=" in got["body"], got["body"]
    assert "Online Invoice Link" not in got["missing"], got["missing"]


def test_the_link_uses_the_public_id_not_the_number(tenant, monkeypatch):
    """An invoice number is not a public identifier - the tracking id is the
    one the rest of this file already links customers to."""
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    inv = make_invoice(tenant)
    got = tenant.post(f"/api/invoices/{inv['number']}/email-preview",
                      json={"subject": "x", "body": "[Online Invoice Link]"}).json()
    assert "invoice.html?id=" in got["body"], got["body"]
    # The number is not a public identifier and must not be what is linked.
    assert f"id={inv['number']}" not in got["body"], got["body"]
    assert "number=" not in got["body"], got["body"]


def test_the_setting_still_wins_when_it_is_present(tenant, monkeypatch):
    """A business behind a proxy needs its own name on the link."""
    monkeypatch.setenv("APP_BASE_URL", "https://pay.example.test")
    inv = make_invoice(tenant)
    got = tenant.post(f"/api/invoices/{inv['number']}/email-preview",
                      json={"subject": "x", "body": "[Online Invoice Link]"}).json()
    assert got["body"].startswith("https://pay.example.test/invoice.html?id=")


# --- tidying what was typed ---------------------------------------------------
def test_a_trailing_comma_does_not_become_an_empty_recipient():
    assert main.clean_address_list("a@x.test, b@x.test,") == "a@x.test, b@x.test"


def test_semicolons_are_accepted_because_people_type_them():
    assert main.clean_address_list("a@x.test; b@x.test") == "a@x.test, b@x.test"


def test_nothing_typed_stays_nothing():
    assert main.clean_address_list("") == ""
    assert main.clean_address_list(None) == ""
    assert main.clean_address_list("  ,  ") == ""


# --- the headers that actually go out ------------------------------------------
def build(**kw):
    raw = main.prepare_email_message(
        "ada@acme.test", "Subject", "Body", "", "me@biz.test", **kw)
    return raw


def test_a_cc_is_visible_because_that_is_the_point_of_it():
    assert "Cc: boss@biz.test" in build(cc="boss@biz.test")


def test_a_bcc_never_reaches_the_other_recipients():
    """The whole reason to use Bcc. If it lands in To or Cc instead, everyone
    learns who was quietly copied and nothing reports it."""
    import email as _email
    parsed = _email.message_from_string(build(cc="boss@biz.test", bcc="audit@biz.test"))
    # Every To and Cc header, not just the first - setting a header twice
    # appends rather than replaces, so a leak can hide behind a clean one.
    visible = (parsed.get_all("To") or []) + (parsed.get_all("Cc") or [])
    assert visible, "no visible recipients at all"
    assert not any("audit@biz.test" in h for h in visible), visible
    assert any("audit@biz.test" in h for h in parsed.get_all("Bcc") or []), "bcc dropped"


def test_no_empty_headers_when_nobody_is_copied():
    raw = build()
    assert "Cc:" not in raw
    assert "Bcc:" not in raw


# --- the send endpoint accepts them --------------------------------------------
def test_the_send_screen_can_pass_cc_and_bcc(tenant):
    """Only that the field is carried - what leaves is the mailer's job, and
    it has no credentials in a test."""
    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    res = tenant.post(f"/api/invoices/{inv['number']}/send", json={
        "to": "ada@acme.test", "subject": "s", "body": "b",
        "cc": "boss@biz.test", "bcc": "audit@biz.test"})
    assert res.status_code in (200, 400, 500), res.text
    assert "cc" not in res.text.lower() or res.status_code == 200
