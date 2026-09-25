"""Bringing training in from the care sector's learning platforms.

None of these platforms can simply be called: the few with an API give it
to their own customers under an agreement, and most offer none at all. What
every one of them does give a business is its certificates, as PDFs, and a
report of who has done what, as Excel or CSV. This reads both.

Pure: it is handed bytes, the business's staff and its course titles, and
returns what it found. Nothing is saved here - the business looks at what
was read, corrects it, and only then does the app file it. A certificate
read wrongly and filed silently is worse than one typed by hand.

The partner list records what each platform actually offers, as found on
their own sites in September 2026 - not what it would be convenient for
them to offer.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# The platforms
# ---------------------------------------------------------------------------
# `match` is what identifies the platform in the text of one of its
# certificates. Deliberately specific: "florence" alone is also a first
# name, and "flourish" an ordinary word, so neither is matched bare. Skills
# for Care is last because its logo is printed on other providers'
# certificates, and it should only win when nobody else does.

PARTNERS = (
    {"key": "flourish", "name": "Flourish - Click Learning", "site": "https://flourish.co.uk/click-learning/",
     "sign_in": "https://app.click-learning.co.uk/", "match": ("click learning", "click-learning", "flourish.co.uk"),
     "api": "planned", "api_note": "An open API is on their 2025-26 roadmap; not available yet.",
     "export": "Download certificates as PDF and the training report from your Click Learning account."},
    {"key": "caretutor", "name": "CareTutor", "site": "https://caretutor.org/", "sign_in": "https://caretutor.org/",
     "match": ("caretutor", "care tutor"),
     "api": "available", "api_note": "API connectivity on their Pathway LMS plans - ask CareTutor for access.",
     "export": "Certificates can be downloaded in bulk by an account admin."},
    {"key": "mylearningcloud", "name": "My Learning Cloud", "site": "https://mylearningcloud.org.uk/",
     "sign_in": "https://mylearningcloud.org.uk/", "match": ("my learning cloud", "mylearningcloud", "lumis"),
     "api": "available", "api_note": "An open API for HR and rostering systems - ask My Learning Cloud for access.",
     "export": "Download certificates and the training matrix from your account."},
    {"key": "educare", "name": "EduCare", "site": "https://www.educare.co.uk/", "sign_in": "https://www.educare.co.uk/",
     "match": ("educare", "tes safeguarding"),
     "api": "on request", "api_note": "SSO and API options for organisations - ask EduCare.",
     "export": "Certificates and course transcripts as PDF; reports from the admin area."},
    {"key": "chth", "name": "Children's Homes Training Hub", "site": "https://thechildrenshometraininghub.com/",
     "sign_in": "https://thechildrenshometraininghub.com/",
     "match": ("children's home training hub", "childrens home training hub", "children’s home training hub",
               "children's homes training hub", "vocational training hub"),
     "api": "unknown", "api_note": "No integration published - ask them.",
     "export": "Download certificates as PDF."},
    {"key": "caredemy", "name": "Caredemy", "site": "https://caredemy.co.uk/", "sign_in": "https://caredemy.co.uk/",
     "match": ("caredemy",),
     "api": "none published", "api_note": "No API published.",
     "export": "Certificate management and a colour-coded training matrix report."},
    {"key": "florence", "name": "Florence Academy", "site": "https://www.florence.co.uk/florence-academy",
     "sign_in": "https://www.florence.co.uk/florence-academy",
     "match": ("florence academy", "florence.co.uk", "florenceapp"),
     "api": "none published", "api_note": "No API published.",
     "export": "One-click Excel export, and all the week's new certificates in one download."},
    {"key": "custoris", "name": "Custoris Academy", "site": "", "sign_in": "",
     "match": ("custoris",),
     "api": "unknown", "api_note": "No public presence could be found - check them before relying on them.",
     "export": "Ask them how certificates are issued."},
    {"key": "elfh", "name": "NHS e-Learning for Healthcare", "site": "https://www.e-lfh.org.uk/",
     "sign_in": "https://portal.e-lfh.org.uk/",
     "match": ("e-learning for healthcare", "elearning for healthcare", "e-lfh", "elfh"),
     "api": "none published", "api_note": "No API published; sharing through the NHS Digital Staff Passport is in private beta.",
     "export": "Each certificate is a PDF, with the course summary from page 2."},
    {"key": "skillsforcare", "name": "Skills for Care", "site": "https://www.skillsforcare.org.uk/",
     "sign_in": "https://www.skillsforcare.org.uk/",
     "match": ("skills for care",),
     "api": "none", "api_note": "Skills for Care endorses training providers; it is not a training platform to connect to.",
     "export": "Free resources and endorsed providers' certificates."},
)
PARTNER_KEYS = tuple(p["key"] for p in PARTNERS)
PARTNERS_BY_KEY = {p["key"]: p for p in PARTNERS}

MAX_DOCUMENT_BYTES = 3_000_000


def partner_in(text: str):
    """The platform a piece of text came from, or None."""
    low = (text or "").lower()
    for p in PARTNERS:
        if any(m in low for m in p["match"]):
            return p
    return None


def partner_in_filename(name: str):
    """A file name is nobody's first name, so the platform's short key is
    enough there: florence-export.xlsx is Florence's."""
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    for p in PARTNERS:
        if p["key"] in low or any(re.sub(r"[^a-z]", "", m) in low for m in p["match"]):
            return p
    return None


