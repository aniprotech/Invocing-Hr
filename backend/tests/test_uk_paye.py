"""The UK PAYE engine, against payslips worked by hand.

Every expected figure below is worked from HMRC's published 2026-27 rates
and thresholds (see backend/uk_paye.py for the source), not produced by the
code and copied back. Where the working is not obvious it is written out.
"""
from datetime import date
from decimal import Decimal as D

import pytest

import uk_paye as P


def tax(code="1257L", frequency="monthly", period=1, gross="3000", ytd_pay="0", ytd_tax="0", extra=False):
    return P.income_tax(code=code, frequency=frequency, period=period, gross_this=D(gross),
                        gross_to_date_before=D(ytd_pay), tax_to_date_before=D(ytd_tax), extra_week=extra)


# --- the calendar -------------------------------------------------------------
def test_the_tax_year_starts_on_6_april():
    assert P.tax_year_of(date(2026, 4, 5)) == 2025
    assert P.tax_year_of(date(2026, 4, 6)) == 2026
    assert P.tax_year_of(date(2027, 4, 5)) == 2026
    assert P.tax_year_label(2026) == "2026-27"


def test_month_1_runs_from_6_april_to_5_may():
    assert P.tax_month(date(2026, 4, 6)) == 1
    assert P.tax_month(date(2026, 5, 5)) == 1
    assert P.tax_month(date(2026, 5, 6)) == 2
    assert P.tax_month(date(2027, 3, 31)) == 12
    assert P.tax_month(date(2027, 4, 5)) == 12


def test_week_1_runs_from_6_to_12_april_and_there_can_be_a_week_53():
    assert P.tax_week(date(2026, 4, 6)) == 1
    assert P.tax_week(date(2026, 4, 12)) == 1
    assert P.tax_week(date(2026, 4, 13)) == 2
    # 6 April 2026 + 364 days is 5 April 2027: the 53rd week.
    assert P.tax_week(date(2027, 4, 5)) == 53
    assert P.tax_period(date(2027, 4, 5), "weekly") == (2026, 53, True)


def test_the_period_is_set_by_the_pay_date():
    assert P.tax_period(date(2026, 6, 30), "monthly") == (2026, 3, False)


def test_pay_frequencies_are_named_the_ways_people_write_them():
    assert P.frequency_key("Fortnightly") == "biweekly"
    assert P.frequency_key("4-weekly") == "fourweekly"
    assert P.frequency_key("bi-weekly") == "biweekly"
    with pytest.raises(P.PayeError):
        P.frequency_key("daily")


def test_a_year_with_no_rates_loaded_says_so_rather_than_guessing():
    with pytest.raises(P.PayeError, match="2027-28"):
        P.rates_for(2027)


# --- tax codes ----------------------------------------------------------------
@pytest.mark.parametrize("code,region,kind,number,cumulative", [
    ("1257L", "rUK", "allowance", 1257, True),
    ("1257l", "rUK", "allowance", 1257, True),
    ("S1257L", "scotland", "allowance", 1257, True),
    ("C1257L", "wales", "allowance", 1257, True),
    ("1257L W1", "rUK", "allowance", 1257, False),
    ("1257LM1", "rUK", "allowance", 1257, False),
    ("1257L X", "rUK", "allowance", 1257, False),
    ("K475", "rUK", "k", 475, True),
    ("SK475", "scotland", "k", 475, True),
    ("0T", "rUK", "zero", 0, True),
    ("C0T", "wales", "zero", 0, True),
    ("NT", "rUK", "nt", 0, True),
])
def test_tax_codes_are_read(code, region, kind, number, cumulative):
    tc = P.parse_tax_code(code)
    assert (tc.region, tc.kind, tc.number, tc.cumulative) == (region, kind, number, cumulative)


def test_a_code_is_written_back_the_way_a_payslip_shows_it():
    assert P.parse_tax_code("1257lm1").raw == "1257L M1"
    assert P.parse_tax_code("s1257l").raw == "S1257L"
    assert P.parse_tax_code("0T X").raw == "0T X"
    assert P.parse_tax_code("1257L/W1").raw == "1257L W1"
    assert P.parse_tax_code("1257L W1/M1").raw == "1257L W1/M1"
    assert not P.parse_tax_code("1257L W1/M1").cumulative


