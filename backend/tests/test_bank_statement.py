"""The bank statement: brought in, matched, recorded.

A CSV from any bank - or an OFX - comes in as lines against an account.
Money in is set against the open invoices by amount, invoice number and
customer name; a confident match records a receipt dated the day the
money landed, in that account, with the bank's narrative as reference; a
line already typed in by hand is recognised, not recorded twice; money
out is kept and left alone; the same line in two files is one line. A
reversed receipt puts its line back. Nothing crosses a business.
"""
from datetime import date, timedelta

import pytest

import main
from conftest import make_invoice


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def d(n):
    return (date.today() + timedelta(days=n)).isoformat()


def uk(n):
    dt = date.today() + timedelta(days=n)
    return dt.strftime("%d/%m/%Y")


def inv(tenant, contact, total, number=None):
    kw = {"invoice_number": number} if number else {}
    return make_invoice(tenant, status="Awaiting Payment", contact=contact, line_items=[{"description": "x", "qty": 1, "price": float(total), "tax_rate": "0%"}], **kw)


def account(tenant, name="Bank"):
    return tenant.post("/api/accounts", json={"name": name, "kind": "bank"}).json()


def imp(tenant, text, **kw):
    res = tenant.post("/api/bank/import", json=dict({"text": text, "filename": "statement.csv"}, **kw))
    assert res.status_code == 200, res.text
    return res.json()


def lines(tenant, status="unmatched"):
    return tenant.get("/api/bank/lines", params={"status": status}).json()


UK_CSV = """Date,Description,Paid out,Paid in,Balance
{d1},FPS ACME LTD INV-0001,,780.00,"1,234.50"
{d2},CARD PAYMENT TESCO,45.20,,"1,189.30"
{d3},BACS BRAMLEY WORKS,,500.00,"1,689.30"
{d4},FPS UNKNOWN REF 8812,,100.00,"1,789.30"
"""


def test_a_uk_style_csv_comes_in_with_money_in_matched_and_money_out_kept(tenant):
    bank = account(tenant)
    a = inv(tenant, "Acme Ltd", 780, "INV-0001")
    b = inv(tenant, "Bramley Works", 500)
    c = inv(tenant, "Somebody Else", 100)
    text = UK_CSV.format(d1=uk(-3), d2=uk(-2), d3=uk(-1), d4=uk(0))
    dry = imp(tenant, text, dry_run=1, account_id=bank["id"])
    assert dry["summary"]["rows"] == 4 and dry["summary"]["new"] == 4 and dry["summary"]["money_in"] == 3 and dry["summary"]["money_out"] == 1
    assert dry["summary"]["kind"] == "csv" and dry["sample"][0]["amount"] == 780.0 and dry["sample"][1]["amount"] == -45.2
    assert tenant.get("/api/bank/lines").json()["lines"] == [], "a dry run writes nothing"
    out = imp(tenant, text, account_id=bank["id"])
    got = lines(tenant)
    assert len(got["lines"]) == 3 and got["counts"] == {"unmatched": 3, "out": 1}
    by_desc = {l["description"]: l for l in got["lines"]}
    acme = by_desc["FPS ACME LTD INV-0001"]
    assert acme["suggestions"][0]["number"] == "INV-0001" and acme["suggestions"][0]["confidence"] == "auto"
    assert "invoice number" in acme["suggestions"][0]["why"] and "exact amount" in acme["suggestions"][0]["why"]
    bram = by_desc["BACS BRAMLEY WORKS"]
    assert bram["suggestions"][0]["number"] == b["number"] and bram["suggestions"][0]["confidence"] == "auto", "amount and name"
    unk = by_desc["FPS UNKNOWN REF 8812"]
    assert unk["suggestions"][0]["number"] == c["number"] and unk["suggestions"][0]["confidence"] == "likely", "the amount alone is a lead, not a match"
    assert got["auto"] == 2 and got["unmatched_total"] == 1380.0
    outgoing = lines(tenant, "out")["lines"]
    assert len(outgoing) == 1 and outgoing[0]["amount"] == -45.2 and outgoing[0]["balance"] == 1189.3
    imports = tenant.get("/api/bank/imports").json()["imports"]
    assert imports[0]["lines"] == 4 and imports[0]["account"] == "Bank" and imports[0]["filename"] == "statement.csv"


