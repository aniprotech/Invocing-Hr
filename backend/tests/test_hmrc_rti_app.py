"""HMRC payroll filings through the app: what a business has to give, how its
payslips become a Full Payment Submission, what stops one being sent, and the
record of what was.

The message building and HMRC's rules are proven in test_hmrc_rti.py. These
are the joins: year-to-date figures that leave out the previous job, a letter
per National Insurance category, starters only once, the right pension field
for the scheme, a Gateway password that never comes back out, and one business
never seeing another's filings.
"""
import json

import pytest
from lxml import etree

import hmrc_rti
import main
import models
from conftest import make_employee
from test_hmrc_rti import Gateway, reply

KEY = "test-encryption-key"
_REAL_SEND = hmrc_rti.send


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    main.rate_limiter._hits.clear()
    for name in ("HMRC_VENDOR_ID", "HMRC_RTI_ENDPOINT", "HMRC_RTI_MODE", "HMRC_RTI_IRMARK", "HMRC_ENCRYPTION_KEY"):
        monkeypatch.delenv(name, raising=False)
    yield


def platform(monkeypatch, mode="test", gateway=None, **extra):
    monkeypatch.setenv("HMRC_VENDOR_ID", "9999")
    monkeypatch.setenv("HMRC_RTI_ENDPOINT", "https://gateway.example/submission")
    monkeypatch.setenv("HMRC_RTI_MODE", mode)
    monkeypatch.setenv("HMRC_ENCRYPTION_KEY", KEY)
    for k, v in extra.items():
        monkeypatch.setenv(k, v)
    if gateway is not None:
        monkeypatch.setattr(hmrc_rti, "send", lambda *a, **k: _REAL_SEND(*a, post=gateway, sleep=lambda s: None, **k))


def good_gateway():
    return Gateway(reply("acknowledgement", endpoint="https://gateway.example/poll"), reply("response", body="<ok/>"), reply("response"))


def business(tenant, **kw):
    refs = {"office_no": "123", "paye_ref": "AB456", "ao_ref": "123PA00012345", "contact_name": "Jane Doe",
            "contact_email": "jane@example.com", "contact_phone": "020 7946 0000", "gateway_user": "123456789012"}
    refs.update(kw)
    res = tenant.put("/api/hmrc/rti/settings", json=refs)
    assert res.status_code == 200, res.text
    return res.json()


def go_uk(tenant):
    assert tenant.put("/api/payroll/settings", json={"regime": "uk"}).status_code == 200


def person(tenant, **kw):
    fields = dict(salary=3000.0, tax_rate=0.0, pay_frequency="monthly", ni_number="AB123456C", tax_code="1257L",
                  ni_category="A", date_of_birth="1990-05-17", gender="F", hours_band="D", start_date="2020-01-06",
                  address="1 High Street, Leeds, LS1 4AB", status="active")
    fields.update(kw)
    return make_employee(tenant, **fields)


def payslip(tenant, emp, pay_date, **kw):
    res = tenant.post("/api/payslips", json=dict(employee_id=emp["id"], period_start=pay_date[:8] + "01",
                                                 period_end=pay_date, pay_date=pay_date, **kw))
    assert res.status_code == 200, res.text
    return res.json()


def shown(tenant, ps):
    p = tenant.get(f"/api/payslips/{ps['id']}").json()
    uk = p["uk"]
    return {"taxable_pay": uk["taxable_pay"], "tax_amount": p["tax_amount"], "ni_earnings": uk["ni_earnings"],
            "employee_ni": uk["employee_ni"], "employer_ni": uk["employer_ni"],
            "pension_employee": (uk["pension"] or {}).get("employee", 0)}


def check(tenant, pay_date, **kw):
    res = tenant.post("/api/hmrc/rti/fps/check", json={"pay_date": pay_date, **kw})
    assert res.status_code == 200, res.text
    return res.json()


def xml_of(result):
    return etree.fromstring(result["xml"].encode())


def text(doc, path):
    return [e.text for e in doc.iterfind(".//{*}" + path)]


@pytest.fixture
def ready(tenant):
    go_uk(tenant)
    business(tenant)
    return tenant


# --- what the business gives -------------------------------------------------------------
def test_a_new_business_has_nothing_set_and_is_told_what_is_missing(tenant):
    got = tenant.get("/api/hmrc/rti").json()
    assert got["employer"]["paye_ref"] == "" and got["has_gateway_password"] is False
    assert got["can_check"] is False and got["can_send"] is False
    missing = {r["key"]: r for r in got["readiness"] if not r["ok"]}
    assert {"regime", "refs", "gateway", "vendor", "endpoint", "encryption"} <= set(missing)
    assert missing["vendor"]["owner"] == "platform" and missing["refs"]["owner"] == "you"
    assert "not_built" in got and "Statutory pay" in " ".join(got["not_built"])


