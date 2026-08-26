from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime
import uuid
import hashlib
import os


def hash_password(password: str) -> str:
    salt = hashlib.sha256(os.urandom(32)).hexdigest().encode()
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return salt.hex() + ':' + pwd_hash.hex()


def verify_password(password: str, stored: str) -> bool:
    if ':' not in stored:
        return hashlib.sha256(password.encode()).hexdigest() == stored
    salt_hex, pwd_hash_hex = stored.split(':')
    salt = bytes.fromhex(salt_hex)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return pwd_hash.hex() == pwd_hash_hex


class DBClient(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    company_name = Column(String, default="")
    contact_name = Column(String, default="")
    phone_number = Column(String, default="")
    logo_url = Column(String, default="")
    address = Column(String, default="")
    website = Column(String, default="")
    abn = Column(String, default="")
    industry = Column(String, default="")
    is_active = Column(Boolean, default=True)
    is_onboarded = Column(Boolean, default=False)
    currency = Column(String, default="GBP")
    last_login = Column(String, default="")
    login_count = Column(Integer, default=0)

    # Which parts of the product this business has bought. Invoicing and
    # HR used to be two separate pages with two separate logins, which
    # made "which do I have" a question about which URL you opened rather
    # than about what you pay for. They are one app now, and this is what
    # decides what appears in it.
    #
    # Comma separated, and everything by default: an account that existed
    # before this column did was already reaching both, and taking that
    # away on upgrade would be a silent downgrade.
    modules = Column(String, default="invoicing,hr")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    settings = relationship("DBSettings", back_populates="client")
    invoices = relationship("DBInvoice", back_populates="client")
    bills = relationship("DBBill", back_populates="client")
    contacts = relationship("DBContact", back_populates="client")
    departments = relationship("DBDepartment", back_populates="client")
    employees = relationship("DBEmployee", back_populates="client")
    attendance = relationship("DBAttendance")


class DBInvoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint('client_id', 'number', name='uq_client_invoice_number'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    number = Column(String, index=True)
    ref = Column(String, default="")
    to_contact = Column(String)
    email = Column(String, default="")
    phone_number = Column(String, default="")
    issue_date = Column(String)
    due_date = Column(String)
    paid = Column(Float, default=0.0)
    due = Column(Float, default=0.0)
    status = Column(String, default="Draft", index=True)
    sent = Column(String, default="")
    tax_type = Column(String, default="exclusive")
    currency = Column(String, default="")
    bank_details = Column(String, default="")
    tracking_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    open_count = Column(Integer, default=0)
    last_opened = Column(String, default="")

    line_items = relationship("DBLineItem", back_populates="invoice")
    client = relationship("DBClient", back_populates="invoices")


class DBPayment(Base):
    """A single receipt against an invoice. Invoices keep running `paid`/`due`
    totals; this table is the ledger that explains how they got there."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    amount = Column(Float, default=0.0)
    paid_on = Column(String, default="")
    method = Column(String, default="bank_transfer")
    reference = Column(String, default="")
    note = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBLineItem(Base):
    __tablename__ = "line_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), index=True)
    name = Column(String, default="")
    description = Column(String)
    qty = Column(Float)
    price = Column(Float)
    disc = Column(Float, default=0.0)
    account = Column(String, default="200 - Sales")
    tax_rate = Column(String, default="20% (VAT on Income)")

    invoice = relationship("DBInvoice", back_populates="line_items")


class DBRecurringInvoice(Base):
    """A standing instruction to raise the same invoice on a schedule.

    Holds the lines itself rather than pointing at an invoice, so editing the
    template never rewrites invoices already issued from it.
    """
    __tablename__ = "recurring_invoices"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    name = Column(String, default="")
    to_contact = Column(String, default="")
    email = Column(String, default="")
    phone_number = Column(String, default="")
    reference = Column(String, default="")
    tax_type = Column(String, default="exclusive")
    currency = Column(String, default="")
    bank_details = Column(String, default="")
    # weekly | monthly | quarterly | yearly
    frequency = Column(String, default="monthly")
    # Days after issue that the generated invoice falls due.
    payment_terms_days = Column(Integer, default=14)
    next_run = Column(String, default="", index=True)
    end_date = Column(String, default="")
    is_active = Column(Boolean, default=True, index=True)
    # Whether to email each one as it is raised, or leave it as a draft.
    auto_send = Column(Boolean, default=False)
    last_run = Column(String, default="")
    last_invoice_number = Column(String, default="")
    invoices_created = Column(Integer, default=0)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    line_items = relationship("DBRecurringLineItem", back_populates="template")


class DBRecurringLineItem(Base):
    __tablename__ = "recurring_line_items"

    id = Column(Integer, primary_key=True, index=True)
    recurring_id = Column(Integer, ForeignKey("recurring_invoices.id"), index=True)
    name = Column(String, default="")
    description = Column(String)
    qty = Column(Float)
    price = Column(Float)
    disc = Column(Float, default=0.0)
    account = Column(String, default="200 - Sales")
    tax_rate = Column(String, default="20% (VAT on Income)")

    template = relationship("DBRecurringInvoice", back_populates="line_items")


class DBInvoiceReminder(Base):
    """One chase actually sent, so the same one is never sent twice."""
    __tablename__ = "invoice_reminders"
    __table_args__ = (
        UniqueConstraint('invoice_id', 'stage_days', name='uq_invoice_reminder_stage'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    # Which rung of the ladder this was: days past due.
    stage_days = Column(Integer, default=0)
    sent_to = Column(String, default="")
    sent_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBInterviewReminder(Base):
    """One interview reminder actually sent, so nobody is nudged twice."""
    __tablename__ = "interview_reminders"
    __table_args__ = (
        UniqueConstraint('interview_id', 'recipient', name='uq_interview_reminder'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), nullable=False, index=True)
    # "candidate" or "interviewer" - each gets at most one.
    recipient = Column(String, default="candidate")
    sent_to = Column(String, default="")
    sent_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBJobRun(Base):
    """A claim on one run of one scheduled job.

    Railway can run more than one worker, and each would otherwise fire the
    same job. The unique constraint is the lock: whoever inserts the row for a
    period gets to do the work, everyone else finds it taken.
    """
    __tablename__ = "job_runs"
    __table_args__ = (
        UniqueConstraint('job_name', 'period_key', name='uq_job_period'),
    )

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String, nullable=False, index=True)
    # What "this run" means for the job - usually a date, so a daily job runs
    # once a day however often the loop wakes up.
    period_key = Column(String, nullable=False, index=True)
    status = Column(String, default="running")
    detail = Column(String, default="")
    started_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    finished_at = Column(String, default="")


class DBTeamMember(Base):
    """Somebody who works at a tenant, other than the account owner.

    The owner stays on DBClient, which is where the company and its original
    credentials live. Everyone else is a row here, so adding colleagues never
    touches the record the whole tenancy hangs off.
    """
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint('client_id', 'email', name='uq_client_member_email'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    email = Column(String, nullable=False, index=True)
    name = Column(String, default="")
    password_hash = Column(String, default="")
    # owner: everything. admin: everything but the team and the wallet.
    # viewer: read-only, enforced centrally rather than endpoint by endpoint.
    role = Column(String, default="admin", index=True)
    is_active = Column(Boolean, default=True)
    invited_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    accepted_at = Column(String, default="")
    last_login = Column(String, default="")


class DBPasswordReset(Base):
    """One password reset link.

    Only a hash of the token is kept, the same way passwords are, so a copy of
    this table is not a set of working reset links.
    """
    __tablename__ = "password_resets"

    id = Column(Integer, primary_key=True, index=True)
    # Owners and staff both need a way back in, and the mechanism is identical,
    # so one table serves both rather than two that can drift apart.
    user_type = Column(String, default="client", index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    member_id = Column(Integer, ForeignKey("team_members.id"), nullable=True, index=True)
    token_hash = Column(String, nullable=False, index=True)
    expires_at = Column(String, nullable=False)
    used_at = Column(String, default="")
    requested_ip = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBTaxRate(Base):
    """A tax rate the tenant can pick when writing a line.

    This is only the picker. Documents store the rendered label ("20% VAT") on
    the line itself, so editing or deleting a rate here never restates an
    invoice that has already gone out.
    """
    __tablename__ = "tax_rates"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    percent = Column(Float, default=0.0)
    sort_order = Column(Integer, default=0)
    is_default = Column(Boolean, default=False)


class DBQuote(Base):
    """A priced proposal, before any money is owed.

    Deliberately a separate table from invoices rather than a status on one:
    a quote has an expiry instead of a due date, is never part-paid, and must
    keep its own numbering sequence so QU-0007 does not consume INV-0007.
    """
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint('client_id', 'number', name='uq_client_quote_number'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    number = Column(String, index=True)
    ref = Column(String, default="")
    to_contact = Column(String)
    email = Column(String, default="")
    phone_number = Column(String, default="")
    issue_date = Column(String)
    expiry_date = Column(String)
    total = Column(Float, default=0.0)
    # Draft, Sent, Accepted, Declined, Expired, Invoiced
    status = Column(String, default="Draft", index=True)
    sent = Column(String, default="")
    tax_type = Column(String, default="exclusive")
    currency = Column(String, default="")
    title = Column(String, default="")
    summary = Column(String, default="")
    terms = Column(String, default="")
    # Set once the quote has been turned into an invoice, so it cannot be
    # converted twice.
    invoice_number = Column(String, default="")
    decided_at = Column(String, default="")

    line_items = relationship("DBQuoteLineItem", back_populates="quote")


class DBQuoteLineItem(Base):
    __tablename__ = "quote_line_items"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), index=True)
    name = Column(String, default="")
    description = Column(String)
    qty = Column(Float)
    price = Column(Float)
    disc = Column(Float, default=0.0)
    account = Column(String, default="200 - Sales")
    tax_rate = Column(String, default="20% (VAT on Income)")

    quote = relationship("DBQuote", back_populates="line_items")


class DBSettings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    key = Column(String, index=True)
    value = Column(String)
    description = Column(String, default="")

    client = relationship("DBClient", back_populates="settings")


class DBContact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    name = Column(String, index=True)
    email = Column(String)
    phone_number = Column(String)

    client = relationship("DBClient", back_populates="contacts")


class DBSuperAdmin(Base):
    __tablename__ = "super_admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    email = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBAdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)


class DBDepartment(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    color = Column(String, default="#00f0ff")
    icon = Column(String, default="building")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    client = relationship("DBClient", back_populates="departments")
    employees = relationship("DBEmployee", back_populates="department")


class DBEmployee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    reports_to = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)

    employee_id = Column(String, default="")
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, default="")
    address = Column(String, default="")

    job_title = Column(String, default="")
    role = Column(String, default="employee")
    # Seniority band (L1..L8). Kept separate from `role`, which describes what
    # the person does in the reporting line, not how senior they are.
    level = Column(String, default="", index=True)
    employment_type = Column(String, default="full_time")
    pay_frequency = Column(String, default="monthly")

    salary = Column(Float, default=0.0)
    hourly_rate = Column(Float, default=0.0)
    tax_rate = Column(Float, default=0.0)
    deductions = Column(Float, default=0.0)
    allowances = Column(Float, default=0.0)
    bonus = Column(Float, default=0.0)

    bank_name = Column(String, default="")
    bank_account = Column(String, default="")
    tax_id = Column(String, default="")

    emergency_contact = Column(String, default="")
    emergency_phone = Column(String, default="")

    annual_leave_entitlement = Column(Float, default=25.0)
    sick_leave_entitlement = Column(Float, default=10.0)

    password_hash = Column(String, default="")
    work_location = Column(String, default="")
    latitude = Column(Float, default=0.0)
    longitude = Column(Float, default=0.0)

    start_date = Column(String, default="")
    end_date = Column(String, default="")
    status = Column(String, default="active", index=True)
    onboarding_complete = Column(Boolean, default=False)
    offboarding_complete = Column(Boolean, default=False)

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    client = relationship("DBClient", back_populates="employees")
    department = relationship("DBDepartment", back_populates="employees")
    manager = relationship("DBEmployee", remote_side=[id], backref="direct_reports")
    payslips = relationship("DBPayslip", back_populates="employee")
    onboarding_items = relationship("DBOnboardingItem", back_populates="employee")
    attendance = relationship("DBAttendance")


class DBPayslip(Base):
    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint('client_id', 'number', name='uq_client_payslip_number'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    number = Column(String, index=True)

    period_start = Column(String, default="")
    period_end = Column(String, default="")
    pay_date = Column(String, default="")

    hours_worked = Column(Float, default=0.0)
    overtime_hours = Column(Float, default=0.0)
    overtime_rate = Column(Float, default=0.0)

    basic_salary = Column(Float, default=0.0)
    overtime_pay = Column(Float, default=0.0)
    bonus = Column(Float, default=0.0)
    allowances = Column(Float, default=0.0)
    gross_pay = Column(Float, default=0.0)

    tax_amount = Column(Float, default=0.0)
    insurance = Column(Float, default=0.0)
    retirement = Column(Float, default=0.0)
    other_deductions = Column(Float, default=0.0)
    total_deductions = Column(Float, default=0.0)

    net_pay = Column(Float, default=0.0)

    status = Column(String, default="Draft", index=True)
    sent = Column(String, default="")
    notes = Column(String, default="")
    pay_frequency = Column(String, default="")

    tracking_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    open_count = Column(Integer, default=0)
    last_opened = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    employee = relationship("DBEmployee", back_populates="payslips")


class DBOnboardingItem(Base):
    __tablename__ = "onboarding_items"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(String, default="")
    category = Column(String, default="general")
    is_completed = Column(Boolean, default=False)
    completed_at = Column(String, default="")
    assigned_to = Column(String, default="")
    due_date = Column(String, default="")
    sort_order = Column(Integer, default=0)

    employee = relationship("DBEmployee", back_populates="onboarding_items")


class DBOnboardingTemplate(Base):
    __tablename__ = "onboarding_templates"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    items_json = Column(Text, default="[]")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBAttendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    date = Column(String, nullable=False, index=True)
    clock_in = Column(String, default="")
    clock_out = Column(String, default="")
    total_hours = Column(Float, default=0.0)
    status = Column(String, default="present", index=True)
    check_type = Column(String, default="manual")
    ip_address = Column(String, default="")
    device_info = Column(String, default="")
    location_lat = Column(Float, default=0.0)
    location_lng = Column(Float, default=0.0)
    location_label = Column(String, default="")
    break_start = Column(String, default="")
    break_minutes = Column(Float, default=0.0)
    is_on_break = Column(Boolean, default=False)
    overtime_hours = Column(Float, default=0.0)
    overtime_announced = Column(Boolean, default=False)
    overtime_announced_by = Column(String, default="")
    notes = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBAttendanceSettings(Base):
    __tablename__ = "attendance_settings"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, unique=True)
    office_name = Column(String, default="Head Office")
    office_lat = Column(Float, default=0.0)
    office_lng = Column(Float, default=0.0)
    geofence_radius = Column(Float, default=200.0)
    work_start = Column(String, default="09:00")
    work_end = Column(String, default="17:30")
    grace_minutes = Column(Float, default=15.0)
    auto_clockout_hours = Column(Float, default=10.0)
    max_overtime_hours = Column(Float, default=4.0)
    allow_remote = Column(Boolean, default=True)
    require_location = Column(Boolean, default=True)
    # ISO weekday numbers, Monday = 1 through Sunday = 7.
    working_days = Column(String, default="1,2,3,4,5")
    # Whether signing in to the portal counts as starting a shift. Off means
    # people clock in deliberately, so opening the portal on a day off - to
    # read a payslip or upload a document - does not record attendance.
    auto_clock_in = Column(Boolean, default=True)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBClientLoginLog(Base):
    __tablename__ = "client_login_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    email = Column(String, nullable=False)
    user_type = Column(String, default="client")
    login_type = Column(String, default="password")
    ip_address = Column(String, default="")
    device_info = Column(String, default="")
    location_label = Column(String, default="")
    status = Column(String, default="success")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBOvertimeLog(Base):
    __tablename__ = "overtime_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    date = Column(String, nullable=False)
    hours = Column(Float, default=0.0)
    reason = Column(String, default="")
    announced_by = Column(String, default="")
    status = Column(String, default="announced")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBJobRequisition(Base):
    """An open role. The application form describes *how* to apply; the
    requisition describes *what* is being hired for, which is what a hiring
    manager, the job board and the reporting all key off."""
    __tablename__ = "job_requisitions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    reference = Column(String, default="", index=True)
    title = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    hiring_manager_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)

    description = Column(Text, default="")
    requirements = Column(Text, default="")
    location = Column(String, default="")
    work_mode = Column(String, default="onsite")       # onsite | hybrid | remote
    employment_type = Column(String, default="full_time")
    level = Column(String, default="")

    salary_min = Column(Float, default=0.0)
    salary_max = Column(Float, default=0.0)
    salary_currency = Column(String, default="")
    show_salary = Column(Boolean, default=True)

    openings = Column(Integer, default=1)
    status = Column(String, default="draft", index=True)  # draft|open|on_hold|closed|filled
    is_published = Column(Boolean, default=False, index=True)
    closing_date = Column(String, default="")
    opened_at = Column(String, default="")
    closed_at = Column(String, default="")

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    department = relationship("DBDepartment")
    hiring_manager = relationship("DBEmployee")


class DBRecruitmentForm(Base):
    __tablename__ = "recruitment_forms"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    job_id = Column(Integer, ForeignKey("job_requisitions.id"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    fields = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    form_token = Column(String, unique=True, index=True, default=lambda: str(__import__('uuid').uuid4()))
    pipeline_stages = Column(Text, default='["Applied","Screening","Interview","Offer","Hired"]')
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    job = relationship("DBJobRequisition")


class DBInterview(Base):
    """A scheduled conversation with a candidate, plus the scorecard."""
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    submission_id = Column(Integer, ForeignKey("form_submissions.id"), nullable=False, index=True)

    round_name = Column(String, default="Interview")
    scheduled_at = Column(String, default="", index=True)   # YYYY-MM-DD HH:MM
    duration_minutes = Column(Integer, default=45)
    mode = Column(String, default="video")                  # video | phone | onsite
    location = Column(String, default="")
    meeting_link = Column(String, default="")
    interviewer_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    interviewer_name = Column(String, default="")

    status = Column(String, default="scheduled", index=True)  # scheduled|completed|cancelled|no_show
    outcome = Column(String, default="")                      # pass | fail | hold
    score = Column(Integer, default=0)                        # 0-5
    feedback = Column(Text, default="")

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    interviewer = relationship("DBEmployee")


class DBOffer(Base):
    """An offer extended to a candidate."""
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    submission_id = Column(Integer, ForeignKey("form_submissions.id"), nullable=False, index=True)

    job_title = Column(String, default="")
    level = Column(String, default="")
    salary = Column(Float, default=0.0)
    currency = Column(String, default="")
    start_date = Column(String, default="")
    expires_on = Column(String, default="")
    notes = Column(Text, default="")

    status = Column(String, default="draft", index=True)  # draft|sent|accepted|declined|withdrawn
    sent_at = Column(String, default="")
    responded_at = Column(String, default="")
    decline_reason = Column(String, default="")

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBFormSubmission(Base):
    __tablename__ = "form_submissions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    form_id = Column(Integer, ForeignKey("recruitment_forms.id"), nullable=False, index=True)
    answers = Column(Text, default="{}")
    file_name = Column(String, default="")
    file_type = Column(String, default="")
    file_data = Column(Text, default="")
    candidate_name = Column(String, default="")
    candidate_email = Column(String, default="")
    candidate_phone = Column(String, default="")
    status = Column(String, default="new")
    current_stage = Column(String, default="Applied")
    stage_order = Column(Integer, default=0)
    rating = Column(Integer, default=0)
    notes = Column(String, default="")
    source = Column(String, default="direct")
    owner_name = Column(String, default="")
    rejected_reason = Column(String, default="")
    rejected_at = Column(String, default="")
    hired_at = Column(String, default="")
    hired_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    form = relationship("DBRecruitmentForm")
    documents = relationship("DBCandidateDocument", back_populates="submission")


class DBCandidateDocument(Base):
    """Files attached to an application. The submission row carries a single
    legacy attachment; a candidate normally sends several (CV, cover letter,
    right-to-work, certificates), so they live here."""
    __tablename__ = "candidate_documents"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    submission_id = Column(Integer, ForeignKey("form_submissions.id"), nullable=False, index=True)
    doc_type = Column(String, default="other")
    file_name = Column(String, default="")
    file_type = Column(String, default="")
    file_size = Column(Integer, default=0)
    file_data = Column(Text, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    submission = relationship("DBFormSubmission", back_populates="documents")


class DBSubmissionEvent(Base):
    """Audit trail of a candidate's movement through the pipeline."""
    __tablename__ = "submission_events"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    submission_id = Column(Integer, ForeignKey("form_submissions.id"), nullable=False, index=True)
    from_stage = Column(String, default="")
    to_stage = Column(String, default="")
    note = Column(String, default="")
    actor = Column(String, default="HR")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBEmployeeGoal(Base):
    __tablename__ = "employee_goals"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    target_value = Column(Float, default=100.0)
    current_value = Column(Float, default=0.0)
    unit = Column(String, default="%")
    category = Column(String, default="performance")
    priority = Column(String, default="medium")
    start_date = Column(String, default="")
    due_date = Column(String, default="")
    status = Column(String, default="in_progress")
    created_by = Column(String, default="HR")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    employee = relationship("DBEmployee")
    department = relationship("DBDepartment")


class DBDepartmentGoal(Base):
    __tablename__ = "department_goals"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    target_value = Column(Float, default=100.0)
    unit = Column(String, default="%")
    category = Column(String, default="performance")
    priority = Column(String, default="medium")
    start_date = Column(String, default="")
    due_date = Column(String, default="")
    created_by = Column(String, default="HR")
    is_assigned = Column(Boolean, default=False)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    department = relationship("DBDepartment")


class DBAuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    user_type = Column(String, default="client")
    user_name = Column(String, default="")
    action = Column(String, nullable=False)
    entity_type = Column(String, default="")
    entity_id = Column(Integer, nullable=True)
    entity_name = Column(String, default="")
    details = Column(Text, default="")
    ip_address = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBNotification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    message = Column(String, default="")
    type = Column(String, default="info")
    # Empty when the system raised it, which is most of them.
    sent_by = Column(String, default="")
    is_read = Column(Boolean, default=False)
    link = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBLeaveRequest(Base):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    leave_type = Column(String, default="annual")
    start_date = Column(String, nullable=False)
    end_date = Column(String, nullable=False)
    days = Column(Float, default=0.0)
    reason = Column(String, default="")
    status = Column(String, default="pending")
    approved_by = Column(String, default="")
    decided_at = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    employee = relationship("DBEmployee")


class DBDocument(Base):
    __tablename__ = "employee_documents"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    doc_type = Column(String, default="other")
    file_name = Column(String, default="")
    file_type = Column(String, default="")
    file_size = Column(Integer, default=0)
    file_data = Column(Text, default="")
    uploaded_by = Column(String, default="HR")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBDocumentRequirement(Base):
    """What HR asks new starters to provide.

    This is the template. Each employee gets their own request row against it,
    so a policy change does not rewrite what someone already submitted.
    """
    __tablename__ = "document_requirements"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    doc_type = Column(String, default="other")
    is_mandatory = Column(Boolean, default=True)
    due_days = Column(Integer, default=7)          # days after start date

    # Documents like a passport, visa or DBS check go out of date. HR decides
    # which ones need an expiry, and the employee supplies the actual date.
    requires_expiry = Column(Boolean, default=False)
    expiry_reminder_days = Column(Integer, default=30)

    # An optional blank form for the employee to download, complete and return.
    template_file_name = Column(String, default="")
    template_file_type = Column(String, default="")
    template_file_data = Column(Text, default="")

    applies_to = Column(String, default="all")     # all | department | level
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    level = Column(String, default="")
    is_active = Column(Boolean, default=True, index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    department = relationship("DBDepartment")


class DBDocumentRequest(Base):
    """One employee's obligation to provide one document, and its review."""
    __tablename__ = "document_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    requirement_id = Column(Integer, ForeignKey("document_requirements.id"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("employee_documents.id"), nullable=True)

    name = Column(String, nullable=False)          # copied so it survives template edits
    description = Column(String, default="")
    doc_type = Column(String, default="other")
    is_mandatory = Column(Boolean, default=True)
    due_date = Column(String, default="")

    # Supplied by the employee when the requirement asks for it.
    requires_expiry = Column(Boolean, default=False)
    expires_on = Column(String, default="", index=True)

    status = Column(String, default="pending", index=True)  # pending|submitted|approved|rejected
    submitted_at = Column(String, default="")
    reviewed_at = Column(String, default="")
    reviewed_by = Column(String, default="")
    review_note = Column(String, default="")

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    employee = relationship("DBEmployee")
    document = relationship("DBDocument")
    # Needed so a request can report its template and reminder window; without
    # it the lookups silently returned None.
    requirement = relationship("DBDocumentRequirement")


class DBBill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint('client_id', 'number', name='uq_client_bill_number'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    number = Column(String, index=True)
    vendor_name = Column(String, default="")
    vendor_email = Column(String, default="")
    issue_date = Column(String)
    due_date = Column(String)
    amount = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    amount_paid = Column(Float, default=0.0)
    status = Column(String, default="Draft", index=True)
    category = Column(String, default="general")
    reference = Column(String, default="")
    notes = Column(String, default="")

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    client = relationship("DBClient", back_populates="bills")

    line_items = relationship("DBBillLineItem", back_populates="bill")


class DBBillLineItem(Base):
    __tablename__ = "bill_line_items"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), index=True)
    description = Column(String, default="")
    qty = Column(Float, default=1.0)
    price = Column(Float, default=0.0)
    tax_rate = Column(String, default="20%")

    bill = relationship("DBBill", back_populates="line_items")


# ===========================================================================
# WALLET & BILLING
# Balances are held in integer minor units (pence, cents, paise). A wallet has
# to reconcile exactly, and repeated float arithmetic on a running balance
# drifts; the rest of the app uses floats because invoice totals are recomputed
# from their lines rather than accumulated.
# ===========================================================================

class DBWallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, unique=True, index=True)
    balance_minor = Column(Integer, default=0)
    currency = Column(String, default="GBP")
    low_balance_minor = Column(Integer, default=500)      # warn under this

    # Topping itself up rather than waiting to be noticed. Off until a
    # business sets it up, because charging somebody unasked is worse than
    # an empty wallet.
    auto_topup_enabled = Column(Boolean, default=False)
    auto_topup_threshold_minor = Column(Integer, default=0)
    auto_topup_amount_minor = Column(Integer, default=0)
    is_suspended = Column(Boolean, default=False)
    lifetime_topped_up_minor = Column(Integer, default=0)
    lifetime_spent_minor = Column(Integer, default=0)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    client = relationship("DBClient")


class DBWalletTransaction(Base):
    """Append-only ledger. `balance_after_minor` is stored on every row so the
    running balance can be audited against the wallet at any point."""
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True, index=True)

    direction = Column(String, default="debit", index=True)   # credit | debit
    amount_minor = Column(Integer, default=0)
    balance_after_minor = Column(Integer, default=0)
    currency = Column(String, default="GBP")

    action_key = Column(String, default="", index=True)       # which billable action
    module = Column(String, default="", index=True)           # invoicing | hr | platform
    description = Column(String, default="")
    reference = Column(String, default="")                    # invoice number, payslip id...
    quantity = Column(Integer, default=1)

    performed_by = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"), index=True)