def test_recording_a_line_makes_the_receipt_the_bank_says(tenant):
    bank = account(tenant)
    a = inv(tenant, "Acme Ltd", 780, "INV-0001")
    imp(tenant, UK_CSV.format(d1=uk(-3), d2=uk(-2), d3=uk(-1), d4=uk(0)), account_id=bank["id"])
    acme = next(l for l in lines(tenant)["lines"] if "ACME" in l["description"])
    res = tenant.post(f"/api/bank/lines/{acme['id']}/record", json={"invoice_number": "INV-0001"})
    assert res.status_code == 200, res.text
    assert res.json()["invoice"]["status"] == "Paid" and res.json()["line"]["status"] == "matched"
    got = tenant.get("/api/invoices/INV-0001").json()
    p = got["payments"][0]
    assert p["amount"] == 780.0 and p["paid_on"] == d(-3) and p["method"] == "bank_transfer" and p["account_name"] == "Bank"
    assert p["reference"] == "FPS ACME LTD INV-0001"
    assert lines(tenant, "matched")["lines"][0]["payment_ids"] == [p["id"]]
    assert tenant.post(f"/api/bank/lines/{acme['id']}/record", json={"invoice_number": "INV-0001"}).status_code == 400, "not twice"
    # Reversing the receipt puts the line back.
    assert tenant.delete(f"/api/invoices/INV-0001/payments/{p['id']}").status_code == 200
    back = next(l for l in lines(tenant)["lines"] if l["id"] == acme["id"])
    assert back["status"] == "unmatched" and back["allocated"] == 0 and back["payment_ids"] == []


def test_a_line_can_cover_part_of_an_invoice_or_be_split_across_two(tenant):
    bank = account(tenant)
    big = inv(tenant, "Acme Ltd", 1000, "INV-0001")
    small = inv(tenant, "Acme Ltd", 200, "INV-0002")
    text = "Date,Description,Amount\n" + f"{uk(0)},ACME PART,600.00\n" + f"{uk(0)},ACME BOTH INV-0001 INV-0002,1200.00\n"
    imp(tenant, text, account_id=bank["id"])
    got = {l["description"]: l for l in lines(tenant)["lines"]}
    part = got["ACME PART"]
    assert part["suggestions"][0]["number"] == "INV-0001" and part["suggestions"][0]["confidence"] == "likely", "a part payment with a name is a lead"
    assert tenant.post(f"/api/bank/lines/{part['id']}/record", json={"invoice_number": "INV-0001"}).json()["invoice"]["due"] == 400.0
    both = got["ACME BOTH INV-0001 INV-0002"]
    res = tenant.post(f"/api/bank/lines/{both['id']}/record", json={"invoice_number": "INV-0001"}).json()
    assert res["invoice"]["status"] == "Paid" and res["line"]["status"] == "unmatched" and res["line"]["remaining"] == 800.0, "what is left stays on the line"
    assert tenant.post(f"/api/bank/lines/{both['id']}/record", json={"invoice_number": "INV-0002", "amount": 500}).status_code == 400, "never more than the invoice is owed"
    assert tenant.post(f"/api/bank/lines/{both['id']}/record", json={"invoice_number": "INV-0002", "amount": 900}).status_code == 400, "never more than the line has left"
    res = tenant.post(f"/api/bank/lines/{both['id']}/record", json={"invoice_number": "INV-0002"}).json()
    assert res["line"]["remaining"] == 600.0 and res["line"]["status"] == "unmatched", "600 of it is still unexplained"
    assert tenant.post(f"/api/bank/lines/{both['id']}/ignore", json={"note": "overpayment"}).status_code == 400, "recorded in part: reverse first"