def test_references_are_saved_and_tidied(tenant):
    got = business(tenant, office_no=" 123 ", paye_ref="ab 456", ao_ref="123pa 00012345")
    assert got["employer"]["office_no"] == "123" and got["employer"]["paye_ref"] == "AB456"
    assert got["employer"]["ao_ref"] == "123PA00012345"


def test_a_whole_paye_reference_typed_in_one_box_is_split(tenant):
    got = tenant.put("/api/hmrc/rti/settings", json={"office_no": "123/AB456", "ao_ref": "123PA00012345"}).json()
    assert got["employer"]["office_no"] == "123" and got["employer"]["paye_ref"] == "AB456"


@pytest.mark.parametrize("field,value,says", [
    ("office_no", "12", "three digits"), ("paye_ref", "AB 45-6", "up to 10"),
    ("ao_ref", "12PA0001234", "Accounts Office"), ("contact_email", "not-an-email", "email"),
])
def test_a_reference_that_cannot_be_right_is_refused_in_plain_words(tenant, field, value, says):
    refs = {"office_no": "123", "paye_ref": "AB456", "ao_ref": "123PA00012345", field: value}
    res = tenant.put("/api/hmrc/rti/settings", json=refs)
    assert res.status_code == 400 and says in res.json()["detail"], res.text


def test_the_gateway_password_is_stored_encrypted_and_never_comes_back(tenant, monkeypatch):
    monkeypatch.setenv("HMRC_ENCRYPTION_KEY", KEY)
    got = business(tenant, gateway_password="S3cret-Gateway!")
    assert got["has_gateway_password"] is True
    assert "S3cret" not in json.dumps(got) and "S3cret" not in json.dumps(tenant.get("/api/hmrc/rti").json())
    with main.SessionLocal() as db:
        stored = db.query(models.DBSettings).filter(models.DBSettings.key == main.RTI_PASSWORD_KEY).order_by(models.DBSettings.id.desc()).first().value
        assert "S3cret" not in stored and hmrc_rti.unseal(stored, KEY) == "S3cret-Gateway!"
        audit = " ".join(str(a.details) for a in db.query(models.DBAuditLog).all()) if hasattr(models, "DBAuditLog") else ""
        assert "S3cret" not in audit


def test_a_password_is_not_stored_without_a_key(tenant):
    res = tenant.put("/api/hmrc/rti/settings", json={"gateway_password": "pw"})
    assert res.status_code == 503 and "HMRC_ENCRYPTION_KEY" in res.json()["detail"]


def test_saving_other_details_leaves_the_password_alone(tenant, monkeypatch):
    monkeypatch.setenv("HMRC_ENCRYPTION_KEY", KEY)
    business(tenant, gateway_password="first")
    again = tenant.put("/api/hmrc/rti/settings", json={"contact_name": "New Name"}).json()
    assert again["has_gateway_password"] is True and again["employer"]["contact_name"] == "New Name"


def test_a_password_can_be_cleared(tenant, monkeypatch):
    monkeypatch.setenv("HMRC_ENCRYPTION_KEY", KEY)
    business(tenant, gateway_password="first")
    assert tenant.put("/api/hmrc/rti/settings", json={"clear_gateway_password": True}).json()["has_gateway_password"] is False


def test_a_password_that_cannot_be_read_is_said_to_need_entering_again(tenant, monkeypatch):
    monkeypatch.setenv("HMRC_ENCRYPTION_KEY", KEY)
    business(tenant, gateway_password="first")
    monkeypatch.setenv("HMRC_ENCRYPTION_KEY", "a-different-key")
    gate = next(r for r in tenant.get("/api/hmrc/rti").json()["readiness"] if r["key"] == "gateway")
    assert gate["ok"] is False and "enter it again" in gate["detail"]


# --- the employee record -------------------------------------------------------------------
def test_the_new_employee_fields_are_saved_and_read_back(tenant):
    emp = person(tenant, gender="m", postcode="ls14ab", hours_band="b")
    got = tenant.get(f"/api/employees/{emp['id']}").json()
    assert (got["gender"], got["postcode"], got["hours_band"]) == ("M", "LS1 4AB", "B")