def test_flat_rate_codes_are_read():
    assert P.parse_tax_code("BR").flat_code == "BR"
    assert P.parse_tax_code("SD0").region == "scotland"
    assert P.parse_tax_code("D1").kind == "flat"


def test_a_code_that_is_not_a_code_is_refused():
    for bad in ("", "1257", "XYZ", "L1257", "K", "D9", "1257Q"):
        with pytest.raises(P.PayeError):
            P.parse_tax_code(bad)


def test_d3_is_scottish_only():
    assert P.tax_code_problem("SD3") == ""
    assert "not a" in P.tax_code_problem("D3")


def test_the_code_number_times_ten_plus_nine_is_the_years_tax_free_pay():
    assert P.parse_tax_code("1257L").annual_adjustment == D("12579")
    assert P.parse_tax_code("K475").annual_adjustment == D("-4759")
    assert P.parse_tax_code("0T").annual_adjustment == D("0")


# --- Income Tax, England ----------------------------------------------------------
def test_a_month_1_payslip_on_1257l():
    # free pay 12,579 / 12 = 1,048.25; taxable 3,000 - 1,048.25 = 1,951.75 -> 1,951
    # basic band to date 37,700 / 12 = 3,141.67 -> 3,142; 1,951 x 20% = 390.20
    r = tax(gross="3000")
    assert r["free_pay_to_date"] == D("1048.25")
    assert r["taxable_pay_to_date"] == D("1951")
    assert r["tax"] == D("390.20")


def test_month_2_is_worked_on_the_year_so_far():
    # to date: pay 6,000, free 2,096.50, taxable 3,903 x 20% = 780.60; less 390.20 paid
    r = tax(period=2, gross="3000", ytd_pay="3000", ytd_tax="390.20")
    assert r["taxable_pay_to_date"] == D("3903")
    assert r["tax"] == D("390.40")


def test_higher_rate_starts_where_the_basic_band_to_date_ends():
    # taxable 6,000 - 1,048.25 = 4,951; basic 3,142 x 20% = 628.40;
    # the rest, 1,809, inside the higher band (87,440 / 12 -> 7,287) x 40% = 723.60
    r = tax(gross="6000")
    assert r["tax"] == D("1352.00")


def test_additional_rate_above_the_higher_band():
    # month 1, 20,000: taxable 18,951; basic 3,142 = 628.40; higher 7,287 = 2,914.80;
    # additional 18,951 - 3,142 - 7,287 = 8,522 x 45% = 3,834.90
    r = tax(gross="20000")
    assert r["tax"] == D("7378.10")


def test_week_1_month_1_ignores_the_year_so_far():
    # Month 6 on a this-period-only code is taxed exactly like month 1.
    assert tax(code="1257L M1", period=6, gross="3000", ytd_pay="15000", ytd_tax="0")["tax"] == D("390.20")
    # The same pay cumulatively, with nothing paid yet this year, is covered
    # by six months of tax-free pay.
    assert tax(code="1257L", period=6, gross="3000")["tax"] == D("0.00")


def test_the_emergency_x_suffix_is_this_period_only():
    assert tax(code="1257L X", period=9, gross="3000", ytd_pay="24000", ytd_tax="0")["basis"] == "week1/month1"


def test_over_deducted_tax_comes_back_on_a_cumulative_code():
    # month 3, 6,000 paid so far with 1,200 taken (too much); no pay this month.
    # free to date 3,144.75; taxable 2,855 x 20% = 571.00 due; 571 - 1,200 = a refund of 629.00
    assert tax(period=3, gross="0", ytd_pay="6000", ytd_tax="1200")["tax"] == D("-629.00")


def test_but_never_on_week_1_month_1():
    assert tax(code="1257L M1", period=3, gross="0", ytd_pay="6000", ytd_tax="1200")["tax"] == D("0")


def test_week_53_is_worked_on_week_1_alone():
    # 500 in week 53: free 12,579 / 52 = 241.9038 -> 241.91; taxable 258;
    # basic band 37,700 / 52 = 725 -> 258 x 20% = 51.60, whatever came before.
    r = tax(code="1257L", frequency="weekly", period=53, gross="500", ytd_pay="30000", ytd_tax="3500", extra=True)
    assert r["basis"] == "week1/month1"
    assert r["tax"] == D("51.60")


