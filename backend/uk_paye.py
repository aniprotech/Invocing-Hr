"""UK PAYE for one pay period: Income Tax, National Insurance and student loans.

Pure arithmetic. Nothing here touches the database or knows who the employer
is; it is given the rates, the employee's codes, this period's pay and what
has already been paid this tax year, and it returns what to deduct. That is
what makes it testable against worked payslips, and what lets the payroll run,
a payslip edit and a what-if on the employee screen all come out the same.

Every figure in RATES is copied from a primary source, named beside it:

  HMRC, "Rates and thresholds for employers 2026 to 2027"
      https://www.gov.uk/guidance/rates-and-thresholds-for-employers-2026-to-2027
      (published 30 January 2026, updated 1 September 2026)

A new tax year is a new entry in RATES and nothing else.

The method is the one HMRC's tax tables describe:

  * A tax code's number, times ten, plus nine, is the year's tax-free pay
    (1257L -> 12,579). K codes are the same figure added to pay instead.
  * On a cumulative code the tax-free pay and every band are spread over the
    year and taken "to date" - month 3 gets three twelfths of each - so tax
    stays right across a year of uneven pay and over-deductions come back.
  * Taxable pay to date is rounded down to whole pounds, band limits to date
    up to whole pounds, and tax to date down to the penny.
  * Week 1 / Month 1 (and the emergency X suffix) looks only at this period:
    no history, and no refunds.
  * A K code may never take more than half of the period's pay.

VERIFY BEFORE HMRC RECOGNITION: the rounding of tax-free pay per period (up to
the penny here) and of NI (nearest penny, a half penny down) follow HMRC's
published method; HMRC's recognition test scenarios are the final word on the
last penny, and these are the two places a one-penny difference would show.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_DOWN
import re

D = Decimal
ZERO = D("0")
PENNY = D("0.01")
POUND = D("1")


# ---------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------
# Tax bands are widths of taxable pay above the tax-free amount, in order.
# None is "everything above". England, Northern Ireland and Wales share one
# set for 2026-27; Wales is listed separately because it will not always.

RATES = {
    2026: {
        "label": "2026-27",
        "source": "HMRC rates and thresholds for employers 2026 to 2027 (updated 1 September 2026)",
        "personal_allowance": D("12570"),
        "bands": {
            # Basic up to 37,700; higher 37,701 to 125,140; additional above.
            "rUK": [(D("37700"), D("20")), (D("87440"), D("40")), (None, D("45"))],
            "wales": [(D("37700"), D("20")), (D("87440"), D("40")), (None, D("45"))],
            # Starter to 3,967; basic to 16,956; intermediate to 31,092;
            # higher to 62,430; advanced to 125,140; top above.
            "scotland": [(D("3967"), D("19")), (D("12989"), D("20")), (D("14136"), D("21")),
                         (D("31338"), D("42")), (D("62710"), D("45")), (None, D("48"))],
        },
        # Flat-rate codes: every pound of pay at one rate.
        "flat": {
            "rUK": {"BR": D("20"), "D0": D("40"), "D1": D("45")},
            "wales": {"BR": D("20"), "D0": D("40"), "D1": D("45")},
            "scotland": {"BR": D("20"), "D0": D("21"), "D1": D("42"), "D2": D("45"), "D3": D("48")},
        },
        "emergency_code": "1257L",
        # National Insurance thresholds, per week and per month (the table
        # gives both; two- and four-weekly are the weekly figure times 2 and 4)
        # and per year for directors.
        "ni": {
            "weekly":  {"LEL": D("129"), "PT": D("242"), "ST": D("96"), "FUST": D("481"), "UST": D("967"), "UEL": D("967")},
            "monthly": {"LEL": D("559"), "PT": D("1048"), "ST": D("417"), "FUST": D("2083"), "UST": D("4189"), "UEL": D("4189")},
            "annual":  {"LEL": D("6708"), "PT": D("12570"), "ST": D("5000"), "FUST": D("25000"), "UST": D("50270"), "UEL": D("50270")},
        },
        # Employee (primary) rates: between PT and UEL, and above UEL.
        # Earnings between LEL and PT are at 0% but still count.
        "ni_employee": {
            "A": (D("8"), D("2")), "B": (D("1.85"), D("2")), "C": (ZERO, ZERO),
            "D": (D("2"), D("2")), "E": (D("1.85"), D("2")), "F": (D("8"), D("2")),
            "H": (D("8"), D("2")), "I": (D("1.85"), D("2")), "J": (D("2"), D("2")),
            "K": (ZERO, ZERO), "L": (D("2"), D("2")), "M": (D("8"), D("2")),
            "N": (D("8"), D("2")), "S": (ZERO, ZERO), "V": (D("8"), D("2")),
            "Z": (D("2"), D("2")),
        },
        # Employer (secondary) rates, by band:
        #   ST..LEL, LEL..FUST, FUST..upper, above upper
        # where "upper" is the UEL, or the UST for under 21s, apprentices and
        # veterans (the same figure in 2026-27).
        "ni_employer": {
            **{c: (D("15"), D("15"), D("15"), D("15")) for c in "ABCJ"},
            **{c: (ZERO, ZERO, D("15"), D("15")) for c in "DEFIKLNS"},
            **{c: (ZERO, ZERO, ZERO, D("15")) for c in "HMVZ"},
        },
        # Student and postgraduate loans: the annual thresholds; the per
        # period figure is derived the way HMRC's table shows it (monthly
        # 26,900 -> 2,241.66: divided and cut to the penny).
        "student_loans": {
            "1": D("26900"), "2": D("29385"), "4": D("33795"), "5": D("25000"),
        },
        "student_loan_rate": D("9"),
        "postgrad_loan": D("21000"),
        "postgrad_loan_rate": D("6"),
        "employment_allowance": D("10500"),
        "class_1a_rate": D("15"),
    },
}

FREQUENCIES = {
    # key: (periods in a year, weeks in one period or None for monthly)
    "weekly": (52, 1),
    "biweekly": (26, 2),
    "fourweekly": (13, 4),
    "monthly": (12, None),
}

NI_CATEGORIES = tuple(sorted(RATES[2026]["ni_employee"]))
STUDENT_LOAN_PLANS = ("1", "2", "4", "5")


class PayeError(ValueError):
    """Something about the codes that would make the figures wrong."""


# ---------------------------------------------------------------------------
# The tax year and its periods
# ---------------------------------------------------------------------------

def tax_year_of(d: date) -> int:
    """The year a tax year starts in: 6 April 2026 to 5 April 2027 is 2026."""
    return d.year if (d.month, d.day) >= (4, 6) else d.year - 1


def tax_year_label(year: int) -> str:
    return f"{year}-{str(year + 1)[-2:]}"


def tax_year_bounds(year: int):
    return date(year, 4, 6), date(year + 1, 4, 5)


def tax_week(d: date) -> int:
    """Week 1 is 6 to 12 April. There can be a week 53 (and 54, 56 for two-
    and four-weekly payrolls) when the year does not divide into weeks."""
    start, _ = tax_year_bounds(tax_year_of(d))
    return (d - start).days // 7 + 1


def tax_month(d: date) -> int:
    """Month 1 is 6 April to 5 May."""
    y = tax_year_of(d)
    months = (d.year - y) * 12 + (d.month - 4)
    if d.day < 6:
        months -= 1
    return months + 1


def tax_period(d: date, frequency: str):
    """(tax year, period number used for the to-date figures, is it an extra
    week beyond 52). The PAYE period is set by the pay date, not the dates
    the work was done."""
    freq = frequency_key(frequency)
    year = tax_year_of(d)
    if freq == "monthly":
        return year, tax_month(d), False
    week = tax_week(d)
    return year, week, week > 52


def frequency_key(frequency: str) -> str:
    f = (frequency or "monthly").strip().lower().replace("-", "").replace(" ", "").replace("_", "")
    aliases = {"fortnightly": "biweekly", "2weekly": "biweekly", "twoweekly": "biweekly",
               "4weekly": "fourweekly", "fourweekly": "fourweekly", "lunar": "fourweekly",
               "week": "weekly", "month": "monthly"}
    f = aliases.get(f, f)
    if f not in FREQUENCIES:
        raise PayeError(f"Pay frequency '{frequency}' is not one PAYE knows: weekly, fortnightly, four-weekly or monthly")
    return f


def rates_for(year: int) -> dict:
    if year not in RATES:
        known = ", ".join(RATES[y]["label"] for y in sorted(RATES))
        raise PayeError(f"No PAYE rates are loaded for {tax_year_label(year)}. Loaded: {known}")
    return RATES[year]


# ---------------------------------------------------------------------------
# Tax codes
# ---------------------------------------------------------------------------

@dataclass
class TaxCode:
    raw: str
    region: str             # rUK | scotland | wales
    kind: str               # allowance | k | flat | nt | zero
    number: int = 0
    flat_code: str = ""     # BR, D0, D1, ...
    cumulative: bool = True

    @property
    def annual_adjustment(self) -> D:
        """Tax-free pay for the year: the code number times ten, plus nine.
        Positive for an ordinary code, negative for a K code."""
        if self.kind == "allowance":
            return D(self.number * 10 + 9)
        if self.kind == "k":
            return -D(self.number * 10 + 9)
        return ZERO


_CODE = re.compile(r"^(?P<region>[SC])?(?P<body>0T|K\d{1,4}|\d{1,4}[LMNT]|BR|D[0-3]|NT)"
                   r"(?:\s*(?P<basis>W1M1|W1|M1|X))?$")


def parse_tax_code(code: str) -> TaxCode:
    """1257L, S1257L, C1257L, K475, BR, SD0, NT, 0T, and any of them with
    W1, M1 or X after them (all three mean: this period only)."""
    raw = (code or "").strip().upper().replace(" ", "")
    # Written either "1257LW1", "1257L W1", "1257L/W1" or "1257L X".
    raw_compact = raw.replace("/", "")
    m = _CODE.match(raw_compact)
    if not m:
        raise PayeError(f"'{code}' is not a tax code PAYE recognises")
    region = {"S": "scotland", "C": "wales", None: "rUK"}[m.group("region")]
    body = m.group("body")
    cumulative = m.group("basis") is None
    # Written back the way a payslip shows it: "S1257L", "1257L M1", "0T X".
    basis = {"W1M1": "W1/M1"}.get(m.group("basis"), m.group("basis"))
    raw = (m.group("region") or "") + body + ("" if cumulative else " " + basis)
    if body == "NT":
        return TaxCode(raw, region, "nt", cumulative=cumulative)
    # Before the numbered codes: read as a number 0T would be code 0, which
    # is nine pounds of tax-free pay, and 0T means none.
    if body == "0T":
        return TaxCode(raw, region, "zero", cumulative=cumulative)
    if body == "BR" or body.startswith("D") and body[1:].isdigit():
        return TaxCode(raw, region, "flat", flat_code=body, cumulative=cumulative)
    if body.startswith("K"):
        return TaxCode(raw, region, "k", number=int(body[1:]), cumulative=cumulative)
    return TaxCode(raw, region, "allowance", number=int(body[:-1]), cumulative=cumulative)


def tax_code_problem(code: str, year: int = 2026) -> str:
    """Why a code would not work, or '' if it would."""
    try:
        tc = parse_tax_code(code)
    except PayeError as e:
        return str(e)
    if tc.kind == "flat" and tc.flat_code not in rates_for(year)["flat"][tc.region]:
        where = {"scotland": "Scottish", "wales": "Welsh", "rUK": ""}[tc.region]
        return f"{tc.flat_code} is not a {where} flat-rate code".replace("  ", " ")
    return ""


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------

def _pence_up(x: D) -> D:
    return x.quantize(PENNY, rounding=ROUND_CEILING)


def _pence_down(x: D) -> D:
    return x.quantize(PENNY, rounding=ROUND_FLOOR)


def _pounds_up(x: D) -> D:
    return x.quantize(POUND, rounding=ROUND_CEILING)


def _pounds_down(x: D) -> D:
    return x.quantize(POUND, rounding=ROUND_FLOOR)


def _nearest_penny_half_down(x: D) -> D:
    """National Insurance: to the nearest penny, and exactly half a penny
    goes down."""
    return x.quantize(PENNY, rounding=ROUND_HALF_DOWN)


def _money(x) -> D:
    return D(str(x)) if not isinstance(x, D) else x


# ---------------------------------------------------------------------------
# Income Tax
# ---------------------------------------------------------------------------

def _fraction(frequency: str, period: int, cumulative: bool):
    """(numerator, denominator) of the year the to-date figures cover.
    Weekly-based payrolls count in weeks, monthly in months. On Week 1 /
    Month 1 it is the length of one period."""
    periods, weeks = FREQUENCIES[frequency]
    if frequency == "monthly":
        return (period if cumulative else 1), 12
    return (period if cumulative else weeks), 52


def _tax_on(taxable: D, bands, num: int, den: int) -> D:
    """Tax on `taxable` pounds against bands spread over num/den of a year."""
    tax = ZERO
    left = taxable
    for width, rate in bands:
        if left <= 0:
            break
        if width is None:
            slice_ = left
        else:
            limit = _pounds_up(width * num / den)
            slice_ = min(left, limit)
        tax += slice_ * rate / 100
        left -= slice_
    return tax


def income_tax(*, code: str, frequency: str, period: int, gross_this: D,
               gross_to_date_before: D = ZERO, tax_to_date_before: D = ZERO,
               extra_week: bool = False, year: int = 2026) -> dict:
    """Tax for this period.

    `gross_to_date_before` and `tax_to_date_before` are this tax year's
    taxable pay and tax up to, but not including, this period - from this
    employer and, for a starter with a P45, the previous one.
    """
    rates = rates_for(year)
    freq = frequency_key(frequency)
    tc = parse_tax_code(code)
    gross_this = _money(gross_this)
    gross_before = _money(gross_to_date_before)
    tax_before = _money(tax_to_date_before)

    # Week 53 (and 54 / 56) is always worked on this period alone.
    cumulative = tc.cumulative and not extra_week
    num, den = _fraction(freq, period, cumulative)
    gross_to_date = (gross_before + gross_this) if cumulative else gross_this
    # This-period-only never sees tax already paid, which is also why it can
    # never give a refund: tax due on one period's pay is never below zero.
    paid_before = tax_before if cumulative else ZERO

    if tc.kind == "nt":
        due = ZERO
        free_to_date = ZERO
        taxable_to_date = ZERO
    elif tc.kind == "flat":
        flat = rates["flat"][tc.region].get(tc.flat_code)
        if flat is None:
            raise PayeError(tax_code_problem(code, year))
        free_to_date = ZERO
        taxable_to_date = _pounds_down(gross_to_date)
        due = _pence_down(taxable_to_date * flat / 100)
    else:
        free_to_date = _pence_up(tc.annual_adjustment * num / den) if tc.kind == "allowance" \
            else -_pence_up(-tc.annual_adjustment * num / den)
        taxable_to_date = max(ZERO, _pounds_down(gross_to_date - free_to_date))
        due = _pence_down(_tax_on(taxable_to_date, rates["bands"][tc.region], num, den))

    tax_this = due - paid_before
    limited = False
    if tc.kind == "k" and tax_this > 0:
        cap = _pence_down(gross_this / 2)
        if tax_this > cap:
            tax_this, limited = cap, True

    return {
        "tax": tax_this,
        "tax_code": tc.raw,
        "basis": "cumulative" if cumulative else "week1/month1",
        "region": tc.region,
        "period": period,
        "free_pay_to_date": free_to_date,
        "taxable_pay_to_date": taxable_to_date,
        "tax_due_to_date": due,
        "regulatory_limit_applied": limited,
    }


# ---------------------------------------------------------------------------
# National Insurance
# ---------------------------------------------------------------------------

def _period_thresholds(rates: dict, frequency: str) -> dict:
    ni = rates["ni"]
    if frequency == "monthly":
        return dict(ni["monthly"])
    weeks = FREQUENCIES[frequency][1]
    return {k: v * weeks for k, v in ni["weekly"].items()}


def _slice(earnings: D, low: D, high) -> D:
    top = earnings if high is None else min(earnings, high)
    return max(ZERO, top - low)


def _ni_on(earnings: D, category: str, t: dict, rates: dict) -> dict:
    cat = (category or "A").upper()
    if cat not in rates["ni_employee"]:
        raise PayeError(f"National Insurance category '{category}' is not one HMRC uses")
    main, over = rates["ni_employee"][cat]
    b1, b2, b3, b4 = rates["ni_employer"][cat]
    upper = t["UST"] if cat in "HMVZ" else t["UEL"]

    # The bands RTI reports: at LEL, LEL to PT, PT to UEL.
    at_lel = min(earnings, t["LEL"]) if earnings >= t["LEL"] else ZERO
    lel_to_pt = _slice(earnings, t["LEL"], t["PT"]) if earnings >= t["LEL"] else ZERO
    pt_to_uel = _slice(earnings, t["PT"], t["UEL"])
    above_uel = _slice(earnings, t["UEL"], None)

    employee = pt_to_uel * main / 100 + above_uel * over / 100

    er = (_slice(earnings, t["ST"], t["LEL"]) * b1
          + _slice(earnings, max(t["LEL"], t["ST"]), t["FUST"]) * b2
          + _slice(earnings, t["FUST"], upper) * b3
          + _slice(earnings, upper, None) * b4) / 100

    return {
        "employee": _nearest_penny_half_down(employee),
        "employer": _nearest_penny_half_down(er),
        "earnings_at_lel": at_lel,
        "earnings_lel_to_pt": lel_to_pt,
        "earnings_pt_to_uel": pt_to_uel,
        "earnings_above_uel": above_uel,
    }


def national_insurance(*, category: str, frequency: str, earnings: D, year: int = 2026) -> dict:
    """Employee and employer NI for one period, the ordinary way: each period
    stands alone against that period's thresholds."""
    rates = rates_for(year)
    freq = frequency_key(frequency)
    return _ni_on(_money(earnings), category, _period_thresholds(rates, freq), rates)