@pytest.mark.parametrize("field,value,says", [("gender", "X", "M or F"), ("postcode", "Leeds", "postcode"), ("hours_band", "Q", "A, B, C, D or E")])
def test_a_bad_value_for_them_is_refused(tenant, field, value, says):
    emp = person(tenant)
    res = tenant.put(f"/api/employees/{emp['id']}", json={field: value})
    assert res.status_code == 400 and says in res.json()["detail"]
    res = tenant.post("/api/employees", json={"first_name": "A", "last_name": "B", "email": "ab@example.com", field: value})
    assert res.status_code == 400


# --- building the Full Payment Submission -----------------------------------------------------
def test_it_cannot_be_checked_without_the_business_references(tenant):
    go_uk(tenant)
    payslip(tenant, person(tenant), "2026-04-30")
    res = tenant.post("/api/hmrc/rti/fps/check", json={"pay_date": "2026-04-30"})
    assert res.status_code == 400 and "tax office number" in res.json()["detail"]


def test_a_day_with_no_payslips_is_not_found(ready):
    assert ready.post("/api/hmrc/rti/fps/check", json={"pay_date": "2026-04-30"}).status_code == 404


def test_a_pay_date_is_needed(ready):
    assert ready.post("/api/hmrc/rti/fps/check", json={}).status_code == 400


def test_one_payslip_becomes_a_submission_that_passes_hmrcs_rules(ready):
    emp = person(ready)
    payslip(ready, emp, "2026-04-30")
    got = check(ready, "2026-04-30")
    assert got["problems"] == [], got["problems"]
    assert got["ok"] is True and got["status"] == "checked" and got["people"] == 1
    doc = xml_of(got)
    assert text(doc, "NINO") == ["AB123456C"] and text(doc, "EmployeeDetails/{*}Name/{*}Sur") == [hmrc_rti.surname(emp["last_name"])]
    assert text(doc, "PayId") == [emp["employee_id"]] and text(doc, "PayFreq") == ["M1"] and text(doc, "MonthNo") == ["1"]
    assert text(doc, "BirthDate") == ["1990-05-17"] and text(doc, "Gender") == ["F"] and text(doc, "HoursWorked") == ["D"]
    assert text(doc, "TaxCode") == ["1257L"] and text(doc, "OfficeNo") == ["123"] and text(doc, "AORef") == ["123PA00012345"]
    assert text(doc, "UKPostcode") == ["LS1 4AB"] and text(doc, "Line") == ["1 High Street", "Leeds"]
    assert text(doc, "RelatedTaxYear") == ["26-27"] and text(doc, "NIletter") == ["A"]
    assert "starter" not in got["starters"]


def test_the_figures_are_the_payslips(ready):
    emp = person(ready)
    shown_ps = shown(ready, payslip(ready, emp, "2026-04-30"))
    doc = xml_of(check(ready, "2026-04-30"))
    payment = doc.find(".//{*}Payment")
    pay = lambda tag: payment.findtext("{*}" + tag)
    assert pay("TaxablePay") == f"{shown_ps['taxable_pay']:.2f}" and pay("TaxDeductedOrRefunded") == f"{shown_ps['tax_amount']:.2f}"
    ni = doc.find(".//{*}NIlettersAndValues")
    assert ni.findtext("{*}EmpeeContribnsInPd") == f"{shown_ps['employee_ni']:.2f}"
    assert ni.findtext("{*}TotalEmpNICInPd") == f"{shown_ps['employer_ni']:.2f}"
    assert ni.findtext("{*}GrossEarningsForNICsInPd") == f"{shown_ps['ni_earnings']:.2f}"


def test_year_to_date_adds_up_this_employers_payslips_only(ready):
    emp = person(ready, p45_tax_year=2026, p45_taxable_pay=5000, p45_tax=1000)
    first = shown(ready, payslip(ready, emp, '2026-04-30'))
    second = shown(ready, payslip(ready, emp, '2026-05-29'))
    doc = xml_of(check(ready, "2026-05-29"))
    figs = doc.find(".//{*}FiguresToDate")
    # Not 5000 more and 1000 more: the P45 is for working out tax, not for telling HMRC.
    assert figs.findtext("{*}TaxablePay") == f"{first['taxable_pay'] + second['taxable_pay']:.2f}"
    assert figs.findtext("{*}TotalTax") == f"{first['tax_amount'] + second['tax_amount']:.2f}"
    ni = doc.find(".//{*}NIlettersAndValues")
    assert ni.findtext("{*}GrossEarningsForNICsYTD") == f"{first['ni_earnings'] + second['ni_earnings']:.2f}"
    assert ni.findtext("{*}GrossEarningsForNICsInPd") == f"{second['ni_earnings']:.2f}"
    assert doc.find(".//{*}Payment").findtext("{*}MonthNo") == "2"