def test_record_all_takes_only_the_confident_and_unambiguous(tenant):
    bank = account(tenant)
    inv(tenant, "Acme Ltd", 780, "INV-0001")
    inv(tenant, "Bramley Works", 500, "INV-0002")
    inv(tenant, "Bramley Works", 500, "INV-0003")            # two Bramley invoices for 500: ambiguous
    inv(tenant, "Nobody Named", 100, "INV-0004")
    text = ("Date,Description,Amount\n" + f"{uk(-1)},FPS ACME LTD INV-0001,780\n" + f"{uk(-1)},BACS BRAMLEY WORKS,500\n" + f"{uk(0)},FPS REF 8812,100\n")
    imp(tenant, text, account_id=bank["id"])
    out = tenant.post("/api/bank/record-all", json={}).json()
    assert out == {"recorded": 1, "left": 2}
    assert tenant.get("/api/invoices/INV-0001").json()["status"] == "Paid"
    left = {l["description"] for l in lines(tenant)["lines"]}
    assert left == {"BACS BRAMLEY WORKS", "FPS REF 8812"}


def test_a_receipt_typed_in_by_hand_is_recognised_not_doubled(tenant):
    bank = account(tenant)
    a = inv(tenant, "Acme Ltd", 780, "INV-0001")
    tenant.post("/api/invoices/INV-0001/payments", json={"amount": 780, "paid_on": d(-2), "method": "bank_transfer", "reference": "FPS 1"})
    imp(tenant, "Date,Description,Amount\n" + f"{uk(-3)},FPS ACME LTD,780\n", account_id=bank["id"])
    l = lines(tenant)["lines"][0]
    assert l["already_recorded"]["amount"] == 780.0 and l["suggestions"] == []
    assert tenant.post(f"/api/bank/lines/{l['id']}/link", json={"payment_id": l["already_recorded"]["payment_id"]}).status_code == 200
    assert lines(tenant)["lines"] == [] and lines(tenant, "matched")["lines"][0]["note"] == "Already recorded by hand"
    assert len(tenant.get("/api/invoices/INV-0001").json()["payments"]) == 1
    assert tenant.post("/api/bank/record-all", json={}).json() == {"recorded": 0, "left": 0}


def test_the_same_line_in_two_files_is_one_line(tenant):
    bank = account(tenant)
    text = "Date,Description,Amount\n" + f"{uk(-1)},FPS ONE,10\n" + f"{uk(0)},FPS TWO,20\n"
    imp(tenant, text, account_id=bank["id"])
    again = text + f"{uk(1)},FPS THREE,30\n"
    out = imp(tenant, again, account_id=bank["id"])
    assert out["summary"]["new"] == 1 and out["summary"]["duplicates"] == 2
    assert tenant.post("/api/bank/import", json={"text": text, "account_id": bank["id"]}).status_code == 400, "nothing new"
    assert len(lines(tenant)["lines"]) == 3
    # Ignore and restore.
    l = lines(tenant)["lines"][0]
    assert tenant.post(f"/api/bank/lines/{l['id']}/ignore", json={"note": "loan"}).json()["line"]["status"] == "ignored"
    assert lines(tenant, "ignored")["lines"][0]["note"] == "loan"
    assert tenant.post(f"/api/bank/lines/{l['id']}/restore").json()["line"]["status"] == "unmatched"


def test_indian_bank_columns_and_dd_mm_yy_dates(tenant):
    bank = account(tenant)
    inv(tenant, "Sharma Traders", 25000, "INV-0001")
    text = ("Account Number: 1234\nStatement of account\n\n"
            "Txn Date,Narration,Chq/Ref No,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
            f"{(date.today() - timedelta(days=1)).strftime('%d-%m-%y')},NEFT SHARMA TRADERS INV0001,N123,,\"25,000.00\",\"1,25,000.00\"\n"
            f"{date.today().strftime('%d-%m-%y')},ATM WDL,,\"2,000.00\",,\"1,23,000.00\"\n")
    out = imp(tenant, text, account_id=bank["id"])
    assert out["summary"]["new"] == 2 and out["summary"]["columns"]["credit"] == "Deposit Amt." and out["summary"]["unreadable"] == 0
    l = lines(tenant)["lines"][0]
    assert l["amount"] == 25000.0 and l["date"] == d(-1) and l["reference"] == "N123"
    assert l["suggestions"][0]["number"] == "INV-0001" and l["suggestions"][0]["confidence"] == "auto", "INV0001 matches INV-0001"