def test_weekly_and_fortnightly_count_in_weeks():
    # week 2 on a fortnightly payroll: free 12,579 x 2 / 52 = 483.8077 -> 483.81
    r = tax(frequency="biweekly", period=2, gross="1000")
    assert r["free_pay_to_date"] == D("483.81")
    # taxable 516 x 20% = 103.20
    assert r["tax"] == D("103.20")


# --- flat, zero and K codes ----------------------------------------------------------
def test_br_is_every_pound_at_basic_rate():
    assert tax(code="BR", gross="2000.99")["tax"] == D("400.00")


def test_d0_and_d1():
    assert tax(code="D0", gross="1000")["tax"] == D("400.00")
    assert tax(code="D1", gross="1000")["tax"] == D("450.00")


def test_nt_takes_nothing():
    assert tax(code="NT", gross="9000")["tax"] == D("0")


def test_0t_has_no_tax_free_pay_but_keeps_the_bands():
    assert tax(code="0T", gross="1000")["tax"] == D("200.00")


def test_a_k_code_adds_to_pay():
    # K500: 5,009 / 12 = 417.4167 -> 417.42 added; 1,000 + 417.42 -> 1,417 x 20% = 283.40
    r = tax(code="K500", gross="1000")
    assert r["tax"] == D("283.40") and not r["regulatory_limit_applied"]


def test_a_k_code_never_takes_more_than_half_the_pay():
    # K1000 on 200: 10,009 / 12 -> 834.09 added; 1,034 x 20% = 206.80, capped at 100.00
    r = tax(code="K1000", gross="200")
    assert r["tax"] == D("100.00") and r["regulatory_limit_applied"]


# --- Scotland and Wales ----------------------------------------------------------------
def test_a_scottish_code_uses_the_scottish_bands():
    # taxable 1,951; starter 3,967 / 12 -> 331 x 19% = 62.89;
    # basic 12,989 / 12 -> 1,083 x 20% = 216.60; intermediate on the last 537 x 21% = 112.77
    assert tax(code="S1257L", gross="3000")["tax"] == D("392.26")


def test_scottish_flat_codes_have_their_own_rates():
    assert tax(code="SBR", gross="1000")["tax"] == D("200.00")
    assert tax(code="SD0", gross="1000")["tax"] == D("210.00")
    assert tax(code="SD1", gross="1000")["tax"] == D("420.00")
    assert tax(code="SD3", gross="1000")["tax"] == D("480.00")


def test_a_welsh_code_matches_england_this_year():
    assert tax(code="C1257L", gross="6000")["tax"] == tax(code="1257L", gross="6000")["tax"]


# --- National Insurance ---------------------------------------------------------------------
def ni(category="A", frequency="monthly", earnings="3000"):
    return P.national_insurance(category=category, frequency=frequency, earnings=D(earnings))


def test_category_a_monthly():
    r = ni()
    assert r["employee"] == D("156.16")   # (3,000 - 1,048) x 8%
    assert r["employer"] == D("387.45")   # (3,000 - 417) x 15%


def test_above_the_upper_earnings_limit_the_employee_pays_2_percent():
    # (4,189 - 1,048) x 8% = 251.28; (6,000 - 4,189) x 2% = 36.22
    assert ni(earnings="6000")["employee"] == D("287.50")


def test_weekly_fortnightly_and_four_weekly_thresholds():
    assert ni(frequency="weekly", earnings="500")["employee"] == D("20.64")        # (500 - 242) x 8%
    assert ni(frequency="weekly", earnings="500")["employer"] == D("60.60")        # (500 - 96) x 15%
    assert ni(frequency="biweekly", earnings="1000")["employee"] == D("41.28")     # (1,000 - 484) x 8%
    assert ni(frequency="biweekly", earnings="1000")["employer"] == D("121.20")    # (1,000 - 192) x 15%
    assert ni(frequency="fourweekly", earnings="2000")["employee"] == D("82.56")   # (2,000 - 968) x 8%
    assert ni(frequency="fourweekly", earnings="2000")["employer"] == D("242.40")  # (2,000 - 384) x 15%


def test_under_the_secondary_threshold_nothing_is_paid_or_counted():
    r = ni(earnings="400")
    assert (r["employee"], r["employer"], r["earnings_at_lel"]) == (D("0"), D("0.00"), D("0"))