def test_a_voided_payslip_does_not_count_towards_the_year_to_date(ready):
    emp = person(ready)
    first = payslip(ready, emp, "2026-04-30")
    second = shown(ready, payslip(ready, emp, "2026-05-29"))
    with main.SessionLocal() as db:
        db.query(models.DBPayslip).filter(models.DBPayslip.id == first["id"]).update({"status": "Void"})
        db.commit()
    figs = xml_of(check(ready, "2026-05-29")).find(".//{*}FiguresToDate")
    assert figs.findtext("{*}TaxablePay") == f"{second['taxable_pay']:.2f}"


def test_a_later_payslip_does_not_leak_into_an_earlier_filing(ready):
    emp = person(ready)
    first = shown(ready, payslip(ready, emp, '2026-04-30'))
    payslip(ready, emp, "2026-05-29")
    figs = xml_of(check(ready, "2026-04-30")).find(".//{*}FiguresToDate")
    assert figs.findtext("{*}TaxablePay") == f"{first['taxable_pay']:.2f}"


def test_a_change_of_ni_category_gives_a_block_for_each_letter(ready):
    emp = person(ready)
    payslip(ready, emp, "2026-04-30")
    ready.put(f"/api/employees/{emp['id']}", json={"ni_category": "H"})
    payslip(ready, emp, "2026-05-29")
    doc = xml_of(check(ready, "2026-05-29"))
    blocks = {b.findtext("{*}NIletter"): b for b in doc.iterfind(".//{*}NIlettersAndValues")}
    assert set(blocks) == {"A", "H"}
    assert blocks["A"].findtext("{*}GrossEarningsForNICsInPd") == "0.00" and float(blocks["A"].findtext("{*}GrossEarningsForNICsYTD")) > 0
    assert float(blocks["H"].findtext("{*}GrossEarningsForNICsInPd")) > 0


def test_student_loan_is_whole_pounds_with_its_plan(ready):
    emp = person(ready, student_loan_plan="2", salary=4000.0)
    payslip(ready, emp, "2026-04-30")
    doc = xml_of(check(ready, "2026-04-30"))
    loan = doc.find(".//{*}StudentLoanRecovered")
    assert loan is not None and loan.get("PlanType") == "02" and loan.text.endswith(".00")
    assert doc.find(".//{*}FiguresToDate/{*}StudentLoansTD").text.endswith(".00")


def pension_on(tenant, method):
    res = tenant.put("/api/pension/scheme", json={"enabled": True, "provider": "NEST", "employer_pct": 3,
                                                  "employee_pct": 5, "method": method})
    assert res.status_code == 200, res.text


def test_a_net_pay_pension_is_reported_as_paid_under_net_pay(ready):
    pension_on(ready, "net_pay")
    emp = person(ready, date_of_birth="1990-05-17")
    ps = shown(ready, payslip(ready, emp, '2026-04-30'))
    doc = xml_of(check(ready, "2026-04-30"))
    assert ps["pension_employee"] > 0
    assert doc.findtext(".//{*}Payment/{*}EmpeePenContribnsPaid") == f"{ps['pension_employee']:.2f}"
    assert doc.find(".//{*}Payment/{*}EmpeePenContribnsNotPaid") is None


def test_a_relief_at_source_pension_is_reported_as_not_under_net_pay(ready):
    pension_on(ready, "relief_at_source")
    emp = person(ready)
    ps = shown(ready, payslip(ready, emp, '2026-04-30'))
    doc = xml_of(check(ready, "2026-04-30"))
    assert doc.findtext(".//{*}Payment/{*}EmpeePenContribnsNotPaid") == f"{ps['pension_employee']:.2f}"
    assert doc.find(".//{*}Payment/{*}EmpeePenContribnsPaid") is None


# --- starters, leavers, directors ---------------------------------------------------------------
def test_a_new_starter_is_reported_on_their_first_payment_only(ready):
    emp = person(ready, start_date="2026-04-20", starter_declaration="A")
    payslip(ready, emp, "2026-04-30")
    payslip(ready, emp, "2026-05-29")
    first = check(ready, "2026-04-30")
    assert first["ok"] and first["starters"] == [f"{emp['first_name']} {emp['last_name']}"]
    doc = xml_of(first)
    assert text(doc, "StartDate") == ["2026-04-20"] and text(doc, "StartDec") == ["A"]
    assert xml_of(check(ready, "2026-05-29")).find(".//{*}Starter") is None


