"""How a business wants its invoices to look.

Presentation only - none of this may ever change what is owed. Most of these
tests are about the rules that keep the renderer safe: there is always exactly
one default theme, a colour is always a colour, and a logo is always an image.
"""
import pytest

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


PIXEL = ("data:image/gif;base64,"
         "R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")


def themes(tenant):
    res = tenant.get("/api/branding-themes")
    assert res.status_code == 200, res.text
    return res.json()["themes"]


def make(tenant, **body):
    body.setdefault("name", "Bold")
    res = tenant.post("/api/branding-themes", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# --- every account starts usable ---------------------------------------------

def test_a_new_account_already_has_a_theme(tenant):
    """The renderer must never have to cope with there being none."""
    rows = themes(tenant)
    assert len(rows) == 1
    assert rows[0]["name"] == "Standard"
    assert rows[0]["is_default"] is True


def test_the_default_endpoint_always_answers(tenant):
    body = tenant.get("/api/branding-themes/default").json()
    assert body["brand_color"].startswith("#")
    assert body["font"] in ("helvetica", "times", "courier")


# --- the settings Xero exposes ------------------------------------------------

def test_it_keeps_every_setting_it_is_given(tenant):
    theme = make(tenant,
                 logo_position="left", brand_color="#00A3E0", font="times",
                 show_discount=True, show_tax=False,
                 label_quantity="Hours", tax_breakdown="combined",
                 always_show_currency_code=True, show_qr_code=False,
                 approved_invoice_title="INVOICE",
                 address_position="window_envelope")
    assert theme["logo_position"] == "left"
    assert theme["brand_color"] == "#00a3e0"
    assert theme["font"] == "times"
    assert theme["show_discount"] is True
    assert theme["show_tax"] is False
    assert theme["label_quantity"] == "Hours"
    assert theme["tax_breakdown"] == "combined"
    assert theme["always_show_currency_code"] is True
    assert theme["show_qr_code"] is False
    assert theme["approved_invoice_title"] == "INVOICE"
    assert theme["address_position"] == "window_envelope"


def test_editing_a_theme_sticks(tenant):
    theme = make(tenant)
    res = tenant.put(f"/api/branding-themes/{theme['id']}",
                     json={"brand_color": "#123456", "show_item": True})
    assert res.status_code == 200, res.text
    assert res.json()["brand_color"] == "#123456"
    assert res.json()["show_item"] is True


def test_an_untouched_setting_is_left_alone(tenant):
    """The editor saves one panel at a time, so a partial body must not reset
    everything the caller did not mention."""
    theme = make(tenant, label_price="Rate", show_qr_code=False)
    tenant.put(f"/api/branding-themes/{theme['id']}", json={"brand_color": "#111111"})
    after = tenant.get("/api/branding-themes").json()["themes"]
    mine = next(t for t in after if t["id"] == theme["id"])
    assert mine["label_price"] == "Rate"
    assert mine["show_qr_code"] is False


# --- what must be rejected ----------------------------------------------------

@pytest.mark.parametrize("colour", ["red", "javascript:alert(1)", "#12", "", "#gggggg"])
def test_a_colour_that_is_not_a_colour_is_refused(tenant, colour):
    """This string is written into a PDF and into inline CSS, so it can only
    ever be a hex colour."""
    theme = make(tenant, brand_color="#4f46e5")
    tenant.put(f"/api/branding-themes/{theme['id']}", json={"brand_color": colour})
    after = tenant.get("/api/branding-themes").json()["themes"]
    assert next(t for t in after if t["id"] == theme["id"])["brand_color"] == "#4f46e5"


def test_a_logo_must_be_an_image(tenant):
    theme = make(tenant)
    res = tenant.put(f"/api/branding-themes/{theme['id']}",
                     json={"logo_data": "data:text/html,<script>alert(1)</script>"})
    assert res.status_code == 400
    assert "image" in res.json()["detail"].lower()


def test_a_real_image_is_accepted(tenant):
    theme = make(tenant)
    res = tenant.put(f"/api/branding-themes/{theme['id']}", json={"logo_data": PIXEL})
    assert res.status_code == 200, res.text
    assert res.json()["logo_data"] == PIXEL


def test_an_enormous_logo_is_refused(tenant):
    theme = make(tenant)
    huge = "data:image/png;base64," + ("A" * 3_000_001)
    res = tenant.put(f"/api/branding-themes/{theme['id']}", json={"logo_data": huge})
    assert res.status_code == 400


def test_an_unknown_font_is_ignored(tenant):
    """jsPDF has three core families. Storing anything else would silently fall
    back and change every invoice."""
    theme = make(tenant, font="Comic Sans")
    assert theme["font"] == "helvetica"


def test_two_themes_cannot_share_a_name(tenant):
    make(tenant, name="Bold")
    res = tenant.post("/api/branding-themes", json={"name": "Bold"})
    assert res.status_code == 400
    assert "already have" in res.json()["detail"]


def test_a_theme_needs_a_name(tenant):
    theme = make(tenant)
    res = tenant.put(f"/api/branding-themes/{theme['id']}", json={"name": "   "})
    assert res.status_code == 400


# --- exactly one default ------------------------------------------------------

def test_choosing_a_default_unsets_the_old_one(tenant):
    theme = make(tenant)
    tenant.post(f"/api/branding-themes/{theme['id']}/default")
    rows = themes(tenant)
    assert [t["is_default"] for t in rows].count(True) == 1
    assert next(t for t in rows if t["id"] == theme["id"])["is_default"] is True


def test_deleting_the_default_promotes_another(tenant):
    """An account with no default would break the renderer."""
    theme = make(tenant)
    tenant.post(f"/api/branding-themes/{theme['id']}/default")
    tenant.delete(f"/api/branding-themes/{theme['id']}")
    rows = themes(tenant)
    assert [t["is_default"] for t in rows].count(True) == 1


def test_the_last_theme_cannot_be_deleted(tenant):
    only = themes(tenant)[0]
    res = tenant.delete(f"/api/branding-themes/{only['id']}")
    assert res.status_code == 400
    assert "only theme" in res.json()["detail"]


# --- isolation ----------------------------------------------------------------

def test_themes_are_per_tenant(client, tenant):
    make(tenant, name="Mine", brand_color="#abcdef")

    import uuid
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    names = [t["name"] for t in client.get("/api/branding-themes").json()["themes"]]
    assert names == ["Standard"], "another business's theme must not be visible"


def test_you_cannot_edit_somebody_elses_theme(client, tenant, account):
    theme = make(tenant, name="Mine")

    import uuid
    other = f"other-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/client/register", json={
        "email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    main.rate_limiter._hits.clear()
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})

    res = client.put(f"/api/branding-themes/{theme['id']}", json={"brand_color": "#000000"})
    assert res.status_code == 404


def test_it_needs_a_session(client):
    assert client.get("/api/branding-themes").status_code == 401