def director_national_insurance(*, category: str, earnings_to_date: D, employee_ni_before: D,
                                employer_ni_before: D, weeks_as_director: int = 52,
                                year: int = 2026) -> dict:
    """A director's NI on the annual earnings period: worked on the year's
    earnings so far against the year's thresholds (pro rata for a director
    appointed part-way through), less what has already been taken. This stops
    a director avoiding NI by taking pay in a lump."""
    rates = rates_for(year)
    weeks = max(1, min(52, int(weeks_as_director)))
    annual = rates["ni"]["annual"]
    if weeks == 52:
        t = dict(annual)
    else:
        # Pro rata: the weekly figure times the weeks left, up to the pound.
        t = {k: _pounds_up(rates["ni"]["weekly"][k] * weeks) for k in annual}
    total = _ni_on(_money(earnings_to_date), category, t, rates)
    return {
        **total,
        "employee": total["employee"] - _money(employee_ni_before),
        "employer": total["employer"] - _money(employer_ni_before),
        "employee_to_date": total["employee"],
        "employer_to_date": total["employer"],
    }


# ---------------------------------------------------------------------------
# Student and postgraduate loans
# ---------------------------------------------------------------------------

def _loan_threshold(annual: D, frequency: str) -> D:
    if frequency == "monthly":
        return _pence_down(annual / 12)
    weeks = FREQUENCIES[frequency][1]
    return _pence_down(annual / 52) * weeks