# ---------------------------------------------------------------------------
# Dates, the way UK platforms write them
# ---------------------------------------------------------------------------

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
DATE_RE = re.compile(
    r"\b(\d{4}-\d{1,2}-\d{1,2}"                                     # 2026-09-14
    r"|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"                            # 14/09/2026, 14.09.26
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r",?\s+\d{4}"  # 14th September 2026
    r"|" + _MON + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b",       # September 14, 2026
    re.I)


def parse_date(value):
    """A date, from the text a UK platform writes, an Excel cell, or a
    spreadsheet serial number. Day before month, as the UK writes it."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Excel's day count, for a sheet that stored dates as numbers.
        if 20000 < value < 80000:
            return date(1899, 12, 30) + timedelta(days=int(value))
        return None
    t = re.sub(r"\s+", " ", str(value)).strip().lower().replace(",", "")
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t).replace(" of ", " ")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ t].*)?", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _safe(y, mo, d)
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})(?: .*)?", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        return _safe(y, mo, d)
    m = re.fullmatch(r"(\d{1,2}) ([a-z]+) (\d{4})", t)
    if m:
        mo = _month(m.group(2))
        return _safe(int(m.group(3)), mo, int(m.group(1))) if mo else None
    m = re.fullmatch(r"([a-z]+) (\d{1,2}) (\d{4})", t)
    if m:
        mo = _month(m.group(1))
        return _safe(int(m.group(3)), mo, int(m.group(2))) if mo else None
    return None


def _month(word):
    for i, name in enumerate(_MONTHS, 1):
        if name.startswith(word[:3]) and len(word) >= 3:
            return i
    return None


def _safe(y, mo, d):
    try:
        found = date(y, mo, d)
    except ValueError:
        return None
    return found if 1990 <= found.year <= 2100 else None


def _iso(d):
    return d.isoformat() if d else ""


# ---------------------------------------------------------------------------
# Matching a name to a member of staff
# ---------------------------------------------------------------------------

def _norm(s):
    s = (s or "").lower().replace("’", "'")
    return re.sub(r"[^a-z0-9@.' -]", " ", re.sub(r"\s+", " ", s)).strip()


class Staff:
    """The business's people, looked up by email, staff number or name."""

    def __init__(self, people):
        # people: iterable of dicts {id, first_name, last_name, email, employee_id}
        self.people = list(people)
        self.by_email = {}
        self.by_code = {}
        self.by_name = {}
        for p in self.people:
            full = _norm(f"{p.get('first_name', '')} {p.get('last_name', '')}")
            p["_full"] = full
            if p.get("email"):
                self.by_email[p["email"].strip().lower()] = p
            if p.get("employee_id"):
                self.by_code[str(p["employee_id"]).strip().lower()] = p
            for key in (full, _norm(f"{p.get('last_name', '')} {p.get('first_name', '')}")):
                if key:
                    self.by_name.setdefault(key, []).append(p)

    def find(self, name="", email="", code="", first="", last=""):
        """The one person these point to, or None - never a guess between two."""
        if email and email.strip().lower() in self.by_email:
            return self.by_email[email.strip().lower()]
        if code and str(code).strip().lower() in self.by_code:
            return self.by_code[str(code).strip().lower()]
        candidates = []
        if first or last:
            candidates.append(_norm(f"{first} {last}"))
        if name:
            n = _norm(name)
            candidates.append(n)
            if "," in (name or ""):
                a, _, b = name.partition(",")
                candidates.append(_norm(f"{b} {a}"))
        for c in candidates:
            hits = self.by_name.get(c, [])
            if len(hits) == 1:
                return hits[0]
        return None

    def in_text(self, text):
        """The one member of staff named in a block of text, if exactly one is."""
        low = " " + _norm(text) + " "
        hits = [p for p in self.people if p["_full"] and f" {p['_full']} " in low]
        # "Ann Lee" inside "Joann Lee" is not a match - the spaces see to that.
        # "Ann Lee" inside "Mary Ann Lee" is: the longer name is the person,
        # so a name that is only there as part of another does not count.
        hits = [p for p in hits if not any(q is not p and len(q["_full"]) > len(p["_full"])
                                           and f" {p['_full']} " in f" {q['_full']} " for q in hits)]
        # Two different people still named: the certificate is not clearly anyone's.
        if len({p["id"] for p in hits}) == 1:
            return hits[0]
        return None


