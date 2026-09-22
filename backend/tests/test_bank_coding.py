"""Coding the money out.

A customer paying an invoice is matched; everything else on the statement
is coded: a category and the tax in it, a transfer to one of your own
accounts, a bill on the books. Rules do the lines that repeat; the rest
are suggested from what was coded before, from a mirror line on another
account, or from an open bill. The profit and loss reads the bank.
"""
from datetime import date, timedelta

import pytest

import main
from conftest import make_invoice


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


STATEMENT = """Date,Description,Amount
{d3},BRITISH GAS DD,-80.50
{d2},ACME LTD INV-0001,120.00
{d2},TRANSFER TO SAVINGS,-500.00
{d1},RENT MR PATEL,-1200.00
{d1},CLOUDCO SUBSCRIPTION,-24.00
{d0},HMRC VAT,-310.00
"""


def statement(**extra):
    return STATEMENT.format(d3=d(-3), d2=d(-2), d1=d(-1), d0=d(0)) + "".join(f"{k},{v}\n" for k, v in extra.items())


def import_lines(tenant, text=None, account_id=None):
    body = {"text": text or statement(), "filename": "sept.csv"}
    if account_id:
        body["account_id"] = account_id
    r = tenant.post("/api/bank/import", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def lines(tenant, status):
    return tenant.get(f"/api/bank/lines?status={status}").json()["lines"]


def by_words(rows, words):
    return next(l for l in rows if words in l["description"])


@pytest.fixture
def accounts(tenant):
    current = tenant.post("/api/accounts", json={"name": "Current", "kind": "bank"}).json()
    savings = tenant.post("/api/accounts", json={"name": "Savings", "kind": "bank"}).json()
    return current, savings


# --- categories and coding -----------------------------------------------------------------
def test_the_categories_are_split_by_direction(tenant):
    cats = tenant.get("/api/bank/categories").json()
    out = {c["key"] for c in cats["out"]}
    inn = {c["key"] for c in cats["in"]}
    assert {"rent", "utilities", "wages", "software", "tax", "drawings", "bill", "transfer"} <= out
    assert {"other_income", "refund_in", "owner_funds", "loan_in", "transfer"} <= inn
    assert "rent" not in inn and "other_income" not in out
    assert next(c for c in cats["out"] if c["key"] == "rent")["label"] == "Rent & premises"


def test_a_money_out_line_is_coded_with_a_category_and_the_tax_in_it(tenant):
    import_lines(tenant)
    gas = by_words(lines(tenant, "out"), "BRITISH GAS")
    r = tenant.post("/api/bank/lines/code", json={"ids": [gas["id"]], "category": "utilities", "tax_rate": "20% VAT"})
    assert r.status_code == 200, r.text
    coded = r.json()["lines"][0]
    assert coded["status"] == "coded" and coded["category"] == "utilities" and coded["category_label"] == "Utilities" and coded["tax_rate"] == "20% VAT"
    assert [l["id"] for l in lines(tenant, "coded")] == [gas["id"]]
    assert gas["id"] not in [l["id"] for l in lines(tenant, "out")]
    counts = tenant.get("/api/bank/lines?status=out").json()["counts"]
    assert counts["coded"] == 1 and counts["out"] == 4


def test_a_category_for_money_in_is_refused_on_money_out_and_the_reverse(tenant):
    import_lines(tenant)
    gas = by_words(lines(tenant, "out"), "BRITISH GAS")
    r = tenant.post("/api/bank/lines/code", json={"ids": [gas["id"]], "category": "other_income"})
    assert r.status_code == 400 and "money in" in r.text
    acme = by_words(lines(tenant, "unmatched"), "ACME")
    r = tenant.post("/api/bank/lines/code", json={"ids": [acme["id"]], "category": "rent"})
    assert r.status_code == 400 and "money out" in r.text
    assert tenant.post("/api/bank/lines/code", json={"ids": [gas["id"]], "category": "made_up"}).status_code == 400
    assert tenant.post("/api/bank/lines/code", json={"ids": [], "category": "rent"}).status_code == 400


def test_many_lines_are_coded_in_one_go_and_one_can_be_taken_back(tenant):
    import_lines(tenant)
    out = lines(tenant, "out")
    ids = [by_words(out, "RENT")["id"], by_words(out, "CLOUDCO")["id"]]
    assert tenant.post("/api/bank/lines/code", json={"ids": ids, "category": "general"}).json()["coded"] == 2
    assert tenant.post(f"/api/bank/lines/{ids[0]}/uncode").status_code == 200
    assert by_words(lines(tenant, "out"), "RENT")["status"] == "out"
    assert [l["id"] for l in lines(tenant, "coded")] == [ids[1]]
    # Restore works on a coded line too.
    assert tenant.post(f"/api/bank/lines/{ids[1]}/restore").status_code == 200
    assert lines(tenant, "coded") == []


def test_money_in_that_is_not_a_customer_is_coded_too(tenant):
    import_lines(tenant, statement(**{d(0): "OWNER TOPUP,2000.00"}))
    topup = by_words(lines(tenant, "unmatched"), "OWNER TOPUP")
    r = tenant.post("/api/bank/lines/code", json={"ids": [topup["id"]], "category": "owner_funds"})
    assert r.status_code == 200 and r.json()["lines"][0]["category"] == "owner_funds"
    assert topup["id"] not in [l["id"] for l in lines(tenant, "unmatched")]


# --- transfers -----------------------------------------------------------------------------------
def test_a_transfer_codes_both_sides_at_once(tenant, accounts):
    current, savings = accounts
    import_lines(tenant, f"Date,Description,Amount\n{d(-2)},TRANSFER TO SAVINGS,-500.00\n", account_id=current["id"])
    import_lines(tenant, f"Date,Description,Amount\n{d(-1)},FROM CURRENT,500.00\n", account_id=savings["id"])
    out = by_words(lines(tenant, "out"), "TRANSFER TO SAVINGS")
    assert out["coding"] and out["coding"]["category"] == "transfer" and out["coding"]["transfer_account_id"] == savings["id"] \
        and out["coding"]["confidence"] == "likely" and "Savings" in out["coding"]["why"]
    inn = by_words(lines(tenant, "unmatched"), "FROM CURRENT")
    assert inn["coding"]["category"] == "transfer" and inn["coding"]["transfer_account_id"] == current["id"]
    r = tenant.post("/api/bank/lines/code", json={"ids": [out["id"]], "category": "transfer", "transfer_account_id": savings["id"]})
    assert r.status_code == 200
    coded = {l["id"]: l for l in lines(tenant, "coded")}
    assert out["id"] in coded and inn["id"] in coded, "the other side was coded with it"
    assert coded[inn["id"]]["transfer_account"] == "Current" and coded[out["id"]]["transfer_account"] == "Savings"
    assert lines(tenant, "unmatched") == []


def test_a_transfer_needs_a_different_account_of_yours(tenant, accounts):
    current, savings = accounts
    import_lines(tenant, account_id=current["id"])
    t = by_words(lines(tenant, "out"), "TRANSFER TO SAVINGS")
    assert tenant.post("/api/bank/lines/code", json={"ids": [t["id"]], "category": "transfer"}).status_code == 400
    r = tenant.post("/api/bank/lines/code", json={"ids": [t["id"]], "category": "transfer", "transfer_account_id": current["id"]})
    assert r.status_code == 400 and "two different accounts" in r.text
    assert tenant.post("/api/bank/lines/code", json={"ids": [t["id"]], "category": "transfer", "transfer_account_id": 999999}).status_code == 400


# --- bills ------------------------------------------------------------------------------------------
def test_paying_a_bill_from_the_bank_settles_the_bill(tenant):
    bill = tenant.post("/api/bills", json={"vendor_name": "Cloudco", "issue_date": d(-10), "due_date": d(5), "amount": 20.0, "tax_amount": 4.0,
                                            "total": 24.0, "category": "software", "status": "Awaiting Payment"}).json()
    import_lines(tenant)
    cloud = by_words(lines(tenant, "out"), "CLOUDCO")
    assert cloud["coding"] and cloud["coding"]["category"] == "bill" and cloud["coding"]["bill_id"] == bill["id"] and cloud["coding"]["confidence"] == "likely"
    r = tenant.post("/api/bank/lines/code", json={"ids": [cloud["id"]], "category": "bill", "bill_id": bill["id"]})
    assert r.status_code == 200, r.text
    paid = tenant.get(f"/api/bills/{bill['id']}").json()
    assert paid["status"] == "Paid" and paid["amount_paid"] == 24.0
    # Taking the coding back owes the bill again.
    tenant.post(f"/api/bank/lines/{cloud['id']}/uncode")
    again = tenant.get(f"/api/bills/{bill['id']}").json()
    assert again["amount_paid"] == 0.0 and again["status"] != "Paid"
    # A line bigger than the bill's balance is refused.
    rent = by_words(lines(tenant, "out"), "RENT")
    r = tenant.post("/api/bank/lines/code", json={"ids": [rent["id"]], "category": "bill", "bill_id": bill["id"]})
    assert r.status_code == 400 and "more than bill" in r.text


# --- rules -------------------------------------------------------------------------------------------
def test_a_rule_codes_the_lines_here_and_every_line_that_arrives(tenant):
    import_lines(tenant)
    r = tenant.post("/api/bank/rules", json={"name": "Gas", "contains": "british gas", "direction": "out", "action": "categorise",
                                              "category": "utilities", "tax_rate": "20% VAT"})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 1 and r.json()["rule"]["applied_count"] == 1
    gas = by_words(lines(tenant, "coded"), "BRITISH GAS")
    assert gas["category"] == "utilities" and gas["tax_rate"] == "20% VAT" and gas["rule_id"] == r.json()["rule"]["id"]
    # The next statement's gas line is coded on arrival.
    out = import_lines(tenant, f"Date,Description,Amount\n{d(0)},BRITISH GAS DD OCT,-82.00\n{d(0)},SOMETHING ELSE,-5.00\n")
    assert out["summary"]["coded_by_rules"] == 1
    assert by_words(lines(tenant, "coded"), "OCT")["category"] == "utilities"
    assert by_words(lines(tenant, "out"), "SOMETHING ELSE")["status"] == "out"
    assert tenant.get("/api/bank/rules").json()["rules"][0]["applied_count"] == 2


def test_rules_can_ignore_transfer_and_be_bounded_by_amount(tenant, accounts):
    current, savings = accounts
    import_lines(tenant, account_id=current["id"])
    tenant.post("/api/bank/rules", json={"name": "Savings", "contains": "to savings", "action": "transfer", "transfer_account_id": savings["id"]})
    t = by_words(lines(tenant, "coded"), "TRANSFER TO SAVINGS")
    assert t["category"] == "transfer" and t["transfer_account"] == "Savings"
    tenant.post("/api/bank/rules", json={"name": "Small stuff", "contains": "cloudco", "action": "ignore", "max_amount": 30})
    assert by_words(lines(tenant, "ignored"), "CLOUDCO")["note"] == "Rule: Small stuff"
    # A bound that does not fit leaves the line alone.
    r = tenant.post("/api/bank/rules", json={"name": "Big rent", "contains": "rent", "action": "categorise", "category": "rent", "min_amount": 5000})
    assert r.json()["applied"] == 0 and by_words(lines(tenant, "out"), "RENT")["status"] == "out"
    # And a rule can be corrected, deleted, and applied on demand.
    rid = r.json()["rule"]["id"]
    assert tenant.put(f"/api/bank/rules/{rid}", json={"name": "Rent", "contains": "rent", "action": "categorise", "category": "rent"}).status_code == 200
    assert tenant.post("/api/bank/rules/apply").json()["applied"] == 1
    assert by_words(lines(tenant, "coded"), "RENT")["category"] == "rent"
    assert tenant.delete(f"/api/bank/rules/{rid}").status_code == 200
    assert len(tenant.get("/api/bank/rules").json()["rules"]) == 2
    assert by_words(lines(tenant, "coded"), "RENT")["category"] == "rent", "what a rule coded stays coded when it goes"


def test_a_rule_needs_words_and_a_category(tenant):
    assert tenant.post("/api/bank/rules", json={"name": "x", "contains": "", "action": "categorise", "category": "rent"}).status_code == 400
    assert tenant.post("/api/bank/rules", json={"contains": "x", "action": "categorise", "category": "made_up"}).status_code == 400
    assert tenant.post("/api/bank/rules", json={"contains": "x", "action": "transfer"}).status_code == 400
    assert tenant.post("/api/bank/rules", json={"contains": "x", "action": "categorise", "category": "rent", "min_amount": "lots"}).status_code == 400


# --- suggestions and cash coding -----------------------------------------------------------------------
def test_what_was_coded_before_is_suggested_and_coded_in_one_go(tenant):
    import_lines(tenant)
    gas = by_words(lines(tenant, "out"), "BRITISH GAS")
    tenant.post("/api/bank/lines/code", json={"ids": [gas["id"]], "category": "utilities", "tax_rate": "20% VAT"})
    import_lines(tenant, f"Date,Description,Amount\n{d(0)},BRITISH GAS DD,-84.00\n{d(0)},NEW SUPPLIER,-9.00\n")
    again = by_words(lines(tenant, "out"), "BRITISH GAS")
    assert again["coding"]["category"] == "utilities" and again["coding"]["tax_rate"] == "20% VAT" and again["coding"]["confidence"] == "auto"
    assert "coded that way on" in again["coding"]["why"]
    assert by_words(lines(tenant, "out"), "NEW SUPPLIER")["coding"] is None
    assert tenant.get("/api/bank/lines?status=out").json()["auto_coding"] == 1
    r = tenant.post("/api/bank/lines/code-suggested")
    assert r.json() == {"coded": 1, "left": 5}
    assert by_words(lines(tenant, "coded"), "-84.00" if False else "BRITISH GAS DD")["tax_rate"] == "20% VAT"


# --- the report -----------------------------------------------------------------------------------------
def test_the_profit_and_loss_reads_the_bank(tenant, accounts):
    current, savings = accounts
    inv = make_invoice(tenant, status="Awaiting Payment", contact="Acme", issue_date=d(-5), due_date=d(20), tax_type="exclusive",
                       line_items=[{"description": "x", "qty": 1, "price": 100.0, "tax_rate": "20% VAT"}])
    import_lines(tenant, account_id=current["id"])
    out = lines(tenant, "out")
    tenant.post("/api/bank/lines/code", json={"ids": [by_words(out, "BRITISH GAS")["id"]], "category": "utilities", "tax_rate": "20% VAT"})
    tenant.post("/api/bank/lines/code", json={"ids": [by_words(out, "RENT")["id"]], "category": "rent"})
    tenant.post("/api/bank/lines/code", json={"ids": [by_words(out, "HMRC")["id"]], "category": "tax"})
    tenant.post("/api/bank/lines/code", json={"ids": [by_words(out, "TRANSFER")["id"]], "category": "transfer", "transfer_account_id": savings["id"]})
    acme = by_words(lines(tenant, "unmatched"), "ACME")
    tenant.post(f"/api/bank/lines/{acme['id']}/record", json={"invoice_number": inv["number"]})
    r = tenant.get(f"/api/reports/profit-loss/detail?from={d(-10)}&to={d(0)}").json()
    assert r["income"]["invoices"] == 120.0 and r["income"]["other"] == 0.0 and r["income"]["total"] == 120.0
    cats = {x["category"]: x for x in r["expenses"]["by_category"]}
    assert cats["rent"]["gross"] == 1200.0 and cats["rent"]["vat"] == 0.0
    assert cats["utilities"]["gross"] == 80.5 and cats["utilities"]["vat"] == 13.42 and cats["utilities"]["net"] == 67.08
    assert r["expenses"]["total"] == 1280.5 and r["net"] == money_(120.0 - 1280.5)
    assert {m["category"] for m in r["movements"]} == {"tax", "transfer"}, "tax and transfers are movements, not trade"
    assert r["vat"]["output"] == 20.0 and r["vat"]["input"] == 13.42 and r["vat"]["due"] == 6.58
    assert r["uncoded"]["count"] == 1 and r["uncoded"]["amount"] == 24.0, "the Cloudco line is still to code"
    csv = tenant.get(f"/api/reports/profit-loss/detail.csv?from={d(-10)}&to={d(0)}")
    assert csv.status_code == 200 and "Rent & premises,1200.00" in csv.text and "VAT due,6.58" in csv.text
    assert tenant.get(f"/api/reports/profit-loss/detail?from={d(0)}&to={d(-10)}").status_code == 400


def money_(v):
    return main.money(v)


def test_another_business_sees_none_of_it(tenant, client, account, accounts):
    import_lines(tenant)
    gas = by_words(lines(tenant, "out"), "BRITISH GAS")
    rule = tenant.post("/api/bank/rules", json={"contains": "rent", "action": "categorise", "category": "rent"}).json()["rule"]
    other = f"other-{account['email']}"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.post("/api/bank/lines/code", json={"ids": [gas["id"]], "category": "utilities"}).status_code == 404
    assert client.post(f"/api/bank/lines/{gas['id']}/uncode").status_code == 404
    assert client.get("/api/bank/rules").json()["rules"] == []
    assert client.delete(f"/api/bank/rules/{rule['id']}").status_code == 404
    assert client.get(f"/api/reports/profit-loss/detail?from={d(-10)}&to={d(0)}").json()["expenses"]["by_category"] == []