class DBPricingRule(Base):
    """What each billable action costs. Set by the platform operator, not by
    tenants."""
    __tablename__ = "pricing_rules"

    id = Column(Integer, primary_key=True, index=True)
    action_key = Column(String, nullable=False, unique=True, index=True)
    label = Column(String, nullable=False)
    description = Column(String, default="")
    module = Column(String, default="platform", index=True)   # invoicing | hr | platform
    unit_price_minor = Column(Integer, default=0)
    currency = Column(String, default="GBP")
    free_allowance = Column(Integer, default=0)               # free units per calendar month
    is_active = Column(Boolean, default=True, index=True)
    sort_order = Column(Integer, default=0)
    updated_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBTopUpOrder(Base):
    """A payment attempt against a gateway. Kept even when it fails, so a
    disputed or duplicated payment can be traced."""
    __tablename__ = "topup_orders"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    provider = Column(String, default="", index=True)         # stripe | razorpay | paypal | manual
    amount_minor = Column(Integer, default=0)
    currency = Column(String, default="GBP")

    status = Column(String, default="created", index=True)    # created|pending|paid|failed|cancelled
    provider_order_id = Column(String, default="", index=True)
    provider_payment_id = Column(String, default="", index=True)
    checkout_url = Column(String, default="")
    failure_reason = Column(String, default="")

    credited = Column(Boolean, default=False)                 # guards double-crediting
    credited_at = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBBrandingTheme(Base):
    """How a business wants its invoices and quotes to look.

    A tenant can keep several - a standard theme, one for a customer who wants
    their PO number as a column, a plainer one for print. Exactly one is the
    default, which is what a new document uses.

    Every display decision lives here rather than in the PDF code, so changing
    a theme re-renders every document that uses it without touching a stored
    file. Nothing here affects what is owed; it is presentation only.
    """
    __tablename__ = "branding_themes"
    __table_args__ = (
        UniqueConstraint('client_id', 'name', name='uq_client_theme_name'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    name = Column(String, default="Standard")
    is_default = Column(Boolean, default=False, index=True)

    # --- brand and styling ---
    logo_data = Column(Text, default="")            # data: URI, per theme
    logo_position = Column(String, default="right")  # left | center | right
    brand_color = Column(String, default="#0284C7")
    font = Column(String, default="helvetica")       # a jsPDF core font

    # --- which columns the line-item table shows, and what they are called ---
    show_item = Column(Boolean, default=False)
    show_quantity = Column(Boolean, default=True)
    show_price = Column(Boolean, default=True)
    show_discount = Column(Boolean, default=False)
    show_tax = Column(Boolean, default=True)
    label_item = Column(String, default="Item")
    label_description = Column(String, default="Description")
    label_quantity = Column(String, default="Quantity")
    label_price = Column(String, default="Unit Price")
    label_discount = Column(String, default="Discount")
    label_tax = Column(String, default="Tax")
    label_amount = Column(String, default="Amount")

    # --- tax ---
    # combined | separate_rates | separate_components
    tax_breakdown = Column(String, default="separate_rates")
    exclude_zero_rates = Column(Boolean, default=False)

    # --- currency ---
    always_show_currency_code = Column(Boolean, default=False)
    show_conversion_rate = Column(Boolean, default=False)

    # --- the online invoice ---
    show_text_links = Column(Boolean, default=True)
    show_qr_code = Column(Boolean, default=True)

    # --- wording ---
    approved_invoice_title = Column(String, default="TAX INVOICE")
    draft_invoice_title = Column(String, default="DRAFT INVOICE")
    quote_title = Column(String, default="QUOTE")
    payment_terms = Column(Text, default="")
    footer_note = Column(Text, default="")

    # --- print ---
    address_position = Column(String, default="default")   # default | window_envelope
    show_page_numbers = Column(Boolean, default=True)

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBStaffRequest(Base):
    """A conversation between one employee and HR.

    Two gaps, one shape. Everything the portal sent an employee was one-way -
    they could read that a document was returned but not ask why. And leave was
    the only thing they could raise at all, so anything else (a payslip query,
    a broken laptop, a change of address) happened somewhere this system never
    saw.

    A thread carries its own status so HR can work a queue rather than
    remembering what they have answered.
    """
    __tablename__ = "staff_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    subject = Column(String, nullable=False)
    # question | document | payroll | equipment | personal_details | other
    category = Column(String, default="question", index=True)
    # open | answered | closed
    status = Column(String, default="open", index=True)

    # Set when the thread was started from something the portal showed them, so
    # HR can see what they were looking at.
    about_document_id = Column(Integer, ForeignKey("document_requests.id"), nullable=True)

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    closed_at = Column(String, default="")

    messages = relationship("DBStaffMessage", back_populates="request",
                            cascade="all, delete-orphan")


class DBAttendanceCorrection(Base):
    """A day an employee says their attendance record has wrong, waiting on HR.

    Clocking in and forgetting to clock out is the ordinary case, not the rare
    one - the nightly job closes those and marks them needs_review, but it
    deliberately records no hours, because the length of the shift is not
    knowable from the outside. Until this existed the person who actually
    worked the day had no way to say so, and the day stayed worth nothing.

    Shaped like DBProfileChange for the same reason: the request never changes
    the record. The proposed times sit here until HR decides, and the values
    they would replace are kept alongside so whoever approves can see what is
    moving. Approving writes them across and recomputes the hours; rejecting
    leaves the attendance row exactly as it was.
    """
    __tablename__ = "attendance_corrections"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    attendance_id = Column(Integer, ForeignKey("attendance.id"), nullable=False, index=True)

    # What the row said when the request was raised, so an approval that lands
    # days later can still show what it changed.
    old_clock_in = Column(String, default="")
    old_clock_out = Column(String, default="")

    requested_clock_in = Column(String, default="")
    requested_clock_out = Column(String, default="")

    # The employee's account of the day. Required: "fix my hours" with no
    # explanation is not something HR can reasonably approve.
    reason = Column(String, nullable=False)

    status = Column(String, default="pending", index=True)   # pending|approved|rejected
    note = Column(String, default="")            # why HR turned it down

    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    decided_at = Column(String, default="")
    decided_by = Column(String, default="")


class DBProfileChange(Base):
    """One field an employee wants changed, waiting on HR.

    Most of a person's own record is theirs to correct - a new phone number is
    not HR's business and making them ask for it is why the numbers on file go
    stale. Bank details are different: whatever is stored here is where the
    money goes, so a change to one is a change to where somebody's wages land.
    That gets a second pair of eyes, and the old value is kept so the person
    approving can see what it is moving from.

    Rejecting leaves the record untouched; approving writes the value across.
    Either way nothing is applied by the request itself.
    """
    __tablename__ = "profile_changes"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)

    field = Column(String, nullable=False)       # bank_name | bank_account | tax_id
    old_value = Column(String, default="")
    new_value = Column(String, nullable=False)

    status = Column(String, default="pending", index=True)   # pending|approved|rejected
    note = Column(String, default="")            # why HR turned it down
    decided_by = Column(String, default="")
    decided_at = Column(String, default="")
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBStaffMessage(Base):
    """One message in a thread, from either side."""
    __tablename__ = "staff_messages"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    request_id = Column(Integer, ForeignKey("staff_requests.id"), nullable=False, index=True)

    author = Column(String, default="employee")   # employee | hr
    author_name = Column(String, default="")
    body = Column(Text, nullable=False)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    request = relationship("DBStaffRequest", back_populates="messages")


class DBClientGateway(Base):
    """A business's own payment credentials, for collecting from its customers.

    Deliberately separate from the platform's keys. The platform's live in the
    environment and take wallet top-ups - money paid to us. These belong to the
    tenant and take invoice payments - money paid to them. Mixing the two would
    route a customer's payment into the wrong account.

    Secrets are stored so a payment can be verified server-side. They are never
    returned to any browser; the read endpoint masks them.
    """
    __tablename__ = "client_gateways"
    __table_args__ = (
        UniqueConstraint('client_id', 'provider', name='uq_client_gateway'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    provider = Column(String, nullable=False)        # stripe | razorpay | paypal

    # The half that is safe in a browser - Razorpay's key id, Stripe's
    # publishable key, PayPal's client id.
    public_key = Column(String, default="")
    # The half that never leaves the server.
    secret_key = Column(String, default="")
    webhook_secret = Column(String, default="")

    is_active = Column(Boolean, default=True, index=True)
    is_live = Column(Boolean, default=False)         # false while using test keys
    updated_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class DBSettlement(Base):
    """Money collected on a tenant's behalf, and whether it has reached them.

    When the platform takes invoice payments into its own account, the customer
    has paid and the tenant has not been paid. Without a record of that, the
    money is simply missing from the tenant's point of view. Every collection
    writes a row here, and it stays owed until somebody says it went out.
    """
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)

    amount_minor = Column(Integer, default=0)
    currency = Column(String, default="INR")

    # owed | paid_out
    status = Column(String, default="owed", index=True)
    collected_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    paid_out_at = Column(String, default="")
    payout_reference = Column(String, default="")

    # The gateway payment this came from, so it can be traced both ways.
    gateway = Column(String, default="razorpay")
    gateway_payment_id = Column(String, default="", index=True)


class DBPaymentMandate(Base):
    """Standing permission to charge somebody without them being present.

    Two different payers use the same shape:

      payer_type 'customer' - a customer of one of our businesses authorised
                              their invoices to be paid automatically.
      payer_type 'tenant'   - a business authorised its own wallet to top
                              itself up when it runs low.

    The token is what the gateway gives back after an authorised payment; it
    stands in for the card or UPI id, which we never hold. A mandate carries
    its own ceiling, because "you may charge me" is not "you may charge me
    anything".
    """
    __tablename__ = "payment_mandates"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    payer_type = Column(String, default="customer", index=True)   # customer | tenant
    # Which customer of this business, matched the way invoices are.
    payer_ref = Column(String, default="", index=True)

    provider = Column(String, default="razorpay")
    token_id = Column(String, default="", index=True)
    customer_id = Column(String, default="")
    method = Column(String, default="")        # card | upi | emandate
    masked = Column(String, default="")        # last four, or the vpa

    # active | cancelled | failed
    status = Column(String, default="active", index=True)
    max_amount_minor = Column(Integer, default=0)
    currency = Column(String, default="INR")

    created_from_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    created_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    last_used_at = Column(String, default="")
    cancelled_at = Column(String, default="")
    failure_reason = Column(String, default="")


class DBAutoCharge(Base):
    """One attempt to charge a mandate, kept whether it worked or not.

    Every attempt is written before the gateway is called, so a crash midway
    leaves a record rather than a silent gap, and the same thing is never
    charged twice for the same reason.
    """
    __tablename__ = "auto_charges"
    __table_args__ = (
        UniqueConstraint('idempotency_key', name='uq_auto_charge_key'),
    )

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    mandate_id = Column(Integer, ForeignKey("payment_mandates.id"), nullable=False, index=True)

    # invoice | wallet_topup
    purpose = Column(String, default="invoice", index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)

    amount_minor = Column(Integer, default=0)
    currency = Column(String, default="INR")

    # What makes a retry safe: one key per thing-being-paid-for.
    idempotency_key = Column(String, nullable=False, index=True)

    # pending | succeeded | failed
    status = Column(String, default="pending", index=True)
    gateway_payment_id = Column(String, default="")
    failure_reason = Column(String, default="")
    attempted_at = Column(String, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    settled_at = Column(String, default="")