def test_someone_who_started_in_an_earlier_year_is_not_a_starter(ready):
    payslip(ready, person(ready, start_date="2020-01-06"), "2026-04-30")
    assert xml_of(check(ready, "2026-04-30")).find(".//{*}Starter") is None


def test_a_starter_with_no_declaration_is_named_and_blocked(ready):
    emp = person(ready, start_date="2026-04-20", starter_declaration="")
    payslip(ready, emp, "2026-04-30")
    got = check(ready, "2026-04-30")
    assert got["ok"] is False and any(emp["last_name"] in p and "starter declaration" in p for p in got["problems"])


def test_a_starter_with_no_postcode_is_blocked_with_their_name(ready):
    emp = person(ready, start_date="2026-04-20", starter_declaration="A", address="1 High Street, Leeds")
    payslip(ready, emp, "2026-04-30")
    got = check(ready, "2026-04-30")
    assert got["ok"] is False and any(emp["last_name"] in p and "address" in p for p in got["problems"]), got["problems"]


def test_a_starter_with_a_student_loan_says_so(ready):
    emp = person(ready, start_date="2026-04-20", starter_declaration="B", student_loan_plan="1", postgrad_loan=True)
    payslip(ready, emp, "2026-04-30")
    doc = xml_of(check(ready, "2026-04-30"))
    assert doc.findtext(".//{*}Starter/{*}StudentLoan") == "yes" and doc.findtext(".//{*}Starter/{*}PostgradLoan") == "yes"


def test_the_final_payment_to_a_leaver_carries_the_leaving_date(ready):
    emp = person(ready)
    ready.put(f"/api/employees/{emp['id']}", json={"end_date": "2026-05-29"})
    payslip(ready, emp, "2026-04-30")
    payslip(ready, emp, "2026-05-29")
    assert xml_of(check(ready, "2026-04-30")).find(".//{*}LeavingDate") is None
    assert text(xml_of(check(ready, "2026-05-29")), "LeavingDate") == ["2026-05-29"]


def test_a_director_is_reported_with_the_annual_method(ready):
    emp = person(ready, is_director=True, director_since="2026-04-06")
    payslip(ready, emp, "2026-04-30")
    doc = xml_of(check(ready, "2026-04-30"))
    assert text(doc, "DirectorsNIC") == ["AN"] and doc.find(".//{*}TaxWkOfApptOfDirector") is None


def test_a_director_appointed_later_in_the_year_gives_the_week(ready):
    emp = person(ready, is_director=True, director_since="2026-06-01")
    payslip(ready, emp, "2026-06-30")
    assert text(xml_of(check(ready, "2026-06-30")), "TaxWkOfApptOfDirector") == ["9"]


# --- what stops a submission, said by name --------------------------------------------------------------
@pytest.mark.parametrize("fields,says", [
    ({"gender": ""}, "gender"), ({"date_of_birth": ""}, "date of birth"), ({"hours_band": "", "employment_type": "part_time"}, "weekly hours"),
])
def test_missing_details_are_named_with_the_person(ready, fields, says):
    emp = person(ready, **fields)
    payslip(ready, emp, "2026-04-30")
    got = check(ready, "2026-04-30")
    assert got["ok"] is False and any(emp["last_name"] in p and says in p for p in got["problems"]), got["problems"]


def test_full_time_staff_default_to_the_thirty_hour_band(ready):
    emp = person(ready, hours_band="", employment_type="full_time")
    payslip(ready, emp, "2026-04-30")
    assert text(xml_of(check(ready, "2026-04-30")), "HoursWorked") == ["D"]


def test_no_ni_number_is_allowed_with_an_address_and_a_birth_date(ready):
    payslip(ready, person(ready, ni_number=""), "2026-04-30")
    got = check(ready, "2026-04-30")
    assert got["ok"] is True and xml_of(got).find(".//{*}NINO") is None


def test_no_ni_number_and_no_address_is_blocked(ready):
    emp = person(ready, ni_number="", address="")
    payslip(ready, emp, "2026-04-30")
    got = check(ready, "2026-04-30")
    assert got["ok"] is False and any("NI number" in p and "postcode" in p for p in got["problems"])


def test_a_value_hmrcs_schema_refuses_comes_back_in_plain_words(ready):
    # A number the NI-number check on the form lets through but HMRC's schema does not.
    emp = person(ready)
    with main.SessionLocal() as db:
        db.query(models.DBEmployee).filter(models.DBEmployee.id == emp["id"]).update({"ni_number": "ZZ123456C"})
        db.commit()
    payslip(ready, emp, "2026-04-30")
    got = check(ready, "2026-04-30")
    assert got["ok"] is False and any("NINO" in p for p in got["problems"]), got["problems"]