def student_loan(*, plan: str, frequency: str, earnings: D, year: int = 2026) -> D:
    """9% of earnings above the plan's threshold for the period, in whole
    pounds rounded down. Each period stands alone; nothing is carried."""
    if not plan:
        return ZERO
    rates = rates_for(year)
    plan = str(plan).strip().upper().replace("PLAN", "").strip()
    if plan not in rates["student_loans"]:
        raise PayeError(f"Student loan plan '{plan}' is not one HMRC uses: 1, 2, 4 or 5")
    over = _money(earnings) - _loan_threshold(rates["student_loans"][plan], frequency_key(frequency))
    return _pounds_down(over * rates["student_loan_rate"] / 100) if over > 0 else ZERO


def postgraduate_loan(*, frequency: str, earnings: D, year: int = 2026) -> D:
    """6% above the postgraduate threshold, in whole pounds rounded down."""
    rates = rates_for(year)
    over = _money(earnings) - _loan_threshold(rates["postgrad_loan"], frequency_key(frequency))
    return _pounds_down(over * rates["postgrad_loan_rate"] / 100) if over > 0 else ZERO


# ---------------------------------------------------------------------------
# One pay period
# ---------------------------------------------------------------------------

@dataclass
class YearToDate:
    """What this tax year has already paid, before this period."""
    taxable_pay: D = ZERO
    tax: D = ZERO
    ni_earnings: D = ZERO
    employee_ni: D = ZERO
    employer_ni: D = ZERO


