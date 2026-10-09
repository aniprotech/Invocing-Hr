"""HMRC Real Time Information (RTI): the Full Payment Submission and the
Employer Payment Summary.

Every time an employer pays somebody in the UK, HMRC must be told, on or
before the pay date, through the Government Gateway. This module builds
those two XML messages from payroll figures, checks them against HMRC's own
published rules, and (once the business has credentials from HMRC) sends them.

What is in here and why it can be trusted:

* The XML Schema and Schematron files in backend/hmrc/rim/<tax year>/ are
  HMRC's, unmodified, from the RTI Release Information Pack (see
  backend/hmrc/README.md for where they came from). A message is checked
  against both before it can be sent - the schema for shape, the Schematron
  for the business rules HMRC applies at its end (a start date needs a
  starter declaration, a man cannot have NI letter B, and so on) - so
  most rejections happen here, with a plain reason, instead of at HMRC.
* Nothing in here talks to the network except `send`, which is handed the
  endpoint and credentials by the caller and does nothing when they are not
  there.

What is NOT verified, and cannot be until HMRC gives the business test
access: the IRmark (the hash HMRC checks to know the message was not changed
in transit) and the exact Gateway handshake. Both are written from HMRC's
published description and are exercised by HMRC's own test service first;
see `irmark` below.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import os
import re
import threading
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
RIM_DIR = os.path.join(HERE, "hmrc", "rim")

GT_NS = "http://www.govtalk.gov.uk/CM/envelope"
SCHEMA_FILES = {
    "FPS": "FullPaymentSubmission",
    "EPS": "EmployerPaymentSummary",
}
CLASS_OF = {"FPS": "HMRC-PAYE-RTI-FPS", "EPS": "HMRC-PAYE-RTI-EPS"}


class RtiError(Exception):
    """Something HMRC would refuse, or that cannot be worked out, said plainly."""


# ---------------------------------------------------------------------------
# Tax years
# ---------------------------------------------------------------------------

def tax_year_folder(year: int) -> str:
    """2026 -> '2026-27', the folder of that year's HMRC files."""
    return f"{year}-{(year + 1) % 100:02d}"


def related_tax_year(year: int) -> str:
    """2026 -> '26-27', the form HMRC's RelatedTaxYear takes."""
    return f"{year % 100:02d}-{(year + 1) % 100:02d}"


def namespace_for(kind: str, year: int) -> str:
    return f"http://www.govtalk.gov.uk/taxation/PAYE/RTI/{SCHEMA_FILES[kind]}/{related_tax_year(year)}/1"


def _schema_dir(year: int) -> str:
    return os.path.join(RIM_DIR, tax_year_folder(year))


def schema_path(kind: str, year: int, ext: str) -> str:
    folder = _schema_dir(year)
    if not os.path.isdir(folder):
        raise RtiError(f"HMRC's {tax_year_folder(year)} filing definitions are not installed in this build")
    prefix = SCHEMA_FILES[kind] + "-"
    for name in sorted(os.listdir(folder)):
        if name.startswith(prefix) and name.endswith(ext):
            return os.path.join(folder, name)
    raise RtiError(f"HMRC's {kind} {ext} file for {tax_year_folder(year)} is missing")


def supported_years() -> list:
    out = []
    if os.path.isdir(RIM_DIR):
        for name in sorted(os.listdir(RIM_DIR)):
            m = re.fullmatch(r"(\d{4})-\d{2}", name)
            if m:
                out.append(int(m.group(1)))
    return out


# The web server answers requests on a pool of threads. Compiling HMRC's files
# takes a few milliseconds, so each thread keeps its own copy rather than
# sharing lxml's compiled objects between threads.
_local = threading.local()


def _cache() -> dict:
    if not hasattr(_local, "compiled"):
        _local.compiled = {}
    return _local.compiled


def _xsd(kind: str, year: int) -> etree.XMLSchema:
    cache, key = _cache(), ("xsd", kind, year)
    if key not in cache:
        cache[key] = etree.XMLSchema(etree.parse(schema_path(kind, year, ".xsd")))
    return cache[key]


def _rules(kind: str, year: int):
    """HMRC's Schematron, as the XSLT they publish it compiled to."""
    cache, key = _cache(), ("xslt", kind, year)
    if key not in cache:
        cache[key] = etree.XSLT(etree.parse(schema_path(kind, year, ".xslt")))
    return cache[key]


# ---------------------------------------------------------------------------
# Checking a message
# ---------------------------------------------------------------------------

