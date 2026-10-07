"""Workplace pensions, through the app: the scheme, enrolment as payslips are
made, what comes off pay and goes in, and the actions people have a right to.

The rules and the arithmetic are proven in test_uk_pension.py. These are the
joins: that assessment follows the person, that nothing is saved by a
preview or an edit, that a net pay arrangement lowers tax and relief at
source does not, and that one business never sees another's.

The hand-worked month used throughout: 3,000 gross, 1257L, category A.
Qualifying earnings 3,000 - 520 = 2,480; employee 5% = 124.00, employer 3% = 74.40.
Net pay arrangement: taxable 2,876 - 1,048.25 = 1,827 x 20% = 365.40 tax.
Relief at source: tax on the full 3,000 = 390.20, and 80% of 124.00 = 99.20 leaves pay.
"""
import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def go_uk(tenant, **scheme):
    assert tenant.put("/api/payroll/settings", json={"regime": "uk"}).status_code == 200
    body = {"enabled": True, "provider": "NEST", "employer_pct": 3, "employee_pct": 5}
    body.update(scheme)
    res = tenant.put("/api/pension/scheme", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def person(tenant, **kw):
    fields = dict(salary=3000.0, tax_rate=0.0, pay_frequency="monthly", ni_number="AB123456C", tax_code="1257L",
                  ni_category="A", date_of_birth="1995-01-01")
    fields.update(kw)
    return make_employee(tenant, **fields)


def payslip(tenant, emp, pay_date, **kw):
    res = tenant.post("/api/payslips", json=dict(employee_id=emp["id"], period_start=pay_date[:8] + "01",
                                                 period_end=pay_date, pay_date=pay_date, **kw))
    assert res.status_code == 200, res.text
    return tenant.get(f"/api/payslips/{res.json()['id']}").json()


def employee(tenant, emp):
    return tenant.get(f"/api/employees/{emp['id']}").json()


def staff_row(tenant, emp):
    return next(r for r in tenant.get("/api/pension/staff").json()["staff"] if r["id"] == emp["id"])


# --- the scheme --------------------------------------------------------------------
def test_a_business_starts_with_no_pension_scheme(tenant):
    got = tenant.get("/api/pension/scheme").json()
    assert got["scheme"]["enabled"] is False
    assert got["thresholds"]["lower"] == 6240 and got["thresholds"]["trigger"] == 10000 and got["thresholds"]["upper"] == 50270
    assert "Regulator" in got["thresholds"]["source"]
    assert "Salary sacrifice" in got["not_built"]


def test_a_scheme_is_saved(tenant):
    got = go_uk(tenant, postponement_months=2, duties_start="2024-03-01")
    assert got["scheme"]["provider"] == "NEST" and got["scheme"]["postponement_months"] == 2
    assert got["next_reenrolment"] == "2027-03-01"


@pytest.mark.parametrize("body,says", [
    ({"employer_pct": 2, "employee_pct": 6}, "at least 3%"),
    ({"employer_pct": 3, "employee_pct": 4}, "at least 8%"),
    ({"postponement_months": 5}, "three months"),
    ({"basis": "basic", "employer_pct": 3, "employee_pct": 6}, "at least 4%"),
])
def test_a_scheme_under_the_law_is_refused(tenant, body, says):
    res = tenant.put("/api/pension/scheme", json={"enabled": True, "employer_pct": 3, "employee_pct": 5, **body})
    assert res.status_code == 400 and says in res.json()["detail"]


def test_with_the_scheme_off_payroll_is_as_it_was(tenant):
    tenant.put("/api/payroll/settings", json={"regime": "uk"})
    emp = person(tenant)
    ps = payslip(tenant, emp, "2026-04-30")
    assert ps["tax_amount"] == 390.20 and ps["net_pay"] == 2453.64 and ps["uk"]["pension"] is None
    assert employee(tenant, emp)["pension_status"] == ""


# --- enrolment as pay is worked ----------------------------------------------------------
def test_an_eligible_jobholder_is_enrolled_on_their_first_payslip(tenant):
    go_uk(tenant)
    emp = person(tenant)
    ps = payslip(tenant, emp, "2026-04-30")
    pen = ps["uk"]["pension"]
    assert (pen["pensionable"], pen["employee"], pen["employer"], pen["relief"]) == (2480.0, 124.0, 74.40, 0.0)
    assert ps["tax_amount"] == 365.40, "a net pay arrangement comes off before tax"
    assert ps["uk"]["employee_ni"] == 156.16, "but not before National Insurance"
    assert ps["total_deductions"] == 645.56 and ps["net_pay"] == 2354.44
    assert ps["standing_deduction"] == 0.0, "pension is its own line, not a mystery"
    e = employee(tenant, emp)
    assert (e["pension_status"], e["pension_joined_on"], e["pension_group"]) == ("member", "2026-04-30", "eligible_jobholder")
    assert e["pension_letter_due"] == "enrolment"


def test_relief_at_source_takes_tax_on_the_full_pay_and_80_percent_of_the_share(tenant):
    go_uk(tenant, method="relief_at_source")
    ps = payslip(tenant, person(tenant), "2026-04-30")
    pen = ps["uk"]["pension"]
    assert (pen["employee"], pen["relief"], pen["employer"]) == (99.20, 24.80, 74.40)
    assert ps["tax_amount"] == 390.20
    assert ps["net_pay"] == 2354.44, "the same take-home as a net pay arrangement: the tax saved is the relief claimed"


def test_the_next_month_carries_on_and_tax_follows_the_pay_after_the_deduction(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    ps = payslip(tenant, emp, "2026-05-29")
    assert ps["uk"]["pension"]["employee"] == 124.0
    # to date taxable 5,752 - 2,096.50 = 3,655 x 20% = 731.00 due, less 365.40 paid
    assert ps["tax_amount"] == 365.60
    assert ps["uk"]["year_to_date"]["taxable_pay"] == 5752.0


def test_a_preview_shows_the_pension_and_saves_nothing(tenant):
    go_uk(tenant)
    emp = person(tenant)
    got = tenant.post("/api/payroll/preview", json={"employee_id": emp["id"], "pay_date": "2026-04-30"}).json()
    assert got["pension_employee"] == 124.0 and got["pension_employer"] == 74.40
    assert employee(tenant, emp)["pension_status"] == ""


def test_editing_a_payslip_never_enrols_anybody(tenant):
    """Made before the scheme was on, edited after: the edit is not a reason to enrol."""
    tenant.put("/api/payroll/settings", json={"regime": "uk"})
    emp = person(tenant)
    ps = payslip(tenant, emp, "2026-04-30")
    go_uk(tenant)
    assert tenant.put(f"/api/payslips/{ps['id']}", json={"bonus": 100}).status_code == 200
    again = tenant.get(f"/api/payslips/{ps['id']}").json()
    assert again["uk"]["pension"] is None
    assert employee(tenant, emp)["pension_status"] == ""


# --- who is not enrolled ------------------------------------------------------------------
def test_a_non_eligible_jobholder_is_not_enrolled(tenant):
    go_uk(tenant)
    emp = person(tenant, salary=700.0)
    ps = payslip(tenant, emp, "2026-04-30")
    assert ps["uk"]["pension"] is None
    assert employee(tenant, emp)["pension_status"] == ""
    assert staff_row(tenant, emp)["next"] == "Not enrolled - may opt in"


def test_somebody_under_22_is_not_enrolled_however_much_they_earn(tenant):
    go_uk(tenant)
    emp = person(tenant, date_of_birth="2006-01-01")
    assert payslip(tenant, emp, "2026-04-30")["uk"]["pension"] is None


def test_without_a_date_of_birth_nobody_is_guessed_at_and_the_run_says_so(tenant):
    go_uk(tenant)
    person(tenant, date_of_birth="")
    res = tenant.post("/api/payroll/run", json={"period_start": "2026-04-01", "period_end": "2026-04-30", "pay_date": "2026-04-30"})
    assert res.status_code == 200, res.text
    assert any("date of birth" in w["reason"] for w in res.json()["warnings"])
    assert res.json()["total_pension_employee"] == 0


# --- postponement ------------------------------------------------------------------------------
def test_postponement_holds_them_then_enrols(tenant):
    go_uk(tenant, postponement_months=3)
    emp = person(tenant, start_date="2026-04-15")
    first = payslip(tenant, emp, "2026-04-30")
    assert first["uk"]["pension"] is None
    e = employee(tenant, emp)
    assert (e["pension_status"], e["pension_postponed_until"], e["pension_letter_due"]) == ("postponed", "2026-07-15", "postponement")
    assert staff_row(tenant, emp)["postponed_until"] == "2026-07-15"
    later = payslip(tenant, emp, "2026-07-31")
    assert later["uk"]["pension"]["employee"] == 124.0
    assert employee(tenant, emp)["pension_status"] == "member"


# --- the people's own rights ---------------------------------------------------------------------
def test_a_non_eligible_jobholder_who_opts_in_gets_the_employer_contribution(tenant):
    go_uk(tenant)
    emp = person(tenant, salary=700.0)
    res = tenant.post(f"/api/pension/staff/{emp['id']}/join", json={"date": "2026-04-01"})
    assert res.status_code == 200, res.text
    assert employee(tenant, emp)["pension_status"] == "member"
    pen = payslip(tenant, emp, "2026-04-30")["uk"]["pension"]
    # 700 - 520 = 180; 5% = 9.00, 3% = 5.40
    assert (pen["employee"], pen["employer"]) == (9.0, 5.40)


def test_an_entitled_worker_who_joins_gets_no_employer_contribution(tenant):
    go_uk(tenant)
    emp = person(tenant, salary=500.0)
    tenant.post(f"/api/pension/staff/{emp['id']}/join", json={"date": "2026-04-01"})
    ps = payslip(tenant, emp, "2026-04-30")
    assert employee(tenant, emp)["pension_status"] == "member"
    assert ps["uk"]["pension"] is None, "500 is under the lower limit: nothing is pensionable"


def test_already_a_member_cannot_join_again(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    assert tenant.post(f"/api/pension/staff/{emp['id']}/join", json={}).status_code == 409


def test_opting_out_in_the_first_month_repays_what_was_taken(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    res = tenant.post(f"/api/pension/staff/{emp['id']}/opt-out", json={"date": "2026-05-10"}).json()
    assert res["within_refund_window"] is True
    assert res["refund_due"] == 124.0 and res["employer_contributions_made"] == 74.40
    assert employee(tenant, emp)["pension_status"] == "opted_out"
    assert payslip(tenant, emp, "2026-05-29")["uk"]["pension"] is None, "contributions stop"


def test_opting_out_after_the_first_month_repays_nothing(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    res = tenant.post(f"/api/pension/staff/{emp['id']}/opt-out", json={"date": "2026-08-01"}).json()
    assert res["within_refund_window"] is False and res["refund_due"] == 0.0


def test_somebody_who_opted_out_is_not_pulled_back_in_by_the_next_payslip(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    tenant.post(f"/api/pension/staff/{emp['id']}/opt-out", json={"date": "2026-05-10"})
    payslip(tenant, emp, "2026-05-29")
    payslip(tenant, emp, "2026-06-30")
    assert employee(tenant, emp)["pension_status"] == "opted_out"


def test_only_a_member_can_opt_out(tenant):
    go_uk(tenant)
    emp = person(tenant)
    assert tenant.post(f"/api/pension/staff/{emp['id']}/opt-out", json={}).status_code == 409


def test_re_enrolment_puts_eligible_leavers_of_the_scheme_back_in(tenant):
    go_uk(tenant)
    a = person(tenant)
    b = person(tenant, salary=700.0)           # no longer eligible
    payslip(tenant, a, "2026-04-30")
    tenant.post(f"/api/pension/staff/{a['id']}/opt-out", json={"date": "2026-08-01"})
    tenant.post(f"/api/pension/staff/{b['id']}/join", json={})
    tenant.post(f"/api/pension/staff/{b['id']}/opt-out", json={"date": "2026-08-01"})
    res = tenant.post("/api/pension/reenrol", json={"date": "2026-12-01"}).json()
    assert [p["id"] for p in res["re_enrolled"]] == [a["id"]]
    e = employee(tenant, a)
    assert (e["pension_status"], e["pension_joined_on"], e["pension_letter_due"]) == ("member", "2026-12-01", "re_enrolment")
    assert employee(tenant, b)["pension_status"] == "opted_out"
    assert [s["id"] for s in res["skipped"]] == [b["id"]] and "no longer an eligible jobholder" in res["skipped"][0]["reason"]


def test_re_enrolment_says_who_it_could_not_do_rather_than_skipping_them(tenant):
    """A year with no thresholds loaded, and somebody with no date of birth,
    are both reasons it cannot assess - and both are named, not passed over."""
    go_uk(tenant)
    a = person(tenant)
    b = person(tenant, date_of_birth="")
    for e in (a, b):
        payslip(tenant, e, "2026-04-30") if e is a else None
    with main.SessionLocal() as db:
        db.query(models.DBEmployee).filter(models.DBEmployee.id.in_([a["id"], b["id"]])).update(
            {"pension_status": "opted_out"}, synchronize_session=False)
        db.commit()
    res = tenant.post("/api/pension/reenrol", json={"date": "2029-05-01"}).json()
    reasons = {s["id"]: s["reason"] for s in res["skipped"]}
    assert res["count"] == 0
    assert "No pension thresholds" in reasons[a["id"]] or "No PAYE rates" in reasons[a["id"]]
    assert reasons[b["id"]] == "no date of birth"


def test_actions_need_the_scheme_to_be_on(tenant):
    emp = person(tenant)
    for path in ("join", "opt-out"):
        assert tenant.post(f"/api/pension/staff/{emp['id']}/{path}", json={}).status_code == 409
    assert tenant.post("/api/pension/reenrol", json={}).status_code == 409


# --- the letter the law says they are owed ----------------------------------------------------------
def test_the_enrolment_letter_names_the_scheme_the_rates_and_how_to_opt_out(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    got = tenant.get(f"/api/pension/staff/{emp['id']}/letter").json()
    assert got["kind"] == "enrolment" and "enrolled" in got["subject"]
    assert "NEST" in got["body"] and "5%" in got["body"] and "3%" in got["body"]
    assert "opt out" in got["body"].lower() and "one month" in got["body"]


def test_once_sent_the_letter_is_no_longer_due(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    tenant.post(f"/api/pension/staff/{emp['id']}/letter-sent")
    assert employee(tenant, emp)["pension_letter_due"] == ""
    assert tenant.get(f"/api/pension/staff/{emp['id']}/letter").status_code == 404


def test_a_non_eligible_jobholder_has_a_letter_about_their_right_to_join(tenant):
    go_uk(tenant)
    emp = person(tenant, salary=700.0)
    payslip(tenant, emp, "2026-04-30")
    got = tenant.get(f"/api/pension/staff/{emp['id']}/letter?kind=non_eligible").json()
    assert "right to join" in got["subject"]


def test_an_unknown_letter_is_refused(tenant):
    go_uk(tenant)
    emp = person(tenant)
    assert tenant.get(f"/api/pension/staff/{emp['id']}/letter?kind=nonsense").status_code == 400


# --- the run and the report -------------------------------------------------------------------------
def test_the_run_says_what_the_pension_costs_on_top_of_pay(tenant):
    go_uk(tenant)
    person(tenant)
    res = tenant.post("/api/payroll/run", json={"period_start": "2026-04-01", "period_end": "2026-04-30", "pay_date": "2026-04-30"}).json()
    assert res["total_pension_employee"] == 124.0 and res["total_pension_employer"] == 74.40
    assert res["employer_cost"] == 3000 + 387.45 + 74.40


def test_the_staff_list_counts_where_everyone_stands(tenant):
    go_uk(tenant)
    a, b = person(tenant), person(tenant, salary=700.0)
    payslip(tenant, a, "2026-04-30")
    got = tenant.get("/api/pension/staff").json()
    assert got["counts"] == {"member": 1, "postponed": 0, "opted_out": 0, "not_in": 1} and got["scheme_enabled"] is True
    assert staff_row(tenant, a)["group_label"].startswith("Eligible jobholder")


def test_the_contributions_report_adds_up_and_exports(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    payslip(tenant, emp, "2026-05-29")
    got = tenant.get("/api/pension/contributions?from=2026-04-01&to=2026-04-30").json()
    assert len(got["rows"]) == 1 and got["totals"]["employee_deducted"] == 124.0 and got["totals"]["total"] == 198.4
    both = tenant.get("/api/pension/contributions").json()["totals"]
    assert both["employer"] == 148.8
    csv = tenant.get("/api/pension/contributions.csv")
    assert csv.status_code == 200 and "text/csv" in csv.headers["content-type"]
    assert "Deducted from employee" in csv.text and "AB123456C" in csv.text and csv.text.strip().splitlines()[-1].startswith("Total")


def test_a_void_payslip_is_not_in_the_report(tenant):
    go_uk(tenant)
    emp = person(tenant)
    ps = payslip(tenant, emp, "2026-04-30")
    with main.SessionLocal() as db:
        db.query(models.DBPayslip).filter(models.DBPayslip.id == ps["id"]).update({"status": "Void"})
        db.commit()
    assert tenant.get("/api/pension/contributions").json()["rows"] == []


# --- one business at a time ---------------------------------------------------------------------------
def test_another_business_has_its_own_scheme_and_sees_none_of_this(tenant, client, account):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    other = f"other-{account['email']}"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/pension/scheme").json()["scheme"]["enabled"] is False
    assert client.get("/api/pension/staff").json()["staff"] == []
    assert client.get("/api/pension/contributions").json()["rows"] == []
    assert client.post(f"/api/pension/staff/{emp['id']}/join", json={}).status_code == 409
    client.put("/api/pension/scheme", json={"enabled": True, "employer_pct": 3, "employee_pct": 5})
    assert client.post(f"/api/pension/staff/{emp['id']}/opt-out", json={}).status_code == 404


def test_signed_out_it_answers_nothing(client):
    client.post("/api/client/logout")
    assert client.get("/api/pension/scheme").status_code == 401
    assert client.get("/api/pension/staff").status_code == 401


# --- everywhere a payslip appears ----------------------------------------------------------------
@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(main.BackgroundTasks, "add_task", lambda self, func, *a, **kw: func(*a, **kw))
    monkeypatch.setattr(main, "send_email_background",
                        lambda to, subject, body, from_email, html_body=None, *a, **kw:
                        (sent.append({"to": to, "html": html_body or ""}), (True, "sent"))[1])
    return sent


def test_the_emailed_payslip_shows_the_pension_so_it_adds_up(tenant, outbox):
    go_uk(tenant)
    emp = person(tenant)
    ps = payslip(tenant, emp, "2026-04-30")
    assert tenant.post(f"/api/payslips/{ps['id']}/send", json={}).status_code == 200
    html = outbox[-1]["html"]
    assert "Workplace pension" in html and "124.00" in html


def test_the_staff_portal_payslip_shows_both_halves_of_their_pension(tenant, client):
    go_uk(tenant)
    emp = person(tenant, password="EmpPass123")
    ps = payslip(tenant, emp, "2026-04-30")
    main.rate_limiter._hits.clear()
    client.post("/api/client/logout")
    assert client.post("/api/employee/auth/login", json={"email": emp["email"], "password": "EmpPass123"}).status_code == 200
    got = client.get(f"/api/employee/payslips/{ps['id']}").json()["uk"]
    assert got["pension"] == {"employee": 124.0, "employer": 74.4, "relief": 0.0}
    assert got["year_to_date"]["pension_employer"] == 74.4


def test_the_year_to_date_carries_the_pension(tenant):
    go_uk(tenant)
    emp = person(tenant)
    payslip(tenant, emp, "2026-04-30")
    ps = payslip(tenant, emp, "2026-05-29")
    ytd = ps["uk"]["year_to_date"]
    assert (ytd["pension_employee"], ytd["pension_employer"]) == (248.0, 148.8)


def test_somebody_who_joins_later_is_not_charged_on_a_payslip_from_before(tenant):
    """A payslip dated before they joined is not a payslip of the scheme."""
    go_uk(tenant)
    emp = person(tenant, salary=700.0)
    tenant.post(f"/api/pension/staff/{emp['id']}/join", json={"date": "2026-06-01"})
    assert payslip(tenant, emp, "2026-04-30")["uk"]["pension"] is None
    assert payslip(tenant, emp, "2026-06-30")["uk"]["pension"]["employee"] == 9.0
