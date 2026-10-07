"""UK workplace pensions: who must be enrolled, and what is paid in.

Pure arithmetic and rules. It is handed a person's date of birth, their pay
this period and where they stand, and says which kind of worker they are,
whether they are to be enrolled, postponed or left alone, and what goes in.
Nothing here touches a database; the payroll saves what it decides.

Every figure is from The Pensions Regulator's published earnings thresholds
for the year (named beside them) and the rules the Regulator and GOV.UK
publish:

  * A worker aged 22 to State Pension age earning over the earnings trigger
    in a pay period is an ELIGIBLE JOBHOLDER and must be enrolled.
  * Aged 16 to 21, or State Pension age to 74, earning over the lower level
    of qualifying earnings: a NON-ELIGIBLE JOBHOLDER - not enrolled, but may
    opt in, and then the employer must contribute.
  * Aged 22 to State Pension age earning above the lower level but not above
    the trigger is a non-eligible jobholder too.
  * Anyone aged 16 to 74 earning at or under the lower level is an ENTITLED
    WORKER: may ask to join, and the employer need not contribute.
  * Minimums: 8% of qualifying earnings in total, 3% of it the employer's.
    Certified on basic pay: 9% total, 4% employer. On total pay: 7%, 3%.
  * Enrolment may be postponed up to three months. A worker may opt out
    within a month of joining and has their contributions back.

Not built, and said so on the screen: salary sacrifice, the 8%/3%-of-basic
certification that needs 85% of pay to be basic, the Regulator's declaration
of compliance, and provider-specific upload file layouts.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import calendar

D = Decimal
PENNY = D("0.01")

# The Pensions Regulator, "Earnings thresholds", 2026-27.
# https://www.thepensionsregulator.gov.uk/en/employers/new-employers/
#   im-an-employer-who-has-to-provide-a-pension/declare-your-compliance/
#   ongoing-duties-for-employers/earnings-thresholds
THRESHOLDS = {
    2026: {
        "label": "2026-27",
        "source": "The Pensions Regulator, automatic enrolment earnings thresholds 2026-27",
        #           lower          trigger         upper
        "weekly":     (D("120"), D("192"), D("967")),
        "biweekly":   (D("240"), D("384"), D("1934")),
        "fourweekly": (D("480"), D("768"), D("3867")),
        "monthly":    (D("520"), D("833"), D("4189")),
        "annual":     (D("6240"), D("10000"), D("50270")),
    },
}

# What the law asks of a scheme, by what the percentages are worked on:
# (employer minimum %, total minimum %).
BASES = {
    "qualifying": {"label": "Qualifying earnings (the band between the lower and upper limits)", "min": (D("3"), D("8"))},
    "basic": {"label": "Basic pay", "min": (D("4"), D("9"))},
    "total": {"label": "All pay (basic, overtime, bonus, allowances)", "min": (D("3"), D("7"))},
}
METHODS = {
    "net_pay": "Net pay arrangement - the employee's share comes off before tax",
    "relief_at_source": "Relief at source - taken after tax; the provider claims 20% back",
}
GROUPS = ("eligible_jobholder", "non_eligible_jobholder", "entitled_worker", "none")
GROUP_LABELS = {
    "eligible_jobholder": "Eligible jobholder - must be enrolled",
    "non_eligible_jobholder": "Non-eligible jobholder - may opt in",
    "entitled_worker": "Entitled worker - may ask to join",
    "none": "Not covered",
}

BASIC_RATE = D("20")


class PensionError(ValueError):
    """A scheme or an input the law would not allow."""


def _q(x) -> D:
    return D(str(x)).quantize(PENNY, rounding=ROUND_HALF_UP)


def thresholds_for(year: int, frequency: str):
    """(lower, trigger, upper) for one pay period of this length."""
    if year not in THRESHOLDS:
        known = ", ".join(THRESHOLDS[y]["label"] for y in sorted(THRESHOLDS))
        raise PensionError(f"No pension thresholds are loaded for {year}-{str(year + 1)[-2:]}. Loaded: {known}")
    t = THRESHOLDS[year]
    if frequency not in t:
        raise PensionError(f"Pay frequency '{frequency}' has no pension thresholds")
    return t[frequency]


# ---------------------------------------------------------------------------
# Age and State Pension age
# ---------------------------------------------------------------------------

def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def state_pension_age_date(dob: date) -> date:
    """The day this person reaches State Pension age, from the legislated
    timetable: 66 before 6 April 1960; 66 plus one to eleven months for the
    monthly bands from 6 April 1960 to 5 March 1961; 67 from then until
    5 April 1977. After that the rise to 68 is legislated for 2044 to 2046
    and is treated here as 68 outright - nobody it touches reaches the age
    before 2043, and the timetable is under review, so it is for that review
    to settle."""
    if dob < date(1960, 4, 6):
        return add_months(dob, 66 * 12)
    if dob < date(1961, 3, 6):
        months_into = (dob.year - 1960) * 12 + dob.month - 4 - (1 if dob.day < 6 else 0)
        return add_months(dob, 66 * 12 + months_into + 1)
    if dob < date(1977, 4, 6):
        return add_months(dob, 67 * 12)
    return add_months(dob, 68 * 12)


# ---------------------------------------------------------------------------
# Which kind of worker
# ---------------------------------------------------------------------------

def worker_group(*, dob, earnings, frequency: str, on: date, year: int) -> str:
    """The category this person is in for this pay period. Needs a date of
    birth: without one, age cannot be known and nobody can be enrolled on a
    guess, so the caller asks for it."""
    if dob is None:
        raise PensionError("A date of birth is needed to assess this person for a workplace pension")
    lower, trigger, _upper = thresholds_for(year, frequency)
    age = age_on(dob, on)
    if age < 16 or age >= 75:
        return "none"
    earnings = D(str(earnings))
    in_main_age = age >= 22 and on < state_pension_age_date(dob)
    if in_main_age and earnings > trigger:
        return "eligible_jobholder"
    if earnings > lower:
        return "non_eligible_jobholder"
    return "entitled_worker"


# ---------------------------------------------------------------------------
# The scheme a business has chosen
# ---------------------------------------------------------------------------

def clean_scheme(raw: dict) -> dict:
    """A scheme as the business set it, checked against the law's minimums.
    Raises PensionError saying which minimum was missed."""
    raw = raw or {}
    basis = str(raw.get("basis") or "qualifying")
    method = str(raw.get("method") or "net_pay")
    if basis not in BASES:
        raise PensionError("Contributions are worked on qualifying earnings, basic pay or all pay")
    if method not in METHODS:
        raise PensionError("Tax relief is by net pay arrangement or relief at source")
    try:
        employer = D(str(raw.get("employer_pct", "3")))
        employee = D(str(raw.get("employee_pct", "5")))
    except Exception:
        raise PensionError("Contribution percentages must be numbers")
    if employer < 0 or employee < 0 or employer > 100 or employee > 100:
        raise PensionError("A contribution is between 0% and 100%")
    min_er, min_total = BASES[basis]["min"]
    if employer < min_er:
        raise PensionError(f"The employer must pay at least {min_er:g}% on {BASES[basis]['label'].split(' (')[0].lower()}")
    if employer + employee < min_total:
        raise PensionError(f"Employer and employee together must pay at least {min_total:g}% on "
                           f"{BASES[basis]['label'].split(' (')[0].lower()}")
    try:
        postpone = int(raw.get("postponement_months") or 0)
    except (TypeError, ValueError):
        raise PensionError("Postponement is a number of months, 0 to 3")
    if postpone < 0 or postpone > 3:
        raise PensionError("Enrolment can be postponed by up to three months")
    duties = str(raw.get("duties_start") or "").strip()
    if duties:
        try:
            date.fromisoformat(duties)
        except ValueError:
            raise PensionError("The date your duties started must be a date")
    return {
        "enabled": bool(raw.get("enabled")), "provider": str(raw.get("provider") or "").strip()[:100],
        "basis": basis, "method": method,
        "employer_pct": float(employer), "employee_pct": float(employee),
        "postponement_months": postpone, "duties_start": duties,
    }


def default_scheme() -> dict:
    return clean_scheme({"enabled": False})


# ---------------------------------------------------------------------------
# What happens at a payslip
# ---------------------------------------------------------------------------

def assess(*, status: str, postponed_until: str, scheme: dict, dob, start_date, earnings,
           frequency: str, on: date, year: int) -> dict:
    """What to do with this person on this pay date.

    `status` is where they stand: "" (never in), "member", "postponed" or
    "opted_out". Returns {"group", "action", "postponed_until"} where action
    is one of: member (carry on contributing), opted_out (stay out - they are
    not re-assessed until re-enrolment), enrol, postpone, postponed (still
    waiting), none (no duty to enrol).
    """
    group = worker_group(dob=dob, earnings=earnings, frequency=frequency, on=on, year=year)
    if status == "member":
        return {"group": group, "action": "member", "postponed_until": ""}
    if status == "opted_out":
        return {"group": group, "action": "opted_out", "postponed_until": ""}

    if group != "eligible_jobholder":
        # Not (or no longer) someone the law makes enrol - including a worker
        # whose postponement ended while they earned under the trigger.
        return {"group": group, "action": "none", "postponed_until": ""}

    until = None
    if postponed_until:
        try:
            until = date.fromisoformat(postponed_until)
        except ValueError:
            until = None
    months = int(scheme.get("postponement_months") or 0)
    if until is None and months > 0:
        base = start_date or on
        until = add_months(base, months)
    if until is not None and on < until:
        return {"group": group, "action": "postpone" if status != "postponed" else "postponed",
                "postponed_until": until.isoformat()}
    return {"group": group, "action": "enrol", "postponed_until": ""}


def pensionable_earnings(*, basis: str, gross, basic, frequency: str, year: int) -> D:
    """The pay the percentages are worked on."""
    gross, basic = D(str(gross)), D(str(basic))
    if basis == "total":
        return max(D("0"), gross)
    if basis == "basic":
        return max(D("0"), basic)
    lower, _trigger, upper = thresholds_for(year, frequency)
    return max(D("0"), min(gross, upper) - lower) if gross > lower else D("0")


def contributions(*, scheme: dict, gross, basic, frequency: str, year: int, employer_due: bool = True) -> dict:
    """What goes in for one pay period.

    employee_gross: the employee's whole share, tax relief included.
    employee_deduction: what actually leaves their pay - the whole share on a
    net pay arrangement (it also comes off taxable pay), 80% of it on relief
    at source (the provider claims the other 20% from HMRC).
    """
    earn = pensionable_earnings(basis=scheme["basis"], gross=gross, basic=basic, frequency=frequency, year=year)
    employee_gross = _q(earn * D(str(scheme["employee_pct"])) / 100)
    employer = _q(earn * D(str(scheme["employer_pct"])) / 100) if employer_due else D("0.00")
    if scheme["method"] == "relief_at_source":
        deduction = _q(employee_gross * (100 - BASIC_RATE) / 100)
        relief = employee_gross - deduction
        reduces_taxable = D("0.00")
    else:
        deduction = employee_gross
        relief = D("0.00")
        reduces_taxable = employee_gross
    return {"pensionable": earn, "employee_gross": employee_gross, "employee_deduction": deduction,
            "relief": relief, "employer": employer, "reduces_taxable_pay": reduces_taxable}


def opt_out_refund_window(joined_on: str, opted_out_on: str) -> bool:
    """Within a month of joining, an opt-out is treated as never having
    joined and the employee's contributions are repaid."""
    try:
        joined = date.fromisoformat(joined_on)
        out = date.fromisoformat(opted_out_on)
    except ValueError:
        return False
    return joined <= out <= add_months(joined, 1)


def next_reenrolment(duties_start: str, today: date):
    """The next third anniversary of the duties start date on or after today
    - when the business must re-enrol anyone who opted out, within a window
    around it. None if no start date is set."""
    try:
        start = date.fromisoformat(duties_start)
    except (TypeError, ValueError):
        return None
    n = 3
    while add_months(start, n * 12) < today:
        n += 3
    return add_months(start, n * 12)