ERR = "{http://www.govtalk.gov.uk/CM/errorresponse}"


def _body_root(message: etree._Element) -> etree._Element:
    body = message.find(f"{{{GT_NS}}}Body")
    if body is None or len(body) == 0:
        raise RtiError("the message has no body")
    return body[0]


def check(message_xml, kind: str, year: int) -> list:
    """Every reason HMRC's own rules would refuse this message, in plain
    words, in the order found. Empty when it passes both the schema and the
    Schematron. `message_xml` is the whole GovTalkMessage (bytes or text)."""
    if isinstance(message_xml, str):
        message_xml = message_xml.encode("utf-8")
    try:
        doc = etree.fromstring(message_xml, etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as e:
        return [f"The message is not well-formed XML: {e}"]
    problems = []
    xsd = _xsd(kind, year)
    body = copy.deepcopy(_body_root(doc))
    if not xsd.validate(etree.ElementTree(body)):
        for err in xsd.error_log:
            problems.append(_explain_schema_error(err))
    # HMRC's rules read the envelope too (the keys must match in both), so
    # they are run on the whole message, not the body.
    try:
        result = _rules(kind, year)(etree.ElementTree(doc))
    except etree.XSLTApplyError as e:
        return problems + [f"HMRC's rules could not be applied: {e}"]
    for error in result.getroot().iter(f"{ERR}Error"):
        text = " ".join("".join(error.find(f"{ERR}Text").itertext()).split()) if error.find(f"{ERR}Text") is not None else ""
        number = error.findtext(f"{ERR}Number") or ""
        where = _where(error.findtext(f"{ERR}Location") or "")
        line = f"{text} [HMRC error {number}]" if number else text
        if where:
            line += f" - at {where}"
        if text and line not in problems:
            problems.append(line)
    return problems


def _where(location: str) -> str:
    """'/hd:GovTalkMessage[1]/.../fps:Employee[2]/...' -> 'Employee 2, NIletter'."""
    parts = re.findall(r"/\w+:(\w+)\[(\d+)\]", location)
    skip = {"GovTalkMessage", "Body", "IRenvelope", "FullPaymentSubmission", "EmployerPaymentSummary"}
    out = []
    for name, idx in parts:
        if name in skip:
            continue
        out.append(f"{name} {idx}" if name in ("Employee", "Employment", "NIlettersAndValues") and idx != "1" or name == "Employee" else name)
    return ", ".join(out[-3:])


def _explain_schema_error(err) -> str:
    msg = re.sub(r"\{https?://[^}]*\}", "", err.message)
    msg = re.sub(r"\s+", " ", msg).strip()
    return f"{msg} (line {err.line})"


# ---------------------------------------------------------------------------
# Small formatting helpers: HMRC is strict about the shape of a number
# ---------------------------------------------------------------------------

def D(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def pounds(value) -> str:
    """Two decimal places, always: HMRC rejects 12.5 where it wants 12.50."""
    return str(D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def whole_pounds(value) -> str:
    """The 'whole units' fields still end .00 in the XML."""
    return str(D(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) + ".00"


_NAME_OK = re.compile(r"[^A-Za-z'\-]")
_SURNAME_OK = re.compile(r"[^A-Za-z '\-]")


def forename(value: str) -> str:
    """HMRC allows letters, apostrophes and hyphens in a forename, nothing
    else - no spaces, digits or accents - and it must start with a letter."""
    return re.sub(r"^[^A-Za-z]+", "", _NAME_OK.sub("", _ascii(value)))[:35]


def surname(value: str) -> str:
    """An employee's surname: letters, spaces, hyphens and apostrophes."""
    return re.sub(r"\s+", " ", _SURNAME_OK.sub("", _ascii(value))).strip()[:35]


def contact_surname(value: str) -> str:
    """A contact's surname is allowed a little more than an employee's."""
    return re.sub(r"[^A-Za-z0-9 ,.()/&\-']", "", _ascii(value)).strip()[:35]


def _ascii(value) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")


def address_line(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9 &'()*,\-./]", "", _ascii(value)).strip()[:35]


_POSTCODE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$")


def clean_postcode(value) -> str:
    """'sw1a1aa' -> 'SW1A 1AA'; '' when it is not a UK postcode."""
    raw = re.sub(r"\s+", "", str(value or "")).upper()
    if len(raw) < 5 or not _POSTCODE.match(raw):
        return ""
    return raw[:-3] + " " + raw[-3:]


# ---------------------------------------------------------------------------
# Building the Full Payment Submission
# ---------------------------------------------------------------------------

PAY_FREQ = {
    "weekly": "W1", "fortnightly": "W2", "biweekly": "W2", "twoweekly": "W2",
    "fourweekly": "W4", "4weekly": "W4", "lunar": "W4",
    "monthly": "M1", "quarterly": "M3", "biannually": "M6", "annually": "MA",
}
HOURS_BANDS = {"A": "Up to 15.99 hours a week", "B": "16 to 23.99 hours", "C": "24 to 29.99 hours",
               "D": "30 hours or more", "E": "Other - no regular pattern"}


def pay_freq_code(frequency: str) -> str:
    key = re.sub(r"[\s_-]+", "", str(frequency or "monthly").strip().lower())
    if key not in PAY_FREQ:
        raise RtiError(f"'{frequency}' is not a pay frequency HMRC accepts (weekly, fortnightly, four-weekly, monthly...)")
    return PAY_FREQ[key]


def hmrc_pay_period(frequency: str, pay_date: date, tax_year: int) -> tuple:
    """(element name, number) - the tax week or month this payment falls in.
    HMRC counts weeks and months from 6 April."""
    start = date(tax_year, 4, 6)
    if pay_date < start or pay_date > date(tax_year + 1, 4, 5):
        raise RtiError(f"{pay_date} is not in the {tax_year_folder(tax_year)} tax year")
    code = pay_freq_code(frequency)
    if code in ("W1", "W2", "W4"):
        # A fortnightly or 4-weekly payroll reports the week its period ends
        # in: 2, 4, 6... or 4, 8, 12... - not the week the money was paid.
        per = {"W1": 1, "W2": 2, "W4": 4}[code]
        week = (pay_date - start).days // 7 + 1
        return "WeekNo", -(-week // per) * per
    months = (pay_date.year - tax_year) * 12 + pay_date.month - 4
    if pay_date.day < 6:
        months -= 1
    return "MonthNo", months + 1


def _sub(parent, ns, tag, text=None, **attrs):
    el = etree.SubElement(parent, f"{{{ns}}}{tag}", **attrs)
    if text is not None:
        el.text = str(text)
    return el


def split_tax_code(code: str) -> tuple:
    """'S1257L W1' -> ('1257L', 'S', True): the code HMRC wants, the Scottish
    or Welsh prefix as a separate field, and whether it is a week 1 / month 1
    code. HMRC takes those three apart; a payslip shows them together."""
    raw = re.sub(r"\s+", " ", str(code or "").strip().upper())
    non_cumulative = False
    for tail in (" W1/M1", " W1", " M1", " X"):
        if raw.endswith(tail):
            raw, non_cumulative = raw[: -len(tail)].strip(), True
            break
    regime = ""
    if raw[:1] in ("S", "C") and raw[1:2].isdigit() or raw[:2] in ("SK", "CK", "SB", "CB", "S0", "C0", "SN", "CN", "SD", "CD"):
        regime, raw = raw[0], raw[1:]
    return raw, regime, non_cumulative


def _ymd(value) -> str:
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


def _contact(parent, ns, name: str, email: str, phone: str):
    """The person HMRC can ring. A name needs a first name and a surname that
    HMRC's rules accept; one that does not is left out rather than made up."""
    parts = [p for p in re.split(r"\s+", _ascii(name).strip()) if p]
    fores = [forename(p) for p in parts[:-1][:2] if forename(p)]
    sur = contact_surname(parts[-1]) if len(parts) > 1 else ""
    if fores and sur:
        n = _sub(parent, ns, "Name")
        for fore in fores:
            _sub(n, ns, "Fore", fore)
        _sub(n, ns, "Sur", sur)
    if email:
        _sub(parent, ns, "Email", email)
    digits = re.sub(r"[^0-9+]", "", str(phone or ""))
    if digits:
        t = _sub(parent, ns, "Telephone")
        _sub(t, ns, "Number", digits)


def _emp_refs(parent, ns, employer: dict):
    refs = _sub(parent, ns, "EmpRefs")
    _sub(refs, ns, "OfficeNo", employer["office_no"])
    _sub(refs, ns, "PayeRef", employer["paye_ref"])
    _sub(refs, ns, "AORef", employer["ao_ref"])
    return refs


def _header(root, ns, employer: dict, tax_year: int):
    h = _sub(root, ns, "IRheader")
    keys = _sub(h, ns, "Keys")
    _sub(keys, ns, "Key", employer["office_no"], Type="TaxOfficeNumber")
    _sub(keys, ns, "Key", employer["paye_ref"], Type="TaxOfficeReference")
    _sub(h, ns, "PeriodEnd", f"{tax_year + 1}-04-05")
    if employer.get("contact_name") or employer.get("contact_email") or employer.get("contact_phone"):
        principal = _sub(h, ns, "Principal")
        _contact(_sub(principal, ns, "Contact"), ns, employer.get("contact_name", ""),
                 employer.get("contact_email", ""), employer.get("contact_phone", ""))
    _sub(h, ns, "DefaultCurrency", "GBP")
    _sub(h, ns, "Sender", "Employer")


def build_fps(employer: dict, payments: list, tax_year: int, *, final: bool = False) -> etree._Element:
    """The IRenvelope for a Full Payment Submission: one entry per person
    paid. `payments` are plain dicts - see the keys read below - prepared by
    the caller from payslips, so this stays free of the database."""
    if not payments:
        raise RtiError("a Full Payment Submission needs at least one payment")
    ns = namespace_for("FPS", tax_year)
    root = etree.Element(f"{{{ns}}}IRenvelope", nsmap={None: ns})
    _header(root, ns, employer, tax_year)
    fps = _sub(root, ns, "FullPaymentSubmission")
    _emp_refs(fps, ns, employer)
    _sub(fps, ns, "RelatedTaxYear", related_tax_year(tax_year))
    for p in payments:
        _employee(fps, ns, p, tax_year)
    if final:
        fin = _sub(fps, ns, "FinalSubmission")
        _sub(fin, ns, "ForYear", "yes")
    return root


def _employee(fps, ns, p: dict, tax_year: int):
    emp = _sub(fps, ns, "Employee")
    det = _sub(emp, ns, "EmployeeDetails")
    if p.get("nino"):
        _sub(det, ns, "NINO", p["nino"])
    name = _sub(det, ns, "Name")
    fore = forename(str(p.get("first_name", "")).split(" ")[0])
    last = surname(p.get("last_name", ""))
    if not last:
        raise RtiError(f"{p.get('first_name', '')} has no surname HMRC can accept - it must contain letters")
    if fore:
        _sub(name, ns, "Fore", fore)
    else:
        initial = re.sub(r"[^A-Za-z]", "", _ascii(p.get("first_name", "")))[:1].upper()
        if not initial:
            raise RtiError(f"{p.get('last_name', '')} has no first name HMRC can accept - it must contain letters")
        _sub(name, ns, "Initials", initial)
    _sub(name, ns, "Sur", last)
    lines = [address_line(l) for l in (p.get("address_lines") or []) if address_line(l)][:4]
    postcode = clean_postcode(p.get("postcode"))
    country = re.sub(r"[^A-Za-z .'\-]", "", _ascii(p.get("country"))).strip()[:35]
    # HMRC's address ends in either a UK postcode or a foreign country, and
    # nothing else. Lines with neither are left out: calling a UK address
    # "foreign" would be worse than sending none.
    if postcode or (lines and country):
        addr = _sub(det, ns, "Address")
        for line in lines:
            _sub(addr, ns, "Line", line)
        if postcode:
            _sub(addr, ns, "UKPostcode", postcode)
        else:
            _sub(addr, ns, "ForeignCountry", country)
    if p.get("birth_date"):
        _sub(det, ns, "BirthDate", _ymd(p["birth_date"]))
    _sub(det, ns, "Gender", p.get("gender", ""))

    job = _sub(emp, ns, "Employment")
    director = p.get("director")
    if director:
        _sub(job, ns, "DirectorsNIC", director.get("nic_method", "AN"))
        if director.get("appointed_week"):
            _sub(job, ns, "TaxWkOfApptOfDirector", director["appointed_week"])
    if p.get("start_date"):
        st = _sub(job, ns, "Starter")
        _sub(st, ns, "StartDate", _ymd(p["start_date"]))
        _sub(st, ns, "StartDec", p.get("start_decl", ""))
        if p.get("student_loan_starter"):
            _sub(st, ns, "StudentLoan", "yes")
        if p.get("postgrad_starter"):
            _sub(st, ns, "PostgradLoan", "yes")
    if clean_postcode(p.get("workplace_postcode")):
        _sub(job, ns, "EmployeeWorkplacePostcode", clean_postcode(p["workplace_postcode"]))
    if p.get("payroll_id"):
        _sub(job, ns, "PayId", str(p["payroll_id"])[:35])
    if p.get("leaving_date"):
        _sub(job, ns, "LeavingDate", _ymd(p["leaving_date"]))

    figs = _sub(job, ns, "FiguresToDate")
    _sub(figs, ns, "TaxablePay", pounds(p["taxable_pay_ytd"]))
    _sub(figs, ns, "TotalTax", pounds(p["tax_ytd"]))
    if D(p.get("student_loan_ytd")) > 0:
        _sub(figs, ns, "StudentLoansTD", pounds(p["student_loan_ytd"]))
    if D(p.get("postgrad_ytd")) > 0:
        _sub(figs, ns, "PostgradLoansTD", pounds(p["postgrad_ytd"]))
    if D(p.get("pension_net_pay_ytd")) > 0:
        _sub(figs, ns, "EmpeePenContribnsPaidYTD", pounds(p["pension_net_pay_ytd"]))
    if D(p.get("pension_not_net_ytd")) > 0:
        _sub(figs, ns, "EmpeePenContribnsNotPaidYTD", pounds(p["pension_not_net_ytd"]))

    pay = _sub(job, ns, "Payment")
    _sub(pay, ns, "PayFreq", pay_freq_code(p["frequency"]))
    pay_date = p["pay_date"]
    _sub(pay, ns, "PmtDate", _ymd(pay_date))
    if p.get("late_reason"):
        _sub(pay, ns, "LateReason", p["late_reason"])
    which, number = hmrc_pay_period(p["frequency"], pay_date, tax_year)
    _sub(pay, ns, which, number)
    _sub(pay, ns, "PeriodsCovered", int(p.get("periods_covered") or 1))
    if p.get("pay_after_leaving"):
        _sub(pay, ns, "PmtAfterLeaving", "yes")
    _sub(pay, ns, "HoursWorked", p.get("hours_band", "E"))
    attrs = {}
    if p.get("non_cumulative"):
        attrs["BasisNonCumulative"] = "yes"
    if p.get("tax_regime"):
        attrs["TaxRegime"] = p["tax_regime"]
    _sub(pay, ns, "TaxCode", p["tax_code"], **attrs)
    _sub(pay, ns, "TaxablePay", pounds(p["taxable_pay"]))
    if D(p.get("pension_net_pay")) > 0:
        _sub(pay, ns, "EmpeePenContribnsPaid", pounds(p["pension_net_pay"]))
    if D(p.get("pension_not_net")) > 0:
        _sub(pay, ns, "EmpeePenContribnsNotPaid", pounds(p["pension_not_net"]))
    if D(p.get("student_loan")) > 0:
        _sub(pay, ns, "StudentLoanRecovered", whole_pounds(p["student_loan"]), PlanType=f"0{p['student_loan_plan']}"
             if str(p.get("student_loan_plan", "")).isdigit() else str(p.get("student_loan_plan", "")))
    if D(p.get("postgrad")) > 0:
        _sub(pay, ns, "PostgradLoanRecovered", whole_pounds(p["postgrad"]))
    _sub(pay, ns, "TaxDeductedOrRefunded", pounds(p["tax"]))

    for n in (p.get("ni") or [])[:4]:
        row = _sub(job, ns, "NIlettersAndValues")
        _sub(row, ns, "NIletter", n["letter"])
        for tag, key in (("GrossEarningsForNICsInPd", "gross_pd"), ("GrossEarningsForNICsYTD", "gross_ytd"),
                         ("AtLELYTD", "lel_ytd"), ("LELtoPTYTD", "lel_pt_ytd"), ("PTtoUELYTD", "pt_uel_ytd"),
                         ("TotalEmpNICInPd", "er_pd"), ("TotalEmpNICYTD", "er_ytd"),
                         ("EmpeeContribnsInPd", "ee_pd"), ("EmpeeContribnsYTD", "ee_ytd")):
            _sub(row, ns, tag, pounds(n[key]))


RECOVERABLE_TAGS = (
    ("SMPRecovered", "smp"), ("SPPRecovered", "spp"), ("SAPRecovered", "sap"), ("ShPPRecovered", "shpp"),
    ("SPBPRecovered", "spbp"), ("NICCompensationOnSMP", "nic_smp"), ("NICCompensationOnSPP", "nic_spp"),
    ("NICCompensationOnSAP", "nic_sap"), ("NICCompensationOnShPP", "nic_shpp"), ("NICCompensationOnSPBP", "nic_spbp"),
)


def build_eps(employer: dict, tax_year: int, *, no_payment_from: Optional[date] = None,
              no_payment_to: Optional[date] = None, inactive_from: Optional[date] = None,
              inactive_to: Optional[date] = None, employment_allowance: Optional[bool] = None,
              recoverable: Optional[dict] = None, recoverable_month: Optional[int] = None,
              levy_due_ytd=None, levy_month: Optional[int] = None, levy_allowance=None,
              final: bool = False) -> etree._Element:
    """The IRenvelope for an Employer Payment Summary: the things that are
    not a payment to anyone - a month with nobody paid, a quiet spell, the
    Employment Allowance claim, statutory pay to recover, the Apprenticeship
    Levy. Only what is given is sent."""
    ns = namespace_for("EPS", tax_year)
    root = etree.Element(f"{{{ns}}}IRenvelope", nsmap={None: ns})
    _header(root, ns, employer, tax_year)
    eps = _sub(root, ns, "EmployerPaymentSummary")
    _emp_refs(eps, ns, employer)
    if no_payment_from and no_payment_to:
        _sub(eps, ns, "NoPaymentForPeriod", "yes")
        dates = _sub(eps, ns, "NoPaymentDates")
        _sub(dates, ns, "From", _ymd(no_payment_from))
        _sub(dates, ns, "To", _ymd(no_payment_to))
    if inactive_from and inactive_to:
        quiet = _sub(eps, ns, "PeriodOfInactivity")
        _sub(quiet, ns, "From", _ymd(inactive_from))
        _sub(quiet, ns, "To", _ymd(inactive_to))
    if employment_allowance is not None:
        _sub(eps, ns, "EmpAllceInd", "yes" if employment_allowance else "no")
    amounts = {k: D(v) for k, v in (recoverable or {}).items() if D(v) > 0}
    if amounts:
        rec = _sub(eps, ns, "RecoverableAmountsYTD")
        if recoverable_month:
            _sub(rec, ns, "TaxMonth", int(recoverable_month))
        for tag, key in RECOVERABLE_TAGS:
            if key in amounts:
                _sub(rec, ns, tag, pounds(amounts[key]))
    if levy_due_ytd is not None and levy_month:
        levy = _sub(eps, ns, "ApprenticeshipLevy")
        _sub(levy, ns, "LevyDueYTD", pounds(levy_due_ytd))
        _sub(levy, ns, "TaxMonth", int(levy_month))
        _sub(levy, ns, "AnnualAllce", pounds(levy_allowance if levy_allowance is not None else 15000))
    _sub(eps, ns, "RelatedTaxYear", related_tax_year(tax_year))
    if final:
        fin = _sub(eps, ns, "FinalSubmission")
        _sub(fin, ns, "ForYear", "yes")
    return root


# ---------------------------------------------------------------------------
# The Government Gateway envelope
# ---------------------------------------------------------------------------

def govtalk_message(body_root: etree._Element, kind: str, employer: dict, *, sender_id: str = "",
                    password: str = "", vendor_id: str = "", product: str = "aniprotech", version: str = "1.0",
                    test: bool = True, qualifier: str = "request", correlation_id: str = "",
                    include_irmark: bool = False) -> bytes:
    """Wrap an IRenvelope in the GovTalk message the Gateway takes. `test`
    sets GatewayTest=1, which tells the Gateway to validate and answer without
    recording anything - the only mode used until HMRC has recognised the
    software."""
    nsmap = {None: GT_NS}
    msg = etree.Element(f"{{{GT_NS}}}GovTalkMessage", nsmap=nsmap)
    _sub(msg, GT_NS, "EnvelopeVersion", "2.0")
    header = _sub(msg, GT_NS, "Header")
    md = _sub(header, GT_NS, "MessageDetails")
    _sub(md, GT_NS, "Class", CLASS_OF[kind])
    _sub(md, GT_NS, "Qualifier", qualifier)
    if qualifier == "request":
        _sub(md, GT_NS, "Function", "submit")
    _sub(md, GT_NS, "CorrelationID", correlation_id)
    _sub(md, GT_NS, "Transformation", "XML")
    _sub(md, GT_NS, "GatewayTest", "1" if test else "0")
    if sender_id or password:
        sd = _sub(header, GT_NS, "SenderDetails")
        ida = _sub(sd, GT_NS, "IDAuthentication")
        _sub(ida, GT_NS, "SenderID", sender_id)
        auth = _sub(ida, GT_NS, "Authentication")
        _sub(auth, GT_NS, "Method", "clear")
        _sub(auth, GT_NS, "Value", password)
    details = _sub(msg, GT_NS, "GovTalkDetails")
    keys = _sub(details, GT_NS, "Keys")
    _sub(keys, GT_NS, "Key", employer["office_no"], Type="TaxOfficeNumber")
    _sub(keys, GT_NS, "Key", employer["paye_ref"], Type="TaxOfficeReference")
    if vendor_id:
        routing = _sub(details, GT_NS, "ChannelRouting")
        ch = _sub(routing, GT_NS, "Channel")
        _sub(ch, GT_NS, "URI", vendor_id)
        _sub(ch, GT_NS, "Product", product)
        _sub(ch, GT_NS, "Version", version)
    body = _sub(msg, GT_NS, "Body")
    body.append(copy.deepcopy(body_root))
    if include_irmark:
        _set_irmark(msg, body_root.tag.split("}")[0][1:])
    return etree.tostring(msg, xml_declaration=True, encoding="UTF-8")


def irmark(message: etree._Element) -> str:
    """The IRmark: SHA-1 of the canonical form of the Body with the IRmark
    element removed, base64. UNVERIFIED against HMRC - their published
    description is followed, and their test service is what confirms it. It
    is off unless asked for, because a wrong IRmark gets a message refused
    while a missing one does not."""
    body = copy.deepcopy(message.find(f"{{{GT_NS}}}Body"))
    for mark in body.iter("{*}IRmark"):
        mark.getparent().remove(mark)
    canon = etree.tostring(body, method="c14n")
    return base64.b64encode(hashlib.sha1(canon).digest()).decode("ascii")


def _set_irmark(message: etree._Element, ns: str):
    header = message.find(f".//{{{ns}}}IRheader")
    mark = etree.Element(f"{{{ns}}}IRmark", Type="generic")
    sender = header.find(f"{{{ns}}}Sender")
    sender.addprevious(mark)
    mark.text = irmark(message)


# ---------------------------------------------------------------------------
# Sending, and what comes back
# ---------------------------------------------------------------------------
# The Gateway answers a submission with an acknowledgement and a place to
# ask; the business-rule result comes later, by asking ("polling"). Only
# when HMRC has answered with a response or an error is the submission done,
# and the answer is then deleted from the Gateway. Written from HMRC's
# published GovTalk description; HMRC's test service is what confirms it.

class Reply(dict):
    """qualifier: acknowledgement | response | error; correlation_id;
    poll_interval (seconds); endpoint (where to poll); errors: list of
    dicts(number, type, text, location); body (the response XML text)."""


def parse_reply(content) -> Reply:
    if isinstance(content, str):
        content = content.encode("utf-8")
    try:
        doc = etree.fromstring(content, etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as e:
        raise RtiError(f"HMRC's answer was not readable XML: {e}")
    if etree.QName(doc).localname != "GovTalkMessage":
        raise RtiError("HMRC's answer was not a GovTalk message")
    md = f"{{{GT_NS}}}Header/{{{GT_NS}}}MessageDetails"
    reply = Reply(qualifier=(doc.findtext(f"{md}/{{{GT_NS}}}Qualifier") or "").strip().lower(),
                  correlation_id=(doc.findtext(f"{md}/{{{GT_NS}}}CorrelationID") or "").strip(),
                  poll_interval=2, endpoint="", errors=[], body="")
    ep = doc.find(f"{md}/{{{GT_NS}}}ResponseEndPoint")
    if ep is not None:
        reply["endpoint"] = (ep.text or "").strip()
        try:
            reply["poll_interval"] = max(1, min(int(ep.get("PollInterval") or 2), 300))
        except ValueError:
            pass
    for err in doc.iter(f"{{{GT_NS}}}Error"):
        reply["errors"].append({
            "number": (err.findtext(f"{{{GT_NS}}}Number") or "").strip(),
            "type": (err.findtext(f"{{{GT_NS}}}Type") or "").strip(),
            "text": " ".join(" ".join(t.text or "" for t in err.findall(f"{{{GT_NS}}}Text")).split()),
            "location": " ".join(" ".join(t.text or "" for t in err.findall(f"{{{GT_NS}}}Location")).split()),
        })
    body = doc.find(f"{{{GT_NS}}}Body")
    if body is not None and len(body):
        reply["body"] = etree.tostring(body, encoding="unicode")
    if reply["qualifier"] == "error" and not reply["errors"]:
        reply["errors"].append({"number": "", "type": "", "text": "HMRC refused the message without saying why", "location": ""})
    return reply


def _control_message(kind: str, correlation_id: str, qualifier: str, function: str, test: bool) -> bytes:
    msg = etree.Element(f"{{{GT_NS}}}GovTalkMessage", nsmap={None: GT_NS})
    _sub(msg, GT_NS, "EnvelopeVersion", "2.0")
    header = _sub(msg, GT_NS, "Header")
    md = _sub(header, GT_NS, "MessageDetails")
    _sub(md, GT_NS, "Class", CLASS_OF[kind])
    _sub(md, GT_NS, "Qualifier", qualifier)
    _sub(md, GT_NS, "Function", function)
    _sub(md, GT_NS, "CorrelationID", correlation_id)
    _sub(md, GT_NS, "Transformation", "XML")
    _sub(md, GT_NS, "GatewayTest", "1" if test else "0")
    details = _sub(msg, GT_NS, "GovTalkDetails")
    _sub(details, GT_NS, "Keys")
    _sub(msg, GT_NS, "Body")
    return etree.tostring(msg, xml_declaration=True, encoding="UTF-8")


def poll_message(kind: str, correlation_id: str, *, test: bool = True) -> bytes:
    return _control_message(kind, correlation_id, "poll", "submit", test)


def delete_message(kind: str, correlation_id: str, *, test: bool = True) -> bytes:
    return _control_message(kind, correlation_id, "request", "delete", test)


def default_post(url: str, content: bytes, timeout: float = 60.0) -> bytes:
    import httpx
    r = httpx.post(url, content=content, timeout=timeout,
                   headers={"Content-Type": "text/xml; charset=UTF-8"})
    if r.status_code >= 500:
        raise RtiError(f"HMRC's Gateway answered with an error ({r.status_code}); nothing was recorded - try again later")
    if r.status_code >= 400:
        raise RtiError(f"HMRC's Gateway refused the request ({r.status_code})")
    return r.content


def send(kind: str, message_xml: bytes, *, endpoint: str, test: bool = True, post=default_post,
         sleep=None, max_polls: int = 20) -> dict:
    """Submit, then ask until HMRC has answered. Returns
    {ok, qualifier, correlation_id, errors, body, attempts, pending}. Raises
    RtiError only when the Gateway could not be reached or answered nonsense;
    a refusal from HMRC comes back as ok=False with its reasons."""
    import time
    sleep = sleep or time.sleep
    reply = parse_reply(post(endpoint, message_xml))
    correlation, attempts, where = reply["correlation_id"], 0, reply["endpoint"] or endpoint
    while reply["qualifier"] == "acknowledgement" and attempts < max_polls:
        sleep(reply["poll_interval"])
        attempts += 1
        reply = parse_reply(post(where, poll_message(kind, correlation, test=test)))
        correlation = reply["correlation_id"] or correlation
        where = reply["endpoint"] or where
    ok = reply["qualifier"] == "response" and not reply["errors"]
    if reply["qualifier"] in ("response", "error") and correlation:
        try:  # tidy up: the Gateway keeps an answer until asked to forget it
            post(where, delete_message(kind, correlation, test=test))
        except Exception:
            pass
    return {"ok": ok, "qualifier": reply["qualifier"], "correlation_id": correlation,
            "errors": reply["errors"], "body": reply["body"], "attempts": attempts,
            "pending": reply["qualifier"] == "acknowledgement"}


# ---------------------------------------------------------------------------
# Keeping a business's Gateway password
# ---------------------------------------------------------------------------

def _fernet(key_material: str):
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(("aniprotech-hmrc|" + key_material).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(secret: str, key_material: str) -> str:
    """A secret as stored: encrypted with a key that is not in the database."""
    if not key_material:
        raise RtiError("HMRC_ENCRYPTION_KEY is not set, so a Government Gateway password cannot be stored safely")
    return _fernet(key_material).encrypt(secret.encode("utf-8")).decode("ascii")


def unseal(token: str, key_material: str) -> str:
    from cryptography.fernet import InvalidToken
    if not token:
        return ""
    if not key_material:
        raise RtiError("HMRC_ENCRYPTION_KEY is not set")
    try:
        return _fernet(key_material).decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise RtiError("the stored Government Gateway password cannot be read with the current HMRC_ENCRYPTION_KEY - enter it again")