@dataclass
class PayPeriod:
    gross: D
    pay_date: date
    frequency: str
    tax_code: str = "1257L"
    ni_category: str = "A"
    student_loan_plan: str = ""
    postgraduate_loan: bool = False
    is_director: bool = False
    director_weeks: int = 52
    # Pay the employee sacrifices or puts into a net-pay pension comes off
    # before tax (and, for salary sacrifice, before NI too).
    pre_tax_deductions: D = ZERO
    pre_ni_deductions: D = ZERO
    ytd: YearToDate = field(default_factory=YearToDate)


def run_period(p: PayPeriod) -> dict:
    """Everything the payslip, the employer's bill and RTI need for one
    employee in one period."""
    freq = frequency_key(p.frequency)
    year, period, extra = tax_period(p.pay_date, freq)
    gross = _money(p.gross)
    taxable = gross - _money(p.pre_tax_deductions)
    ni_earnings = gross - _money(p.pre_ni_deductions)

    tax = income_tax(code=p.tax_code, frequency=freq, period=period, gross_this=taxable,
                     gross_to_date_before=p.ytd.taxable_pay, tax_to_date_before=p.ytd.tax,
                     extra_week=extra, year=year)

    if p.is_director:
        ni = director_national_insurance(
            category=p.ni_category, earnings_to_date=p.ytd.ni_earnings + ni_earnings,
            employee_ni_before=p.ytd.employee_ni, employer_ni_before=p.ytd.employer_ni,
            weeks_as_director=p.director_weeks, year=year)
    else:
        ni = national_insurance(category=p.ni_category, frequency=freq, earnings=ni_earnings, year=year)

    sl = student_loan(plan=p.student_loan_plan, frequency=freq, earnings=ni_earnings, year=year)
    pgl = postgraduate_loan(frequency=freq, earnings=ni_earnings, year=year) if p.postgraduate_loan else ZERO

    return {
        "tax_year": year,
        "tax_year_label": tax_year_label(year),
        "tax_period": period,
        "extra_week": extra,
        "frequency": freq,
        "gross": gross,
        "taxable_pay": taxable,
        "ni_earnings": ni_earnings,
        "tax": tax["tax"],
        "tax_detail": tax,
        "employee_ni": ni["employee"],
        "employer_ni": ni["employer"],
        "ni_detail": ni,
        "student_loan": sl,
        "postgraduate_loan": pgl,
        "ytd_after": {
            "taxable_pay": p.ytd.taxable_pay + taxable,
            "tax": p.ytd.tax + tax["tax"],
            "ni_earnings": p.ytd.ni_earnings + ni_earnings,
            "employee_ni": p.ytd.employee_ni + ni["employee"],
            "employer_ni": p.ytd.employer_ni + ni["employer"],
        },
    }