def test_ofx_comes_in_too(tenant):
    bank = account(tenant)
    inv(tenant, "Acme Ltd", 780, "INV-0001")
    ymd = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    ofx = ("OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>"
           f"<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>{ymd}120000<TRNAMT>780.00<FITID>F1<NAME>ACME LTD<MEMO>INV-0001</STMTTRN>"
           f"<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{ymd}<TRNAMT>-12.50<FITID>F2<NAME>BANK FEE</STMTTRN>"
           "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
    out = imp(tenant, ofx, account_id=bank["id"], filename="statement.ofx")
    assert out["summary"]["kind"] == "ofx" and out["summary"]["new"] == 2
    l = lines(tenant)["lines"][0]
    assert l["amount"] == 780.0 and l["reference"] == "F1" and l["description"] == "ACME LTD INV-0001" and l["suggestions"][0]["confidence"] == "auto"


def test_what_cannot_be_read_is_refused_or_counted(tenant):
    assert tenant.post("/api/bank/import", json={"text": "Name,Age\nBob,3\n"}).status_code == 400
    assert tenant.post("/api/bank/import", json={"text": ""}).status_code == 400
    out = imp(tenant, "Date,Description,Amount\nnot a date,X,10\n" + f"{uk(0)},OK,10\n", dry_run=1)
    assert out["summary"]["unreadable"] == 1 and out["summary"]["new"] == 1


def test_an_import_can_be_removed_until_a_line_is_recorded(tenant):
    bank = account(tenant)
    inv(tenant, "Acme Ltd", 10, "INV-0001")
    out = imp(tenant, "Date,Description,Amount\n" + f"{uk(0)},ACME INV-0001,10\n", account_id=bank["id"])
    assert tenant.delete(f"/api/bank/imports/{out['import_id']}").status_code == 200
    assert lines(tenant)["lines"] == []
    out = imp(tenant, "Date,Description,Amount\n" + f"{uk(0)},ACME INV-0001,10\n", account_id=bank["id"])
    tenant.post("/api/bank/record-all", json={})
    assert tenant.delete(f"/api/bank/imports/{out['import_id']}").status_code == 400


def test_nothing_crosses_a_business(tenant, account):
    bank = account_ = tenant.post("/api/accounts", json={"name": "Bank", "kind": "bank"}).json()
    inv(tenant, "Acme Ltd", 780, "INV-0001")
    out = imp(tenant, "Date,Description,Amount\n" + f"{uk(0)},FPS ACME LTD INV-0001,780\n", account_id=bank["id"])
    mine = lines(tenant)["lines"][0]
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/bank/lines").json()["lines"] == [] and tenant.get("/api/bank/imports").json()["imports"] == []
    assert tenant.post(f"/api/bank/lines/{mine['id']}/record", json={"invoice_number": "INV-0001"}).status_code == 404
    assert tenant.post(f"/api/bank/lines/{mine['id']}/ignore", json={}).status_code == 404
    assert tenant.delete(f"/api/bank/imports/{out['import_id']}").status_code == 404
    assert tenant.post("/api/bank/import", json={"text": "Date,Description,Amount\n" + f"{uk(0)},X,1\n", "account_id": bank["id"]}).status_code == 400, "not my account"
    # The other business's identical line is its own line.
    theirs = imp(tenant, "Date,Description,Amount\n" + f"{uk(0)},FPS ACME LTD INV-0001,780\n")
    assert theirs["summary"]["new"] == 1 and theirs["summary"]["duplicates"] == 0
    assert tenant.get("/api/bank/lines").json()["lines"][0]["suggestions"] == [], "no INV-0001 here"
