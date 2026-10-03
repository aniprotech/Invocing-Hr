"""Pre-boarding: the restricted portal a new hire gets before they are verified.

Pure helpers only - no database, no request - so the rules that keep the
sandbox shut can be read, and tested, in one place. main.py does the wiring.

States (Employee.portal_stage):
    initiated  credentials sent; the hire is uploading documents
    submitted  everything is in; waiting on HR
    active     verified; full portal

A rejection sends "submitted" back to "initiated". "Verified" is not a resting
state: approval makes the person active in the same transaction.
"""
import io
import secrets
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

INITIATED, SUBMITTED, ACTIVE = "initiated", "submitted", "active"
RESTRICTED = (INITIATED, SUBMITTED)

TEMP_PASSWORD_TTL_DAYS = 7

# Everything a restricted session may call. Anything not listed is refused, so
# a route written next year is closed to pre-boarding by default.
_ALWAYS = (
    "/api/employee/auth/logout",
    "/api/employee/preboarding/status",
    "/api/employee/preboarding/change-password",
)
_DOCUMENTS = (
    "/api/employee/document-requests",   # list, and /{id}/upload beneath it
    "/api/employee/preboarding/submit",
)


def temp_password():
    """Readable, unambiguous, ~71 bits. No 0/O/1/l/I to misread in an email."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"{body[:4]}-{body[4:8]}-{body[8:]}"


def temp_password_expiry(now=None):
    return ((now or datetime.now()) + timedelta(days=TEMP_PASSWORD_TTL_DAYS)
            ).strftime("%Y-%m-%d %H:%M:%S")


def temp_password_expired(emp, now=None):
    if not emp.must_change_password or not emp.temp_password_expires_at:
        return False
    return (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S") > emp.temp_password_expires_at


def request_allowed(path, method, stage, must_change_password):
    """Whether a signed-in employee in this state may make this request."""
    if stage not in RESTRICTED and not must_change_password:
        return True
    if path in _ALWAYS:
        return True
    if must_change_password:
        return False            # nothing else until the password is theirs
    if stage == INITIATED:
        return any(path == p or path.startswith(p + "/") for p in _DOCUMENTS)
    # Submitted: read-only. Uploading again would change what HR is reviewing.
    return method == "GET" and path == "/api/employee/document-requests"


def welcome_email(name, company, email, password, login_url, days=TEMP_PASSWORD_TTL_DAYS):
    subject = f"Congratulations - welcome to {company}"
    text = (
        f"Hi {name},\n\n"
        f"Congratulations, and welcome to {company}!\n\n"
        f"Your employee portal account is ready. Sign in to upload the documents "
        f"we need before your start:\n\n"
        f"  {login_url}\n  Email: {email}\n  Temporary password: {password}\n\n"
        f"You will be asked to choose your own password the first time you sign "
        f"in. This temporary password stops working in {days} days.\n\n"
        f"Until your documents are checked, the portal only shows the upload "
        f"page. The rest opens as soon as they are approved.\n\n"
        f"If you were not expecting this email, ignore it.\n")
    return subject, text


def offer_letter_pdf(company, name, job_title, start_date, salary, pay_frequency, signed_by):
    """The offer letter as PDF bytes: a plain, correct letter HR can brand later."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Offer of employment - {name}")
    w, h = A4
    y = h - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, company)
    y -= 36
    c.setFont("Helvetica", 11)
    lines = [
        datetime.now().strftime("%d %B %Y"), "",
        f"Dear {name},", "",
        f"We are delighted to offer you the position of {job_title or 'team member'} "
        f"at {company}.", "",
    ]
    if start_date:
        lines.append(f"Your start date will be {start_date}.")
    if salary:
        lines.append(f"Your salary will be {salary:,.2f}, paid {pay_frequency or 'monthly'}.")
    lines += ["", "This offer follows the successful verification of your documents.",
              "Please reply to this email to confirm your acceptance.", "",
              "Yours sincerely,", "", signed_by or company]
    for line in lines:
        c.drawString(72, y, line)
        y -= 16
    c.showPage()
    c.save()
    return buf.getvalue()
