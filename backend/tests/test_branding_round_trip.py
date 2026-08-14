"""Does pressing Save actually keep it?

The editor sends the whole form as one body and then reloads the list. These
tests walk that exact path, because a setting that silently fails to persist
looks identical to one that saved until the page is reopened.
"""
import pytest

import main

PIXEL = ("data:image/gif;base64,"
         "R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def the_whole_form(**overrides):
    """Exactly what readThemeForm() posts - every field, every time."""
    body = {
        "name": "House style",
        "logo_data": PIXEL,
        "logo_position": "left",
        "brand_color": "#00a3e0",
        "font": "times",
        "tax_breakdown": "combined",
        "address_position": "window_envelope",
        "exclude_zero_rates": True,
        "always_show_currency_code": True,
        "show_conversion_rate": True,
        "show_text_links": False,
        "show_qr_code": False,
        "show_page_numbers": False,
        "approved_invoice_title": "INVOICE",
        "draft_invoice_title": "PROFORMA",
        "quote_title": "ESTIMATE",
        "payment_terms": "Payable within 14 days by bank transfer.",
        "footer_note": "Thank you for your custom.",
        "show_item": True,
        "show_quantity": False,
        "show_price": True,
        "show_discount": True,
        "show_tax": False,
        "label_item": "Code",
        "label_description": "Work done",
        "label_quantity": "Hours",
        "label_price": "Rate",
        "label_discount": "Less",
        "label_tax": "VAT",
        "label_amount": "Total",
    }
    body.update(overrides)
    return body


def reopen(tenant, theme_id):
    """What the page does next time it loads: fetch the list and find it."""
    rows = tenant.get("/api/branding-themes").json()["themes"]
    return next(t for t in rows if t["id"] == theme_id)


def test_every_field_survives_a_save_and_a_reload(tenant):
    made = tenant.post("/api/branding-themes", json={"name": "House style"}).json()
    body = the_whole_form()

    res = tenant.put(f"/api/branding-themes/{made['id']}", json=body)
    assert res.status_code == 200, res.text

    saved = reopen(tenant, made["id"])
    for field, expected in body.items():
        if field == "brand_color":
            expected = expected.lower()
        assert saved[field] == expected, f"{field} did not survive the save"


def test_the_renderer_is_handed_the_saved_theme(tenant):
    """The PDF asks for the default theme. Saving a theme and making it the
    default has to change what the renderer gets."""
    made = tenant.post("/api/branding-themes", json={"name": "House style"}).json()
    tenant.put(f"/api/branding-themes/{made['id']}", json=the_whole_form())
    tenant.post(f"/api/branding-themes/{made['id']}/default")

    used = tenant.get("/api/branding-themes/default").json()
    assert used["id"] == made["id"]
    assert used["font"] == "times"
    assert used["label_quantity"] == "Hours"
    assert used["show_tax"] is False


def test_saving_twice_is_stable(tenant):
    """Pressing Save again without touching anything must not drift."""
    made = tenant.post("/api/branding-themes", json={"name": "House style"}).json()
    tenant.put(f"/api/branding-themes/{made['id']}", json=the_whole_form())
    first = reopen(tenant, made["id"])

    tenant.put(f"/api/branding-themes/{made['id']}", json=the_whole_form())
    second = reopen(tenant, made["id"])

    first.pop("updated_at", None)
    second.pop("updated_at", None)
    assert first == second


def test_renaming_keeps_the_settings(tenant):
    made = tenant.post("/api/branding-themes", json={"name": "House style"}).json()
    tenant.put(f"/api/branding-themes/{made['id']}", json=the_whole_form())
    tenant.put(f"/api/branding-themes/{made['id']}", json={"name": "Renamed"})

    saved = reopen(tenant, made["id"])
    assert saved["name"] == "Renamed"
    assert saved["label_price"] == "Rate", "renaming must not reset the rest"
    assert saved["logo_data"] == PIXEL


def test_a_logo_survives(tenant):
    """Logos go in as a data URI and come back byte for byte, or the invoice
    loses its branding on the next render."""
    made = tenant.post("/api/branding-themes", json={"name": "Logo test"}).json()
    tenant.put(f"/api/branding-themes/{made['id']}", json={"logo_data": PIXEL})
    assert reopen(tenant, made["id"])["logo_data"] == PIXEL


def test_turning_a_column_off_persists_as_off(tenant):
    """False is the value most easily lost - a truthiness bug reads it as
    'not sent' and leaves the old True in place."""
    made = tenant.post("/api/branding-themes", json={"name": "Minimal"}).json()
    tenant.put(f"/api/branding-themes/{made['id']}", json={
        "show_quantity": False, "show_price": False, "show_tax": False,
        "show_page_numbers": False, "show_qr_code": False})

    saved = reopen(tenant, made["id"])
    for f in ("show_quantity", "show_price", "show_tax",
              "show_page_numbers", "show_qr_code"):
        assert saved[f] is False, f"{f} came back on"
