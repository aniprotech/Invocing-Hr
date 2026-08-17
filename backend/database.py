import os
import sys
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

# SQLAlchemy 1.4+ requires postgresql:// instead of postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    print("WARNING: No DATABASE_URL found in .env, falling back to SQLite")
    DATABASE_URL = "sqlite:///./invoicing.db"

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=2,
        max_overflow=3,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Populated by ensure_columns(). A migration that silently did not run is
# indistinguishable from one that succeeded, so failures are recorded and
# surfaced on /api/health rather than disappearing.
MIGRATION_ERRORS = []


def migration_report():
    return list(MIGRATION_ERRORS)


def ensure_columns():
    """Add missing columns to existing tables."""
    if DATABASE_URL.startswith("sqlite"):
        return
    try:
        with engine.connect() as conn:
            # line_items.name
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='line_items' AND column_name='name'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE line_items ADD COLUMN name VARCHAR DEFAULT ''"))
                conn.commit()
                print("Added 'name' column to line_items table")

            # invoices.client_id
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='invoices' AND column_name='client_id'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE invoices ADD COLUMN client_id INTEGER"))
                conn.commit()
                print("Added 'client_id' column to invoices table")

            # settings.client_id
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='settings' AND column_name='client_id'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE settings ADD COLUMN client_id INTEGER"))
                conn.commit()
                print("Added 'client_id' column to settings table")

            # contacts.client_id
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='contacts' AND column_name='client_id'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE contacts ADD COLUMN client_id INTEGER"))
                conn.commit()
                print("Added 'client_id' column to contacts table")

            # invoices.tracking_id
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='invoices' AND column_name='tracking_id'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE invoices ADD COLUMN tracking_id VARCHAR"))
                conn.commit()
                print("Added 'tracking_id' column to invoices table")

            # invoices.open_count
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='invoices' AND column_name='open_count'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE invoices ADD COLUMN open_count INTEGER DEFAULT 0"))
                conn.commit()
                print("Added 'open_count' column to invoices table")

            # invoices.last_opened
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='invoices' AND column_name='last_opened'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE invoices ADD COLUMN last_opened VARCHAR DEFAULT ''"))
                conn.commit()
                print("Added 'last_opened' column to invoices table")

            # invoices.currency
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='invoices' AND column_name='currency'"))
            if not result.fetchone():
                conn.execute(text("ALTER TABLE invoices ADD COLUMN currency VARCHAR DEFAULT ''"))
                conn.commit()
                print("Added 'currency' column to invoices table")

            # Backfill tracking_ids for existing invoices (single query, no SQL injection)
            try:
                conn.execute(text("UPDATE invoices SET tracking_id = gen_random_uuid()::text WHERE tracking_id IS NULL OR tracking_id = ''"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 1: {sys.exc_info()[1]}")

            # Make settings.key non-unique (now per-client)
            try:
                result = conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = :tname AND indexdef LIKE '%UNIQUE%' AND indexdef LIKE '%key%'"), {"tname": "settings"})
                for row in result.fetchall():
                    conn.execute(text(f"DROP INDEX IF EXISTS {row[0]}"))
                    conn.commit()
                    print(f"Dropped unique index on settings.key: {row[0]}")
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 2: {sys.exc_info()[1]}")
            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_settings_key ON settings (key)"))
                conn.commit()
                print("Created non-unique index ix_settings_key")
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 3: {sys.exc_info()[1]}")

            # Drop old global unique constraint on invoices.number (now per-client unique)
            try:
                result = conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = :tname"), {"tname": "invoices"})
                for row in result.fetchall():
                    idx_name = row[0]
                    if "number" in idx_name and idx_name != "uq_client_invoice_number":
                        conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
                        conn.commit()
                        print(f"Dropped old index: {idx_name}")
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 4: {sys.exc_info()[1]}")

            # Add composite unique constraint (client_id, number) if not exists
            try:
                conn.execute(text("ALTER TABLE invoices ADD CONSTRAINT uq_client_invoice_number UNIQUE (client_id, number)"))
                conn.commit()
                print("Added composite unique constraint (client_id, number)")
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 5: {sys.exc_info()[1]}")

            # Create performance indexes on foreign keys (safe to run multiple times)
            idx_statements = [
                "CREATE INDEX IF NOT EXISTS ix_invoices_client_id ON invoices (client_id)",
                "CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices (status)",
                "CREATE INDEX IF NOT EXISTS ix_line_items_invoice_id ON line_items (invoice_id)",
                "CREATE INDEX IF NOT EXISTS ix_contacts_client_id ON contacts (client_id)",
                "CREATE INDEX IF NOT EXISTS ix_settings_client_id ON settings (client_id)",
            ]
            for stmt in idx_statements:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    MIGRATION_ERRORS.append(f"migration step 6: {sys.exc_info()[1]}")
            conn.commit()

            # Create HR tables if they don't exist
            hr_tables = [
                """CREATE TABLE IF NOT EXISTS departments (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id),
                    name VARCHAR NOT NULL,
                    description VARCHAR DEFAULT '',
                    created_at VARCHAR DEFAULT ''
                )""",
                """CREATE TABLE IF NOT EXISTS employees (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id),
                    department_id INTEGER REFERENCES departments(id),
                    reports_to INTEGER REFERENCES employees(id),
                    employee_id VARCHAR DEFAULT '',
                    first_name VARCHAR NOT NULL,
                    last_name VARCHAR NOT NULL,
                    email VARCHAR NOT NULL,
                    phone VARCHAR DEFAULT '',
                    address VARCHAR DEFAULT '',
                    job_title VARCHAR DEFAULT '',
                    role VARCHAR DEFAULT 'employee',
                    employment_type VARCHAR DEFAULT 'full_time',
                    pay_frequency VARCHAR DEFAULT 'monthly',
                    salary DOUBLE PRECISION DEFAULT 0,
                    hourly_rate DOUBLE PRECISION DEFAULT 0,
                    tax_rate DOUBLE PRECISION DEFAULT 0,
                    deductions DOUBLE PRECISION DEFAULT 0,
                    allowances DOUBLE PRECISION DEFAULT 0,
                    bonus DOUBLE PRECISION DEFAULT 0,
                    bank_name VARCHAR DEFAULT '',
                    bank_account VARCHAR DEFAULT '',
                    tax_id VARCHAR DEFAULT '',
                    emergency_contact VARCHAR DEFAULT '',
                    emergency_phone VARCHAR DEFAULT '',
                    start_date VARCHAR DEFAULT '',
                    end_date VARCHAR DEFAULT '',
                    status VARCHAR DEFAULT 'active',
                    onboarding_complete BOOLEAN DEFAULT FALSE,
                    offboarding_complete BOOLEAN DEFAULT FALSE,
                    created_at VARCHAR DEFAULT ''
                )""",
                """CREATE TABLE IF NOT EXISTS payslips (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id),
                    employee_id INTEGER REFERENCES employees(id) NOT NULL,
                    number VARCHAR,
                    period_start VARCHAR DEFAULT '',
                    period_end VARCHAR DEFAULT '',
                    pay_date VARCHAR DEFAULT '',
                    hours_worked DOUBLE PRECISION DEFAULT 0,
                    overtime_hours DOUBLE PRECISION DEFAULT 0,
                    overtime_rate DOUBLE PRECISION DEFAULT 0,
                    basic_salary DOUBLE PRECISION DEFAULT 0,
                    overtime_pay DOUBLE PRECISION DEFAULT 0,
                    bonus DOUBLE PRECISION DEFAULT 0,
                    allowances DOUBLE PRECISION DEFAULT 0,
                    gross_pay DOUBLE PRECISION DEFAULT 0,
                    tax_amount DOUBLE PRECISION DEFAULT 0,
                    insurance DOUBLE PRECISION DEFAULT 0,
                    retirement DOUBLE PRECISION DEFAULT 0,
                    other_deductions DOUBLE PRECISION DEFAULT 0,
                    total_deductions DOUBLE PRECISION DEFAULT 0,
                    net_pay DOUBLE PRECISION DEFAULT 0,
                    status VARCHAR DEFAULT 'Draft',
                    sent VARCHAR DEFAULT '',
                    notes VARCHAR DEFAULT '',
                    tracking_id VARCHAR,
                    open_count INTEGER DEFAULT 0,
                    last_opened VARCHAR DEFAULT '',
                    created_at VARCHAR DEFAULT '',
                    UNIQUE(client_id, number)
                )""",
                """CREATE TABLE IF NOT EXISTS onboarding_items (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id),
                    employee_id INTEGER REFERENCES employees(id) NOT NULL,
                    title VARCHAR NOT NULL,
                    description VARCHAR DEFAULT '',
                    category VARCHAR DEFAULT 'general',
                    is_completed BOOLEAN DEFAULT FALSE,
                    completed_at VARCHAR DEFAULT '',
                    assigned_to VARCHAR DEFAULT '',
                    due_date VARCHAR DEFAULT ''
                )""",
                """CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id),
                    employee_id INTEGER REFERENCES employees(id) NOT NULL,
                    date VARCHAR NOT NULL,
                    clock_in VARCHAR DEFAULT '',
                    clock_out VARCHAR DEFAULT '',
                    total_hours FLOAT DEFAULT 0.0,
                    status VARCHAR DEFAULT 'present',
                    check_type VARCHAR DEFAULT 'manual',
                    ip_address VARCHAR DEFAULT '',
                    device_info VARCHAR DEFAULT '',
                    location_lat FLOAT DEFAULT 0.0,
                    location_lng FLOAT DEFAULT 0.0,
                    location_label VARCHAR DEFAULT '',
                    break_minutes FLOAT DEFAULT 0.0,
                    overtime_hours FLOAT DEFAULT 0.0,
                    notes VARCHAR DEFAULT '',
                    created_at VARCHAR DEFAULT ''
                )""",
                """CREATE TABLE IF NOT EXISTS attendance_settings (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER REFERENCES clients(id) UNIQUE,
                    office_name VARCHAR DEFAULT 'Head Office',
                    office_lat FLOAT DEFAULT 0.0,
                    office_lng FLOAT DEFAULT 0.0,
                    geofence_radius FLOAT DEFAULT 200.0,
                    work_start VARCHAR DEFAULT '09:00',
                    work_end VARCHAR DEFAULT '17:30',
                    grace_minutes FLOAT DEFAULT 15.0,
                    auto_clockout_hours FLOAT DEFAULT 10.0,
                    max_overtime_hours FLOAT DEFAULT 4.0,
                    allow_remote BOOLEAN DEFAULT TRUE,
                    require_location BOOLEAN DEFAULT TRUE,
                    created_at VARCHAR DEFAULT ''
                )""",
            ]
            for sql in hr_tables:
                try:
                    conn.execute(text(sql))
                except Exception:
                    MIGRATION_ERRORS.append(f"migration step 7: {sys.exc_info()[1]}")
            conn.commit()

            # Create indexes for HR tables
            hr_indexes = [
                "CREATE INDEX IF NOT EXISTS ix_employees_client_id ON employees (client_id)",
                "CREATE INDEX IF NOT EXISTS ix_employees_department_id ON employees (department_id)",
                "CREATE INDEX IF NOT EXISTS ix_employees_reports_to ON employees (reports_to)",
                "CREATE INDEX IF NOT EXISTS ix_employees_status ON employees (status)",
                "CREATE INDEX IF NOT EXISTS ix_payslips_client_id ON payslips (client_id)",
                "CREATE INDEX IF NOT EXISTS ix_payslips_employee_id ON payslips (employee_id)",
                "CREATE INDEX IF NOT EXISTS ix_payslips_status ON payslips (status)",
                "CREATE INDEX IF NOT EXISTS ix_departments_client_id ON departments (client_id)",
                "CREATE INDEX IF NOT EXISTS ix_onboarding_items_client_id ON onboarding_items (client_id)",
                "CREATE INDEX IF NOT EXISTS ix_onboarding_items_employee_id ON onboarding_items (employee_id)",
                "CREATE INDEX IF NOT EXISTS ix_attendance_client_id ON attendance (client_id)",
                "CREATE INDEX IF NOT EXISTS ix_attendance_employee_id ON attendance (employee_id)",
                "CREATE INDEX IF NOT EXISTS ix_attendance_date ON attendance (date)",
                "CREATE INDEX IF NOT EXISTS ix_attendance_status ON attendance (status)",
                "CREATE INDEX IF NOT EXISTS ix_attendance_settings_client_id ON attendance_settings (client_id)",
            ]
            for stmt in hr_indexes:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    MIGRATION_ERRORS.append(f"migration step 8: {sys.exc_info()[1]}")
            conn.commit()

            # Add new columns to existing tables
            alter_statements = [
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS password_hash VARCHAR DEFAULT ''",
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS work_location VARCHAR DEFAULT ''",
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS latitude FLOAT DEFAULT 0.0",
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS longitude FLOAT DEFAULT 0.0",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS check_type VARCHAR DEFAULT 'manual'",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS ip_address VARCHAR DEFAULT ''",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS device_info VARCHAR DEFAULT ''",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS location_lat FLOAT DEFAULT 0.0",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS location_lng FLOAT DEFAULT 0.0",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS location_label VARCHAR DEFAULT ''",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS break_minutes FLOAT DEFAULT 0.0",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS overtime_hours FLOAT DEFAULT 0.0",
                "ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_login VARCHAR DEFAULT ''",
                "ALTER TABLE clients ADD COLUMN IF NOT EXISTS login_count INTEGER DEFAULT 0",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS break_start VARCHAR DEFAULT ''",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS is_on_break BOOLEAN DEFAULT FALSE",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS overtime_announced BOOLEAN DEFAULT FALSE",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS overtime_announced_by VARCHAR DEFAULT ''",
            ]
            for stmt in alter_statements:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    MIGRATION_ERRORS.append(f"migration step 9: {sys.exc_info()[1]}")
            conn.commit()

            # Create client_login_logs table
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS client_login_logs (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        email VARCHAR NOT NULL,
                        user_type VARCHAR DEFAULT 'client',
                        login_type VARCHAR DEFAULT 'password',
                        ip_address VARCHAR DEFAULT '',
                        device_info VARCHAR DEFAULT '',
                        location_label VARCHAR DEFAULT '',
                        status VARCHAR DEFAULT 'success',
                        created_at VARCHAR DEFAULT ''
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_login_logs_client_id ON client_login_logs (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_login_logs_email ON client_login_logs (email)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_login_logs_created_at ON client_login_logs (created_at)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 10: {sys.exc_info()[1]}")

            # Create overtime_logs table
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS overtime_logs (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        employee_id INTEGER REFERENCES employees(id) NOT NULL,
                        date VARCHAR NOT NULL,
                        hours FLOAT DEFAULT 0.0,
                        reason VARCHAR DEFAULT '',
                        announced_by VARCHAR DEFAULT '',
                        status VARCHAR DEFAULT 'announced',
                        created_at VARCHAR DEFAULT ''
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_overtime_logs_client_id ON overtime_logs (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_overtime_logs_employee_id ON overtime_logs (employee_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 11: {sys.exc_info()[1]}")

            # Recruitment tables
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS recruitment_forms (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        title VARCHAR NOT NULL,
                        description VARCHAR DEFAULT '',
                        fields TEXT DEFAULT '[]',
                        is_active BOOLEAN DEFAULT TRUE,
                        form_token VARCHAR UNIQUE,
                        pipeline_stages TEXT DEFAULT '["Applied","Screening","Interview","Offer","Hired"]',
                        created_at VARCHAR DEFAULT ''
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recruitment_forms_client_id ON recruitment_forms (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recruitment_forms_form_token ON recruitment_forms (form_token)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 12: {sys.exc_info()[1]}")

            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS form_submissions (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        form_id INTEGER REFERENCES recruitment_forms(id) NOT NULL,
                        answers TEXT DEFAULT '{}',
                        file_name VARCHAR DEFAULT '',
                        file_type VARCHAR DEFAULT '',
                        file_data TEXT DEFAULT '',
                        candidate_name VARCHAR DEFAULT '',
                        candidate_email VARCHAR DEFAULT '',
                        status VARCHAR DEFAULT 'new',
                        current_stage VARCHAR DEFAULT 'Applied',
                        stage_order INTEGER DEFAULT 0,
                        notes VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT ''
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_form_submissions_client_id ON form_submissions (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_form_submissions_form_id ON form_submissions (form_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 13: {sys.exc_info()[1]}")

            try:
                conn.execute(text("ALTER TABLE recruitment_forms ADD COLUMN IF NOT EXISTS pipeline_stages TEXT DEFAULT '[]'"))
                conn.execute(text("ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS current_stage VARCHAR DEFAULT 'Applied'"))
                conn.execute(text("ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS stage_order INTEGER DEFAULT 0"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 14: {sys.exc_info()[1]}")

            # Department color/icon
            try:
                conn.execute(text("ALTER TABLE departments ADD COLUMN IF NOT EXISTS color VARCHAR DEFAULT '#00f0ff'"))
                conn.execute(text("ALTER TABLE departments ADD COLUMN IF NOT EXISTS icon VARCHAR DEFAULT 'building'"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 15: {sys.exc_info()[1]}")

            # Onboarding item sort_order
            try:
                conn.execute(text("ALTER TABLE onboarding_items ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 16: {sys.exc_info()[1]}")

            # Onboarding templates table
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS onboarding_templates (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        name VARCHAR NOT NULL,
                        items_json TEXT DEFAULT '[]',
                        created_at VARCHAR DEFAULT ''
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_onboarding_templates_client_id ON onboarding_templates (client_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 17: {sys.exc_info()[1]}")

            # employee_goals.department_id
            try:
                conn.execute(text("ALTER TABLE employee_goals ADD COLUMN IF NOT EXISTS department_id INTEGER"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_employee_goals_department_id ON employee_goals (department_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 18: {sys.exc_info()[1]}")

            # Invoices bank_details
            try:
                conn.execute(text("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS bank_details TEXT DEFAULT ''"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 19: {sys.exc_info()[1]}")

            # Bills tables
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS bills (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        number VARCHAR,
                        vendor_name VARCHAR DEFAULT '',
                        vendor_email VARCHAR DEFAULT '',
                        issue_date VARCHAR DEFAULT '',
                        due_date VARCHAR DEFAULT '',
                        amount DOUBLE PRECISION DEFAULT 0,
                        tax_amount DOUBLE PRECISION DEFAULT 0,
                        total DOUBLE PRECISION DEFAULT 0,
                        amount_paid DOUBLE PRECISION DEFAULT 0,
                        status VARCHAR DEFAULT 'Draft',
                        category VARCHAR DEFAULT 'general',
                        reference VARCHAR DEFAULT '',
                        notes VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT '',
                        UNIQUE(client_id, number)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bills_client_id ON bills (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bills_status ON bills (status)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 20: {sys.exc_info()[1]}")

            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS bill_line_items (
                        id SERIAL PRIMARY KEY,
                        bill_id INTEGER REFERENCES bills(id),
                        description VARCHAR DEFAULT '',
                        qty DOUBLE PRECISION DEFAULT 1,
                        price DOUBLE PRECISION DEFAULT 0,
                        tax_rate VARCHAR DEFAULT '20%'
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bill_line_items_bill_id ON bill_line_items (bill_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 21: {sys.exc_info()[1]}")

            # Department goals table
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS department_goals (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        department_id INTEGER REFERENCES departments(id),
                        title VARCHAR NOT NULL,
                        description VARCHAR DEFAULT '',
                        target_value DOUBLE PRECISION DEFAULT 100,
                        unit VARCHAR DEFAULT '%',
                        category VARCHAR DEFAULT 'performance',
                        priority VARCHAR DEFAULT 'medium',
                        start_date VARCHAR DEFAULT '',
                        due_date VARCHAR DEFAULT '',
                        created_by VARCHAR DEFAULT 'HR',
                        is_assigned BOOLEAN DEFAULT FALSE,
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_department_goals_client_id ON department_goals (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_department_goals_department_id ON department_goals (department_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 22: {sys.exc_info()[1]}")

            # clients.currency
            try:
                conn.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS currency VARCHAR DEFAULT 'GBP'"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 23: {sys.exc_info()[1]}")

            # Invoice payment ledger
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS payments (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        invoice_id INTEGER REFERENCES invoices(id) NOT NULL,
                        amount DOUBLE PRECISION DEFAULT 0,
                        paid_on VARCHAR DEFAULT '',
                        method VARCHAR DEFAULT 'bank_transfer',
                        reference VARCHAR DEFAULT '',
                        note VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payments_client_id ON payments (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payments_invoice_id ON payments (invoice_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 24: {sys.exc_info()[1]}")

            # Leave entitlement / balance tracking
            try:
                conn.execute(text("ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS decided_at VARCHAR DEFAULT ''"))
                conn.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS annual_leave_entitlement DOUBLE PRECISION DEFAULT 25"))
                conn.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS sick_leave_entitlement DOUBLE PRECISION DEFAULT 10"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 25: {sys.exc_info()[1]}")

            # Recruitment: job requisitions, interviews and offers
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS job_requisitions (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        reference VARCHAR DEFAULT '',
                        title VARCHAR NOT NULL,
                        department_id INTEGER REFERENCES departments(id),
                        hiring_manager_id INTEGER REFERENCES employees(id),
                        description TEXT DEFAULT '',
                        requirements TEXT DEFAULT '',
                        location VARCHAR DEFAULT '',
                        work_mode VARCHAR DEFAULT 'onsite',
                        employment_type VARCHAR DEFAULT 'full_time',
                        level VARCHAR DEFAULT '',
                        salary_min DOUBLE PRECISION DEFAULT 0,
                        salary_max DOUBLE PRECISION DEFAULT 0,
                        salary_currency VARCHAR DEFAULT '',
                        show_salary BOOLEAN DEFAULT TRUE,
                        openings INTEGER DEFAULT 1,
                        status VARCHAR DEFAULT 'draft',
                        is_published BOOLEAN DEFAULT FALSE,
                        closing_date VARCHAR DEFAULT '',
                        opened_at VARCHAR DEFAULT '',
                        closed_at VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_job_requisitions_client ON job_requisitions (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_job_requisitions_status ON job_requisitions (status)"))
                conn.execute(text("ALTER TABLE recruitment_forms ADD COLUMN IF NOT EXISTS job_id INTEGER"))

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS interviews (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        submission_id INTEGER REFERENCES form_submissions(id) NOT NULL,
                        round_name VARCHAR DEFAULT 'Interview',
                        scheduled_at VARCHAR DEFAULT '',
                        duration_minutes INTEGER DEFAULT 45,
                        mode VARCHAR DEFAULT 'video',
                        location VARCHAR DEFAULT '',
                        meeting_link VARCHAR DEFAULT '',
                        interviewer_id INTEGER REFERENCES employees(id),
                        interviewer_name VARCHAR DEFAULT '',
                        status VARCHAR DEFAULT 'scheduled',
                        outcome VARCHAR DEFAULT '',
                        score INTEGER DEFAULT 0,
                        feedback TEXT DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_interviews_submission ON interviews (submission_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_interviews_scheduled ON interviews (scheduled_at)"))

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS offers (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        submission_id INTEGER REFERENCES form_submissions(id) NOT NULL,
                        job_title VARCHAR DEFAULT '',
                        level VARCHAR DEFAULT '',
                        salary DOUBLE PRECISION DEFAULT 0,
                        currency VARCHAR DEFAULT '',
                        start_date VARCHAR DEFAULT '',
                        expires_on VARCHAR DEFAULT '',
                        notes TEXT DEFAULT '',
                        status VARCHAR DEFAULT 'draft',
                        sent_at VARCHAR DEFAULT '',
                        responded_at VARCHAR DEFAULT '',
                        decline_reason VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_offers_submission ON offers (submission_id)"))

                for col in [
                    "source VARCHAR DEFAULT 'direct'",
                    "owner_name VARCHAR DEFAULT ''",
                    "rejected_reason VARCHAR DEFAULT ''",
                    "rejected_at VARCHAR DEFAULT ''",
                    "hired_at VARCHAR DEFAULT ''",
                ]:
                    conn.execute(text(f"ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS {col}"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 26: {sys.exc_info()[1]}")

            # Recruitment: candidate documents, pipeline history, rating
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS candidate_documents (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        submission_id INTEGER REFERENCES form_submissions(id) NOT NULL,
                        doc_type VARCHAR DEFAULT 'other',
                        file_name VARCHAR DEFAULT '',
                        file_type VARCHAR DEFAULT '',
                        file_size INTEGER DEFAULT 0,
                        file_data TEXT DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_candidate_documents_submission ON candidate_documents (submission_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_candidate_documents_client ON candidate_documents (client_id)"))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS submission_events (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        submission_id INTEGER REFERENCES form_submissions(id) NOT NULL,
                        from_stage VARCHAR DEFAULT '',
                        to_stage VARCHAR DEFAULT '',
                        note VARCHAR DEFAULT '',
                        actor VARCHAR DEFAULT 'HR',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_submission_events_submission ON submission_events (submission_id)"))
                conn.execute(text("ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS rating INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS candidate_phone VARCHAR DEFAULT ''"))
                conn.execute(text("ALTER TABLE form_submissions ADD COLUMN IF NOT EXISTS hired_employee_id INTEGER"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 27: {sys.exc_info()[1]}")

            # Onboarding document requirements and per-employee requests
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS document_requirements (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        name VARCHAR NOT NULL,
                        description VARCHAR DEFAULT '',
                        doc_type VARCHAR DEFAULT 'other',
                        is_mandatory BOOLEAN DEFAULT TRUE,
                        due_days INTEGER DEFAULT 7,
                        applies_to VARCHAR DEFAULT 'all',
                        department_id INTEGER REFERENCES departments(id),
                        level VARCHAR DEFAULT '',
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0,
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_doc_reqs_client ON document_requirements (client_id)"))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS document_requests (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        employee_id INTEGER REFERENCES employees(id) NOT NULL,
                        requirement_id INTEGER REFERENCES document_requirements(id),
                        document_id INTEGER REFERENCES employee_documents(id),
                        name VARCHAR NOT NULL,
                        description VARCHAR DEFAULT '',
                        doc_type VARCHAR DEFAULT 'other',
                        is_mandatory BOOLEAN DEFAULT TRUE,
                        due_date VARCHAR DEFAULT '',
                        status VARCHAR DEFAULT 'pending',
                        submitted_at VARCHAR DEFAULT '',
                        reviewed_at VARCHAR DEFAULT '',
                        reviewed_by VARCHAR DEFAULT '',
                        review_note VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_doc_requests_employee ON document_requests (employee_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_doc_requests_status ON document_requests (status)"))
                conn.execute(text("ALTER TABLE employee_documents ADD COLUMN IF NOT EXISTS file_size INTEGER DEFAULT 0"))
                for col in [
                    "requires_expiry BOOLEAN DEFAULT FALSE",
                    "expiry_reminder_days INTEGER DEFAULT 30",
                    "template_file_name VARCHAR DEFAULT ''",
                    "template_file_type VARCHAR DEFAULT ''",
                    "template_file_data TEXT DEFAULT ''",
                ]:
                    conn.execute(text(f"ALTER TABLE document_requirements ADD COLUMN IF NOT EXISTS {col}"))
                for col in [
                    "requires_expiry BOOLEAN DEFAULT FALSE",
                    "expires_on VARCHAR DEFAULT ''",
                ]:
                    conn.execute(text(f"ALTER TABLE document_requests ADD COLUMN IF NOT EXISTS {col}"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_doc_requests_expires ON document_requests (expires_on)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 28: {sys.exc_info()[1]}")

            # Wallet, metered billing and top-up orders
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS wallets (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL UNIQUE,
                        balance_minor INTEGER DEFAULT 0,
                        currency VARCHAR DEFAULT 'GBP',
                        low_balance_minor INTEGER DEFAULT 500,
                        is_suspended BOOLEAN DEFAULT FALSE,
                        lifetime_topped_up_minor INTEGER DEFAULT 0,
                        lifetime_spent_minor INTEGER DEFAULT 0,
                        created_at VARCHAR DEFAULT (NOW()::TEXT),
                        updated_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS wallet_transactions (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL,
                        wallet_id INTEGER REFERENCES wallets(id),
                        direction VARCHAR DEFAULT 'debit',
                        amount_minor INTEGER DEFAULT 0,
                        balance_after_minor INTEGER DEFAULT 0,
                        currency VARCHAR DEFAULT 'GBP',
                        action_key VARCHAR DEFAULT '',
                        module VARCHAR DEFAULT '',
                        description VARCHAR DEFAULT '',
                        reference VARCHAR DEFAULT '',
                        quantity INTEGER DEFAULT 1,
                        performed_by VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wallet_tx_client ON wallet_transactions (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wallet_tx_created ON wallet_transactions (created_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wallet_tx_action ON wallet_transactions (action_key)"))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS pricing_rules (
                        id SERIAL PRIMARY KEY,
                        action_key VARCHAR NOT NULL UNIQUE,
                        label VARCHAR NOT NULL,
                        description VARCHAR DEFAULT '',
                        module VARCHAR DEFAULT 'platform',
                        unit_price_minor INTEGER DEFAULT 0,
                        currency VARCHAR DEFAULT 'GBP',
                        free_allowance INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0,
                        updated_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS topup_orders (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL,
                        provider VARCHAR DEFAULT '',
                        amount_minor INTEGER DEFAULT 0,
                        currency VARCHAR DEFAULT 'GBP',
                        status VARCHAR DEFAULT 'created',
                        provider_order_id VARCHAR DEFAULT '',
                        provider_payment_id VARCHAR DEFAULT '',
                        checkout_url VARCHAR DEFAULT '',
                        failure_reason VARCHAR DEFAULT '',
                        credited BOOLEAN DEFAULT FALSE,
                        credited_at VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_topup_client ON topup_orders (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_topup_provider_order ON topup_orders (provider_order_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 29: {sys.exc_info()[1]}")

            # Employee seniority level
            try:
                conn.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS level VARCHAR DEFAULT ''"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_employees_level ON employees (level)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 30: {sys.exc_info()[1]}")

            # Payslip period guard + YTD support
            try:
                conn.execute(text("ALTER TABLE payslips ADD COLUMN IF NOT EXISTS pay_frequency VARCHAR DEFAULT ''"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payslips_period ON payslips (employee_id, period_start, period_end)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 31: {sys.exc_info()[1]}")

            # Audit logs table
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        user_type VARCHAR DEFAULT 'client',
                        user_name VARCHAR DEFAULT '',
                        action VARCHAR NOT NULL,
                        entity_type VARCHAR DEFAULT '',
                        entity_id INTEGER,
                        entity_name VARCHAR DEFAULT '',
                        details TEXT DEFAULT '',
                        ip_address VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_client_id ON audit_logs (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 32: {sys.exc_info()[1]}")

            # Quotes: priced proposals, numbered separately from invoices
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS quotes (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        number VARCHAR,
                        ref VARCHAR DEFAULT '',
                        to_contact VARCHAR,
                        email VARCHAR DEFAULT '',
                        phone_number VARCHAR DEFAULT '',
                        issue_date VARCHAR,
                        expiry_date VARCHAR,
                        total FLOAT DEFAULT 0.0,
                        status VARCHAR DEFAULT 'Draft',
                        sent VARCHAR DEFAULT '',
                        tax_type VARCHAR DEFAULT 'exclusive',
                        currency VARCHAR DEFAULT '',
                        title VARCHAR DEFAULT '',
                        summary VARCHAR DEFAULT '',
                        terms VARCHAR DEFAULT '',
                        invoice_number VARCHAR DEFAULT '',
                        decided_at VARCHAR DEFAULT '',
                        CONSTRAINT uq_client_quote_number UNIQUE (client_id, number)
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS quote_line_items (
                        id SERIAL PRIMARY KEY,
                        quote_id INTEGER REFERENCES quotes(id),
                        name VARCHAR DEFAULT '',
                        description VARCHAR,
                        qty FLOAT,
                        price FLOAT,
                        disc FLOAT DEFAULT 0.0,
                        account VARCHAR DEFAULT '200 - Sales',
                        tax_rate VARCHAR DEFAULT '20% (VAT on Income)'
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quotes_client_id ON quotes (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quotes_number ON quotes (number)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quotes_status ON quotes (status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_quote_line_items_quote_id ON quote_line_items (quote_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 33: {sys.exc_info()[1]}")

            # Tenant-defined tax rates
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tax_rates (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        name VARCHAR NOT NULL,
                        percent FLOAT DEFAULT 0.0,
                        sort_order INTEGER DEFAULT 0,
                        is_default BOOLEAN DEFAULT FALSE
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tax_rates_client_id ON tax_rates (client_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 34: {sys.exc_info()[1]}")

            # Working days, and whether signing in starts a shift
            try:
                conn.execute(text("ALTER TABLE attendance_settings ADD COLUMN IF NOT EXISTS working_days VARCHAR DEFAULT '1,2,3,4,5'"))
                conn.execute(text("ALTER TABLE attendance_settings ADD COLUMN IF NOT EXISTS auto_clock_in BOOLEAN DEFAULT TRUE"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 35: {sys.exc_info()[1]}")

            # Password reset links
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS password_resets (
                        id SERIAL PRIMARY KEY,
                        user_type VARCHAR DEFAULT 'client',
                        client_id INTEGER REFERENCES clients(id),
                        employee_id INTEGER REFERENCES employees(id),
                        token_hash VARCHAR NOT NULL,
                        expires_at VARCHAR NOT NULL,
                        used_at VARCHAR DEFAULT '',
                        requested_ip VARCHAR DEFAULT '',
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_resets_token ON password_resets (token_hash)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_resets_client_id ON password_resets (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_password_resets_employee_id ON password_resets (employee_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 36: {sys.exc_info()[1]}")

            # Scheduled job claims
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS job_runs (
                        id SERIAL PRIMARY KEY,
                        job_name VARCHAR NOT NULL,
                        period_key VARCHAR NOT NULL,
                        status VARCHAR DEFAULT 'running',
                        detail VARCHAR DEFAULT '',
                        started_at VARCHAR DEFAULT (NOW()::TEXT),
                        finished_at VARCHAR DEFAULT '',
                        CONSTRAINT uq_job_period UNIQUE (job_name, period_key)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_job_runs_job_name ON job_runs (job_name)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 37: {sys.exc_info()[1]}")

            # Recurring invoices and the reminder ladder
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS recurring_invoices (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL,
                        name VARCHAR DEFAULT '',
                        to_contact VARCHAR DEFAULT '',
                        email VARCHAR DEFAULT '',
                        phone_number VARCHAR DEFAULT '',
                        reference VARCHAR DEFAULT '',
                        tax_type VARCHAR DEFAULT 'exclusive',
                        currency VARCHAR DEFAULT '',
                        bank_details VARCHAR DEFAULT '',
                        frequency VARCHAR DEFAULT 'monthly',
                        payment_terms_days INTEGER DEFAULT 14,
                        next_run VARCHAR DEFAULT '',
                        end_date VARCHAR DEFAULT '',
                        is_active BOOLEAN DEFAULT TRUE,
                        auto_send BOOLEAN DEFAULT FALSE,
                        last_run VARCHAR DEFAULT '',
                        last_invoice_number VARCHAR DEFAULT '',
                        invoices_created INTEGER DEFAULT 0,
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS recurring_line_items (
                        id SERIAL PRIMARY KEY,
                        recurring_id INTEGER REFERENCES recurring_invoices(id),
                        name VARCHAR DEFAULT '',
                        description VARCHAR,
                        qty FLOAT,
                        price FLOAT,
                        disc FLOAT DEFAULT 0.0,
                        account VARCHAR DEFAULT '200 - Sales',
                        tax_rate VARCHAR DEFAULT '20% (VAT on Income)'
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS invoice_reminders (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        invoice_id INTEGER REFERENCES invoices(id) NOT NULL,
                        stage_days INTEGER DEFAULT 0,
                        sent_to VARCHAR DEFAULT '',
                        sent_at VARCHAR DEFAULT (NOW()::TEXT),
                        CONSTRAINT uq_invoice_reminder_stage UNIQUE (invoice_id, stage_days)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recurring_client_id ON recurring_invoices (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recurring_next_run ON recurring_invoices (next_run)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_invoice_reminders_invoice ON invoice_reminders (invoice_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 38: {sys.exc_info()[1]}")

            # Team members, so a company is not one shared login
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS team_members (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL,
                        email VARCHAR NOT NULL,
                        name VARCHAR DEFAULT '',
                        password_hash VARCHAR DEFAULT '',
                        role VARCHAR DEFAULT 'admin',
                        is_active BOOLEAN DEFAULT TRUE,
                        invited_at VARCHAR DEFAULT (NOW()::TEXT),
                        accepted_at VARCHAR DEFAULT '',
                        last_login VARCHAR DEFAULT '',
                        CONSTRAINT uq_client_member_email UNIQUE (client_id, email)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_team_members_client_id ON team_members (client_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_team_members_email ON team_members (email)"))
                conn.execute(text("ALTER TABLE password_resets ADD COLUMN IF NOT EXISTS member_id INTEGER"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 39: {sys.exc_info()[1]}")

            # Interview reminders
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS interview_reminders (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id),
                        interview_id INTEGER REFERENCES interviews(id) NOT NULL,
                        recipient VARCHAR DEFAULT 'candidate',
                        sent_to VARCHAR DEFAULT '',
                        sent_at VARCHAR DEFAULT (NOW()::TEXT),
                        CONSTRAINT uq_interview_reminder UNIQUE (interview_id, recipient)
                    )
                """))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_interview_reminders_iv ON interview_reminders (interview_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 40: {sys.exc_info()[1]}")

            # Branding themes - how invoices and quotes are presented
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS branding_themes (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL,
                        name VARCHAR DEFAULT 'Standard',
                        is_default BOOLEAN DEFAULT FALSE,
                        logo_data TEXT DEFAULT '',
                        logo_position VARCHAR DEFAULT 'right',
                        brand_color VARCHAR DEFAULT '#4F46E5',
                        font VARCHAR DEFAULT 'helvetica',
                        show_item BOOLEAN DEFAULT FALSE,
                        show_quantity BOOLEAN DEFAULT TRUE,
                        show_price BOOLEAN DEFAULT TRUE,
                        show_discount BOOLEAN DEFAULT FALSE,
                        show_tax BOOLEAN DEFAULT TRUE,
                        label_item VARCHAR DEFAULT 'Item',
                        label_description VARCHAR DEFAULT 'Description',
                        label_quantity VARCHAR DEFAULT 'Quantity',
                        label_price VARCHAR DEFAULT 'Unit Price',
                        label_discount VARCHAR DEFAULT 'Discount',
                        label_tax VARCHAR DEFAULT 'Tax',
                        label_amount VARCHAR DEFAULT 'Amount',
                        tax_breakdown VARCHAR DEFAULT 'separate_rates',
                        exclude_zero_rates BOOLEAN DEFAULT FALSE,
                        always_show_currency_code BOOLEAN DEFAULT FALSE,
                        show_conversion_rate BOOLEAN DEFAULT FALSE,
                        show_text_links BOOLEAN DEFAULT TRUE,
                        show_qr_code BOOLEAN DEFAULT TRUE,
                        approved_invoice_title VARCHAR DEFAULT 'TAX INVOICE',
                        draft_invoice_title VARCHAR DEFAULT 'DRAFT INVOICE',
                        quote_title VARCHAR DEFAULT 'QUOTE',
                        payment_terms TEXT DEFAULT '',
                        footer_note TEXT DEFAULT '',
                        address_position VARCHAR DEFAULT 'default',
                        show_page_numbers BOOLEAN DEFAULT TRUE,
                        created_at VARCHAR DEFAULT (NOW()::TEXT),
                        updated_at VARCHAR DEFAULT (NOW()::TEXT),
                        CONSTRAINT uq_client_theme_name UNIQUE (client_id, name)
                    )
                """))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_branding_themes_client "
                    "ON branding_themes (client_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 41: {sys.exc_info()[1]}")

            # Who sent a notification. Everything used to be system-generated,
            # so there was nobody to name; now HR can send one directly and an
            # employee should see who it came from.
            try:
                conn.execute(text(
                    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS "
                    "sent_by VARCHAR DEFAULT ''"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 42: {sys.exc_info()[1]}")

            # Two-way conversation between an employee and HR, and the way to
            # raise anything that is not leave.
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS staff_requests (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL,
                        employee_id INTEGER REFERENCES employees(id) NOT NULL,
                        subject VARCHAR NOT NULL,
                        category VARCHAR DEFAULT 'question',
                        status VARCHAR DEFAULT 'open',
                        about_document_id INTEGER REFERENCES document_requests(id),
                        created_at VARCHAR DEFAULT (NOW()::TEXT),
                        updated_at VARCHAR DEFAULT (NOW()::TEXT),
                        closed_at VARCHAR DEFAULT ''
                    )
                """))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS staff_messages (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES clients(id) NOT NULL,
                        request_id INTEGER REFERENCES staff_requests(id) NOT NULL,
                        author VARCHAR DEFAULT 'employee',
                        author_name VARCHAR DEFAULT '',
                        body TEXT NOT NULL,
                        created_at VARCHAR DEFAULT (NOW()::TEXT)
                    )
                """))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_staff_requests_emp "
                    "ON staff_requests (employee_id)"))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_staff_messages_req "
                    "ON staff_messages (request_id)"))
                conn.commit()
            except Exception:
                MIGRATION_ERRORS.append(f"migration step 43: {sys.exc_info()[1]}")

    except Exception as e:
        print(f"Column check skipped: {e}")
