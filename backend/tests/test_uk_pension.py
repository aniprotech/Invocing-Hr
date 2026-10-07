"""The pension rules, against cases worked by hand from The Pensions
Regulator's published 2026-27 thresholds and the law's minimums."""
from datetime import date
from decimal import Decimal as D

import pytest

import uk_pension as P

SCHEME = P.clean_scheme({"enabled": True, "provider": "NEST", "employer_pct": 3, "employee_pct": 5})
ON = date(2026, 9, 30)


def group(dob, earnings, freq="monthly", on=ON):
    return P.worker_group(dob=dob, earnings=earnings, frequency=freq, on=on, year=2026)


# --- the thresholds ---------------------------------------------------------------
def test_the_thresholds_are_the_regulators_published_figures():
    assert P.thresholds_for(2026, "monthly") == (D("520"), D("833"), D("4189"))
    assert P.thresholds_for(2026, "weekly") == (D("120"), D("192"), D("967"))
    assert P.thresholds_for(2026, "biweekly") == (D("240"), D("384"), D("1934"))
    assert P.thresholds_for(2026, "fourweekly") == (D("480"), D("768"), D("3867"))
    assert P.thresholds_for(2026, "annual") == (D("6240"), D("10000"), D("50270"))


def test_a_year_with_no_thresholds_is_refused_not_guessed():
    with pytest.raises(P.PensionError, match="2027-28"):
        P.thresholds_for(2027, "monthly")


# --- age and State Pension age -------------------------------------------------------
def test_age_counts_whole_years():
    assert P.age_on(date(2000, 9, 30), date(2026, 9, 30)) == 26
    assert P.age_on(date(2000, 10, 1), date(2026, 9, 30)) == 25


@pytest.mark.parametrize("dob,expected", [
    (date(1955, 1, 1), date(2021, 1, 1)),        # 66
    (date(1960, 4, 5), date(2026, 4, 5)),        # last day before the rise: 66
    (date(1960, 4, 6), date(2026, 5, 6)),        # 66 and 1 month
    (date(1960, 5, 5), date(2026, 6, 5)),        # the same band: still +1 month
    (date(1960, 5, 6), date(2026, 7, 6)),        # next band: 66 and 2 months
    (date(1961, 3, 5), date(2028, 2, 5)),        # last band: 66 and 11 months
    (date(1961, 3, 6), date(2028, 3, 6)),        # 67
    (date(1970, 6, 15), date(2037, 6, 15)),
    (date(1977, 4, 5), date(2044, 4, 5)),        # last 67
])
def test_state_pension_age_follows_the_timetable(dob, expected):
    assert P.state_pension_age_date(dob) == expected


def test_after_the_67_band_the_law_says_68():
    assert P.state_pension_age_date(date(1990, 1, 1)) == date(2058, 1, 1)


# --- which kind of worker --------------------------------------------------------------
def test_an_eligible_jobholder_is_22_to_spa_earning_over_the_trigger():
    assert group(date(1995, 1, 1), "833.01") == "eligible_jobholder"


def test_earning_exactly_the_trigger_is_not_over_it():
    assert group(date(1995, 1, 1), "833") == "non_eligible_jobholder"


def test_between_the_lower_limit_and_the_trigger_is_a_non_eligible_jobholder():
    assert group(date(1995, 1, 1), "600") == "non_eligible_jobholder"


def test_at_or_under_the_lower_limit_is_an_entitled_worker():
    assert group(date(1995, 1, 1), "520") == "entitled_worker"
    assert group(date(1995, 1, 1), "100") == "entitled_worker"


def test_under_22_is_never_an_eligible_jobholder_however_much_they_earn():
    assert group(date(2005, 6, 1), "3000") == "non_eligible_jobholder"   # 21


def test_the_day_they_turn_22_they_are():
    assert group(date(2004, 10, 1), "3000", on=date(2026, 9, 30)) == "non_eligible_jobholder"   # 21, 22 tomorrow
    assert group(date(2004, 9, 30), "3000", on=date(2026, 9, 30)) == "eligible_jobholder"


def test_from_state_pension_age_they_are_non_eligible_even_on_high_pay():
    dob = date(1955, 1, 1)                                                # SPA 66, reached in 2021
    assert group(dob, "3000") == "non_eligible_jobholder"


def test_the_day_before_spa_they_still_are_eligible():
    dob = date(1970, 10, 1)                                               # SPA 1 Oct 2037
    assert group(dob, "3000", on=date(2037, 9, 30)) == "eligible_jobholder"
    assert group(dob, "3000", on=date(2037, 10, 1)) == "non_eligible_jobholder"