def test_two_payslips_on_one_day_for_one_person_are_flagged(ready):
    emp = person(ready)
    ps = payslip(ready, emp, "2026-04-30")
    with main.SessionLocal() as db:
        one = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps["id"]).first()
        db.add(models.DBPayslip(client_id=one.client_id, employee_id=one.employee_id, number="PS-9999", pay_date=one.pay_date,
                                period_start="2026-04-15", period_end="2026-04-30", regime="uk", tax_year=2026,
                                taxable_pay=10, ni_category="A", status="Draft"))
        db.commit()
    got = check(ready, "2026-04-30")
    assert got["ok"] is False and any("more than one payslip" in p for p in got["problems"])


def test_a_void_payslip_is_not_reported(ready):
    emp = person(ready)
    ps = payslip(ready, emp, "2026-04-30")
    with main.SessionLocal() as db:
        db.query(models.DBPayslip).filter(models.DBPayslip.id == ps["id"]).update({"status": "Void"})
        db.commit()
    assert ready.post("/api/hmrc/rti/fps/check", json={"pay_date": "2026-04-30"}).status_code == 404


def test_a_year_hmrcs_pack_is_not_installed_for_is_said(ready):
    res = ready.post("/api/hmrc/rti/fps/check", json={"pay_date": "2031-06-30"})
    assert res.status_code == 400 and "2031-32" in res.json()["detail"]


def test_a_late_reason_must_be_one_hmrc_has(ready):
    payslip(ready, person(ready), "2026-04-30")
    assert ready.post("/api/hmrc/rti/fps/check", json={"pay_date": "2026-04-30", "late_reason": "Z"}).status_code == 400
    got = check(ready, "2026-04-30", late_reason="G")
    assert got["ok"] and text(xml_of(got), "LateReason") == ["G"]


def test_checking_records_nothing_and_sends_nothing(ready, monkeypatch):
    gw = good_gateway()
    platform(monkeypatch, gateway=gw)
    payslip(ready, person(ready), "2026-04-30")
    check(ready, "2026-04-30")
    assert gw.sent == [] and ready.get("/api/hmrc/rti").json()["submissions"] == []


# --- sending ---------------------------------------------------------------------------------------------
def test_it_will_not_send_until_everything_is_in_place_and_says_who_must_fix_what(ready):
    payslip(ready, person(ready), "2026-04-30")
    res = ready.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    assert res.status_code == 503
    said = res.json()["detail"]
    assert "Vendor ID" in said and "the platform" in said and "Government Gateway" in said and "(you)" in said


def set_up_to_send(tenant, monkeypatch, mode="test", gateway=None):
    platform(monkeypatch, mode=mode, gateway=gateway)
    go_uk(tenant)
    business(tenant, gateway_password="gw-password")


def test_a_submission_is_sent_polled_and_recorded_as_accepted(tenant, monkeypatch):
    gw = good_gateway()
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    payslip(tenant, person(tenant), "2026-04-30")
    got = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()
    assert got["ok"] is True and got["status"] == "accepted" and got["sent"] is True and got["correlation_id"] == "CORR123"
    assert gw.qualifiers() == [("request", "submit"), ("poll", "submit"), ("request", "delete")]
    # What went out: the business's own Gateway details, the platform's vendor ID, and the test flag.
    sent = etree.fromstring(gw.sent[0][1])
    assert sent.findtext(".//{*}SenderID") == "123456789012" and sent.findtext(".//{*}Authentication/{*}Value") == "gw-password"
    assert sent.findtext(".//{*}Channel/{*}URI") == "9999" and sent.findtext(".//{*}GatewayTest") == "1"
    assert sent.findtext(".//{*}Class") == "HMRC-PAYE-RTI-FPS"
    log = tenant.get("/api/hmrc/rti").json()["submissions"]
    assert len(log) == 1 and log[0]["status"] == "accepted" and log[0]["mode"] == "test" and log[0]["people"] == 1


def test_the_record_keeps_the_message_but_never_the_password(tenant, monkeypatch):
    set_up_to_send(tenant, monkeypatch, gateway=good_gateway())
    payslip(tenant, person(tenant), "2026-04-30")
    tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    sid = tenant.get("/api/hmrc/rti").json()["submissions"][0]["id"]
    full = tenant.get(f"/api/hmrc/rti/submissions/{sid}").json()
    assert "IRenvelope" in full["body_xml"] and "AB123456C" in full["body_xml"]
    assert "gw-password" not in json.dumps(full) and "123456789012" not in full["body_xml"]