def test_the_employer_pays_below_the_lel_because_its_threshold_is_lower():
    """Since April 2025 the secondary threshold (417 a month) is below the
    lower earnings limit (559). So 500 a month costs the employee nothing
    and is not even counted for their record - but the employer owes 15% of
    the 83 above 417."""
    r = ni(earnings="500")
    assert r["employee"] == D("0") and r["earnings_at_lel"] == D("0")
    assert r["employer"] == D("12.45")


def test_between_lel_and_pt_the_earnings_count_but_the_employee_pays_nothing():
    r = ni(earnings="800")
    assert r["earnings_at_lel"] == D("559") and r["earnings_lel_to_pt"] == D("241")
    assert r["employee"] == D("0")
    assert r["employer"] == D("57.45")    # (800 - 417) x 15%


def test_under_21_apprentice_and_veteran_employers_pay_nothing_up_to_the_upper_threshold():
    for cat in "MHVZ":
        assert ni(category=cat, earnings="3000")["employer"] == D("0.00"), cat
    # ... and 15% above it: (5,000 - 4,189) x 15% = 121.65
    assert ni(category="M", earnings="5000")["employer"] == D("121.65")


def test_freeport_employers_pay_nothing_up_to_the_freeport_threshold():
    assert ni(category="F", earnings="3000")["employer"] == D("137.55")   # (3,000 - 2,083) x 15%


def test_category_c_over_state_pension_age_pays_nothing_but_the_employer_still_does():
    r = ni(category="C")
    assert r["employee"] == D("0") and r["employer"] == D("387.45")


def test_reduced_rate_and_deferment_categories():
    assert ni(category="B")["employee"] == D("36.11")   # 1,952 x 1.85% = 36.112
    assert ni(category="J")["employee"] == D("39.04")   # 1,952 x 2%


def test_half_a_penny_of_ni_goes_down():
    # Category B on 1,058: (1,058 - 1,048) x 1.85% = 0.185 exactly
    assert ni(category="B", earnings="1058")["employee"] == D("0.18")


def test_an_unknown_category_is_refused():
    with pytest.raises(P.PayeError):
        ni(category="Q")


# --- directors ---------------------------------------------------------------------------
def test_a_director_is_worked_on_the_year_not_the_month():
    # 16,000 so far this year against the annual thresholds:
    # employee (16,000 - 12,570) x 8% = 274.40; employer (16,000 - 5,000) x 15% = 1,650.00
    r = P.director_national_insurance(category="A", earnings_to_date=D("16000"),
                                      employee_ni_before=D("0"), employer_ni_before=D("0"))
    assert (r["employee"], r["employer"]) == (D("274.40"), D("1650.00"))
    # ... less what has already been taken
    r = P.director_national_insurance(category="A", earnings_to_date=D("16000"),
                                      employee_ni_before=D("100"), employer_ni_before=D("800"))
    assert (r["employee"], r["employer"]) == (D("174.40"), D("850.00"))


def test_a_director_paid_a_lump_early_in_the_year_pays_no_ni_on_it_yet():
    r = P.director_national_insurance(category="A", earnings_to_date=D("4000"),
                                      employee_ni_before=D("0"), employer_ni_before=D("0"))
    assert r["employee"] == D("0")


def test_a_director_appointed_mid_year_has_pro_rata_thresholds():
    # 26 weeks: PT 242 x 26 = 6,292; ST 96 x 26 = 2,496
    # employee (10,000 - 6,292) x 8% = 296.64; employer (10,000 - 2,496) x 15% = 1,125.60
    r = P.director_national_insurance(category="A", earnings_to_date=D("10000"), employee_ni_before=D("0"),
                                      employer_ni_before=D("0"), weeks_as_director=26)
    assert (r["employee"], r["employer"]) == (D("296.64"), D("1125.60"))


