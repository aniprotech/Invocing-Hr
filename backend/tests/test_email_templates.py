"""What the customer actually receives, and who decides it.

The subject and body of an invoice email were written into the code, so every
business sent the same words and changing them meant a deploy. Now they are a
template with placeholders that fill in from the invoice.

The rule this whole screen exists for: a placeholder that resolves to nothing
must be named before the email goes out. "Hi ," reaching a customer is the
failure being prevented, and it is silent - the send succeeds, the wording is
just wrong.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import main
import models
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def preview(tenant, number, **body):
    res = tenant.post(f"/api/invoices/{number}/email-preview", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# --- placeholders ------------------------------------------------------------
def test_a_known_placeholder_is_filled_in():
    values = {"contact first name": "Ada", "invoice number": "INV-0010"}
    filled, missing = main.fill_placeholders("Hi [Contact First Name], see [Invoice Number].", values)
    assert filled == "Hi Ada, see INV-0010."
    assert missing == []


def test_the_brackets_are_matched_however_they_are_typed():
    """People type these by hand, so case must not decide whether it works."""
    filled, _ = main.fill_placeholders("Hi [contact first name]", {"contact first name": "Ada"})
    assert filled == "Hi Ada"


def test_a_placeholder_with_no_value_is_reported():
    """The whole point of the warning line on the send screen."""
    filled, missing = main.fill_placeholders("Hi [Contact First Name],", {"contact first name": ""})
    assert filled == "Hi ,"
    assert missing == ["Contact First Name"]


def test_a_placeholder_nobody_recognises_is_left_as_written():
    """Deleting what somebody typed is worse than showing it back to them."""
    filled, missing = main.fill_placeholders("Ref [Nonsense Thing].", {})
    assert filled == "Ref [Nonsense Thing]."
    assert missing == ["Nonsense Thing"]


def test_the_same_missing_placeholder_is_only_reported_once():
    """It is read by a person; the same name three times is noise."""
    _, missing = main.fill_placeholders(
        "[Contact First Name] [Contact First Name] [contact first name]",
        {"contact first name": ""})
    assert missing == ["Contact First Name"]


def test_ordinary_square_brackets_are_left_alone():
    filled, missing = main.fill_placeholders("See note [1] and [2].", {})
    assert filled == "See note [1] and [2]."
    assert missing == []


# --- the values that come off an invoice --------------------------------------
def test_the_invoice_supplies_its_own_details(tenant):
    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    got = preview(tenant, inv["number"],
                  subject="[Invoice Number] for [Contact First Name]", body="")
    assert inv["number"] in got["subject"]
    assert "Ada" in got["subject"]
    assert got["to"] == "ada@acme.test"


def test_a_first_name_is_taken_from_the_full_name(tenant):
    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    got = preview(tenant, inv["number"], subject="Hi [Contact First Name]", body="")
    assert got["subject"] == "Hi Ada"


def test_a_contact_with_no_name_is_warned_about_not_guessed(tenant):
    """This is the exact case in the brief - the preview showed "Hi ,"."""
    inv = make_invoice(tenant, contact="", email="ada@acme.test")
    got = preview(tenant, inv["number"], subject="x", body="Hi [Contact First Name],")
    assert got["body"] == "Hi ,"
    assert "Contact First Name" in got["missing"]


def test_the_preview_is_what_the_send_would_say(tenant):
    """Generated from the same values, so what is shown is what goes out."""
    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    got = preview(tenant, inv["number"],
                  subject="Invoice [Invoice Number] from [Trading Name]", body="")
    assert "[" not in got["subject"], got["subject"]


def test_a_preview_of_an_invoice_that_is_not_yours_is_a_404(tenant):
    inv = make_invoice(tenant)
    with TestClient(main.app) as other:
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
        assert other.post(f"/api/invoices/{inv['number']}/email-preview",
                          json={}).status_code == 404


# --- templates ----------------------------------------------------------------
def test_a_business_starts_with_a_template_it_can_edit(tenant):
    """A default that only exists in code is a default nobody can change."""
    rows = tenant.get("/api/email-templates").json()["templates"]
    assert len(rows) == 1
    assert rows[0]["is_default"] is True
    assert "[Invoice Number]" in rows[0]["subject"]


def test_the_seeded_template_is_only_seeded_once(tenant):
    tenant.get("/api/email-templates")
    rows = tenant.get("/api/email-templates").json()["templates"]
    assert len(rows) == 1


def test_a_template_can_be_added(tenant):
    tenant.get("/api/email-templates")          # the built-in one, as the UI does
    res = tenant.post("/api/email-templates", json={
        "name": "Friendly", "subject": "Your invoice [Invoice Number]",
        "body": "Hi [Contact First Name]"})
    assert res.status_code == 200, res.text
    assert len(tenant.get("/api/email-templates").json()["templates"]) == 2


def test_there_is_always_a_default_to_open_on(tenant):
    """A business whose first template was created before it ever opened the
    list had none, so the send screen had nothing to open on. Restored on
    read rather than assumed."""
    tenant.post("/api/email-templates", json={"name": "Only one"})
    rows = tenant.get("/api/email-templates").json()["templates"]
    assert sum(1 for t in rows if t["is_default"]) == 1, rows


def test_a_template_needs_a_name(tenant):
    assert tenant.post("/api/email-templates", json={"name": "  "}).status_code == 400


def test_two_templates_cannot_share_a_name(tenant):
    tenant.post("/api/email-templates", json={"name": "Friendly"})
    res = tenant.post("/api/email-templates", json={"name": "friendly"})
    assert res.status_code == 400
    assert "Friendly" in res.json()["detail"]


def test_only_one_template_is_ever_the_default(tenant):
    """The send screen opens on the default; two of them is undefined."""
    tenant.post("/api/email-templates", json={"name": "Friendly", "is_default": True})
    rows = tenant.get("/api/email-templates").json()["templates"]
    assert sum(1 for t in rows if t["is_default"]) == 1
    assert next(t for t in rows if t["is_default"])["name"] == "Friendly"


def test_making_one_default_stands_down_the_other(tenant):
    original = tenant.get("/api/email-templates").json()["templates"][0]
    made = tenant.post("/api/email-templates", json={"name": "Friendly"}).json()
    tenant.put(f"/api/email-templates/{made['id']}", json={"is_default": True})

    rows = {t["id"]: t for t in tenant.get("/api/email-templates").json()["templates"]}
    assert rows[made["id"]]["is_default"] is True
    assert rows[original["id"]]["is_default"] is False


def test_a_template_can_be_edited(tenant):
    row = tenant.get("/api/email-templates").json()["templates"][0]
    res = tenant.put(f"/api/email-templates/{row['id']}",
                     json={"subject": "Rewritten [Invoice Number]"})
    assert res.status_code == 200, res.text
    assert res.json()["subject"] == "Rewritten [Invoice Number]"


def test_the_last_template_cannot_be_removed(tenant):
    """The send screen would open on nothing."""
    row = tenant.get("/api/email-templates").json()["templates"][0]
    res = tenant.delete(f"/api/email-templates/{row['id']}")
    assert res.status_code == 400
    assert "only template" in res.json()["detail"]


def test_removing_the_default_promotes_another(tenant):
    """Something has to be the default, or the screen opens on nothing."""
    original = tenant.get("/api/email-templates").json()["templates"][0]
    tenant.post("/api/email-templates", json={"name": "Friendly"})
    assert tenant.delete(f"/api/email-templates/{original['id']}").status_code == 200

    rows = tenant.get("/api/email-templates").json()["templates"]
    assert len(rows) == 1
    assert rows[0]["is_default"] is True


def test_one_business_cannot_touch_another_s_templates(tenant):
    mine = tenant.get("/api/email-templates").json()["templates"][0]
    with TestClient(main.app) as other:
        email = f"other-{uuid.uuid4().hex[:8]}@example.com"
        other.post("/api/client/register", json={
            "email": email, "password": "Passw0rdTest", "company_name": "Other Ltd"})
        other.post("/api/client/login", json={"email": email, "password": "Passw0rdTest"})
        assert other.put(f"/api/email-templates/{mine['id']}",
                         json={"subject": "Hijacked"}).status_code == 404
        assert other.delete(f"/api/email-templates/{mine['id']}").status_code == 404


# --- the preview picks up the template ----------------------------------------
def test_with_nothing_written_the_default_template_is_used(tenant):
    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    got = preview(tenant, inv["number"])
    assert inv["number"] in got["subject"]
    assert "Ada" in got["body"]


def test_a_named_template_is_used_when_asked_for(tenant):
    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    made = tenant.post("/api/email-templates", json={
        "name": "Terse", "subject": "[Invoice Number]", "body": "Due [Due Date]."}).json()
    got = preview(tenant, inv["number"], template_id=made["id"])
    assert got["subject"] == inv["number"]


# --- what the placeholder picker offers ---------------------------------------
def test_the_placeholders_offered_are_the_ones_that_work(tenant):
    """A picker that inserts something the filler does not know would put a
    placeholder into a customer's email that never resolves."""
    offered = tenant.get("/api/email-placeholders").json()["placeholders"]
    assert offered, "nothing offered"

    inv = make_invoice(tenant, contact="Ada Reid", email="ada@acme.test")
    with main.SessionLocal() as db:
        row = db.query(models.DBInvoice).filter(
            models.DBInvoice.number == inv["number"]).first()
        values = main.invoice_placeholder_values(db, row)

    unknown = [p["name"] for p in offered if p["name"].lower() not in values]
    assert not unknown, f"offered but never resolved: {unknown}"


def test_every_placeholder_is_described(tenant):
    for p in tenant.get("/api/email-placeholders").json()["placeholders"]:
        assert p["help"].strip(), p["name"]
        assert p["group"].strip(), p["name"]