def test_the_pay_date_list_shows_not_sent_then_tested_then_sent(tenant, monkeypatch):
    gw1 = good_gateway()
    set_up_to_send(tenant, monkeypatch, gateway=gw1)
    payslip(tenant, person(tenant), "2026-04-30")
    state = lambda: tenant.get("/api/hmrc/rti").json()["pay_dates"][0]["state"]
    assert state() == "not_sent"
    tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    assert state() == "tested"
    platform(monkeypatch, mode="live", gateway=good_gateway())
    tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    assert state() == "sent"


def test_live_mode_turns_the_test_flag_off(tenant, monkeypatch):
    gw = good_gateway()
    set_up_to_send(tenant, monkeypatch, mode="live", gateway=gw)
    payslip(tenant, person(tenant), "2026-04-30")
    tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    assert etree.fromstring(gw.sent[0][1]).findtext(".//{*}GatewayTest") == "0"


def test_a_live_day_already_accepted_is_not_sent_twice_by_accident(tenant, monkeypatch):
    set_up_to_send(tenant, monkeypatch, mode="live", gateway=good_gateway())
    payslip(tenant, person(tenant), "2026-04-30")
    assert tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()["status"] == "accepted"
    again = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    assert again.status_code == 409 and "already accepted" in again.json()["detail"]
    platform(monkeypatch, mode="live", gateway=good_gateway())
    assert tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30", "confirm_resend": True}).json()["status"] == "accepted"


def test_a_starter_already_told_to_hmrc_live_is_not_a_starter_again(tenant, monkeypatch):
    set_up_to_send(tenant, monkeypatch, mode="live", gateway=good_gateway())
    emp = person(tenant, start_date="2026-04-20", starter_declaration="A")
    payslip(tenant, emp, "2026-04-30")
    assert tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()["status"] == "accepted"
    platform(monkeypatch, mode="live", gateway=good_gateway())
    again = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30", "confirm_resend": True}).json()
    assert again["status"] == "accepted" and again["starters"] == []


def test_hmrcs_refusal_is_recorded_with_its_reasons(tenant, monkeypatch):
    gw = Gateway(reply("error", errors=[("1046", "Authentication Failure.", "")]), reply("error"))
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    payslip(tenant, person(tenant), "2026-04-30")
    got = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()
    assert got["ok"] is False and got["status"] == "refused" and got["hmrc_errors"][0]["number"] == "1046"
    row = tenant.get("/api/hmrc/rti").json()["submissions"][0]
    assert row["status"] == "refused" and row["hmrc_errors"][0]["text"].startswith("Authentication")


def test_a_gateway_that_is_down_is_recorded_as_failed(tenant, monkeypatch):
    gw = Gateway(hmrc_rti.RtiError("HMRC's Gateway answered with an error (503); nothing was recorded - try again later"))
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    payslip(tenant, person(tenant), "2026-04-30")
    got = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()
    assert got["status"] == "failed" and "503" in got["problems"][0]
    assert tenant.get("/api/hmrc/rti").json()["submissions"][0]["status"] == "failed"


def test_still_waiting_is_recorded_as_sent_not_accepted(tenant, monkeypatch):
    gw = Gateway(*[reply("acknowledgement", endpoint="https://gateway.example/poll")] * 30)
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    payslip(tenant, person(tenant), "2026-04-30")
    got = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()
    assert got["ok"] is False and got["status"] == "sent"


def test_a_message_hmrcs_rules_refuse_is_never_sent(tenant, monkeypatch):
    gw = good_gateway()
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    emp = person(tenant)
    with main.SessionLocal() as db:
        db.query(models.DBEmployee).filter(models.DBEmployee.id == emp["id"]).update({"ni_number": "ZZ123456C"})
        db.commit()
    payslip(tenant, emp, "2026-04-30")
    got = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()
    assert got["ok"] is False and got["status"] == "rejected" and got["sent"] is False
    assert gw.sent == []
    assert tenant.get("/api/hmrc/rti").json()["submissions"][0]["status"] == "rejected"


def test_a_missing_detail_is_never_sent_either(tenant, monkeypatch):
    gw = good_gateway()
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    payslip(tenant, person(tenant, gender=""), "2026-04-30")
    got = tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"}).json()
    assert got["status"] == "rejected" and gw.sent == []


def test_the_irmark_is_added_only_when_asked_for(tenant, monkeypatch):
    gw = good_gateway()
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    payslip(tenant, person(tenant), "2026-04-30")
    tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    assert etree.fromstring(gw.sent[0][1]).find(".//{*}IRmark") is None
    gw2 = good_gateway()
    platform(monkeypatch, gateway=gw2, HMRC_RTI_IRMARK="1")
    tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    assert etree.fromstring(gw2.sent[0][1]).find(".//{*}IRmark") is not None


