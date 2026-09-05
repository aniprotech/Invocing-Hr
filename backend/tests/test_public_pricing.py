"""What using this costs, for somebody who has not signed up.

The nav has said Pricing for as long as there has been a nav, and it landed on
a call-to-action card with no prices on it. There were no tiers to list
either - nothing here is a subscription. Every action draws from a wallet,
each has a price and a free monthly allowance, and those rows already existed
and were already editable.

So this reads them rather than restating them. A price list written into a
page drifts from the one being charged, and the first person to notice is a
customer who has just paid something the site does not mention.

It is open, so most of what is checked here is that being open costs nothing:
prices are public by their nature, and no tenant's anything may come with them.
"""
import pytest

import main
import models


@pytest.fixture
def priced():
    """Known rules, put back afterwards."""
    with main.SessionLocal() as db:
        before = [(r.action_key, r.is_active, r.unit_price_minor, r.free_allowance,
                   r.module, r.label)
                  for r in db.query(models.DBPricingRule).all()]
        db.query(models.DBPricingRule).delete()
        db.add_all([
            models.DBPricingRule(action_key="invoice_send", label="Send invoice by email",
                                 description="Charged when an invoice is emailed.",
                                 module="invoicing", unit_price_minor=5,
                                 currency=main.PLATFORM_CURRENCY, free_allowance=50,
                                 is_active=True, sort_order=0),
            models.DBPricingRule(action_key="payslip_send", label="Send payslip by email",
                                 description="", module="hr", unit_price_minor=5,
                                 currency=main.PLATFORM_CURRENCY, free_allowance=50,
                                 is_active=True, sort_order=1),
            models.DBPricingRule(action_key="retired_thing", label="An old action",
                                 description="", module="platform", unit_price_minor=99,
                                 currency=main.PLATFORM_CURRENCY, free_allowance=0,
                                 is_active=False, sort_order=2),
        ])
        db.commit()
    yield
    with main.SessionLocal() as db:
        db.query(models.DBPricingRule).delete()
        for key, active, price, allowance, module, label in before:
            db.add(models.DBPricingRule(
                action_key=key, label=label, description="", module=module,
                unit_price_minor=price, currency=main.PLATFORM_CURRENCY,
                free_allowance=allowance, is_active=active))
        db.commit()


def get(client):
    res = client.get("/api/platform/pricing")
    assert res.status_code == 200, res.text
    return res.json()


# --- a price nobody can see before signing up is not a price -----------------

def test_a_stranger_can_read_the_prices(client, priced):
    """The whole point. Behind a login this is a surprise, not a price."""
    body = get(client)
    keys = [a["action_key"] for a in body["actions"]]
    assert "invoice_send" in keys, body


def test_it_is_the_same_row_the_operator_edits(client, priced):
    """Not a copy. A page with its own list drifts from what is charged, and
    the first to notice is somebody who has just been billed for it."""
    with main.SessionLocal() as db:
        row = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_send").first()
        row.unit_price_minor = 12
        row.label = "Emailing an invoice"
        db.commit()

    sent = next(a for a in get(client)["actions"]
                if a["action_key"] == "invoice_send")
    assert sent["label"] == "Emailing an invoice"
    assert sent["unit_price"] == main.to_major(12, main.PLATFORM_CURRENCY)


def test_the_free_allowance_comes_with_the_price(client, priced):
    """It is what decides whether any of this costs a small business anything,
    so a price without it is misleading rather than incomplete."""
    sent = next(a for a in get(client)["actions"]
                if a["action_key"] == "invoice_send")
    assert sent["free_allowance"] == 50


def test_a_retired_action_is_not_advertised(client, priced):
    keys = [a["action_key"] for a in get(client)["actions"]]
    assert "retired_thing" not in keys, keys


def test_it_says_there_is_nothing_to_subscribe_to(client, priced):
    """The thing people get wrong about this kind of billing."""
    note = get(client)["note"].lower()
    assert "no monthly fee" in note or "no plan" in note, note
    assert "month" in note, note


def test_the_currency_comes_with_the_numbers(client, priced):
    body = get(client)
    assert body["currency"] == main.PLATFORM_CURRENCY
    assert body["symbol"]


def test_each_action_says_which_part_of_the_product_it_is(client, priced):
    modules = {a["module"] for a in get(client)["actions"]}
    assert modules <= {"invoicing", "hr", "platform"}, modules
    assert "invoicing" in modules and "hr" in modules


# --- being open must cost nothing else ----------------------------------------

def test_nothing_about_any_tenant_comes_with_it(client, priced, tenant):
    """It is read by anybody at all, so a balance, a client id or a usage
    figure slipping in would be a leak with no login in front of it.

    Asked of the shape rather than by scanning the text: "email" appears in
    "Send invoice by email" perfectly legitimately, and a check that trips on
    a word in a label is a check that gets deleted the first time it cries
    wolf. The keys are the contract, so the keys are what is pinned.
    """
    body = get(client)
    assert set(body) == {"currency", "symbol", "actions", "note"}, sorted(body)
    for action in body["actions"]:
        assert set(action) == {
            "action_key", "label", "description", "module",
            "unit_price", "free_allowance",
        }, sorted(action)


def test_it_does_not_need_a_session_and_does_not_start_one(client, priced):
    res = client.get("/api/platform/pricing")
    assert res.status_code == 200
    # A public read that sets a cookie is a public read that tracks people.
    assert "set-cookie" not in {k.lower() for k in res.headers}, dict(res.headers)


def test_an_empty_table_is_filled_rather_than_returned_empty(client):
    """A fresh install has no rules until something asks. A pricing page that
    is blank on a new deployment reads as a product with no prices."""
    with main.SessionLocal() as db:
        before = [(r.action_key, r.label, r.module, r.unit_price_minor,
                   r.free_allowance, r.is_active) for r in
                  db.query(models.DBPricingRule).all()]
        db.query(models.DBPricingRule).delete()
        db.commit()
    try:
        body = get(client)
        assert body["actions"], "a fresh install advertises no prices at all"
    finally:
        with main.SessionLocal() as db:
            db.query(models.DBPricingRule).delete()
            for key, label, module, price, allowance, active in before:
                db.add(models.DBPricingRule(
                    action_key=key, label=label, description="", module=module,
                    unit_price_minor=price, currency=main.PLATFORM_CURRENCY,
                    free_allowance=allowance, is_active=active))
            db.commit()