def staff_record(p):
    return {"employee_id": p["id"], "employee_name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()} if p else \
        {"employee_id": None, "employee_name": ""}


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

def pdf_text(data: bytes) -> str:
    """The words on a PDF, or '' when it is a scanned picture with none."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:3])
    except Exception:
        return ""


_COURSE_LEADS = (
    r"(?:has|have)\s+(?:successfully\s+)?(?:completed|passed|achieved|attended)(?:\s+the)?(?:\s+(?:course|module|training|programme))?(?:\s+(?:in|on|entitled))?",
    r"for\s+(?:successfully\s+)?(?:completing|passing|attending)(?:\s+the)?(?:\s+(?:course|module|training|programme))?",
    r"certificate\s+of\s+(?:completion|achievement|attendance)\s+(?:in|for)",
    r"(?:course|module|training|programme)\s*(?:title|name)?\s*:",
)
_REFERENCE_RE = re.compile(
    r"(?:certificate|cert\.?|verification|credential)\s*(?:no\.?|number|id|ref(?:erence)?|code)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{3,40})",
    re.I)
_EXPIRY_WORDS = re.compile(r"expir|valid\s+(?:until|to|till)|renew|refresh(?:er)?\s+(?:due|by)|re-?certif|due\s+(?:date|by)", re.I)
_ISSUE_WORDS = re.compile(r"complet|award|issued|achiev|passed|attained|date", re.I)


def _clean_course(s):
    s = re.sub(r"\s+", " ", s or "").strip(" .:-–—\"'")
    s = DATE_RE.split(s)[0] if DATE_RE.search(s) else s
    s = re.sub(r"\b(?:on|dated|with|at|in)\s*$", "", s.strip(" .:-,"), flags=re.I).strip(" .:-,")
    return s[:150]


def _course_from(text, lines, course_titles):
    low = text.lower()
    # A course the business already runs, named on the certificate, wins.
    best = ""
    for title in course_titles or ():
        t = (title or "").strip()
        if t and t.lower() in low and len(t) > len(best):
            best = t
    if best:
        return best
    for lead in _COURSE_LEADS:
        for i, line in enumerate(lines):
            m = re.search(lead, line, re.I)
            if not m:
                continue
            rest = _clean_course(line[m.end():])
            if not rest and i + 1 < len(lines):
                rest = _clean_course(lines[i + 1])
            if rest and not DATE_RE.fullmatch(rest) and len(rest) >= 3:
                return rest
    return ""


def _dates_from(lines):
    issued, expires, loose = None, None, []
    for line in lines:
        for m in DATE_RE.finditer(line):
            d = parse_date(m.group(1))
            if not d:
                continue
            before = line[:m.start()][-60:]
            if _EXPIRY_WORDS.search(before):
                expires = expires or d
            elif _ISSUE_WORDS.search(before):
                issued = issued or d
            else:
                loose.append(d)
    loose = sorted(set(loose))
    if not issued and loose:
        issued = loose.pop(0)
    if not expires and loose and issued and loose[-1] > issued:
        expires = loose[-1]
    if issued and expires and expires < issued:
        issued, expires = expires, issued
    return issued, expires


def read_certificate(text: str, staff: Staff, course_titles=()):
    """What a certificate says: whose it is, what for, when, until when,
    its number, and which platform issued it. Every field it could not find
    is named in `missing`, so the business knows what to fill in."""
    text = text or ""
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    partner = partner_in(text)
    person = staff.in_text(text)
    course = _course_from(text, lines, course_titles)
    issued, expires = _dates_from(lines)
    ref = _REFERENCE_RE.search(text)
    found = {
        **staff_record(person),
        "name": course,
        "issuer": partner["name"] if partner else "",
        "partner": partner["key"] if partner else "",
        "issued_on": _iso(issued),
        "expires_on": _iso(expires),
        "reference": ref.group(1) if ref else "",
    }
    labels = {"employee_id": "who it belongs to", "name": "the course", "issued_on": "the date it was completed"}
    found["missing"] = [labels[k] for k in ("employee_id", "name", "issued_on") if not found[k]]
    found["readable"] = bool(text.strip())
    return found


# ---------------------------------------------------------------------------
# Training reports: Excel or CSV, one row per course or one row per person
# ---------------------------------------------------------------------------

_PERSON = {
    "name": re.compile(r"^(?:full\s*)?name$|learner|employee\s*name|staff\s*(?:member|name)|^user(?:\s*name)?$|^person$|^delegate$", re.I),
    "first": re.compile(r"first\s*name|forename|given\s*name|^first$", re.I),
    "last": re.compile(r"last\s*name|surname|family\s*name|^last$", re.I),
    "email": re.compile(r"e-?mail", re.I),
    "code": re.compile(r"employee\s*(?:id|no|number|code)|staff\s*(?:id|no|number)|payroll\s*(?:id|no|number)", re.I),
}
_COURSE_COL = re.compile(r"^(?:course|module|training|title|course\s*(?:name|title)|learning\s*item|qualification)$|course|module", re.I)
_DONE_COL = re.compile(r"complet|date\s*(?:passed|achieved|awarded)|passed\s*on|achieved\s*on|awarded|date\s*taken|^date$", re.I)
_EXPIRY_COL = re.compile(r"expir|renew|valid\s*(?:until|to)|due\s*date|refresh", re.I)
_STATUS_COL = re.compile(r"^status$|result|outcome", re.I)
_REFERENCE_COL = re.compile(r"certificate\s*(?:no|number|id|ref)|reference", re.I)
# Columns in a matrix that describe the person, not a course. Whole headings
# only: a course called "Home care" or "Customer service" is still a course.
_META_COL = re.compile(r"^(?:department|dept|team|role|job(?:\s*title)?|title|position|site|location|home|service|"
                       r"unit|ward|manager|line\s*manager|start(?:\s*date)?|date\s*(?:joined|started)|joined|status|"
                       r"phone|mobile|dob|date\s*of\s*birth|group|contract|hours|compliance(?:\s*%)?|%|total|score|"
                       r"overall(?:\s*%)?|progress|employment\s*type|no\.?|#)$", re.I)
_DONE_WORDS = re.compile(r"^(?:complete[d]?|passed|pass|achieved|yes|y|done|certified|competent)$", re.I)


def _rows_from(filename, data):
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        best = []
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if any(v not in (None, "") for v in r)]
            if len(rows) > len(best):
                best = rows
        return best
    if name.endswith(".xls"):
        raise ValueError("That is the old Excel format - save it as .xlsx or .csv and try again")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("That file could not be read as text")
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [r for r in csv.reader(io.StringIO(text), dialect) if any((c or "").strip() for c in r)]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _header_row(rows):
    """The first row that names a person column."""
    for i, row in enumerate(rows[:20]):
        cells = [str(_cell(c)) for c in row]
        if sum(1 for c in cells if c) >= 2 and any(rx.search(c) for c in cells for rx in _PERSON.values()):
            return i
    return None


def read_training_report(filename, data, staff: Staff, course_titles=()):
    """Who has done what, from a platform's export. Two shapes are read:

    - one row per course taken (Name, Course, Completed, Expires ...)
    - a training matrix, one row per person and one column per course, the
      dates in the grid being when each was completed.
    """
    rows = _rows_from(filename, data)
    h = _header_row(rows)
    if h is None:
        raise ValueError("No column saying who each row is about - a name, email or staff number - was found")
    header = [str(_cell(c)) for c in rows[h]]
    col = {}
    for i, name in enumerate(header):
        for key, rx in _PERSON.items():
            if key not in col and rx.search(name):
                # "Course name" is not a person's name.
                if key == "name" and _COURSE_COL.search(name):
                    continue
                col[key] = i
                break
    person_cols = set(col.values())
    # "Course completion date" is a date, not the course.
    course_col = next((i for i, n in enumerate(header) if i not in person_cols and _COURSE_COL.search(n)
                       and not _DONE_COL.search(n) and not _EXPIRY_COL.search(n)), None)
    done_col = next((i for i, n in enumerate(header) if i not in person_cols and i != course_col
                     and _DONE_COL.search(n) and not _EXPIRY_COL.search(n)), None)
    expiry_col = next((i for i, n in enumerate(header) if _EXPIRY_COL.search(n)), None)
    status_col = next((i for i, n in enumerate(header) if _STATUS_COL.search(n)), None)
    ref_col = next((i for i, n in enumerate(header) if _REFERENCE_COL.search(n)), None)
    partner = partner_in(" ".join(header)) or partner_in_filename(filename)

    out, unmatched, skipped = [], {}, 0
    long_shape = course_col is not None and done_col is not None

    def who(row):
        get = lambda k: str(_cell(row[col[k]])) if k in col and col[k] < len(row) else ""
        p = staff.find(name=get("name"), email=get("email"), code=get("code"), first=get("first"), last=get("last"))
        label = get("name") or f"{get('first')} {get('last')}".strip() or get("email") or get("code")
        return p, label

    for n, row in enumerate(rows[h + 1:], start=h + 2):
        row = list(row) + [None] * (len(header) - len(row))
        person, label = who(row)
        if not label:
            continue
        if long_shape:
            course = str(_cell(row[course_col]))
            done = parse_date(_cell(row[done_col]))
            status = str(_cell(row[status_col])) if status_col is not None else ""
            if not course or not done or (status and not _DONE_WORDS.match(status) and "complet" not in status.lower()
                                          and "pass" not in status.lower()):
                skipped += 1
                continue
            items = [(course, done, parse_date(_cell(row[expiry_col])) if expiry_col is not None else None,
                      str(_cell(row[ref_col])) if ref_col is not None else "")]
        else:
            items = []
            for i, name in enumerate(header):
                if i in person_cols or not name or _META_COL.match(name.strip()):
                    continue
                d = parse_date(_cell(row[i]))
                if d:
                    items.append((name, d, None, ""))
                elif str(_cell(row[i])):
                    skipped += 1
        if person is None:
            unmatched[label] = unmatched.get(label, 0) + len(items)
            continue
        for course, done, expires, ref in items:
            out.append({**staff_record(person), "row": n, "name": _match_title(course, course_titles),
                        "issuer": partner["name"] if partner else "", "partner": partner["key"] if partner else "",
                        "issued_on": _iso(done), "expires_on": _iso(expires), "reference": ref})
    return {
        "shape": "one row per course" if long_shape else "training matrix",
        "rows": out,
        "unmatched": [{"name": k, "courses": v} for k, v in sorted(unmatched.items())],
        "skipped": skipped,
        "partner": partner["key"] if partner else "",
    }


def _match_title(course, course_titles):
    """The business's own spelling of a course, when the export's is the same
    course written differently."""
    c = _norm(course)
    for t in course_titles or ():
        if _norm(t) == c:
            return t
    return course.strip()[:150]
