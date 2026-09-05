"""Every action the product charges for has to have a price.

An action with no pricing rule costs nothing. That is deliberate - it lets
metering be rolled out gradually without blocking anybody - and it is exactly
what makes a missing row dangerous: it is a feature being given away, not an
error anybody sees.

seed_pricing_rules was written to backfill. It skips keys that already exist,
so it can be run any time. But every place that called it guarded the call
with "only if the table is empty", so it ran once on the first boot and never
again. Six actions added to DEFAULT_PRICING afterwards had no row in
production - quote_send and five AI features, which cost real money at the
provider on every call and were charged to nobody.
"""
import pytest

import main
import models


@pytest.fixture
def rules_restored():
    """Whatever the table holds, put it back afterwards."""
    with main.SessionLocal() as db:
        before = [(r.action_key, r.label, r.description, r.module,
                   r.unit_price_minor, r.free_allowance, r.is_active, r.sort_order)
                  for r in db.query(models.DBPricingRule).all()]
    yield
    with main.SessionLocal() as db:
        db.query(models.DBPricingRule).delete()
        for row in before:
            db.add(models.DBPricingRule(
                action_key=row[0], label=row[1], description=row[2], module=row[3],
                unit_price_minor=row[4], currency=main.PLATFORM_CURRENCY,
                free_allowance=row[5], is_active=row[6], sort_order=row[7]))
        db.commit()


def priced_keys():
    with main.SessionLocal() as db:
        return {r.action_key for r in db.query(models.DBPricingRule).all()}


# --- the gap that was live ------------------------------------------------------

def test_every_known_action_has_a_price(client):
    """The one that was false in production. Six actions had no row, so six
    features were free - and nothing anywhere said so."""
    known = {key for key, *_ in main.DEFAULT_PRICING}
    missing = known - priced_keys()
    assert not missing, f"charged for nothing: {sorted(missing)}"


def test_an_action_added_later_gets_a_row_on_the_next_boot(client, rules_restored):
    """This is the case that failed. The backfill exists and was only ever
    called on an empty table, so an existing install never saw a new action."""
    with main.SessionLocal() as db:
        db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "ai_assistant").delete()
        db.commit()
    assert "ai_assistant" not in priced_keys()

    main.ensure_pricing_rules()

    assert "ai_assistant" in priced_keys(), \
        "a newly known action still has no price after a boot"


def test_seeding_does_not_disturb_a_price_the_operator_set(client, rules_restored):
    """It runs on every boot, so overwriting would quietly undo the operator's
    own pricing on each deploy - which is the reason it was guarded in the
    first place."""
    with main.SessionLocal() as db:
        row = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_send").first()
        row.unit_price_minor = 77
        row.label = "What we call it here"
        row.free_allowance = 3
        db.commit()

    main.ensure_pricing_rules()

    with main.SessionLocal() as db:
        row = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_send").first()
        assert row.unit_price_minor == 77
        assert row.label == "What we call it here"
        assert row.free_allowance == 3


def test_seeding_twice_creates_nothing_the_second_time(client, rules_restored):
    main.ensure_pricing_rules()
    before = priced_keys()
    main.ensure_pricing_rules()
    assert priced_keys() == before


def test_an_action_switched_off_stays_off(client, rules_restored):
    """Turning one off is a decision. A boot that switched it back on would
    start charging for something somebody deliberately stopped charging for."""
    with main.SessionLocal() as db:
        row = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_whatsapp").first()
        row.is_active = False
        db.commit()

    main.ensure_pricing_rules()

    with main.SessionLocal() as db:
        row = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_whatsapp").first()
        assert row.is_active is False


def test_a_failure_to_seed_does_not_stop_the_app(monkeypatch):
    """The same trade the schema updates make: a price that could not be
    written must not take the whole app down with it."""
    def explode(db):
        raise RuntimeError("no database today")

    monkeypatch.setattr(main, "seed_pricing_rules", explode)
    main.ensure_pricing_rules()          # must not raise


# --- and the public page shows them ------------------------------------------------

def test_the_public_page_offers_every_active_action(client):
    listed = {a["action_key"] for a in
              client.get("/api/platform/pricing").json()["actions"]}
    with main.SessionLocal() as db:
        active = {r.action_key for r in db.query(models.DBPricingRule).filter(
            models.DBPricingRule.is_active == True).all()}      # noqa: E712
    assert listed == active, sorted(active - listed)


def test_nothing_is_charged_for_without_being_advertised(client):
    """The two have to agree. A price the page does not mention is a charge
    somebody finds on their statement."""
    charged = {key for key, *_ in main.DEFAULT_PRICING}
    listed = {a["action_key"] for a in
              client.get("/api/platform/pricing").json()["actions"]}
    with main.SessionLocal() as db:
        switched_off = {r.action_key for r in db.query(models.DBPricingRule).filter(
            models.DBPricingRule.is_active == False).all()}     # noqa: E712
    assert not (charged - listed - switched_off), \
        sorted(charged - listed - switched_off)


# --- one currency on both sides -------------------------------------------------

def test_prices_and_wallets_agree_on_the_currency(client, tenant):
    """Both are created from PLATFORM_CURRENCY, so they agree until somebody
    changes it. Worth asserting, because nothing else would notice."""
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        wallet = main.get_wallet(db, cid)
        rules = db.query(models.DBPricingRule).all()
        odd = {r.action_key: r.currency for r in rules
               if (r.currency or "") != (wallet.currency or "")}
    assert not odd, f"wallet is {wallet.currency}, these are not: {odd}"


def test_a_price_in_another_currency_does_not_charge_the_wallet(client, tenant,
                                                                rules_restored):
    """Five paise and five pence are both the number 5. Subtracting one from
    the other looks like nothing at all and is a hundred times wrong, so it
    must not happen quietly."""
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        wallet = main.get_wallet(db, cid)
        wallet.balance_minor = 100_000
        rule = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_send").first()
        rule.currency = "JPY" if wallet.currency != "JPY" else "GBP"
        rule.unit_price_minor = 500
        rule.free_allowance = 0
        db.commit()
        before = wallet.balance_minor

    with main.SessionLocal() as db:
        tx = main.charge_wallet(db, cid, "invoice_send", 1)
        db.commit()

    assert tx is None, "it charged across two different currencies"
    with main.SessionLocal() as db:
        assert main.get_wallet(db, cid).balance_minor == before, \
            "the balance moved on a charge that should not have happened"


def test_and_the_same_currency_still_charges(client, tenant, rules_restored):
    """The guard must not be a way of never charging anybody."""
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        wallet = main.get_wallet(db, cid)
        wallet.balance_minor = 100_000
        rule = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.action_key == "invoice_send").first()
        rule.currency = wallet.currency
        rule.unit_price_minor = 500
        rule.free_allowance = 0
        rule.is_active = True
        db.commit()
        before = wallet.balance_minor

    with main.SessionLocal() as db:
        tx = main.charge_wallet(db, cid, "invoice_send", 1)
        db.commit()

    assert tx is not None
    with main.SessionLocal() as db:
        assert main.get_wallet(db, cid).balance_minor == before - 500