# --- student and postgraduate loans --------------------------------------------------------
def test_the_period_thresholds_match_the_figures_hmrc_publishes():
    """HMRC's table gives the monthly and weekly thresholds; ours are derived,
    and must come out identical."""
    published = {
        ("1", "monthly"): "2241.66", ("1", "weekly"): "517.30",
        ("2", "monthly"): "2448.75", ("2", "weekly"): "565.09",
        ("4", "monthly"): "2816.25", ("4", "weekly"): "649.90",
        ("5", "monthly"): "2083.33", ("5", "weekly"): "480.76",
    }
    for (plan, freq), figure in published.items():
        annual = P.RATES[2026]["student_loans"][plan]
        assert P._loan_threshold(annual, freq) == D(figure), (plan, freq)
    assert P._loan_threshold(P.RATES[2026]["postgrad_loan"], "monthly") == D("1750.00")
    assert P._loan_threshold(P.RATES[2026]["postgrad_loan"], "weekly") == D("403.84")


@pytest.mark.parametrize("plan,expected", [
    ("1", "68"),    # (3,000 - 2,241.66) x 9% = 68.25
    ("2", "49"),    # (3,000 - 2,448.75) x 9% = 49.61
    ("4", "16"),    # (3,000 - 2,816.25) x 9% = 16.54
    ("5", "82"),    # (3,000 - 2,083.33) x 9% = 82.50
])
def test_student_loans_are_whole_pounds_rounded_down(plan, expected):
    assert P.student_loan(plan=plan, frequency="monthly", earnings=D("3000")) == D(expected)


def test_a_weekly_student_loan():
    # (700 - 565.09) x 9% = 12.14 -> 12
    assert P.student_loan(plan="2", frequency="weekly", earnings=D("700")) == D("12")


def test_below_the_threshold_there_is_no_student_loan():
    assert P.student_loan(plan="2", frequency="monthly", earnings=D("2000")) == D("0")


def test_the_plan_can_be_written_plan_2():
    assert P.student_loan(plan="Plan 2", frequency="monthly", earnings=D("3000")) == D("49")


def test_a_plan_that_does_not_exist_is_refused():
    with pytest.raises(P.PayeError):
        P.student_loan(plan="3", frequency="monthly", earnings=D("3000"))


def test_a_postgraduate_loan():
    # (3,000 - 1,750) x 6% = 75
    assert P.postgraduate_loan(frequency="monthly", earnings=D("3000")) == D("75")


# --- one whole pay period --------------------------------------------------------------------
def test_a_whole_month_3_payslip():
    r = P.run_period(P.PayPeriod(
        gross=D("3000"), pay_date=date(2026, 6, 30), frequency="monthly", tax_code="1257L",
        ni_category="A", student_loan_plan="2",
        ytd=P.YearToDate(taxable_pay=D("6000"), tax=D("780.60"), ni_earnings=D("6000"),
                         employee_ni=D("312.32"), employer_ni=D("774.90"))))
    # to date: 9,000 - 3,144.75 = 5,855 x 20% = 1,171.00; less 780.60
    assert r["tax_period"] == 3 and r["tax_year_label"] == "2026-27"
    assert r["tax"] == D("390.40")
    assert (r["employee_ni"], r["employer_ni"], r["student_loan"]) == (D("156.16"), D("387.45"), D("49"))
    assert r["ytd_after"]["tax"] == D("1171.00")
    assert r["ytd_after"]["taxable_pay"] == D("9000")


def test_a_net_pay_pension_comes_off_before_tax_but_not_before_ni():
    r = P.run_period(P.PayPeriod(gross=D("3000"), pay_date=date(2026, 4, 30), frequency="monthly",
                                 pre_tax_deductions=D("150")))
    # taxable 2,850 - 1,048.25 = 1,801 x 20% = 360.20; NI still on 3,000
    assert r["tax"] == D("360.20") and r["employee_ni"] == D("156.16")


def test_salary_sacrifice_comes_off_before_both():
    r = P.run_period(P.PayPeriod(gross=D("3000"), pay_date=date(2026, 4, 30), frequency="monthly",
                                 pre_tax_deductions=D("150"), pre_ni_deductions=D("150")))
    assert r["employee_ni"] == D("144.16")    # (2,850 - 1,048) x 8%


def test_a_director_through_the_whole_period():
    r = P.run_period(P.PayPeriod(gross=D("4000"), pay_date=date(2026, 7, 31), frequency="monthly",
                                 is_director=True,
                                 ytd=P.YearToDate(taxable_pay=D("12000"), ni_earnings=D("12000"))))
    # 16,000 to date on the annual method; nothing taken before
    assert (r["employee_ni"], r["employer_ni"]) == (D("274.40"), D("1650.00"))