def test_under_16_and_75_and_over_are_not_covered():
    assert group(date(2012, 1, 1), "3000") == "none"
    assert group(date(1950, 9, 30), "3000", on=date(2026, 9, 30)) == "none"   # 76
    assert group(date(1951, 9, 30), "3000", on=date(2026, 9, 30)) == "none"   # exactly 75


def test_74_is_still_covered():
    assert group(date(1951, 10, 1), "3000", on=date(2026, 9, 30)) == "non_eligible_jobholder"


def test_no_date_of_birth_means_no_guess():
    with pytest.raises(P.PensionError, match="date of birth"):
        P.worker_group(dob=None, earnings=3000, frequency="monthly", on=ON, year=2026)


@pytest.mark.parametrize("freq,over,not_over", [("weekly", "192.01", "192"), ("biweekly", "384.01", "384"),
                                                  ("fourweekly", "768.01", "768"), ("monthly", "833.01", "833")])
def test_the_trigger_is_per_pay_period(freq, over, not_over):
    assert group(date(1995, 1, 1), over, freq) == "eligible_jobholder"
    assert group(date(1995, 1, 1), not_over, freq) == "non_eligible_jobholder"


# --- the scheme and the law's minimums ----------------------------------------------------
def test_the_standard_scheme_is_8_percent_with_3_from_the_employer():
    s = P.clean_scheme({"employer_pct": 3, "employee_pct": 5})
    assert (s["basis"], s["method"], s["employer_pct"], s["employee_pct"]) == ("qualifying", "net_pay", 3.0, 5.0)


@pytest.mark.parametrize("raw,says", [
    ({"employer_pct": 2, "employee_pct": 6}, "at least 3%"),
    ({"employer_pct": 3, "employee_pct": 4}, "together must pay at least 8%"),
    ({"basis": "basic", "employer_pct": 3, "employee_pct": 6}, "at least 4%"),
    ({"basis": "basic", "employer_pct": 4, "employee_pct": 4}, "together must pay at least 9%"),
    ({"basis": "total", "employer_pct": 3, "employee_pct": 3}, "together must pay at least 7%"),
    ({"basis": "nonsense"}, "qualifying earnings, basic pay or all pay"),
    ({"method": "magic"}, "net pay arrangement or relief at source"),
    ({"postponement_months": 4}, "up to three months"),
    ({"postponement_months": -1}, "up to three months"),
    ({"employer_pct": 101}, "between 0% and 100%"),
    ({"duties_start": "last week"}, "must be a date"),
])
def test_a_scheme_below_the_law_or_not_a_scheme_is_refused(raw, says):
    base = {"employer_pct": 3, "employee_pct": 5}
    with pytest.raises(P.PensionError, match=says):
        P.clean_scheme({**base, **raw})


def test_the_basic_pay_and_total_pay_minimums_are_accepted_exactly():
    assert P.clean_scheme({"basis": "basic", "employer_pct": 4, "employee_pct": 5})["basis"] == "basic"
    assert P.clean_scheme({"basis": "total", "employer_pct": 3, "employee_pct": 4})["basis"] == "total"


# --- what to do ---------------------------------------------------------------------------
def do(status="", until="", scheme=SCHEME, earnings="3000", dob=date(1995, 1, 1), start=None, on=ON):
    return P.assess(status=status, postponed_until=until, scheme=scheme, dob=dob, start_date=start,
                    earnings=earnings, frequency="monthly", on=on, year=2026)


def test_an_eligible_jobholder_with_no_postponement_is_enrolled():
    assert do()["action"] == "enrol"


def test_a_member_stays_a_member_even_if_pay_falls_below_the_trigger():
    assert do(status="member", earnings="300")["action"] == "member"


def test_somebody_who_opted_out_is_not_enrolled_again_by_a_payslip():
    assert do(status="opted_out")["action"] == "opted_out"


def test_a_non_eligible_jobholder_is_left_alone():
    assert do(earnings="600")["action"] == "none"


def test_postponement_holds_an_eligible_jobholder_until_the_date():
    s = P.clean_scheme({"employer_pct": 3, "employee_pct": 5, "postponement_months": 3})
    got = do(scheme=s, start=date(2026, 9, 1))
    assert (got["action"], got["postponed_until"]) == ("postpone", "2026-12-01")
    again = do(status="postponed", until="2026-12-01", scheme=s, start=date(2026, 9, 1))
    assert again["action"] == "postponed"