# --- Employer Payment Summary -----------------------------------------------------------------------------
def eps(tenant, path="check", **body):
    res = tenant.post(f"/api/hmrc/rti/eps/{path}", json=body)
    return res


def test_a_month_with_no_pay_can_be_reported(ready):
    res = eps(ready, no_payment_from="2026-05-06", no_payment_to="2026-06-05")
    assert res.status_code == 200 and res.json()["ok"] is True
    doc = xml_of(res.json())
    assert text(doc, "NoPaymentForPeriod") == ["yes"] and text(doc, "From") == ["2026-05-06"]


def test_the_employment_allowance_can_be_reported(ready):
    assert eps(ready, employment_allowance=True).json()["ok"] is True


@pytest.mark.parametrize("body,says", [
    ({}, "Choose what to tell HMRC"), ({"no_payment_from": "2026-05-06"}, "both"),
    ({"no_payment_from": "2026-06-05", "no_payment_to": "2026-05-06"}, "cannot be before"),
    ({"recoverable": {"smp": 100}}, "tax month"), ({"recoverable": {"smp": "lots"}, "recoverable_month": 3}, "amounts"),
])
def test_an_incomplete_summary_is_refused(ready, body, says):
    res = eps(ready, **body)
    assert res.status_code == 400 and says in res.json()["detail"], res.text


def test_a_summary_is_sent_and_recorded(tenant, monkeypatch):
    gw = Gateway(reply("acknowledgement", endpoint="https://gateway.example/poll"), reply("response"), reply("response"))
    set_up_to_send(tenant, monkeypatch, gateway=gw)
    got = eps(tenant, "send", no_payment_from="2026-05-06", no_payment_to="2026-06-05").json()
    assert got["status"] == "accepted"
    assert etree.fromstring(gw.sent[0][1]).findtext(".//{*}Class") == "HMRC-PAYE-RTI-EPS"
    row = tenant.get("/api/hmrc/rti").json()["submissions"][0]
    assert row["kind"] == "EPS" and "no payments" in row["summary"]


# --- one business never sees another's -----------------------------------------------------------------------
def test_another_business_cannot_see_these_filings(tenant, monkeypatch, client):
    set_up_to_send(tenant, monkeypatch, gateway=good_gateway())
    payslip(tenant, person(tenant), "2026-04-30")
    tenant.post("/api/hmrc/rti/fps/send", json={"pay_date": "2026-04-30"})
    sid = tenant.get("/api/hmrc/rti").json()["submissions"][0]["id"]

    from fastapi.testclient import TestClient
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": "rival@example.com", "password": "Passw0rdTest", "company_name": "Rival"})
        other.post("/api/client/login", json={"email": "rival@example.com", "password": "Passw0rdTest"})
        assert other.get(f"/api/hmrc/rti/submissions/{sid}").status_code == 404
        assert other.get("/api/hmrc/rti").json()["submissions"] == []
        assert other.get("/api/hmrc/rti").json()["employer"]["paye_ref"] == ""


def set_plan(tenant, modules):
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        db.query(models.DBClient).filter(models.DBClient.id == cid).update({"modules": modules})
        db.commit()


def test_payroll_filings_belong_to_the_hr_plan(tenant):
    assert main.module_for_path("/api/hmrc/rti") == "hr"
    assert main.module_for_path("/api/hmrc/rti/fps/send") == "hr"
    set_plan(tenant, "invoicing")
    for method, path in (("get", "/api/hmrc/rti"), ("put", "/api/hmrc/rti/settings"), ("post", "/api/hmrc/rti/fps/check"),
                         ("post", "/api/hmrc/rti/fps/send"), ("get", "/api/hmrc/rti/submissions/1")):
        res = getattr(tenant, method)(path)
        assert res.status_code == 403, (path, res.status_code)
    set_plan(tenant, "hr")
    assert tenant.get("/api/hmrc/rti").status_code == 200


def test_the_endpoints_need_a_login(client):
    for method, path in (("get", "/api/hmrc/rti"), ("put", "/api/hmrc/rti/settings"), ("post", "/api/hmrc/rti/fps/check"),
                         ("post", "/api/hmrc/rti/fps/send"), ("post", "/api/hmrc/rti/eps/check"), ("post", "/api/hmrc/rti/eps/send"),
                         ("get", "/api/hmrc/rti/submissions/1")):
        assert getattr(client, method)(path).status_code in (401, 403), path