def test_after_the_postponement_they_are_enrolled():
    s = P.clean_scheme({"employer_pct": 3, "employee_pct": 5, "postponement_months": 3})
    got = do(status="postponed", until="2026-12-01", scheme=s, on=date(2026, 12, 1))
    assert got["action"] == "enrol"


def test_if_they_earn_under_the_trigger_when_it_ends_they_are_not_enrolled():
    s = P.clean_scheme({"employer_pct": 3, "employee_pct": 5, "postponement_months": 3})
    got = do(status="postponed", until="2026-12-01", scheme=s, earnings="600", on=date(2026, 12, 1))
    assert got["action"] == "none"


def test_postponement_is_counted_from_the_start_date_not_from_today():
    s = P.clean_scheme({"employer_pct": 3, "employee_pct": 5, "postponement_months": 3})
    assert do(scheme=s, start=date(2026, 1, 5))["action"] == "enrol", "started in January: already past"


# --- what goes in -----------------------------------------------------------------------------
def pay(gross="3000", basic="3000", scheme=SCHEME, due=True):
    return P.contributions(scheme=scheme, gross=gross, basic=basic, frequency="monthly", year=2026, employer_due=due)


def test_qualifying_earnings_are_the_band_between_the_limits():
    got = pay()
    # 3,000 - 520 = 2,480; 5% = 124.00; 3% = 74.40
    assert got["pensionable"] == D("2480")
    assert (got["employee_gross"], got["employer"]) == (D("124.00"), D("74.40"))


def test_below_the_lower_limit_nothing_is_pensionable():
    assert pay(gross="500", basic="500")["pensionable"] == D("0")


def test_above_the_upper_limit_pay_stops_counting():
    got = pay(gross="6000", basic="6000")
    assert got["pensionable"] == D("3669")               # 4,189 - 520


def test_net_pay_takes_the_whole_share_before_tax():
    got = pay()
    assert got["employee_deduction"] == D("124.00") and got["relief"] == D("0.00")
    assert got["reduces_taxable_pay"] == D("124.00")


def test_relief_at_source_takes_80_percent_after_tax_and_the_provider_claims_the_rest():
    s = P.clean_scheme({"employer_pct": 3, "employee_pct": 5, "method": "relief_at_source"})
    got = pay(scheme=s)
    assert got["employee_deduction"] == D("99.20") and got["relief"] == D("24.80")
    assert got["employee_deduction"] + got["relief"] == got["employee_gross"]
    assert got["reduces_taxable_pay"] == D("0.00")


def test_all_pay_basis_counts_every_pound():
    s = P.clean_scheme({"basis": "total", "employer_pct": 3, "employee_pct": 4})
    got = pay(scheme=s)
    assert (got["pensionable"], got["employee_gross"], got["employer"]) == (D("3000"), D("120.00"), D("90.00"))


def test_basic_pay_basis_ignores_overtime_and_bonus():
    s = P.clean_scheme({"basis": "basic", "employer_pct": 4, "employee_pct": 5})
    got = pay(gross="3500", basic="3000", scheme=s)
    assert got["pensionable"] == D("3000") and got["employer"] == D("120.00")


def test_an_entitled_worker_who_joins_gets_no_employer_contribution():
    assert pay(due=False)["employer"] == D("0.00")


def test_half_a_penny_goes_up():
    s = P.clean_scheme({"employer_pct": 3, "employee_pct": 5})
    got = P.contributions(scheme=s, gross="1000.10", basic="1000.10", frequency="monthly", year=2026)
    # 480.10 x 5% = 24.005 -> 24.01
    assert got["employee_gross"] == D("24.01")


# --- opting out and coming back -----------------------------------------------------------------
def test_opting_out_within_a_month_earns_a_refund():
    assert P.opt_out_refund_window("2026-09-01", "2026-09-30")
    assert P.opt_out_refund_window("2026-09-01", "2026-10-01")
    assert not P.opt_out_refund_window("2026-09-01", "2026-10-02")


def test_an_opt_out_before_joining_is_not_a_refund_case():
    assert not P.opt_out_refund_window("2026-09-10", "2026-09-01")


def test_re_enrolment_falls_on_the_third_anniversary_then_every_three_years():
    assert P.next_reenrolment("2024-03-01", date(2026, 9, 30)) == date(2027, 3, 1)
    assert P.next_reenrolment("2024-03-01", date(2027, 3, 1)) == date(2027, 3, 1)
    assert P.next_reenrolment("2024-03-01", date(2027, 3, 2)) == date(2030, 3, 1)
    assert P.next_reenrolment("", date(2026, 9, 30)) is None
