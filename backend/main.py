import asyncio
import calendar
import hashlib
import hmac
import secrets
import uuid
import smtplib
import ssl
import json
import re
import html as html_mod
import threading
import time
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse, Response, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta, date
import os
import base64
import logging
from email.message import EmailMessage
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from dotenv import load_dotenv
from authlib.integrations.starlette_client import OAuth
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database import engine, get_db, SessionLocal, ensure_columns
import httpx
import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

def hash_password(password: str) -> str:
    salt = hashlib.sha256(os.urandom(32)).hexdigest().encode()
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return salt.hex() + ':' + pwd_hash.hex()

def verify_password(password: str, stored: str) -> bool:
    """Constant-time check that tolerates legacy/absent hashes instead of
    raising. An unsplittable value used to blow up with a ValueError and
    surface as a 500 rather than a failed login."""
    if not stored or not password:
        return False
    if ':' not in stored:
        # Pre-PBKDF2 records stored a bare sha256 digest.
        return secrets.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)
    try:
        salt_hex, pwd_hash_hex = stored.split(':', 1)
        salt = bytes.fromhex(salt_hex)
    except (ValueError, TypeError):
        return False
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return secrets.compare_digest(pwd_hash.hex(), pwd_hash_hex)

def log_login(db, client_id, email, user_type="client", login_type="password", request=None, status="success"):
    ip = ""
    device = ""
    if request and request.client:
        ip = request.client.host or ""
    if request:
        device = request.headers.get("user-agent", "")[:200]
    log = models.DBClientLoginLog(
        client_id=client_id, email=email, user_type=user_type,
        login_type=login_type, ip_address=ip, device_info=device,
        status=status,
    )
    db.add(log)
    if client_id:
        client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
        if client:
            client.last_login = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            client.login_count = (client.login_count or 0) + 1
    db.commit()

def log_audit(db, client_id, action, entity_type="", entity_id=None, entity_name="", details="", request=None, user_type="client", user_name=""):
    ip = ""
    if request and request.client:
        ip = request.client.host or ""
    log = models.DBAuditLog(
        client_id=client_id, user_type=user_type, user_name=user_name,
        action=action, entity_type=entity_type, entity_id=entity_id,
        entity_name=entity_name, details=details, ip_address=ip,
    )
    db.add(log)

def generate_secret_key() -> str:
    return secrets.token_hex(32)

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == "generate_a_random_secret_string":
    SECRET_KEY = generate_secret_key()
    # Writing to .env only helps on a machine with a persistent disk. On a
    # container platform the file is discarded on redeploy, so a generated key
    # differs every boot and every session is invalidated - all users are
    # silently signed out. Say so loudly rather than logging it as info.
    persisted = False
    try:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "a") as f:
            f.write(f"\nSECRET_KEY={SECRET_KEY}\n")
        persisted = True
    except Exception:
        pass
    logger.warning(
        "SECRET_KEY was not set, so a temporary one was generated%s. "
        "Every restart will sign all users out. Set SECRET_KEY in the "
        "environment to fix this.",
        " and written to .env" if persisted else "",
    )

def ensure_admin_user():
    try:
        with SessionLocal() as db:
            existing_admin = db.query(models.DBAdminUser).first()
            if not existing_admin:
                admin_pwd = os.getenv("ADMIN_PASSWORD", "admin")
                hashed = hash_password(admin_pwd)
                db.add(models.DBAdminUser(username="admin", password=hashed))
                db.commit()
                logger.info("Created default admin user (username=admin)")
            elif existing_admin.password and ':' not in existing_admin.password:
                existing_admin.password = hash_password(existing_admin.password)
                db.commit()
                logger.info("Upgraded admin password to hashed format")
    except Exception as e:
        logger.error(f"Admin user init failed: {e}")

# --- Rate Limiter (in-memory, per-IP) ---
class RateLimiter:
    """Fixed-memory sliding window.

    The previous version kept a dict entry for every key it ever saw and never
    removed them, so a long-running process grew without bound (one entry per
    distinct client IP, forever). Stale keys are now swept periodically.
    """

    SWEEP_INTERVAL = 300  # seconds
    MAX_KEYS = 10000

    def __init__(self):
        self._hits = defaultdict(list)
        self._lock = threading.Lock()
        self._last_sweep = time.time()

    def _sweep(self, now: float, window: int) -> None:
        cutoff = now - max(window, 3600)
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] < cutoff]:
            self._hits.pop(key, None)
        # Hard ceiling in case of a burst of unique keys between sweeps.
        if len(self._hits) > self.MAX_KEYS:
            for key in sorted(self._hits, key=lambda k: self._hits[k][-1])[: len(self._hits) - self.MAX_KEYS]:
                self._hits.pop(key, None)
        self._last_sweep = now

    def is_rate_limited(self, key: str, max_requests: int = 10, window: int = 60) -> bool:
        now = time.time()
        with self._lock:
            if now - self._last_sweep > self.SWEEP_INTERVAL:
                self._sweep(now, window)
            hits = [t for t in self._hits[key] if now - t < window]
            if len(hits) >= max_requests:
                self._hits[key] = hits
                return True
            hits.append(now)
            self._hits[key] = hits
            return False


rate_limiter = RateLimiter()

def esc(val) -> str:
    """HTML-escape a value for safe insertion into HTML."""
    if val is None:
        return ""
    return html_mod.escape(str(val))

# --- Money / tax helpers ---------------------------------------------------
# Line items carry a human-readable tax label ("20% VAT", "5% VAT",
# "0% Zero Rated", "No Tax"). Everything downstream must derive the rate from
# that label rather than assuming a single blanket rate.

DEFAULT_TAX_RATE = 0.20
_TAX_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_tax_rate(label, default: float = DEFAULT_TAX_RATE) -> float:
    """Turn a tax label into a decimal rate. '5% VAT' -> 0.05, 'No Tax' -> 0.0."""
    s = str(label or "").strip()
    if not s:
        return default
    m = _TAX_PCT_RE.search(s)
    if m:
        try:
            return max(0.0, float(m.group(1))) / 100.0
        except ValueError:
            return default
    low = s.lower()
    if any(w in low for w in ("no tax", "none", "zero", "exempt", "outside")):
        return 0.0
    return default


def money(val) -> float:
    """Round to 2dp using banker's-free half-up, which is what invoices expect."""
    try:
        d = Decimal(str(val or 0))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def line_net_amount(qty, price, disc) -> float:
    """Amount for a single line after its percentage discount."""
    amount = float(qty or 0) * float(price or 0)
    d = float(disc or 0)
    if d:
        amount *= (1 - d / 100.0)
    return amount


def compute_invoice_totals(line_items, tax_type: str):
    """Subtotal / tax / total for a set of line items, honouring each line's own
    tax rate. `tax_type` is 'exclusive' (tax added on top), 'inclusive' (prices
    already contain tax) or anything else for no tax."""
    subtotal = 0.0
    tax = 0.0
    for item in line_items or []:
        amount = line_net_amount(
            getattr(item, "qty", None), getattr(item, "price", None), getattr(item, "disc", None)
        )
        rate = parse_tax_rate(getattr(item, "tax_rate", None))
        if tax_type == "exclusive":
            subtotal += amount
            tax += amount * rate
        elif tax_type == "inclusive":
            net = amount / (1 + rate) if rate else amount
            subtotal += net
            tax += amount - net
        else:
            subtotal += amount
    subtotal = money(subtotal)
    tax = money(tax)
    return subtotal, tax, money(subtotal + tax)


def _parse_date(value):
    """Parse a YYYY-MM-DD string, returning None when unusable."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


OPEN_INVOICE_STATUSES = ("Awaiting Payment", "Sent", "Partially Paid", "Overdue")


def invoice_overdue_days(inv, today=None) -> int:
    """Days past the due date for an unsettled invoice; 0 when not overdue."""
    if inv.status in ("Paid", "Draft", "Void"):
        return 0
    if (inv.due or 0) <= 0:
        return 0
    due = _parse_date(inv.due_date)
    if not due:
        return 0
    today = today or datetime.now().date()
    return max(0, (today - due).days)


def apply_payment_status(inv):
    """Keep status/paid/due consistent after a payment changes."""
    total = money((inv.paid or 0) + (inv.due or 0))
    if (inv.due or 0) <= 0.005 and total > 0:
        inv.due = 0.0
        inv.status = "Paid"
    elif (inv.paid or 0) > 0.005:
        inv.status = "Partially Paid"
    return inv


from contextlib import asynccontextmanager

CURRENCY_SYMBOLS = {
    "AED": "د.إ", "AFN": "؋", "ALL": "L", "AMD": "֏", "ANG": "ƒ", "AOA": "Kz", "ARS": "$",
    "AUD": "A$", "AWG": "ƒ", "AZN": "₼", "BAM": "KM", "BBD": "$", "BDT": "৳", "BGN": "лв",
    "BHD": "ب.د", "BIF": "FBu", "BMD": "$", "BND": "$", "BOB": "Bs", "BRL": "R$", "BSD": "$",
    "BTN": "Nu.", "BWP": "P", "BYN": "Br", "BZD": "$", "CAD": "C$", "CDF": "FC", "CHF": "CHF",
    "CLP": "$", "CNY": "¥", "COP": "$", "CRC": "₡", "CUP": "$", "CVE": "Esc", "CZK": "Kč",
    "DJF": "Fdj", "DKK": "kr", "DOP": "RD$", "DZD": "دج", "EGP": "£", "ERN": "Nfk", "ETB": "Br",
    "EUR": "€", "FJD": "FJ$", "FKP": "£", "GBP": "£", "GEL": "₾", "GHS": "₵", "GIP": "£",
    "GMD": "D", "GNF": "FG", "GTQ": "Q", "GYD": "$", "HKD": "HK$", "HNL": "L", "HRK": "kn",
    "HTG": "G", "HUF": "Ft", "IDR": "Rp", "ILS": "₪", "INR": "₹", "IQD": "ع.د", "IRR": "﷼",
    "ISK": "kr", "JMD": "J$", "JOD": "د.ا", "JPY": "¥", "KES": "KSh", "KGS": "с", "KHR": "៛",
    "KMF": "CF", "KPW": "₩", "KRW": "₩", "KWD": "د.ك", "KYD": "CI$", "KZT": "₸", "LAK": "₭",
    "LBP": "ل.ل", "LKR": "₨", "LRD": "$", "LSL": "L", "LYD": "ل.د", "MAD": "د.م.", "MDL": "L",
    "MGA": "Ar", "MKD": "ден", "MMK": "K", "MNT": "₮", "MOP": "MOP$", "MRU": "UM", "MUR": "₨",
    "MVR": "Rf", "MWK": "MK", "MXN": "$", "MYR": "RM", "MZN": "MT", "NAD": "$", "NGN": "₦",
    "NIO": "C$", "NOK": "kr", "NPR": "₨", "NZD": "NZ$", "OMR": "ر.ع.", "PAB": "B/.", "PEN": "S/",
    "PGK": "K", "PHP": "₱", "PKR": "₨", "PLN": "zł", "PYG": "₲", "QAR": "ر.ق", "RON": "lei",
    "RSD": "дин", "RUB": "₽", "RWF": "FRw", "SAR": "﷼", "SBD": "SI$", "SCR": "₨", "SDG": "ج.س",
    "SEK": "kr", "SGD": "S$", "SHP": "£", "SLL": "Le", "SOS": "Sh", "SRD": "$", "SSP": "£",
    "STN": "Db", "SVC": "$", "SYP": "£", "SZL": "L", "THB": "฿", "TJS": "SM", "TMT": "m",
    "TND": "د.ت", "TOP": "T$", "TRY": "₺", "TTD": "TT$", "TWD": "NT$", "TZS": "Sh", "UAH": "₴",
    "UGX": "USh", "USD": "$", "UYU": "$U", "UZS": "so'm", "VES": "Bs", "VND": "₫", "VUV": "VT",
    "WST": "T", "XAF": "FCFA", "XCD": "EC$", "XOF": "CFA", "XPF": "₣", "YER": "﷼", "ZAR": "R",
    "ZMW": "ZK", "ZWL": "Z$",
}

def currency_symbol(code):
    code = (code or "").upper()
    return CURRENCY_SYMBOLS.get(code, code or "£")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        models.Base.metadata.create_all(bind=engine)
        ensure_columns()
        ensure_admin_user()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    ensure_super_admin()

    task = None
    if os.getenv("SCHEDULER_ENABLED", "1") == "1":
        task = asyncio.create_task(scheduler_loop())
        logger.info("Scheduler started, tick every %ss", SCHEDULER_TICK_SECONDS)
    try:
        yield
    finally:
        if task:
            task.cancel()

app = FastAPI(title="Accounting Platform API", lifespan=lifespan)

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]
        with SessionLocal() as db:
            user = db.query(models.DBAdminUser).filter_by(username=username).first()
            if user and verify_password(password, user.password):
                request.session.update({"token": "admin_token"})
                return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("token"))

authentication_backend = AdminAuth(secret_key=SECRET_KEY)
admin = Admin(app, engine, authentication_backend=authentication_backend)

class InvoiceAdmin(ModelView, model=models.DBInvoice):
    column_list = [models.DBInvoice.id, models.DBInvoice.number, models.DBInvoice.to_contact, models.DBInvoice.status]

class LineItemAdmin(ModelView, model=models.DBLineItem):
    column_list = [models.DBLineItem.id, models.DBLineItem.invoice_id, models.DBLineItem.description, models.DBLineItem.price]

class SettingsAdmin(ModelView, model=models.DBSettings):
    column_list = [models.DBSettings.id, models.DBSettings.key, models.DBSettings.value]

class ContactAdmin(ModelView, model=models.DBContact):
    column_list = [models.DBContact.id, models.DBContact.name, models.DBContact.email, models.DBContact.phone_number]

class AdminUserAdmin(ModelView, model=models.DBAdminUser):
    column_list = [models.DBAdminUser.id, models.DBAdminUser.username]

admin.add_view(InvoiceAdmin)
admin.add_view(LineItemAdmin)
admin.add_view(SettingsAdmin)
admin.add_view(ContactAdmin)
admin.add_view(AdminUserAdmin)

# Secure cookies are required in production but silently break local http
# development (the browser refuses to store the session at all). Default to
# secure, and let a local run opt out with COOKIE_SECURE=false.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() not in ("false", "0", "no")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=COOKIE_SECURE,
    max_age=int(os.getenv("SESSION_MAX_AGE", "86400")),
)

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/gmail.send'
    }
)

class LineItem(BaseModel):
    name: Optional[str] = ""
    description: str
    qty: float
    price: float
    disc: Optional[float] = 0.0
    account: Optional[str] = "200 - Sales"
    tax_rate: Optional[str] = "20% (VAT on Income)"

    class Config:
        from_attributes = True

class InvoiceCreate(BaseModel):
    contact: str
    email: Optional[str] = ""
    phone_number: Optional[str] = ""
    issue_date: str
    due_date: str
    invoice_number: Optional[str] = ""
    reference: Optional[str] = ""
    line_items: List[LineItem]
    tax_type: Optional[str] = "exclusive"
    status: Optional[str] = "Draft"
    currency: Optional[str] = ""
    bank_details: Optional[str] = ""

class SendInvoiceEmail(BaseModel):
    logo_data: Optional[str] = ""
    pdf_data: Optional[str] = ""

class TestEmail(BaseModel):
    to_email: str
    subject: str
    body: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """A unique-constraint clash is a client mistake, not a server fault.
    Without this it surfaced as an opaque 500."""
    logger.warning("Integrity error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=409,
        content={"detail": "That record conflicts with one that already exists."},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Log the traceback server-side, return a generic message to the client so
    internals are never echoed back."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    elif path.endswith((".js", ".css")):
        # Scripts and styles carried no cache policy at all, so browsers applied
        # their own guess. A stale copy of these is indistinguishable from the
        # application having reverted. A ?v= URL changes whenever the file does,
        # so those can be kept forever; anything unversioned must be revalidated
        # every time rather than guessed at.
        if request.query_params.get("v"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# --- Client Registration & Auth ---

class ClientRegister(BaseModel):
    email: str
    password: str
    company_name: Optional[str] = ""
    contact_name: Optional[str] = ""

class ClientLogin(BaseModel):
    email: str
    password: str

class ClientOnboard(BaseModel):
    company_name: Optional[str] = ""
    contact_name: Optional[str] = ""
    phone_number: Optional[str] = ""
    address: Optional[str] = ""
    website: Optional[str] = ""
    abn: Optional[str] = ""
    industry: Optional[str] = ""
    logo_url: Optional[str] = ""

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_client_user(request: Request, db: Session):
    client_id = request.session.get("client_id")
    if not client_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
    if not client or not client.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    # Read-only members are stopped here rather than on each endpoint. Every
    # route that touches tenant data resolves the tenant through this function,
    # so there is one place to get right instead of two hundred to remember.
    member_id = request.session.get("member_id")
    if member_id and request.method in WRITE_METHODS:
        member = db.query(models.DBTeamMember).filter(
            models.DBTeamMember.id == member_id).first()
        if not member or not member.is_active:
            raise HTTPException(status_code=403, detail="Your access has been removed")
        if member.role == "viewer":
            raise HTTPException(status_code=403,
                                detail="Your account has read-only access.")
    return client


def require_superadmin(request: Request):
    """The one gate in front of every platform-operator endpoint.

    Defined here, beside get_client_user, for the same reason: a superadmin
    route reaches every tenant's data at once, so the check has to be
    impossible to forget rather than remembered thirty-four times. Prefer
    the SuperAdmin dependency below - it applies the guard from the
    signature, so a new route cannot ship without it.
    """
    if not request.session.get("superadmin_id"):
        raise HTTPException(status_code=401, detail="Not authorized")
    return request.session.get("superadmin_id")


# Declaring `_: int = SuperAdmin` on a route runs the guard before the body,
# so a handler that forgets to call require_superadmin still cannot be reached
# unauthenticated.
SuperAdmin = Depends(require_superadmin)


@app.post("/api/client/register")
def client_register(body: ClientRegister, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"register:{ip}", max_requests=5, window=300):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Try again later.")
    validate_password_strength(body.password)
    existing = db.query(models.DBClient).filter(models.DBClient.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    client = models.DBClient(
        email=body.email,
        password_hash=hash_password(body.password),
        company_name=body.company_name,
        contact_name=body.contact_name,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return {"message": "Account created", "client_id": client.id}

@app.post("/api/client/login")
def client_login(body: ClientLogin, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"login:{ip}", max_requests=10, window=60):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    client = db.query(models.DBClient).filter(models.DBClient.email == body.email).first()
    if not client or not verify_password(body.password, client.password_hash):
        # Not the account owner - it may be one of their colleagues.
        member = db.query(models.DBTeamMember).filter(
            sqlfunc.lower(models.DBTeamMember.email) == (body.email or "").strip().lower()
        ).first()
        if (member and member.is_active and member.password_hash
                and verify_password(body.password, member.password_hash)):
            owner = db.query(models.DBClient).filter(
                models.DBClient.id == member.client_id).first()
            if not owner or not owner.is_active:
                raise HTTPException(status_code=403, detail="Account disabled")
            request.session["client_id"] = owner.id
            request.session["member_id"] = member.id
            member.last_login = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_login(db, owner.id, member.email, "member", "password", request, "success")
            db.commit()
            return {"message": "Logged in", "is_onboarded": owner.is_onboarded,
                    "company_name": owner.company_name, "role": member.role}
        log_login(db, None, body.email, "client", "password", request, "failed")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not client.is_active:
        log_login(db, client.id, body.email, "client", "password", request, "disabled")
        raise HTTPException(status_code=403, detail="Account disabled")
    request.session["client_id"] = client.id
    request.session.pop("member_id", None)
    log_login(db, client.id, body.email, "client", "password", request, "success")
    return {"message": "Logged in", "is_onboarded": client.is_onboarded, "company_name": client.company_name}

@app.post("/api/client/logout")
def client_logout(request: Request):
    request.session.pop("client_id", None)
    return {"message": "Logged out"}

@app.get("/api/client/me")
def client_me(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    return {
        "id": client.id,
        "email": client.email,
        "company_name": client.company_name,
        "contact_name": client.contact_name,
        "phone_number": client.phone_number,
        "logo_url": client.logo_url,
        "address": client.address,
        "website": client.website,
        "abn": client.abn,
        "industry": client.industry,
        "is_onboarded": client.is_onboarded,
        "created_at": client.created_at,
        # An operator viewing a tenant keeps their superadmin session, so the
        # app can say whose account is on screen. Without this the only clue
        # was the data itself, which is exactly the wrong moment to guess.
        "impersonated_by_operator": bool(request.session.get("superadmin_id")),
    }

@app.post("/api/superadmin/stop-impersonating")
def superadmin_stop_impersonating(request: Request, db: Session = Depends(get_db)):
    """Hand the operator back their own session.

    Impersonation offered to 'return to the admin panel afterwards' but there
    was no way to do it: the tenant stayed in the session until sign-out,
    which dropped the superadmin session too. Only the tenant keys are
    cleared here, so the operator lands back on the panel still signed in.
    """
    require_superadmin(request)
    for key in ("client_id", "member_id"):
        request.session.pop(key, None)
    return {"message": "Back to the admin panel"}

@app.post("/api/client/onboard")
def client_onboard(body: ClientOnboard, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    client.company_name = body.company_name or client.company_name
    client.contact_name = body.contact_name or client.contact_name
    client.phone_number = body.phone_number or client.phone_number
    client.address = body.address or client.address
    client.website = body.website or client.website
    client.abn = body.abn or client.abn
    client.industry = body.industry or client.industry
    if body.logo_url:
        client.logo_url = body.logo_url
    client.is_onboarded = True
    db.commit()
    return {"message": "Onboarding complete"}

@app.post("/api/client/logo")
def upload_logo(request: Request, db: Session = Depends(get_db)):
    import json
    client = get_client_user(request, db)
    return {"logo_url": client.logo_url or ""}

@app.get("/api/client/logo")
def get_logo(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    return {"logo_url": client.logo_url or ""}

class LogoUpdate(BaseModel):
    logo_url: str = ""

@app.put("/api/client/logo")
def save_logo(body: LogoUpdate, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    client.logo_url = body.logo_url
    db.commit()
    return {"message": "Logo saved"}

# --- Super Admin ---

def ensure_super_admin():
    with SessionLocal() as db:
        env_emails = [e.strip().lower() for e in os.getenv("SUPERADMIN_EMAILS", "hello@keyroutes.co").split(",") if e.strip()]
        existing_all = db.query(models.DBSuperAdmin).all()
        existing_emails = {e.email.strip().lower() for e in existing_all if e.email}
        for em in env_emails:
            if em not in existing_emails:
                db.add(models.DBSuperAdmin(username="superadmin", password_hash="", email=em))
                existing_emails.add(em)
        pwd = os.getenv("SUPERADMIN_PASSWORD", "")
        if pwd:
            for sa in db.query(models.DBSuperAdmin).all():
                sa.password_hash = hash_password(pwd)
        db.commit()
        logger.info("Super admin setup complete (%d admins)", len(env_emails))

@app.post("/api/superadmin/login")
def superadmin_login(request: Request, body: dict = None, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"sa_login:{ip}", max_requests=5, window=60):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    body = body or {}
    identifier = (body.get("identifier") or body.get("username") or "").strip().lower()
    password = body.get("password", "")
    env_pwd = os.getenv("SUPERADMIN_PASSWORD", "")
    sa = None
    if identifier:
        sa = db.query(models.DBSuperAdmin).filter(
            (models.DBSuperAdmin.email == identifier) | (models.DBSuperAdmin.username == identifier)
        ).first()
    if sa:
        ok = False
        if sa.password_hash:
            ok = verify_password(password, sa.password_hash)
        elif env_pwd:
            ok = verify_password(password, hash_password(env_pwd))
        if ok:
            request.session['superadmin_id'] = sa.id
            log_login(db, None, identifier or sa.email, "superadmin", "password", request, "success")
            return {"ok": True, "username": sa.username, "email": sa.email}
    log_login(db, None, identifier or "superadmin", "superadmin", "password", request, "failed")
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/superadmin/change-password")
def superadmin_change_password(request: Request, body: dict = None, db: Session = Depends(get_db)):
    sa_id = require_superadmin(request)
    body = body or {}
    new_pwd = body.get("new_password", "")
    if len(new_pwd) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    admin = db.query(models.DBSuperAdmin).filter(models.DBSuperAdmin.id == sa_id).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Not found")
    admin.password_hash = hash_password(new_pwd)
    db.commit()
    return {"message": "Password updated"}

@app.post("/api/superadmin/logout")
def superadmin_logout(request: Request):
    request.session.pop("superadmin_id", None)
    return {"message": "Logged out"}

@app.get("/api/superadmin/me")
def superadmin_me(request: Request, db: Session = Depends(get_db)):
    sa_id = require_superadmin(request)
    admin = db.query(models.DBSuperAdmin).filter(models.DBSuperAdmin.id == sa_id).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Not found")
    return {"username": admin.username, "email": admin.email}

from sqlalchemy import func

@app.get("/api/superadmin/platform-stats")
def superadmin_platform_stats(request: Request, db: Session = Depends(get_db)):
    """Platform-wide numbers across every module, not just invoicing.

    The original insights endpoint only counted invoices, so HR and
    recruitment usage was invisible to the operator.
    """
    require_superadmin(request)

    def count(model):
        return db.query(model).count()

    paid_total = db.query(sqlfunc.coalesce(sqlfunc.sum(models.DBInvoice.paid), 0)).scalar() or 0
    outstanding = db.query(sqlfunc.coalesce(sqlfunc.sum(models.DBInvoice.due), 0)).filter(
        models.DBInvoice.status.notin_(["Draft", "Paid", "Void"])
    ).scalar() or 0
    payroll_total = db.query(sqlfunc.coalesce(sqlfunc.sum(models.DBPayslip.net_pay), 0)).filter(
        models.DBPayslip.status == "Paid"
    ).scalar() or 0

    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    # Super admin and employee logins carry a NULL client_id; counting them
    # would inflate the tenant activity figure.
    active_30d = db.query(models.DBClientLoginLog.client_id).filter(
        models.DBClientLoginLog.status == "success",
        models.DBClientLoginLog.user_type == "client",
        models.DBClientLoginLog.client_id.isnot(None),
        models.DBClientLoginLog.created_at >= (now - timedelta(days=30)).strftime("%Y-%m-%d"),
    ).distinct().count()

    return {
        "tenants": {
            "total": count(models.DBClient),
            "active": db.query(models.DBClient).filter(models.DBClient.is_active == True).count(),
            "onboarded": db.query(models.DBClient).filter(models.DBClient.is_onboarded == True).count(),
            "active_last_30_days": active_30d,
        },
        "invoicing": {
            "invoices": count(models.DBInvoice),
            "bills": count(models.DBBill),
            "collected": money(paid_total),
            "outstanding": money(outstanding),
            "invoices_this_month": db.query(models.DBInvoice).filter(
                models.DBInvoice.issue_date.like(month_prefix + "%")
            ).count(),
        },
        "hr": {
            "employees": count(models.DBEmployee),
            "departments": count(models.DBDepartment),
            "payslips": count(models.DBPayslip),
            "payroll_paid": money(payroll_total),
            "leave_requests": count(models.DBLeaveRequest),
            "attendance_records": count(models.DBAttendance),
        },
        "recruitment": {
            "jobs": count(models.DBJobRequisition),
            "open_jobs": db.query(models.DBJobRequisition).filter(
                models.DBJobRequisition.status == "open"
            ).count(),
            "applications": count(models.DBFormSubmission),
            "interviews": count(models.DBInterview),
            "offers": count(models.DBOffer),
            "hires": db.query(models.DBFormSubmission).filter(
                models.DBFormSubmission.hired_employee_id.isnot(None)
            ).count(),
        },
    }


@app.get("/api/superadmin/clients/{client_id}/overview")
def superadmin_client_overview(client_id: int, request: Request, db: Session = Depends(get_db)):
    """Everything the operator needs to answer 'how is this tenant doing?'
    without impersonating them."""
    require_superadmin(request)
    client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    def tenant_count(model):
        return db.query(model).filter(model.client_id == client_id).count()

    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client_id).all()
    employees = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client_id).all()
    today = datetime.now().date()
    overdue = [i for i in invoices if invoice_overdue_days(i, today) > 0]

    last_activity = ""
    latest_login = db.query(models.DBClientLoginLog).filter(
        models.DBClientLoginLog.client_id == client_id,
        models.DBClientLoginLog.status == "success",
    ).order_by(models.DBClientLoginLog.id.desc()).first()
    if latest_login:
        last_activity = latest_login.created_at

    return {
        "id": client.id,
        "company_name": client.company_name or "",
        "email": client.email,
        "is_active": client.is_active,
        "is_onboarded": client.is_onboarded,
        "currency": client.currency or "GBP",
        "created_at": client.created_at,
        "last_login": client.last_login or "",
        "login_count": client.login_count or 0,
        "last_activity": last_activity,
        "invoicing": {
            "invoices": len(invoices),
            "collected": money(sum(i.paid or 0 for i in invoices)),
            "outstanding": money(sum(i.due or 0 for i in invoices if i.status not in ("Draft", "Paid", "Void"))),
            "overdue_count": len(overdue),
            "bills": tenant_count(models.DBBill),
            "contacts": tenant_count(models.DBContact),
        },
        "hr": {
            "employees": len(employees),
            "active_employees": sum(1 for e in employees if e.status == "active"),
            "onboarding": sum(1 for e in employees if e.status == "onboarding"),
            "departments": tenant_count(models.DBDepartment),
            "payslips": tenant_count(models.DBPayslip),
            "pending_leave": db.query(models.DBLeaveRequest).filter(
                models.DBLeaveRequest.client_id == client_id,
                models.DBLeaveRequest.status == "pending",
            ).count(),
        },
        "recruitment": {
            "jobs": tenant_count(models.DBJobRequisition),
            "open_jobs": db.query(models.DBJobRequisition).filter(
                models.DBJobRequisition.client_id == client_id,
                models.DBJobRequisition.status == "open",
            ).count(),
            "applications": tenant_count(models.DBFormSubmission),
            "interviews": tenant_count(models.DBInterview),
        },
        "portals": {
            "invoicing": "/app.html",
            "hr": "/hr.html",
            "employee": "/employee-login.html",
            "job_board": f"/jobs.html?c={client.id}",
        },
    }


@app.get("/api/superadmin/clients")
def superadmin_clients(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    results = (
        db.query(
            models.DBClient,
            func.count(models.DBInvoice.id).label('invoice_count'),
            func.count(func.nullif(models.DBInvoice.status, 'Paid')).label('unpaid_count'),
            func.coalesce(func.sum(func.nullif(models.DBInvoice.due, 0)), 0).label('outstanding')
        )
        .outerjoin(models.DBInvoice, models.DBInvoice.client_id == models.DBClient.id)
        .group_by(models.DBClient.id)
        .all()
    )
    return [{
        "id": c.id,
        "email": c.email,
        "company_name": c.company_name,
        "contact_name": c.contact_name,
        "phone_number": c.phone_number,
        "is_active": c.is_active,
        "is_onboarded": c.is_onboarded,
        "last_login": c.last_login or "",
        "login_count": c.login_count or 0,
        "created_at": c.created_at,
        "invoice_count": invoice_count,
        "paid_count": invoice_count - unpaid_count,
        "outstanding": round(float(outstanding), 2),
    } for c, invoice_count, unpaid_count, outstanding in results]

@app.get("/api/superadmin/insights")
def superadmin_insights(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    total_clients = db.query(models.DBClient).count()
    active_clients = db.query(models.DBClient).filter(models.DBClient.is_active == True).count()
    onboarded = db.query(models.DBClient).filter(models.DBClient.is_onboarded == True).count()
    total_invoices = db.query(models.DBInvoice).count()
    total_revenue = db.query(func.coalesce(func.sum(models.DBInvoice.due), 0)).filter(models.DBInvoice.status == "Paid").scalar()
    total_outstanding = db.query(func.coalesce(func.sum(models.DBInvoice.due), 0)).filter(models.DBInvoice.status != "Paid").scalar()
    return {
        "total_clients": total_clients,
        "active_clients": active_clients,
        "onboarded_clients": onboarded,
        "total_invoices": total_invoices,
        "total_revenue": round(float(total_revenue), 2),
        "total_outstanding": round(float(total_outstanding), 2),
    }

@app.get("/api/superadmin/login-logs")
def superadmin_login_logs(request: Request, limit: int = 100, db: Session = Depends(get_db)):
    require_superadmin(request)
    # Bounded because limit arrives from the query string: this table grows
    # with every sign-in attempt on the platform, so an unbounded value asks
    # for all of it at once.
    limit = max(1, min(int(limit or 100), 1000))
    logs = db.query(models.DBClientLoginLog).order_by(models.DBClientLoginLog.created_at.desc()).limit(limit).all()
    return [{
        "id": l.id, "client_id": l.client_id, "email": l.email,
        "user_type": l.user_type, "login_type": l.login_type,
        "ip_address": l.ip_address, "device_info": l.device_info,
        "status": l.status, "created_at": l.created_at,
    } for l in logs]

@app.get("/api/superadmin/login-stats")
def superadmin_login_stats(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    from datetime import timedelta
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    total_logs = db.query(models.DBClientLoginLog).count()
    today_logs = db.query(models.DBClientLoginLog).filter(models.DBClientLoginLog.created_at.like(today + "%")).count()
    week_logs = db.query(models.DBClientLoginLog).filter(models.DBClientLoginLog.created_at >= week_ago).count()
    month_logs = db.query(models.DBClientLoginLog).filter(models.DBClientLoginLog.created_at >= month_ago).count()
    failed_logs = db.query(models.DBClientLoginLog).filter(models.DBClientLoginLog.status == "failed").count()
    google_logins = db.query(models.DBClientLoginLog).filter(models.DBClientLoginLog.login_type == "google").count()
    password_logins = db.query(models.DBClientLoginLog).filter(models.DBClientLoginLog.login_type == "password").count()
    clients_with_logins = db.query(models.DBClient).filter(models.DBClient.login_count > 0).count()
    never_logged_in = db.query(models.DBClient).filter(models.DBClient.login_count == 0).count()
    return {
        "total_logins": total_logs,
        "today_logins": today_logs,
        "week_logins": week_logs,
        "month_logins": month_logs,
        "failed_logins": failed_logs,
        "google_logins": google_logins,
        "password_logins": password_logins,
        "clients_with_logins": clients_with_logins,
        "clients_never_logged_in": never_logged_in,
    }

@app.put("/api/superadmin/clients/{client_id}/toggle")
def superadmin_toggle_client(client_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.is_active = not client.is_active
    log_audit(db, client.id, "client_" + ("enabled" if client.is_active else "disabled"), "client", client.id, client.company_name or client.email, "", request, user_type="superadmin", user_name="superadmin")
    db.commit()
    return {"message": "Client " + ("enabled" if client.is_active else "disabled"), "is_active": client.is_active}

@app.delete("/api/superadmin/clients/{client_id}")
def superadmin_delete_client(client_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    invoice_ids = db.query(models.DBInvoice.id).filter(models.DBInvoice.client_id == client_id)
    db.query(models.DBLineItem).filter(models.DBLineItem.invoice_id.in_(invoice_ids)).delete(synchronize_session=False)
    db.query(models.DBPayment).filter(models.DBPayment.invoice_id.in_(invoice_ids)).delete(synchronize_session=False)
    db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client_id).delete()
    db.query(models.DBContact).filter(models.DBContact.client_id == client_id).delete()
    db.query(models.DBSettings).filter(models.DBSettings.client_id == client_id).delete()
    db.delete(client)
    log_audit(db, client_id, "client_deleted", "client", client_id, "", "Client and all data deleted", request, user_type="superadmin", user_name="superadmin")
    db.commit()
    return {"message": "Client deleted"}

@app.post("/api/superadmin/impersonate/{client_id}")
def superadmin_impersonate(client_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client.is_active:
        raise HTTPException(status_code=400, detail="Client account is disabled")
    request.session['client_id'] = client.id
    log_audit(db, client.id, "impersonate", "client", client.id, client.company_name or client.email, "Super admin logged in as client", request, user_type="superadmin", user_name="superadmin")
    db.commit()
    return {"message": "Now acting as " + (client.company_name or client.email), "client_id": client.id}

@app.get("/api/superadmin/trends")
def superadmin_trends(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    from datetime import timedelta
    from collections import defaultdict
    now = datetime.now()
    months = [(now - timedelta(days=30 * i)).strftime("%Y-%m") for i in range(5, -1, -1)]
    revenue_by_month = defaultdict(float)
    logins_by_month = defaultdict(int)
    for inv in db.query(models.DBInvoice).filter(models.DBInvoice.status == "Paid").all():
        m = inv.issue_date[:7] if inv.issue_date and len(inv.issue_date) >= 7 else None
        if m in months:
            revenue_by_month[m] += (inv.paid or 0)
    for l in db.query(models.DBClientLoginLog).filter(models.DBClientLoginLog.status == "success").all():
        m = l.created_at[:7] if l.created_at and len(l.created_at) >= 7 else None
        if m in months:
            logins_by_month[m] += 1
    return {
        "months": months,
        "revenue": [round(revenue_by_month.get(m, 0), 2) for m in months],
        "active_users": [logins_by_month.get(m, 0) for m in months],
        "total_revenue": round(sum(inv.paid or 0 for inv in db.query(models.DBInvoice).filter(models.DBInvoice.status == "Paid").all()), 2),
    }

@app.get("/api/superadmin/clients/{client_id}")
def superadmin_get_client(client_id: int, request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client_id).all()
    return {
        "id": client.id,
        "email": client.email,
        "company_name": client.company_name,
        "contact_name": client.contact_name,
        "phone_number": client.phone_number,
        "address": client.address,
        "website": client.website,
        "abn": client.abn,
        "industry": client.industry,
        "is_active": client.is_active,
        "is_onboarded": client.is_onboarded,
        "created_at": client.created_at,
        "invoices": [{"number": i.number, "status": i.status, "due": i.due, "date": i.issue_date} for i in invoices],
    }

# --- Gmail API Helpers ---

def get_gmail_credentials(access_token: str = None, refresh_token: str = None):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.error("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured")
        return None
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    try:
        if creds.expired or not creds.valid:
            creds.refresh(GoogleRequest())
    except Exception as e:
        logger.error(f"Failed to refresh Gmail credentials: {e}")
        return None
    return creds

def get_stored_refresh_token(db: Session, client_id: int = None):
    q = db.query(models.DBSettings).filter(models.DBSettings.key == "GOOGLE_REFRESH_TOKEN")
    if client_id:
        # Try client-specific token first
        setting = q.filter(models.DBSettings.client_id == client_id).first()
        if setting:
            return setting.value
    # Fallback to global token (no client_id) for backward compat
    setting = q.filter(models.DBSettings.client_id == None).first()
    if not setting:
        setting = q.first()
    return setting.value if setting else None

def validate_email_address(email: str) -> bool:
    import re as _re
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(_re.match(pattern, email.strip()))
def prepare_email_message(to_email, subject, body_text, html_body, from_email, logo_data="", pdf_bytes=None, pdf_filename="invoice.pdf"):
    """Build a properly structured MIME email with CID-embedded logo and PDF attachment."""
    import re as _re
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders as _encoders

    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Reply-To'] = from_email
    msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')
    msg['List-Unsubscribe'] = '<mailto:hello@keyroutes.co?subject=unsubscribe>'
    msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'

    alt_part = MIMEMultipart('alternative')
    alt_part.attach(MIMEText(body_text, 'plain', 'utf-8'))

    if html_body and logo_data:
        logo_cid = 'logo_' + uuid.uuid4().hex[:12]
        data_url_match = _re.match(r'^data:(image/\w+);base64,(.+)$', logo_data, _re.DOTALL)
        if data_url_match:
            img_mime = data_url_match.group(1)
            img_b64 = data_url_match.group(2)
            img_sub = img_mime.split('/')[1] if '/' in img_mime else 'png'
            if img_sub == 'jpeg':
                img_sub = 'jpg'
            img_bytes = base64.b64decode(img_b64)
            logo_part = MIMEBase('image', img_sub)
            logo_part.set_payload(img_bytes)
            _encoders.encode_base64(logo_part)
            logo_part.add_header('Content-ID', f'<{logo_cid}>')
            logo_part.add_header('Content-Disposition', 'inline', filename='logo.' + img_sub)
            msg.attach(logo_part)
            html_body = html_body.replace(logo_data, f'cid:{logo_cid}')
        elif logo_data.startswith('http'):
            pass
        else:
            pass

    alt_part.attach(MIMEText(html_body, 'html', 'utf-8'))
    msg.attach(alt_part)

    if pdf_bytes:
        pdf_part = MIMEBase('application', 'pdf')
        pdf_part.set_payload(pdf_bytes)
        _encoders.encode_base64(pdf_part)
        pdf_part.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
        msg.attach(pdf_part)

    return msg.as_string()


def send_email_background(to_email: str, subject: str, body: str, from_email: str, html_body: str = None, pdf_b64: str = None, pdf_filename: str = "invoice.pdf", logo_data: str = "", client_id: int = None):
    pdf_bytes = None
    if pdf_b64:
        try:
            pdf_bytes = base64.b64decode(pdf_b64)
        except Exception as e:
            logger.error(f"Failed to decode PDF: {e}")

    raw_msg = prepare_email_message(to_email, subject, body, html_body or "", from_email, logo_data or "", pdf_bytes, pdf_filename)

    with SessionLocal() as db:
        refresh_token = get_stored_refresh_token(db, client_id=client_id)

    if not refresh_token:
        return False, "Gmail refresh token not configured"

    try:
        creds = get_gmail_credentials(access_token=None, refresh_token=refresh_token)
        service = build('gmail', 'v1', credentials=creds)
        encoded_message = base64.urlsafe_b64encode(raw_msg.encode('utf-8')).decode()
        send_result = service.users().messages().send(userId="me", body={'raw': encoded_message}).execute()
        logger.info(f"Email sent via Gmail API to {to_email} (ID: {send_result['id']})")
        return True, "Email sent via Gmail API"
    except Exception as e:
        logger.error(f"Gmail API failed: {e}")
        return False, f"Gmail API error: {str(e)}"


# --- API Endpoints ---

@app.get("/api/dashboard-summary")
def get_dashboard_summary(request: Request, db: Session = Depends(get_db)):
    from collections import defaultdict
    from datetime import datetime, timedelta

    client = get_client_user(request, db)
    all_invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client.id).all()

    today = datetime.now().date()
    invoices_owed = sum(inv.due or 0 for inv in all_invoices if inv.status in OPEN_INVOICE_STATUSES)
    total_revenue = sum(inv.paid or 0 for inv in all_invoices if inv.status != "Draft")
    total_invoiced = sum((inv.paid or 0) + (inv.due or 0) for inv in all_invoices if inv.status != "Draft")
    paid_count = sum(1 for inv in all_invoices if inv.status == "Paid")
    pending_count = sum(1 for inv in all_invoices if inv.status in OPEN_INVOICE_STATUSES)
    draft_count = sum(1 for inv in all_invoices if inv.status == "Draft")
    overdue = [inv for inv in all_invoices if invoice_overdue_days(inv, today) > 0]
    overdue_amount = sum(inv.due or 0 for inv in overdue)

    months = []
    now = datetime.now()
    for i in range(5, -1, -1):
        d = now - timedelta(days=30 * i)
        months.append(d.strftime("%b %Y"))

    # Charting several currencies on one axis says nothing, so the chart is
    # the base currency and the label says so.
    base_currency = (client.currency or "GBP").upper()

    def in_base(inv):
        return (inv.currency or base_currency).upper() == base_currency

    money_in = [0.0] * 6
    money_out = [0.0] * 6

    for inv in all_invoices:
        if not inv.issue_date or not in_base(inv):
            continue
        try:
            inv_date = datetime.strptime(inv.issue_date, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        for i in range(6):
            d = now - timedelta(days=30 * (5 - i))
            month_start = d.replace(day=1)
            next_month = (month_start + timedelta(days=32)).replace(day=1)
            if month_start <= inv_date < next_month:
                money_in[i] += inv.paid or 0
                if inv.status in OPEN_INVOICE_STATUSES:
                    money_out[i] += inv.due or 0
                break

    short_months = [datetime.strptime(m, "%b %Y").strftime("%b") for m in months]

    def split(rows, amount):
        return totals_by_currency(
            [{"currency": i.currency, "total": amount(i)} for i in rows],
            fallback=base_currency)

    open_invoices = [i for i in all_invoices if i.status in OPEN_INVOICE_STATUSES]
    issued = [i for i in all_invoices if i.status != "Draft"]

    return {
        "summary": {
            "total_invoiced": round(total_invoiced, 2),
            "total_revenue": round(total_revenue, 2),
            "invoices_owed": round(invoices_owed, 2),
            "paid_count": paid_count,
            "pending_count": pending_count,
            "draft_count": draft_count,
            "overdue_count": len(overdue),
            "overdue_amount": round(overdue_amount, 2),
            "total_count": len(all_invoices),
            # The figures the cards actually show. A single total across
            # currencies would be a number nobody can act on.
            "by_currency": {
                "total_invoiced": split(issued, lambda i: (i.paid or 0) + (i.due or 0)),
                "total_revenue": split(issued, lambda i: i.paid or 0),
                "invoices_owed": split(open_invoices, lambda i: i.due or 0),
                "overdue_amount": split(overdue, lambda i: i.due or 0),
            },
        },
        "base_currency": base_currency,
        "currencies_used": sorted({(i.currency or base_currency).upper()
                                   for i in all_invoices}),
        "cash_flow": {
            "money_in": [round(x, 2) for x in money_in],
            "money_out": [round(x, 2) for x in money_out],
            "months": short_months,
            "currency": base_currency,
        }
    }

@app.get("/api/invoices")
def get_invoices(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client.id).order_by(models.DBInvoice.id.desc()).all()
    today = datetime.now().date()
    result = []
    for inv in invoices:
        overdue_days = invoice_overdue_days(inv, today)
        result.append({
            "number": inv.number,
            "ref": inv.ref,
            "to": inv.to_contact,
            "email": inv.email,
            "phone_number": inv.phone_number,
            "date": inv.issue_date,
            "due_date": inv.due_date,
            "paid": inv.paid,
            "due": inv.due,
            "total": money((inv.paid or 0) + (inv.due or 0)),
            "status": inv.status,
            "sent": inv.sent,
            "tax_type": inv.tax_type,
            "currency": inv.currency or (client.currency if client else ""),
            "open_count": inv.open_count or 0,
            "last_opened": inv.last_opened or "",
            "is_overdue": overdue_days > 0,
            "days_overdue": overdue_days,
        })
    return result

@app.get("/api/invoices/{number}")
def get_invoice(number: str, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == client.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    settings_rows = db.query(models.DBSettings).filter(models.DBSettings.client_id == inv.client_id).all() if inv.client_id else []
    settings_map = {s.key: s.value for s in settings_rows}
    company = {
        "name": settings_map.get("company_name", "") or (client.company_name if client else ""),
        "email": settings_map.get("email", "") or (client.email if client else ""),
        "phone_number": settings_map.get("phone_number", "") or (client.phone_number if client else ""),
        "address": settings_map.get("company_address", "") or (client.address if client else ""),
        "website": settings_map.get("company_website", "") or (client.website if client else ""),
        "abn": settings_map.get("company_abn", "") or (client.abn if client else ""),
        "logo_url": client.logo_url if client else "",
    }
    subtotal, tax_total, grand_total = compute_invoice_totals(inv.line_items, inv.tax_type)
    overdue_days = invoice_overdue_days(inv)
    payments = db.query(models.DBPayment).filter(
        models.DBPayment.invoice_id == inv.id
    ).order_by(models.DBPayment.id.asc()).all()
    return {
        "id": inv.id,
        "number": inv.number,
        "ref": inv.ref,
        "to": inv.to_contact,
        "email": inv.email,
        "phone_number": inv.phone_number,
        "date": inv.issue_date,
        "due_date": inv.due_date,
        "paid": inv.paid,
        "due": inv.due,
        "subtotal": subtotal,
        "tax_total": tax_total,
        "total": grand_total,
        "is_overdue": overdue_days > 0,
        "days_overdue": overdue_days,
        "payments": [{
            "id": p.id, "amount": p.amount, "paid_on": p.paid_on,
            "method": p.method, "reference": p.reference, "note": p.note,
        } for p in payments],
        "status": inv.status,
        "sent": inv.sent,
        "tax_type": inv.tax_type,
        "currency": inv.currency or (client.currency if client else ""),
        "bank_details": inv.bank_details or "",
        "tracking_id": inv.tracking_id,
        "open_count": inv.open_count or 0,
        "last_opened": inv.last_opened or "",
        "company": company,
        "line_items": [{
            "name": li.name or "",
            "description": li.description,
            "qty": li.qty,
            "price": li.price,
            "disc": li.disc,
            "account": li.account,
            "tax_rate": li.tax_rate,
            "tax_percent": round(parse_tax_rate(li.tax_rate) * 100, 4),
            "amount": money(line_net_amount(li.qty, li.price, li.disc)),
            "tax_amount": money(
                line_net_amount(li.qty, li.price, li.disc) * parse_tax_rate(li.tax_rate)
                if inv.tax_type == "exclusive" else
                (line_net_amount(li.qty, li.price, li.disc)
                 - line_net_amount(li.qty, li.price, li.disc) / (1 + parse_tax_rate(li.tax_rate))
                 if inv.tax_type == "inclusive" and parse_tax_rate(li.tax_rate) else 0)
            ),
        } for li in inv.line_items]
    }

@app.get("/api/next-invoice-number")
def get_next_invoice_number(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    return {"next_number": next_sequence_number(
        db, models.DBInvoice, client.id, invoice_prefix_for(db, client.id)),
        "payment_terms_days": payment_terms_for(db, client.id)}

def validate_line_items(line_items):
    """Reject payloads that would silently produce a nonsense invoice."""
    if not line_items:
        raise HTTPException(status_code=400, detail="An invoice needs at least one line item")
    if len(line_items) > 200:
        raise HTTPException(status_code=400, detail="An invoice cannot have more than 200 line items")
    for idx, item in enumerate(line_items, start=1):
        if (item.qty or 0) < 0:
            raise HTTPException(status_code=400, detail=f"Line {idx}: quantity cannot be negative")
        if (item.price or 0) < 0:
            raise HTTPException(status_code=400, detail=f"Line {idx}: price cannot be negative")
        disc = item.disc or 0
        if disc < 0 or disc > 100:
            raise HTTPException(status_code=400, detail=f"Line {idx}: discount must be between 0 and 100")


def validate_invoice_dates(issue_date, due_date):
    issue = _parse_date(issue_date)
    due = _parse_date(due_date)
    if issue_date and not issue:
        raise HTTPException(status_code=400, detail="Issue date must be in YYYY-MM-DD format")
    if due_date and not due:
        raise HTTPException(status_code=400, detail="Due date must be in YYYY-MM-DD format")
    if issue and due and due < issue:
        raise HTTPException(status_code=400, detail="Due date cannot be before the issue date")


def tenant_setting(db, client_id, key, default=""):
    row = db.query(models.DBSettings).filter(
        models.DBSettings.client_id == client_id, models.DBSettings.key == key
    ).first()
    return (row.value if row and row.value not in (None, "") else default)


def invoice_prefix_for(db, client_id):
    """The tenant's own numbering prefix.

    Stored as a setting for a long time and read by nothing, so every tenant
    was stuck on INV- whatever they put in the box.
    """
    raw = str(tenant_setting(db, client_id, "invoice_prefix", "INV-")).strip()
    # A prefix has to be something numbers can follow, and the sequence reader
    # splits on "-", so keep it simple rather than accept anything at all.
    cleaned = "".join(c for c in raw if c.isalnum() or c in "-_/")[:12]
    return cleaned or "INV-"


def payment_terms_for(db, client_id):
    try:
        days = int(float(tenant_setting(db, client_id, "default_payment_terms", 14)))
    except (TypeError, ValueError):
        return 14
    return days if 0 <= days <= 365 else 14


def next_sequence_number(db, model, client_id, prefix, field="number"):
    """Next number in a per-tenant sequence, based on the highest number ever
    issued. Counting rows breaks as soon as one is deleted.

    `field` names the column holding the sequence (invoices and payslips call
    it `number`; job requisitions call it `reference`)."""
    column = getattr(model, field)
    rows = db.query(column).filter(model.client_id == client_id).all()
    max_num = 0
    for row in rows:
        num_str = getattr(row, field) or ""
        if not num_str.startswith(prefix):
            continue
        tail = num_str[len(prefix):].split("-")[0].strip()
        try:
            max_num = max(max_num, int(tail))
        except (TypeError, ValueError):
            continue
    return f"{prefix}{max_num + 1:04d}"


@app.post("/api/invoices")
def create_invoice(invoice: InvoiceCreate, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)

    validate_line_items(invoice.line_items)
    validate_invoice_dates(invoice.issue_date, invoice.due_date)

    subtotal, tax, total = compute_invoice_totals(invoice.line_items, invoice.tax_type)

    # Auto-save contact (scoped to client)
    if invoice.contact and invoice.contact.strip():
        existing = db.query(models.DBContact).filter(models.DBContact.name == invoice.contact, models.DBContact.client_id == client.id).first()
        if existing:
            if invoice.email and not existing.email:
                existing.email = invoice.email
            if invoice.phone_number and not existing.phone_number:
                existing.phone_number = invoice.phone_number
        else:
            db.add(models.DBContact(name=invoice.contact, email=invoice.email or "", phone_number=invoice.phone_number or "", client_id=client.id))

    if invoice.invoice_number and invoice.invoice_number.strip() != "":
        number = invoice.invoice_number.strip()
    else:
        number = next_sequence_number(db, models.DBInvoice, client.id, invoice_prefix_for(db, client.id))

    clash = db.query(models.DBInvoice).filter(
        models.DBInvoice.client_id == client.id, models.DBInvoice.number == number
    ).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"Invoice number {number} already exists")

    db_invoice = models.DBInvoice(
        client_id=client.id,
        number=number,
        ref=invoice.reference,
        to_contact=invoice.contact,
        email=invoice.email,
        phone_number=invoice.phone_number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        paid=0.00,
        due=round(total, 2),
        status=invoice.status or "Draft",
        sent="",
        tax_type=invoice.tax_type,
        currency=(invoice.currency or "").upper() or (client.currency or ""),
        bank_details=invoice.bank_details or ""
    )
    db.add(db_invoice)
    db.flush()

    for item in invoice.line_items:
        db_line_item = models.DBLineItem(
            invoice_id=db_invoice.id,
            name=item.name or "",
            description=item.description,
            qty=item.qty,
            price=item.price,
            disc=item.disc or 0.0,
            account=item.account,
            tax_rate=item.tax_rate
        )
        db.add(db_line_item)

    db.commit()
    db.refresh(db_invoice)
    log_audit(db, client.id, "invoice_created", "invoice", db_invoice.id, number, f"Total: {total:.2f}", request)
    db.commit()

    return get_invoice(number, request, db)

@app.post("/api/invoices/{number}/send")
def send_invoice_email(number: str, background_tasks: BackgroundTasks, request: Request, payload: Optional[SendInvoiceEmail] = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if payload is None:
        payload = SendInvoiceEmail()
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == client.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not inv.email:
        raise HTTPException(status_code=400, detail="Invoice has no email address associated with it")
    if not validate_email_address(inv.email):
        raise HTTPException(status_code=400, detail=f"Invalid email address: {inv.email}")

    user = request.session.get('user', {})
    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
    if not from_email:
        raise HTTPException(status_code=400, detail="No sender email configured.")

    settings_rows = db.query(models.DBSettings).filter(models.DBSettings.client_id == inv.client_id).all()
    settings_map = {s.key: s.value for s in settings_rows}
    inv_client = db.query(models.DBClient).filter(models.DBClient.id == inv.client_id).first() if inv.client_id else None
    company_name = settings_map.get("company_name", "") or (inv_client.company_name if inv_client else "") or "Accounting Platform"
    company_email = settings_map.get("email", "") or (inv_client.email if inv_client else "")
    company_phone = settings_map.get("phone_number", "") or (inv_client.phone_number if inv_client else "")
    company_address = settings_map.get("company_address", "") or (inv_client.address if inv_client else "")
    company_abn = settings_map.get("company_abn", "") or (inv_client.abn if inv_client else "")
    company_website = settings_map.get("company_website", "") or (inv_client.website if inv_client else "")

    cur = (inv.currency or settings_map.get("currency") or (inv_client.currency if inv_client else "") or "GBP").upper()
    cur_symbol = currency_symbol(cur)

    sender_name = os.getenv("FROM_NAME", "aniprotech")
    from_header = f"{company_name} <{from_email}>"
    subject = f"Invoice {inv.number} from {company_name}"

    logo_html = ""
    logo_data = payload.logo_data or ""
    if not logo_data and inv_client and inv_client.logo_url:
        logo_data = inv_client.logo_url
    if logo_data:
        logo_html = f'<div style="margin-bottom:24px;"><img src="{esc(logo_data)}" style="max-height:48px;max-width:200px;"></div>'

    line_items_html = ""
    if inv.line_items:
        rows = ""
        for li in inv.line_items:
            amount = li.qty * li.price
            disc_val = li.disc or 0
            if disc_val > 0:
                amount *= (1 - disc_val / 100)
            disc_html = f'<span style="display:inline-block;background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;">{disc_val:g}% off</span>' if disc_val > 0 else ''
            rows += f'''
                <div style="padding:16px 20px;border-bottom:1px solid #f1f5f9;">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                    <div style="font-size:15px;font-weight:700;color:#1e293b;">{esc(li.name) or 'Item'}</div>
                    <div style="font-size:16px;font-weight:800;color:#0f172a;">{cur_symbol}{amount:.2f}</div>
                  </div>
                  {f'<div style="font-size:13px;color:#64748b;margin-bottom:8px;word-wrap:break-word;">{esc(li.description)}</div>' if li.description else ''}
                  <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;">
                    <span style="font-size:12px;color:#94a3b8;">Qty: <strong style="color:#475569;">{int(li.qty)}</strong></span>
                    <span style="font-size:12px;color:#94a3b8;">Price: <strong style="color:#475569;">{cur_symbol}{li.price:.2f}</strong></span>
                    {f'<span style="font-size:12px;color:#94a3b8;">Discount: {disc_html}</span>' if disc_val > 0 else ''}
                  </div>
                </div>'''

        line_items_html = f'''
            <div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:24px;">
              <div style="background-color:#f8fafc;padding:10px 20px;border-bottom:2px solid #e2e8f0;display:flex;justify-content:space-between;">
                <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Item</span>
                <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Amount</span>
              </div>
              {rows}
            </div>'''

    body = f"""Hello {esc(inv.to_contact)},

Please find the details of your invoice {inv.number} from {company_name or sender_name} below.

Invoice Number: {inv.number}
Issue Date: {inv.issue_date}
Due Date: {inv.due_date}

Line Items:
"""
    for li in inv.line_items:
        item_label = f"{li.name} - {li.description}" if li.name else li.description
        disc_text = f" (Disc: {li.disc}%)" if li.disc else ""
        body += f"  - {item_label} x{int(li.qty)} @ {cur_symbol}{li.price:.2f}{disc_text}\n"
    body += f"""
Total Amount Due: {cur_symbol}{inv.due:.2f}

Payment is due by {inv.due_date}. If you have any questions about this invoice, please reply to this email.

Thank you for your business!

Best regards,
{company_name}
{company_address or ''}
{company_email or ''}
{company_phone or ''}

Powered by Aniprotech"""

    html_body = f"""
    <!DOCTYPE html>
    <html>
      <body style="font-family: Arial, Helvetica, sans-serif; color: #1e293b; line-height: 1.6; margin: 0; padding: 0; background-color: #f1f5f9;">
        <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
          <div style="background: #ffffff; border-radius: 12px; overflow: hidden;">
            <!-- Header -->
            <div style="background-color: #0f172a; padding: 40px; text-align: center;">
              {logo_html}
              <h1 style="font-size: 32px; font-weight: 800; color: #ffffff; margin: 0 0 8px 0;">INVOICE</h1>
              <p style="font-size: 16px; color: #94a3b8; margin: 0; font-weight: 600;">{inv.number}</p>
              <div style="margin-top: 16px; display: inline-block; background-color: #0ea5e9; padding: 8px 20px; border-radius: 20px;">
                <span style="font-size: 14px; color: #ffffff; font-weight: 600;">Amount Due: {cur_symbol}{inv.due:.2f}</span>
              </div>
            </div>

            <!-- Company Details Bar -->
            {f'''
            <div style="background-color: #f8fafc; padding: 16px 40px; border-bottom: 1px solid #e2e8f0;">
              <div style="font-size: 13px; color: #475569;">
                <strong style="color: #1e293b;">{esc(company_name)}</strong>
                {f' &bull; {esc(company_address)}' if company_address else ''}
                {f' &bull; {esc(company_email)}' if company_email else ''}
                {f' &bull; {esc(company_phone)}' if company_phone else ''}
              </div>
            </div>
            ''' if company_name else ''}

            <!-- Body -->
            <div style="padding: 40px;">
              <p style="font-size: 16px; color: #1e293b; margin: 0 0 6px 0;">Hello <strong>{esc(inv.to_contact)}</strong>,</p>
              <p style="font-size: 14px; color: #64748b; margin: 0 0 32px 0;">Here's your invoice from <strong>{esc(company_name or sender_name)}</strong>. Please find the details below.</p>

              <!-- Invoice Details Cards -->
              <div style="margin-bottom: 32px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">
                  <tr>
                    <td style="background-color: #f1f5f9; border-radius: 10px; padding: 16px; text-align: center; width: 33%;">
                      <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; margin-bottom: 4px;">Issue Date</div>
                      <div style="font-size: 14px; font-weight: 600; color: #1e293b;">{inv.issue_date}</div>
                    </td>
                    <td style="width: 10px;"></td>
                    <td style="background-color: #f1f5f9; border-radius: 10px; padding: 16px; text-align: center; width: 33%;">
                      <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; margin-bottom: 4px;">Due Date</div>
                      <div style="font-size: 14px; font-weight: 600; color: #1e293b;">{inv.due_date}</div>
                    </td>
                    <td style="width: 10px;"></td>
                    <td style="background-color: #f1f5f9; border-radius: 10px; padding: 16px; text-align: center; width: 33%;">
                      <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b; margin-bottom: 4px;">Invoice #</div>
                      <div style="font-size: 14px; font-weight: 600; color: #1e293b;">{inv.number}</div>
                    </td>
                  </tr>
                </table>
              </div>

              <!-- Line Items -->
              {line_items_html}

              <!-- Total -->
              <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse; margin-top: 24px;">
                <tr>
                  <td style="background-color: #0f172a; border-radius: 12px; padding: 24px; text-align: right;">
                    <div style="font-size: 13px; color: #94a3b8; margin-bottom: 4px;">TOTAL AMOUNT</div>
                    <div style="font-size: 32px; font-weight: 800; color: #ffffff;">{cur_symbol}{inv.due:.2f}</div>
                  </td>
                </tr>
              </table>

              <!-- Payment Note -->
              <div style="margin-top: 32px; padding: 20px; background-color: #fefce8; border-radius: 10px; border-left: 4px solid #fcd34d;">
                <p style="font-size: 13px; color: #854d0e; margin: 0;"><strong>Payment Terms:</strong> Please pay by {inv.due_date}. For any questions, reply to this email.</p>
              </div>

              <!-- View and Pay Online -->
              <p style="margin-top: 20px;"><a href="{request.base_url}invoice.html?id={inv.tracking_id}" style="color: #0ea5e9; font-size: 14px; font-weight: 600;">View this invoice online &rarr;</a></p>
            </div>

            <!-- Footer -->
            <div style="padding: 24px 40px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center;">
              <p style="font-size: 13px; color: #94a3b8; margin: 0 0 4px 0;">Thank you for your business!</p>
              <p style="font-size: 12px; color: #64748b; margin: 0;">{company_name}</p>
              {f'<p style="font-size:11px;color:#94a3b8;margin:4px 0 0 0;">{esc(company_address)}</p>' if company_address else ''}
              <p style="font-size: 11px; color: #94a3b8; margin: 12px 0 0 0;">Powered by Aniprotech</p>
            </div>
          </div>
        </div>
        <img src="{request.base_url}api/track/open/{inv.tracking_id}" width="1" height="1" style="display:none;" alt="">
      </body>
    </html>
    """

    pdf_b64 = payload.pdf_data if payload.pdf_data else None
    pdf_filename = f"{inv.number}.pdf" if pdf_b64 else "invoice.pdf"

    # Metered before the send is queued; charging afterwards would mean a
    # refused charge still delivered the email.
    require_credit(db, client.id, "invoice_send", 1, inv.number)

    background_tasks.add_task(send_email_background, inv.email, subject, body, from_header, html_body, pdf_b64, pdf_filename, logo_data, client_id=client.id)

    # Re-sending a receipt must not walk a settled invoice back to unpaid.
    if inv.status not in ("Paid", "Partially Paid", "Void"):
        inv.status = "Sent"
    inv.sent = datetime.now().strftime("%Y-%m-%d")
    log_audit(db, client.id, "invoice_sent", "invoice", inv.id, inv.number, f"Sent to {inv.email}", request)
    db.commit()

    return {"message": "Email sending initiated via Gmail API", "status": "Sent", "sent_date": inv.sent}

def send_whatsapp_background(phone_number: str, message: str):
    with SessionLocal() as db:
        setting_id = db.query(models.DBSettings).filter(models.DBSettings.key == "WHATSAPP_PHONE_NUMBER_ID").first()
        phone_number_id = setting_id.value if setting_id else os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        setting_token = db.query(models.DBSettings).filter(models.DBSettings.key == "WHATSAPP_ACCESS_TOKEN").first()
        access_token = setting_token.value if setting_token else os.getenv("WHATSAPP_ACCESS_TOKEN")

    if not phone_number_id or not access_token:
        logger.warning("WhatsApp credentials missing")
        return

    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": phone_number, "type": "text", "text": {"body": message}}

    try:
        response = httpx.post(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"WhatsApp message sent to {phone_number}")
    except Exception as e:
        logger.error(f"Failed to send WhatsApp: {str(e)}")

@app.post("/api/invoices/{number}/send-whatsapp")
def send_invoice_whatsapp(number: str, background_tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == client.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not inv.phone_number:
        raise HTTPException(status_code=400, detail="Invoice has no phone number")

    inv_client = db.query(models.DBClient).filter(models.DBClient.id == inv.client_id).first() if inv.client_id else None
    ws_cur = (inv.currency or (inv_client.currency if inv_client else "") or "GBP").upper()
    ws_sym = currency_symbol(ws_cur)
    message = f"Hello {inv.to_contact},\n\nPlease find the details of your invoice {inv.number} below:\n\nTotal Due: {ws_sym}{inv.due:.2f}\nDue Date: {inv.due_date}\n\nThank you for your business!"
    require_credit(db, client.id, "invoice_whatsapp", 1, inv.number)
    background_tasks.add_task(send_whatsapp_background, inv.phone_number, message)

    if inv.status == "Draft":
        inv.status = "Sent"
        inv.sent = datetime.now().strftime("%Y-%m-%d")
        db.commit()

    return {"message": "WhatsApp sending initiated", "status": inv.status}

# --- Email Open Tracking ---

TRACKING_PIXEL = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00, 0x80, 0x00,
    0x00, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x21, 0xf9, 0x04, 0x01, 0x00,
    0x00, 0x00, 0x00, 0x2c, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
    0x00, 0x02, 0x02, 0x44, 0x01, 0x00, 0x3b
])

@app.get("/api/track/open/{tracking_id}")
def track_email_open(tracking_id: str, db: Session = Depends(get_db)):
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.tracking_id == tracking_id).first()
    if inv:
        inv.open_count = (inv.open_count or 0) + 1
        inv.last_opened = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
    return StreamingResponse(iter([TRACKING_PIXEL]), media_type="image/gif", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    })

@app.get("/api/invoices/{number}/open-stats")
def get_open_stats(number: str, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == client.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {
        "number": inv.number,
        "tracking_id": inv.tracking_id,
        "open_count": inv.open_count or 0,
        "last_opened": inv.last_opened or "",
    }

# --- Contacts API ---

@app.get("/api/contacts/search")
def search_contacts(request: Request, q: str = "", db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    query = db.query(models.DBContact).filter(models.DBContact.client_id == client.id)
    if q:
        from sqlalchemy import or_
        query = query.filter(or_(
            models.DBContact.name.ilike(f"%{q}%"),
            models.DBContact.email.ilike(f"%{q}%")
        ))
    contacts = query.limit(10).all()
    return [{"id": c.id, "name": c.name, "email": c.email or "", "phone_number": c.phone_number or ""} for c in contacts]

@app.get("/api/contacts")
def list_contacts(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    contacts = db.query(models.DBContact).filter(models.DBContact.client_id == client.id).all()
    return [{"id": c.id, "name": c.name, "email": c.email or "", "phone_number": c.phone_number or ""} for c in contacts]

@app.post("/api/contacts")
def create_contact(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body or not body.get("name"):
        raise HTTPException(status_code=400, detail="Name required")
    existing = db.query(models.DBContact).filter(models.DBContact.name == body["name"], models.DBContact.client_id == client.id).first()
    if existing:
        if body.get("email") and not existing.email:
            existing.email = body["email"]
        if body.get("phone_number") and not existing.phone_number:
            existing.phone_number = body["phone_number"]
        db.commit()
        return {"id": existing.id, "name": existing.name, "email": existing.email or "", "phone_number": existing.phone_number or ""}
    contact = models.DBContact(name=body["name"], email=body.get("email", ""), phone_number=body.get("phone_number", ""), client_id=client.id)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return {"id": contact.id, "name": contact.name, "email": contact.email or "", "phone_number": contact.phone_number or ""}


@app.put("/api/contacts/{contact_id}")
def update_contact(contact_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    contact = db.query(models.DBContact).filter(models.DBContact.id == contact_id, models.DBContact.client_id == client.id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if body:
        if "name" in body: contact.name = body["name"]
        if "email" in body: contact.email = body["email"]
        if "phone_number" in body: contact.phone_number = body["phone_number"]
        db.commit()
        db.refresh(contact)
    return {"id": contact.id, "name": contact.name, "email": contact.email or "", "phone_number": contact.phone_number or ""}


@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    contact = db.query(models.DBContact).filter(models.DBContact.id == contact_id, models.DBContact.client_id == client.id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return {"ok": True}


# --- Bills API ---

@app.get("/api/bills")
def list_bills(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    bills = db.query(models.DBBill).filter(models.DBBill.client_id == client.id).order_by(models.DBBill.id.desc()).all()
    return [{"id": b.id, "number": b.number, "vendor_name": b.vendor_name, "vendor_email": b.vendor_email or "",
             "issue_date": b.issue_date or "", "due_date": b.due_date or "", "amount": b.amount or 0.0,
             "tax_amount": b.tax_amount or 0.0, "total": b.total or 0.0, "amount_paid": b.amount_paid or 0.0,
             "status": b.status or "Draft", "category": b.category or "general", "reference": b.reference or "",
             "notes": b.notes or ""} for b in bills]


@app.post("/api/bills")
def create_bill(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body:
        raise HTTPException(status_code=400, detail="Bill data required")
    existing = db.query(models.DBBill).filter(models.DBBill.number == body.get("number", ""), models.DBBill.client_id == client.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bill number already exists")
    bill = models.DBBill(
        client_id=client.id,
        number=body.get("number", ""),
        vendor_name=body.get("vendor_name", ""),
        vendor_email=body.get("vendor_email", ""),
        issue_date=body.get("issue_date", ""),
        due_date=body.get("due_date", ""),
        amount=body.get("amount", 0.0),
        tax_amount=body.get("tax_amount", 0.0),
        total=body.get("total", 0.0),
        status=body.get("status", "Draft"),
        category=body.get("category", "general"),
        reference=body.get("reference", ""),
        notes=body.get("notes", ""),
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    log_audit(db, client.id, "bill_created", "bill", bill.id, bill.number, f"Vendor: {bill.vendor_name}, Total: {bill.total}", request)
    db.commit()
    return {"id": bill.id, "number": bill.number}


@app.get("/api/bills/{bill_id}")
def get_bill(bill_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    bill = db.query(models.DBBill).filter(models.DBBill.id == bill_id, models.DBBill.client_id == client.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    line_items = db.query(models.DBBillLineItem).filter(models.DBBillLineItem.bill_id == bill.id).all()
    return {
        "id": bill.id, "number": bill.number, "vendor_name": bill.vendor_name, "vendor_email": bill.vendor_email or "",
        "issue_date": bill.issue_date or "", "due_date": bill.due_date or "", "amount": bill.amount or 0.0,
        "tax_amount": bill.tax_amount or 0.0, "total": bill.total or 0.0, "amount_paid": bill.amount_paid or 0.0,
        "status": bill.status or "Draft", "category": bill.category or "general", "reference": bill.reference or "",
        "notes": bill.notes or "",
        "line_items": [{"id": li.id, "description": li.description or "", "qty": li.qty or 1, "price": li.price or 0, "tax_rate": li.tax_rate or "20%"} for li in line_items]
    }


@app.put("/api/bills/{bill_id}")
def update_bill(bill_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    bill = db.query(models.DBBill).filter(models.DBBill.id == bill_id, models.DBBill.client_id == client.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if body:
        for field in ["number", "vendor_name", "vendor_email", "issue_date", "due_date", "amount", "tax_amount", "total", "amount_paid", "status", "category", "reference", "notes"]:
            if field in body:
                setattr(bill, field, body[field])
        db.commit()
        db.refresh(bill)
    return {"id": bill.id, "number": bill.number}


@app.delete("/api/bills/{bill_id}")
def delete_bill(bill_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    bill = db.query(models.DBBill).filter(models.DBBill.id == bill_id, models.DBBill.client_id == client.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    db.query(models.DBBillLineItem).filter(models.DBBillLineItem.bill_id == bill.id).delete()
    log_audit(db, client.id, "bill_deleted", "bill", bill.id, bill.number, "", request)
    db.delete(bill)
    db.commit()
    return {"ok": True}


@app.post("/api/bills/{bill_id}/pay")
def mark_bill_paid(bill_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    bill = db.query(models.DBBill).filter(models.DBBill.id == bill_id, models.DBBill.client_id == client.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill.amount_paid = bill.total or bill.amount or 0.0
    bill.status = "Paid"
    log_audit(db, client.id, "bill_paid", "bill", bill.id, bill.number, f"Amount: {bill.amount_paid}", request)
    db.commit()
    return {"ok": True, "status": "Paid"}


@app.get("/api/next-bill-number")
def next_bill_number(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    last = db.query(models.DBBill).filter(models.DBBill.client_id == client.id).order_by(models.DBBill.id.desc()).first()
    if last and last.number:
        try:
            num = int(last.number.replace("BILL-", "").replace("BILL", ""))
            return {"number": f"BILL-{num + 1:04d}"}
        except (ValueError, TypeError):
            pass
    return {"number": "BILL-0001"}


def base_currency(client) -> str:
    """The currency a business keeps its books in. Bills carry no currency of
    their own, so they are always this one."""
    return ((client.currency or "") or "GBP").upper()


def invoices_by_currency(invoices, base: str) -> dict:
    """Group invoices by the currency they were issued in.

    Every report below reports one currency at a time. Adding GBP to INR needs
    an exchange rate we do not have, and inventing one puts a made-up figure in
    front of somebody making decisions with it - which is exactly how the sales
    pipeline once showed a total in the trillions.
    """
    groups = {}
    for inv in invoices:
        code = ((inv.currency or "") or base).upper() or base
        groups.setdefault(code, []).append(inv)
    return groups


@app.get("/api/reports/profit-loss")
def profit_loss_report(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    base = base_currency(client)
    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client.id).all()
    bills = db.query(models.DBBill).filter(models.DBBill.client_id == client.id).all()
    groups = invoices_by_currency(invoices, base)

    def figures(inv_list, bill_list):
        monthly_revenue = {}
        monthly_expenses = {}
        for inv in inv_list:
            m = inv.issue_date[:7] if inv.issue_date and len(inv.issue_date) >= 7 else "Unknown"
            monthly_revenue[m] = monthly_revenue.get(m, 0) + (inv.paid or 0)
        for b in bill_list:
            m = b.issue_date[:7] if b.issue_date and len(b.issue_date) >= 7 else "Unknown"
            monthly_expenses[m] = monthly_expenses.get(m, 0) + (b.total or 0)
        all_months = sorted(set(list(monthly_revenue.keys()) + list(monthly_expenses.keys())))
        total_revenue = money(sum(monthly_revenue.values()))
        total_expenses = money(sum(monthly_expenses.values()))
        return {
            "months": all_months,
            "revenue": [money(monthly_revenue.get(m, 0)) for m in all_months],
            "expenses": [money(monthly_expenses.get(m, 0)) for m in all_months],
            "profit": [money(monthly_revenue.get(m, 0) - monthly_expenses.get(m, 0)) for m in all_months],
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_profit": money(total_revenue - total_expenses),
        }

    report = figures(groups.get(base, []), bills)
    report["currency"] = base
    report["other_currencies"] = [
        dict(figures(groups[code], []), currency=code)
        for code in sorted(groups) if code != base
    ]
    return report


@app.get("/api/reports/balance-sheet")
def balance_sheet_report(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    base = base_currency(client)
    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client.id).all()
    bills = db.query(models.DBBill).filter(models.DBBill.client_id == client.id).all()
    groups = invoices_by_currency(invoices, base)

    def figures(inv_list, bill_list):
        collected = money(sum(inv.paid or 0 for inv in inv_list))
        outstanding = money(sum(inv.due or 0 for inv in inv_list if inv.status != "Paid"))
        bills_paid = money(sum(b.amount_paid or 0 for b in bill_list))
        bills_unpaid = money(sum((b.total or 0) - (b.amount_paid or 0) for b in bill_list))
        return {
            "assets": {"cash_collected": collected, "accounts_receivable": outstanding},
            "liabilities": {"accounts_payable": bills_unpaid},
            "equity": {"retained_earnings": money(collected - bills_paid)},
            "total_assets": money(collected + outstanding),
            "total_liabilities": bills_unpaid,
            "total_equity": money(collected - bills_paid),
        }

    report = figures(groups.get(base, []), bills)
    report["currency"] = base
    report["other_currencies"] = [
        dict(figures(groups[code], []), currency=code)
        for code in sorted(groups) if code != base
    ]
    return report


@app.get("/api/reports/cash-summary")
def cash_summary_report(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    base = base_currency(client)
    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client.id).all()
    bills = db.query(models.DBBill).filter(models.DBBill.client_id == client.id).all()
    groups = invoices_by_currency(invoices, base)

    def figures(inv_list, bill_list):
        monthly_in = {}
        monthly_out = {}
        for inv in inv_list:
            m = inv.issue_date[:7] if inv.issue_date and len(inv.issue_date) >= 7 else "Unknown"
            monthly_in[m] = monthly_in.get(m, 0) + (inv.paid or 0)
        for b in bill_list:
            m = b.issue_date[:7] if b.issue_date and len(b.issue_date) >= 7 else "Unknown"
            monthly_out[m] = monthly_out.get(m, 0) + (b.amount_paid or 0)
        all_months = sorted(set(list(monthly_in.keys()) + list(monthly_out.keys())))
        return {
            "months": all_months,
            "money_in": [money(monthly_in.get(m, 0)) for m in all_months],
            "money_out": [money(monthly_out.get(m, 0)) for m in all_months],
            "net_cash": [money(monthly_in.get(m, 0) - monthly_out.get(m, 0)) for m in all_months],
        }

    report = figures(groups.get(base, []), bills)
    report["currency"] = base
    report["other_currencies"] = [
        dict(figures(groups[code], []), currency=code)
        for code in sorted(groups) if code != base
    ]
    return report
@app.get("/api/auth/login")
async def login(request: Request, role: str = "client", portal: str = None):
    request.session['oauth_role'] = role
    if portal:
        request.session['oauth_portal'] = portal
    redirect_uri = str(request.url_for('auth_callback'))
    if redirect_uri.startswith('http://') and 'localhost' not in redirect_uri:
        redirect_uri = redirect_uri.replace('http://', 'https://', 1)
    return await oauth.google.authorize_redirect(request, redirect_uri, access_type='offline', prompt='consent')

def auto_clock_in_on_sign_in(db: Session, emp, request, lat=0.0, lng=0.0,
                             device="", loc_label=""):
    """Start a shift if signing in should start one.

    Returns the attendance row it created, or None. Signing in only starts a
    shift on a working day, and only once - opening the portal twice in a
    morning is not two shifts. Shared so Google sign-in and password sign-in
    record attendance the same way.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    existing = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp.id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == emp.client_id,
    ).first()
    if existing and existing.clock_in:
        return None

    settings = attendance_settings_for(db, emp.client_id)
    if not should_auto_clock_in(settings):
        return None

    check_type = "remote"
    if lat and lng and settings and settings.office_lat and settings.office_lng:
        from math import radians, cos, sin, asin, sqrt
        dlat = radians(lat - settings.office_lat)
        dlng = radians(lng - settings.office_lng)
        a = sin(dlat / 2) ** 2 + cos(radians(settings.office_lat)) * cos(radians(lat)) * sin(dlng / 2) ** 2
        dist = 2 * 6371000 * asin(sqrt(a))
        check_type = "office" if dist <= settings.geofence_radius else "field"

    att = models.DBAttendance(
        client_id=emp.client_id, employee_id=emp.id, date=today,
        clock_in=datetime.now().strftime("%H:%M:%S"), status="present",
        check_type=check_type,
        ip_address=request.client.host if request and request.client else "",
        device_info=device, location_lat=lat, location_lng=lng,
        location_label=loc_label,
    )
    db.add(att)
    return att


def employee_by_email(db: Session, email: str):
    """The employee whose record carries this address, if any.

    HR types the address on the employee's record; that is the whole
    enrolment. Matching is case-insensitive because nobody types their own
    address the same way twice, and a terminated employee is not a match -
    their access ends when their employment does.
    """
    if not email:
        return None
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.email.ilike(email.strip())).first()
    if emp and emp.status == "terminated":
        return None
    return emp


def start_employee_session(request: Request, emp, replace_other_sessions=False):
    """Everything that makes a request count as this employee.

    Kept in one place so signing in with Google lands in exactly the same
    state as signing in with a password, rather than a near-copy that drifts.

    `replace_other_sessions` is for Google, where the person has just told us
    who they are: arriving as an employee should not leave an account holder's
    session lying underneath. Password sign-in leaves other sessions alone,
    because that has never been how it behaved and quietly signing somebody out
    of their own business is worse than the shared-browser case it would fix.
    """
    request.session['employee_id'] = emp.id
    request.session['employee_client_id'] = emp.client_id
    if replace_other_sessions:
        for key in ('client_id', 'member_id', 'superadmin_id'):
            request.session.pop(key, None)


def employee_signing_in(db: Session, email: str, portal: str):
    """The employee this Google sign-in should become, or None.

    Somebody who is only an employee lands in the employee portal from any
    sign-in page - that is the whole point of HR just saving their address.

    One address can be both, though: an owner who also keeps an employee record
    for their own payslips and leave. Routing them to the employee portal every
    time would shut them out of their own business, so when both exist the page
    they started from decides, and only the employee page means "as an
    employee".
    """
    emp = employee_by_email(db, email)
    if not emp:
        return None
    owns_an_account = db.query(models.DBClient).filter(
        models.DBClient.email == email).first()
    if owns_an_account and portal != 'employee':
        return None
    return emp


@app.get("/api/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.error(f"Google token exchange failed: {e}")
        return RedirectResponse(url="/login.html?error=auth_failed")
    user = token.get('userinfo')
    access_token = token.get('access_token')
    refresh_token = token.get('refresh_token')
    oauth_role = request.session.pop('oauth_role', 'client')

    try:
        if user:
            request.session['user'] = dict(user)
            request.session['access_token'] = access_token
            if refresh_token:
                request.session['refresh_token'] = refresh_token

            oauth_portal = request.session.pop('oauth_portal', 'invoicing')
            target_dashboard = "/hr.html" if oauth_portal == "hr" else "/app.html"

            google_email = user.get('email', '')

            if oauth_role == 'superadmin' and google_email:
                sa_user = db.query(models.DBSuperAdmin).filter(models.DBSuperAdmin.email == google_email).first()
                if sa_user:
                    request.session['superadmin_id'] = sa_user.id
                    log_login(db, None, google_email, "superadmin", "google", request, "success")
                    return RedirectResponse(url="/superadmin.html")
                else:
                    log_login(db, None, google_email, "superadmin", "google", request, "failed")
                    return RedirectResponse(url="/superadmin-login.html?error=not_admin")

            if google_email:
                sa_check = db.query(models.DBSuperAdmin).filter(models.DBSuperAdmin.email == google_email).first()
                if sa_check:
                    return RedirectResponse(url="/superadmin-login.html")

                # An address HR put on an employee record goes to the employee
                # portal, whichever sign-in page it started from. This is what
                # enrolment means here: no password to set, no invitation to
                # accept, no second account. It is checked before the client
                # lookup so that signing in never silently creates a business
                # account for a member of staff.
                emp = employee_signing_in(db, google_email, oauth_portal)
                if emp:
                    start_employee_session(request, emp, replace_other_sessions=True)
                    log_login(db, emp.client_id, google_email, "employee",
                              "google", request, "success")
                    auto_clock_in_on_sign_in(db, emp, request)
                    db.commit()
                    return RedirectResponse(url="/employee-dashboard.html")

                existing_client = db.query(models.DBClient).filter(models.DBClient.email == google_email).first()
                if existing_client:
                    client_id = existing_client.id
                    request.session['client_id'] = client_id
                    log_login(db, client_id, google_email, "client", "google", request, "success")
                else:
                    new_client = models.DBClient(
                        email=google_email,
                        password_hash=hash_password(secrets.token_hex(16)),
                        company_name=user.get('name', ''),
                        contact_name=user.get('name', ''),
                        is_onboarded=False,
                    )
                    db.add(new_client)
                    db.flush()
                    client_id = new_client.id
                    request.session['client_id'] = client_id
                    log_login(db, client_id, google_email, "client", "google", request, "success")

                # Save refresh token per-client
                if refresh_token and client_id:
                    try:
                        setting = db.query(models.DBSettings).filter(
                            models.DBSettings.key == "GOOGLE_REFRESH_TOKEN",
                            models.DBSettings.client_id == client_id
                        ).first()
                        if not setting:
                            setting = models.DBSettings(key="GOOGLE_REFRESH_TOKEN", value=refresh_token, client_id=client_id)
                            db.add(setting)
                        else:
                            setting.value = refresh_token
                        db.commit()
                    except Exception as e:
                        logger.error(f"Failed to save refresh token: {e}")

                if existing_client:
                    if existing_client.is_onboarded:
                        return RedirectResponse(url=target_dashboard)
                    else:
                        return RedirectResponse(url="/onboard.html")
                else:
                    return RedirectResponse(url="/onboard.html")
    except Exception as e:
        logger.error(f"Callback processing failed: {e}")
        return RedirectResponse(url="/login.html?error=callback_failed")

    return RedirectResponse(url=target_dashboard)

@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Liveness + database readiness.

    This is the path Railway restarts on, so it has to fail when the app cannot
    actually serve traffic - a bare 'ok' kept a database-less instance in
    rotation.
    """
    from sqlalchemy import text as sql_text
    try:
        db.execute(sql_text("SELECT 1"))
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})

    # Schema updates are applied non-fatally so a partial failure cannot stop
    # the app booting, but a migration that never ran must not look identical
    # to one that succeeded.
    try:
        from database import migration_report
        problems = migration_report()
    except Exception:
        problems = []
    body = {"status": "ok", "database": "ok"}
    if problems:
        body["status"] = "ok_with_warnings"
        body["migration_warnings"] = len(problems)
    return body

@app.get("/api/auth/me")
def get_current_user(request: Request, db: Session = Depends(get_db)):
    user = request.session.get('user')
    client_id = request.session.get('client_id')
    if user:
        return {"user": user}
    if client_id:
        client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
        if client:
            return {"user": {"email": client.email, "name": client.contact_name or client.company_name}}
    return JSONResponse(status_code=401, content={"error": "Not authenticated"})

@app.get("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

@app.get("/api/gmail/status")
def gmail_status(request: Request, db: Session = Depends(get_db)):
    user = request.session.get('user')
    client_id = request.session.get('client_id')
    refresh_token = get_stored_refresh_token(db, client_id=client_id)
    # Try to get the authorized Gmail email from the refresh token owner
    gmail_email = None
    if refresh_token:
        try:
            creds = get_gmail_credentials(access_token=None, refresh_token=refresh_token)
            if creds and creds.valid:
                service = build('gmail', 'v1', credentials=creds)
                profile = service.users().getProfile(userId="me").execute()
                gmail_email = profile.get("emailAddress")
        except Exception:
            pass
    return {
        "logged_in": bool(user),
        "user_email": user.get('email') if user else None,
        "user_name": user.get('name') if user else None,
        "refresh_token_stored": bool(refresh_token),
        "gmail_ready": bool(refresh_token),
        "gmail_authorized_email": gmail_email
    }

@app.post("/api/gmail/disconnect")
def disconnect_gmail(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    setting = db.query(models.DBSettings).filter(
        models.DBSettings.key == "GOOGLE_REFRESH_TOKEN",
        models.DBSettings.client_id == client.id
    ).first()
    if setting:
        db.delete(setting)
        db.commit()
    return {"ok": True, "message": "Gmail disconnected. Re-authorize with your Google account."}

# --- Test Email Endpoint (for demos) ---

@app.post("/api/send-test-email")
def send_test_email(test: TestEmail, background_tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
    sender_name = os.getenv("FROM_NAME", "aniprotech")
    from_header = f"{sender_name} <{from_email}>"

    background_tasks.add_task(send_email_background, test.to_email, test.subject, test.body, from_header)
    return {"message": f"Email queued for delivery to {test.to_email}"}

# --- Invoice Management ---

@app.delete("/api/invoices/{number}")
def delete_invoice(number: str, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == client.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.query(models.DBLineItem).filter(models.DBLineItem.invoice_id == inv.id).delete()
    db.query(models.DBPayment).filter(models.DBPayment.invoice_id == inv.id).delete()
    log_audit(db, client.id, "invoice_deleted", "invoice", inv.id, inv.number, f"Contact: {inv.to_contact}", request)
    db.delete(inv)
    db.commit()
    return {"message": "Invoice deleted successfully"}

@app.post("/api/invoices/{number}/mark-paid")
def mark_invoice_paid(number: str, request: Request, db: Session = Depends(get_db)):
    """Settle the whole outstanding balance in one go, recording it in the ledger."""
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(models.DBInvoice.number == number, models.DBInvoice.client_id == client.id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    outstanding = money(inv.due or 0)
    if outstanding > 0:
        db.add(models.DBPayment(
            client_id=client.id, invoice_id=inv.id, amount=outstanding,
            paid_on=datetime.now().strftime("%Y-%m-%d"), method="manual",
            note="Marked as paid in full",
        ))
    inv.paid = money((inv.paid or 0) + outstanding)
    inv.due = 0.0
    inv.status = "Paid"
    log_audit(db, client.id, "invoice_marked_paid", "invoice", inv.id, inv.number, f"Amount: {inv.paid}", request)
    db.commit()
    return {"message": "Invoice marked as paid", "status": "Paid", "paid": inv.paid, "due": inv.due}


class PaymentCreate(BaseModel):
    amount: float
    paid_on: Optional[str] = ""
    method: Optional[str] = "bank_transfer"
    reference: Optional[str] = ""
    note: Optional[str] = ""


@app.post("/api/invoices/{number}/payments")
def record_invoice_payment(number: str, body: PaymentCreate, request: Request, db: Session = Depends(get_db)):
    """Record a part payment. Status moves Draft/Sent -> Partially Paid -> Paid."""
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(
        models.DBInvoice.number == number, models.DBInvoice.client_id == client.id
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    amount = money(body.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    outstanding = money(inv.due or 0)
    if outstanding <= 0:
        raise HTTPException(status_code=400, detail="This invoice has no outstanding balance")
    if amount > outstanding + 0.005:
        raise HTTPException(
            status_code=400,
            detail=f"Payment of {amount:.2f} exceeds the outstanding balance of {outstanding:.2f}",
        )
    payment = models.DBPayment(
        client_id=client.id, invoice_id=inv.id, amount=amount,
        paid_on=body.paid_on or datetime.now().strftime("%Y-%m-%d"),
        method=body.method or "bank_transfer",
        reference=body.reference or "", note=body.note or "",
    )
    db.add(payment)
    inv.paid = money((inv.paid or 0) + amount)
    inv.due = money(outstanding - amount)
    apply_payment_status(inv)
    log_audit(db, client.id, "invoice_payment_recorded", "invoice", inv.id, inv.number,
              f"Amount: {amount:.2f}, remaining: {inv.due:.2f}", request)
    db.commit()
    return {
        "message": "Payment recorded", "status": inv.status,
        "paid": inv.paid, "due": inv.due, "payment_id": payment.id,
    }


@app.delete("/api/invoices/{number}/payments/{payment_id}")
def delete_invoice_payment(number: str, payment_id: int, request: Request, db: Session = Depends(get_db)):
    """Reverse a payment that was entered by mistake."""
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(
        models.DBInvoice.number == number, models.DBInvoice.client_id == client.id
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    payment = db.query(models.DBPayment).filter(
        models.DBPayment.id == payment_id, models.DBPayment.invoice_id == inv.id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    inv.paid = money(max(0.0, (inv.paid or 0) - (payment.amount or 0)))
    inv.due = money((inv.due or 0) + (payment.amount or 0))
    inv.status = "Partially Paid" if (inv.paid or 0) > 0.005 else ("Sent" if inv.sent else "Draft")
    db.delete(payment)
    log_audit(db, client.id, "invoice_payment_reversed", "invoice", inv.id, inv.number,
              f"Amount: {payment.amount:.2f}", request)
    db.commit()
    return {"message": "Payment reversed", "status": inv.status, "paid": inv.paid, "due": inv.due}


@app.put("/api/invoices/{number}")
def update_invoice(number: str, invoice: InvoiceCreate, request: Request, db: Session = Depends(get_db)):
    """Edit a draft/unsent invoice: replaces line items and recomputes totals."""
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(
        models.DBInvoice.number == number, models.DBInvoice.client_id == client.id
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if (inv.paid or 0) > 0:
        raise HTTPException(
            status_code=409,
            detail="This invoice already has payments against it. Reverse them before editing.",
        )
    validate_line_items(invoice.line_items)
    validate_invoice_dates(invoice.issue_date, invoice.due_date)

    if invoice.invoice_number and invoice.invoice_number.strip() and invoice.invoice_number.strip() != inv.number:
        new_number = invoice.invoice_number.strip()
        clash = db.query(models.DBInvoice).filter(
            models.DBInvoice.client_id == client.id, models.DBInvoice.number == new_number
        ).first()
        if clash:
            raise HTTPException(status_code=409, detail=f"Invoice number {new_number} already exists")
        inv.number = new_number

    subtotal, tax, total = compute_invoice_totals(invoice.line_items, invoice.tax_type)

    inv.ref = invoice.reference
    inv.to_contact = invoice.contact
    inv.email = invoice.email
    inv.phone_number = invoice.phone_number
    inv.issue_date = invoice.issue_date
    inv.due_date = invoice.due_date
    inv.tax_type = invoice.tax_type
    inv.due = total
    if invoice.currency:
        inv.currency = invoice.currency.upper()
    if invoice.bank_details is not None:
        inv.bank_details = invoice.bank_details
    if invoice.status:
        inv.status = invoice.status

    db.query(models.DBLineItem).filter(models.DBLineItem.invoice_id == inv.id).delete()
    for item in invoice.line_items:
        db.add(models.DBLineItem(
            invoice_id=inv.id, name=item.name or "", description=item.description,
            qty=item.qty, price=item.price, disc=item.disc or 0.0,
            account=item.account, tax_rate=item.tax_rate,
        ))
    log_audit(db, client.id, "invoice_updated", "invoice", inv.id, inv.number, f"Total: {total:.2f}", request)
    db.commit()
    return get_invoice(inv.number, request, db)


@app.get("/api/reports/aged-receivables")
def aged_receivables(request: Request, db: Session = Depends(get_db)):
    """Outstanding balances bucketed by how late they are - the report every
    finance team asks for first."""
    client = get_client_user(request, db)
    base = base_currency(client)
    invoices = db.query(models.DBInvoice).filter(
        models.DBInvoice.client_id == client.id,
        models.DBInvoice.status.notin_(["Draft", "Paid", "Void"]),
    ).all()
    today = datetime.now().date()

    def figures(inv_list):
        buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "over_90": 0.0}
        rows = []
        for inv in inv_list:
            outstanding = money(inv.due or 0)
            if outstanding <= 0:
                continue
            days = invoice_overdue_days(inv, today)
            if days == 0:
                bucket = "current"
            elif days <= 30:
                bucket = "1_30"
            elif days <= 60:
                bucket = "31_60"
            elif days <= 90:
                bucket = "61_90"
            else:
                bucket = "over_90"
            buckets[bucket] = money(buckets[bucket] + outstanding)
            rows.append({
                "number": inv.number, "contact": inv.to_contact, "due_date": inv.due_date,
                "outstanding": outstanding, "days_overdue": days, "bucket": bucket,
                # Each row carries its own currency so a mixed table can print
                # the right symbol against every line.
                "currency": ((inv.currency or "") or base).upper() or base,
            })
        rows.sort(key=lambda r: r["days_overdue"], reverse=True)
        return {
            "buckets": buckets,
            "total_outstanding": money(sum(buckets.values())),
            "invoices": rows,
        }

    groups = invoices_by_currency(invoices, base)
    report = figures(groups.get(base, []))
    report["currency"] = base
    report["other_currencies"] = [
        dict(figures(groups[code]), currency=code)
        for code in sorted(groups) if code != base
    ]
    return report

# --- Settings API ---

@app.get("/api/settings")
def get_settings(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    settings = db.query(models.DBSettings).filter(models.DBSettings.client_id == client.id).all()
    return {s.key: s.value for s in settings}

@app.post("/api/settings")
def save_settings(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if body:
        for key, val in body.items():
            setting = db.query(models.DBSettings).filter(models.DBSettings.key == key, models.DBSettings.client_id == client.id).first()
            if setting:
                setting.value = str(val)
            else:
                setting = models.DBSettings(key=key, value=str(val), client_id=client.id)
                db.add(setting)
    db.commit()
    return {"message": "Settings saved"}

@app.get("/api/audit-logs")
def get_audit_logs(request: Request, limit: int = 100, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    logs = db.query(models.DBAuditLog).filter(
        models.DBAuditLog.client_id == client.id
    ).order_by(models.DBAuditLog.created_at.desc()).limit(limit).all()
    return [{
        "id": l.id, "user_type": l.user_type, "user_name": l.user_name,
        "action": l.action, "entity_type": l.entity_type, "entity_id": l.entity_id,
        "entity_name": l.entity_name, "details": l.details, "ip_address": l.ip_address,
        "created_at": l.created_at,
    } for l in logs]

@app.get("/api/my/login-history")
def my_login_history(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    logs = db.query(models.DBClientLoginLog).filter(
        models.DBClientLoginLog.client_id == client.id
    ).order_by(models.DBClientLoginLog.created_at.desc()).limit(limit).all()
    return [{
        "id": l.id, "email": l.email, "login_type": l.login_type,
        "ip_address": l.ip_address, "device_info": l.device_info,
        "status": l.status, "created_at": l.created_at,
    } for l in logs]

# ============================================================================
# SCHEDULER - the small amount of work that has to happen without a user
# ============================================================================

# How often the loop wakes. Jobs decide for themselves whether they are due,
# so this only sets how soon after becoming due something runs.
SCHEDULER_TICK_SECONDS = int(os.getenv("SCHEDULER_TICK_SECONDS", "900"))

# Registered as (name, period_key_fn, run_fn). period_key_fn turns "now" into a
# string identifying this run, which is what stops a job running twice.
SCHEDULED_JOBS = []


def daily_key(now=None):
    return (now or datetime.now()).strftime("%Y-%m-%d")


def scheduled_job(name, period_key_fn=daily_key):
    def register(fn):
        SCHEDULED_JOBS.append((name, period_key_fn, fn))
        return fn
    return register


def claim_job_run(db, job_name, period_key):
    """Take this period, or find that another worker already has it.

    The unique index does the arbitrating, so this is safe with any number of
    workers and needs no separate lock service.
    """
    row = models.DBJobRun(job_name=job_name, period_key=period_key, status="running")
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return row


def run_due_jobs(now=None, only=None):
    """Run whatever is due. Safe to call as often as you like.

    Returns what happened, which is what the tests and the operator endpoint
    both read.
    """
    now = now or datetime.now()
    results = []
    for name, period_key_fn, fn in SCHEDULED_JOBS:
        if only and name != only:
            continue
        period_key = period_key_fn(now)
        with SessionLocal() as db:
            claim = claim_job_run(db, name, period_key)
            if claim is None:
                results.append({"job": name, "period": period_key, "status": "already_done"})
                continue
            try:
                detail = fn(db, now) or ""
                claim.status = "done"
                claim.detail = str(detail)[:500]
            except Exception as exc:
                # A job that throws must not take the loop down with it, and
                # must not silently look like it succeeded.
                logger.exception("Scheduled job %s failed", name)
                claim.status = "failed"
                claim.detail = str(exc)[:500]
            claim.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()
            results.append({"job": name, "period": period_key,
                            "status": claim.status, "detail": claim.detail})
    return results


async def scheduler_loop():
    while True:
        try:
            await asyncio.to_thread(run_due_jobs)
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(SCHEDULER_TICK_SECONDS)


@app.post("/api/superadmin/run-jobs")
def superadmin_run_jobs(request: Request, job: str = ""):
    """Run the scheduled work now, for an operator who does not want to wait
    for the next tick. Still claims the period, so this cannot double-send."""
    require_superadmin(request)
    return {"results": run_due_jobs(only=job or None)}


@app.get("/api/superadmin/job-runs")
def superadmin_job_runs(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    require_superadmin(request)
    rows = db.query(models.DBJobRun).order_by(
        models.DBJobRun.id.desc()).limit(min(limit, 200)).all()
    return [{
        "id": r.id, "job": r.job_name, "period": r.period_key, "status": r.status,
        "detail": r.detail or "", "started_at": r.started_at,
        "finished_at": r.finished_at or "",
    } for r in rows]


# ============================================================================
# RECURRING INVOICES and OVERDUE REMINDERS - the work that happens on its own
# ============================================================================

RECURRING_FREQUENCIES = ("weekly", "monthly", "quarterly", "yearly")

# Days past due at which a chase goes out. Each rung is sent at most once.
REMINDER_LADDER = (1, 7, 14, 30)


def advance_date(from_date, frequency):
    """The next occurrence after `from_date`.

    Month arithmetic clamps to the end of a short month, so a template set to
    the 31st still runs in February instead of skipping it.
    """
    if frequency == "weekly":
        return from_date + timedelta(days=7)
    months = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(frequency, 1)
    month_index = from_date.month - 1 + months
    year = from_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(from_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def recurring_to_dict(t, db=None):
    return {
        "id": t.id,
        "name": t.name or "",
        "to": t.to_contact or "",
        "email": t.email or "",
        "phone_number": t.phone_number or "",
        "reference": t.reference or "",
        "frequency": t.frequency,
        "payment_terms_days": t.payment_terms_days or 14,
        "next_run": t.next_run or "",
        "end_date": t.end_date or "",
        "is_active": bool(t.is_active),
        "auto_send": bool(t.auto_send),
        "last_run": t.last_run or "",
        "last_invoice_number": t.last_invoice_number or "",
        "invoices_created": t.invoices_created or 0,
        "tax_type": t.tax_type,
        "currency": t.currency or "",
        "total": compute_invoice_totals(t.line_items, t.tax_type)[2],
        "line_items": [{
            "name": li.name or "", "description": li.description, "qty": li.qty,
            "price": li.price, "disc": li.disc, "account": li.account,
            "tax_rate": li.tax_rate,
        } for li in t.line_items],
    }


class RecurringIn(BaseModel):
    name: Optional[str] = ""
    contact: str
    email: Optional[str] = ""
    phone_number: Optional[str] = ""
    reference: Optional[str] = ""
    line_items: List[LineItem]
    tax_type: Optional[str] = "exclusive"
    currency: Optional[str] = ""
    bank_details: Optional[str] = ""
    frequency: Optional[str] = "monthly"
    payment_terms_days: Optional[int] = 14
    next_run: str
    end_date: Optional[str] = ""
    is_active: Optional[bool] = True
    auto_send: Optional[bool] = False


def validate_recurring(body):
    if body.frequency not in RECURRING_FREQUENCIES:
        raise HTTPException(
            status_code=400,
            detail="Frequency must be one of: " + ", ".join(RECURRING_FREQUENCIES))
    if not _parse_date(body.next_run):
        raise HTTPException(status_code=400, detail="First issue date must be in YYYY-MM-DD format")
    if body.end_date and not _parse_date(body.end_date):
        raise HTTPException(status_code=400, detail="End date must be in YYYY-MM-DD format")
    if body.end_date and _parse_date(body.end_date) < _parse_date(body.next_run):
        raise HTTPException(status_code=400, detail="End date cannot be before the first issue date")
    try:
        terms = int(body.payment_terms_days if body.payment_terms_days is not None else 14)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Payment terms must be a whole number of days")
    if terms < 0 or terms > 365:
        raise HTTPException(status_code=400, detail="Payment terms must be between 0 and 365 days")
    return terms


@app.get("/api/recurring-invoices")
def list_recurring(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    rows = db.query(models.DBRecurringInvoice).filter(
        models.DBRecurringInvoice.client_id == client.id
    ).order_by(models.DBRecurringInvoice.id.desc()).all()
    return [recurring_to_dict(t) for t in rows]


@app.post("/api/recurring-invoices")
def create_recurring(body: RecurringIn, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    validate_line_items(body.line_items)
    terms = validate_recurring(body)

    t = models.DBRecurringInvoice(
        client_id=client.id, name=body.name or "", to_contact=body.contact,
        email=body.email or "", phone_number=body.phone_number or "",
        reference=body.reference or "", tax_type=body.tax_type,
        currency=(body.currency or "").upper() or (client.currency or ""),
        bank_details=body.bank_details or "", frequency=body.frequency,
        payment_terms_days=terms, next_run=body.next_run, end_date=body.end_date or "",
        is_active=bool(body.is_active), auto_send=bool(body.auto_send),
    )
    db.add(t)
    db.flush()
    for item in body.line_items:
        db.add(models.DBRecurringLineItem(
            recurring_id=t.id, name=item.name or "", description=item.description,
            qty=item.qty, price=item.price, disc=item.disc or 0.0,
            account=item.account, tax_rate=item.tax_rate,
        ))
    log_audit(db, client.id, "recurring_created", "recurring", t.id, t.name or t.to_contact,
              t.frequency, request)
    db.commit()
    db.refresh(t)
    return recurring_to_dict(t)


@app.put("/api/recurring-invoices/{rec_id}")
def update_recurring(rec_id: int, body: RecurringIn, request: Request,
                     db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    t = db.query(models.DBRecurringInvoice).filter(
        models.DBRecurringInvoice.id == rec_id,
        models.DBRecurringInvoice.client_id == client.id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")
    validate_line_items(body.line_items)
    terms = validate_recurring(body)

    t.name = body.name or ""
    t.to_contact = body.contact
    t.email = body.email or ""
    t.phone_number = body.phone_number or ""
    t.reference = body.reference or ""
    t.tax_type = body.tax_type
    t.currency = (body.currency or "").upper() or t.currency
    t.bank_details = body.bank_details or ""
    t.frequency = body.frequency
    t.payment_terms_days = terms
    t.next_run = body.next_run
    t.end_date = body.end_date or ""
    t.is_active = bool(body.is_active)
    t.auto_send = bool(body.auto_send)

    db.query(models.DBRecurringLineItem).filter(
        models.DBRecurringLineItem.recurring_id == t.id).delete()
    for item in body.line_items:
        db.add(models.DBRecurringLineItem(
            recurring_id=t.id, name=item.name or "", description=item.description,
            qty=item.qty, price=item.price, disc=item.disc or 0.0,
            account=item.account, tax_rate=item.tax_rate,
        ))
    log_audit(db, client.id, "recurring_updated", "recurring", t.id,
              t.name or t.to_contact, t.frequency, request)
    db.commit()
    db.refresh(t)
    return recurring_to_dict(t)


@app.delete("/api/recurring-invoices/{rec_id}")
def delete_recurring(rec_id: int, request: Request, db: Session = Depends(get_db)):
    """Stops future invoices. The ones already issued are real documents and
    are left exactly where they are."""
    client = get_client_user(request, db)
    t = db.query(models.DBRecurringInvoice).filter(
        models.DBRecurringInvoice.id == rec_id,
        models.DBRecurringInvoice.client_id == client.id,
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Recurring invoice not found")
    db.query(models.DBRecurringLineItem).filter(
        models.DBRecurringLineItem.recurring_id == t.id).delete()
    log_audit(db, client.id, "recurring_deleted", "recurring", t.id,
              t.name or t.to_contact, "", request)
    db.delete(t)
    db.commit()
    return {"message": "Recurring invoice stopped"}


def issue_recurring_invoice(db, t, on_date):
    """Raise one invoice from a template and move the schedule on."""
    subtotal, tax, total = compute_invoice_totals(t.line_items, t.tax_type)
    number = next_sequence_number(db, models.DBInvoice, t.client_id, invoice_prefix_for(db, t.client_id))
    due = on_date + timedelta(days=t.payment_terms_days or 14)

    inv = models.DBInvoice(
        client_id=t.client_id, number=number, ref=t.reference or "",
        to_contact=t.to_contact, email=t.email or "", phone_number=t.phone_number or "",
        issue_date=on_date.strftime("%Y-%m-%d"), due_date=due.strftime("%Y-%m-%d"),
        paid=0.00, due=round(total, 2), status="Draft", sent="",
        tax_type=t.tax_type, currency=t.currency or "", bank_details=t.bank_details or "",
    )
    db.add(inv)
    db.flush()
    for li in t.line_items:
        db.add(models.DBLineItem(
            invoice_id=inv.id, name=li.name or "", description=li.description,
            qty=li.qty, price=li.price, disc=li.disc or 0.0,
            account=li.account, tax_rate=li.tax_rate,
        ))

    t.last_run = on_date.strftime("%Y-%m-%d")
    t.last_invoice_number = number
    t.invoices_created = (t.invoices_created or 0) + 1
    nxt = advance_date(on_date, t.frequency)
    t.next_run = nxt.strftime("%Y-%m-%d")
    # A template that has reached its end date stops rather than lingering.
    end = _parse_date(t.end_date)
    if end and nxt > end:
        t.is_active = False
    return inv


@scheduled_job("recurring_invoices")
def job_recurring_invoices(db, now):
    """Raise whatever is due today.

    Catches up if the app was down: a template whose date has passed is issued
    for each period it missed, rather than silently losing months.
    """
    today = now.date()
    issued = 0
    templates = db.query(models.DBRecurringInvoice).filter(
        models.DBRecurringInvoice.is_active == True,          # noqa: E712
        models.DBRecurringInvoice.next_run != "",
        models.DBRecurringInvoice.next_run <= today.strftime("%Y-%m-%d"),
    ).all()
    for t in templates:
        guard = 0
        while t.is_active and guard < 60:
            due_on = _parse_date(t.next_run)
            if not due_on or due_on > today:
                break
            end = _parse_date(t.end_date)
            if end and due_on > end:
                t.is_active = False
                break
            if not t.line_items:
                break
            issue_recurring_invoice(db, t, due_on)
            issued += 1
            guard += 1
    db.commit()
    return f"{issued} invoice(s) raised"


def reminder_stage_for(days_overdue):
    """The highest rung reached, so a gap in ticks does not skip a chase."""
    reached = [d for d in REMINDER_LADDER if days_overdue >= d]
    return max(reached) if reached else None


@scheduled_job("overdue_reminders")
def job_overdue_reminders(db, now):
    """Chase invoices that have gone past their due date.

    A paid, part-paid or void invoice is never chased, and each rung of the
    ladder goes out at most once per invoice.
    """
    today = now.date()
    sent = 0
    candidates = db.query(models.DBInvoice).filter(
        models.DBInvoice.status.notin_(["Paid", "Void", "Draft"]),
        models.DBInvoice.due > 0,
        models.DBInvoice.due_date != "",
    ).all()

    for inv in candidates:
        due_date = _parse_date(inv.due_date)
        if not due_date or due_date >= today:
            continue
        stage = reminder_stage_for((today - due_date).days)
        if stage is None or not inv.email or not validate_email_address(inv.email):
            continue

        already = db.query(models.DBInvoiceReminder).filter(
            models.DBInvoiceReminder.invoice_id == inv.id,
            models.DBInvoiceReminder.stage_days == stage,
        ).first()
        if already:
            continue

        settings_rows = db.query(models.DBSettings).filter(
            models.DBSettings.client_id == inv.client_id).all()
        settings_map = {s.key: s.value for s in settings_rows}
        inv_client = db.query(models.DBClient).filter(
            models.DBClient.id == inv.client_id).first()
        company = (settings_map.get("company_name", "")
                   or (inv_client.company_name if inv_client else "") or "Accounts")
        cur = currency_symbol((inv.currency or "GBP").upper())
        days = (today - due_date).days

        subject = f"Reminder: invoice {inv.number} is {days} day(s) overdue"
        text_body = (
            f"Hello {inv.to_contact},\n\n"
            f"Invoice {inv.number} for {cur}{inv.due:.2f} was due on {inv.due_date} "
            f"and is now {days} day(s) overdue.\n\n"
            "If you have already paid, please ignore this note.\n\n"
            f"Kind regards,\n{company}\n"
        )
        html_body = f"""
        <!DOCTYPE html><html><body style="font-family:Arial,Helvetica,sans-serif;background:#f1f5f9;margin:0;padding:0;">
          <div style="max-width:520px;margin:0 auto;padding:40px 20px;">
            <div style="background:#fff;border-radius:12px;overflow:hidden;">
              <div style="background:#0f172a;padding:28px;text-align:center;">
                <div style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;">Payment reminder</div>
                <div style="font-size:24px;font-weight:800;color:#fff;margin-top:6px;">{esc(inv.number)}</div>
              </div>
              <div style="padding:26px;">
                <p style="margin:0 0 16px;font-size:15px;">Hello {esc(inv.to_contact)},</p>
                <p style="margin:0 0 18px;font-size:15px;color:#475569;">
                  Invoice <strong>{esc(inv.number)}</strong> for
                  <strong>{cur}{inv.due:.2f}</strong> was due on
                  <strong>{esc(inv.due_date)}</strong>, which is {days} day(s) ago.
                </p>
                <p style="margin:0;font-size:13px;color:#64748b;">
                  If you have already paid, please ignore this note.
                </p>
              </div>
              <div style="background:#f8fafc;padding:18px;text-align:center;border-top:1px solid #e2e8f0;">
                <div style="font-size:13px;font-weight:700;color:#0f172a;">{esc(company)}</div>
              </div>
            </div>
          </div>
        </body></html>
        """

        from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
        # Recorded before sending, and the unique index means a second worker
        # racing this cannot send the same rung twice.
        db.add(models.DBInvoiceReminder(
            client_id=inv.client_id, invoice_id=inv.id,
            stage_days=stage, sent_to=inv.email,
        ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue

        send_email_background(
            inv.email, subject, text_body, f"{company} <{from_email}>",
            html_body, None, "", "", client_id=inv.client_id,
        )
        sent += 1

    return f"{sent} reminder(s) sent"


# --- Interview reminders ----------------------------------------------------

# How far ahead of an interview the nudge goes out.
INTERVIEW_REMINDER_HOURS = 24


@scheduled_job("close_abandoned_shifts")
def job_close_abandoned_shifts(db, now):
    """Close a shift somebody clocked into and never out of.

    Nothing did this, so a forgotten clock-out stayed open for ever: the row
    kept a live "Clock Out" button weeks later, the status stayed "present",
    and payroll counted the day as nothing at all despite the person having
    worked it.

    Deliberately records zero hours rather than assuming a working day. The
    length of that shift is not knowable from here, and a guessed number in
    payroll is worse than a visible gap - it is wrong, and it looks right.
    The row is marked needs_review instead, which is what puts it in front of
    HR and what the employee can raise a correction against.

    Yesterday and earlier only. A shift opened today is somebody still at
    work, not an abandoned one.
    """
    cutoff = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    stale = db.query(models.DBAttendance).filter(
        models.DBAttendance.clock_in != "",
        models.DBAttendance.clock_out == "",
        models.DBAttendance.date <= cutoff,
        models.DBAttendance.status != "needs_review",
    ).all()

    for att in stale:
        att.clock_out = ""            # still unknown; we are not inventing one
        att.total_hours = 0.0
        att.status = "needs_review"
        note = f"Auto-closed on {now.strftime('%Y-%m-%d')}: no clock-out recorded."
        att.notes = f"{att.notes} {note}".strip() if att.notes else note

    if stale:
        db.commit()
    return f"closed {len(stale)}"


@scheduled_job("interview_reminders")
def job_interview_reminders(db, now):
    """Remind both sides about an interview happening tomorrow.

    An interview was booked and then nothing happened until it either did or
    did not. Candidates no-show when nobody reminds them, and an interviewer
    who has forgotten is worse than one who cancels.
    """
    horizon = now + timedelta(hours=INTERVIEW_REMINDER_HOURS)
    sent = 0

    rows = db.query(models.DBInterview, models.DBFormSubmission).join(
        models.DBFormSubmission,
        models.DBInterview.submission_id == models.DBFormSubmission.id,
    ).filter(
        models.DBInterview.status == "scheduled",
        models.DBInterview.scheduled_at != "",
    ).all()

    for iv, sub in rows:
        try:
            when = datetime.strptime(iv.scheduled_at[:16], "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            continue
        # Only the ones inside the window, and never one already in the past.
        if not (now <= when <= horizon):
            continue

        client = db.query(models.DBClient).filter(
            models.DBClient.id == iv.client_id).first()
        company = (client.company_name if client else "") or "the team"
        from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
        where = iv.meeting_link or iv.location or (
            "a video call" if iv.mode == "video" else iv.mode)

        recipients = []
        if sub.candidate_email and validate_email_address(sub.candidate_email):
            recipients.append(("candidate", sub.candidate_email,
                               sub.candidate_name or "there"))
        if iv.interviewer_id:
            interviewer = db.query(models.DBEmployee).filter(
                models.DBEmployee.id == iv.interviewer_id).first()
            if interviewer and interviewer.email and validate_email_address(interviewer.email):
                recipients.append(("interviewer", interviewer.email,
                                   interviewer.first_name or "there"))

        for who, address, name in recipients:
            # Written before sending, and the unique index means two workers
            # racing cannot both send the same nudge.
            db.add(models.DBInterviewReminder(
                client_id=iv.client_id, interview_id=iv.id,
                recipient=who, sent_to=address))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                continue

            subject = "Reminder: {} on {}".format(iv.round_name, iv.scheduled_at[:16])
            if who == "candidate":
                body = (
                    "Hello {},\n\nA reminder that your {} with {} is on {}.\n\n"
                    "Where: {}\nLasting about {} minutes.\n\n"
                    "If you can no longer make it, reply to this email and we "
                    "will rearrange.\n\nGood luck,\n{}\n"
                ).format(name, iv.round_name, company, iv.scheduled_at[:16],
                         where, iv.duration_minutes, company)
            else:
                body = (
                    "Hello {},\n\nYou are interviewing {} ({}) on {}.\n\n"
                    "Where: {}\nLasting about {} minutes.\n\n{}\n"
                ).format(name, sub.candidate_name or "a candidate", iv.round_name,
                         iv.scheduled_at[:16], where, iv.duration_minutes, company)

            html = (
                '<!DOCTYPE html><html><body style="font-family:Arial,Helvetica,sans-serif;'
                'background:#f1f5f9;margin:0;"><div style="max-width:520px;margin:0 auto;'
                'padding:40px 20px;"><div style="background:#fff;border-radius:12px;'
                'overflow:hidden;"><div style="background:#0f172a;padding:28px;'
                'text-align:center;"><div style="font-size:12px;letter-spacing:2px;'
                'text-transform:uppercase;color:#94a3b8;">Interview reminder</div>'
                '<div style="font-size:22px;font-weight:800;color:#fff;margin-top:6px;">'
                + esc(iv.round_name) + '</div></div><div style="padding:26px;">'
                '<p style="margin:0 0 16px;font-size:15px;">Hello ' + esc(name) + ',</p>'
                '<p style="margin:0 0 18px;font-size:15px;color:#475569;">'
                'This is a reminder about the ' + esc(iv.round_name) + ' on <strong>'
                + esc(iv.scheduled_at[:16]) + '</strong>, lasting about '
                + str(iv.duration_minutes) + ' minutes.</p>'
                '<p style="margin:0;font-size:14px;"><strong>Where:</strong> '
                + esc(where) + '</p></div>'
                '<div style="background:#f8fafc;padding:18px;text-align:center;'
                'border-top:1px solid #e2e8f0;"><div style="font-size:13px;'
                'font-weight:700;color:#0f172a;">' + esc(company) + '</div></div>'
                '</div></div></body></html>'
            )

            send_email_background(address, subject, body,
                                  "{} <{}>".format(company, from_email),
                                  html, None, "", "", client_id=iv.client_id)
            sent += 1

    return "{} interview reminder(s) sent".format(sent)


@app.get("/api/recruitment/interviews/{interview_id}/reminders")
def interview_reminders(interview_id: int, request: Request,
                        db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    iv = db.query(models.DBInterview).filter(
        models.DBInterview.id == interview_id,
        models.DBInterview.client_id == client.id,
    ).first()
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    rows = db.query(models.DBInterviewReminder).filter(
        models.DBInterviewReminder.interview_id == iv.id).all()
    return [{"recipient": r.recipient, "sent_to": r.sent_to, "sent_at": r.sent_at}
            for r in rows]


@app.get("/api/invoices/{number}/reminders")
def invoice_reminders(number: str, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    inv = db.query(models.DBInvoice).filter(
        models.DBInvoice.number == number, models.DBInvoice.client_id == client.id
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    rows = db.query(models.DBInvoiceReminder).filter(
        models.DBInvoiceReminder.invoice_id == inv.id
    ).order_by(models.DBInvoiceReminder.stage_days.asc()).all()
    return [{"stage_days": r.stage_days, "sent_to": r.sent_to, "sent_at": r.sent_at}
            for r in rows]


# ============================================================================
# PASSWORD RESET - the way back in for a locked-out account owner
# ============================================================================

RESET_TOKEN_TTL_MINUTES = 60


def validate_password_strength(password: str):
    """One rule, shared by registering and resetting, so the two cannot drift."""
    if len(password or "") < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one uppercase letter and one number",
        )


def hash_reset_token(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def find_valid_reset(db, token: str):
    """The reset a token refers to, or None if it is unknown, spent or expired."""
    if not token:
        return None
    row = db.query(models.DBPasswordReset).filter(
        models.DBPasswordReset.token_hash == hash_reset_token(token)
    ).first()
    if not row or row.used_at:
        return None
    try:
        expires = datetime.strptime(row.expires_at, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None
    if expires < datetime.now():
        return None
    return row


def issue_reset_token(db, user_type, subject_id, ip=""):
    """Start a new link and spend any earlier one, so a forwarded old email
    stops working the moment a fresh link is asked for."""
    q = db.query(models.DBPasswordReset).filter(
        models.DBPasswordReset.user_type == user_type,
        models.DBPasswordReset.used_at == "",
    )
    column = {"client": models.DBPasswordReset.client_id,
              "employee": models.DBPasswordReset.employee_id,
              "member": models.DBPasswordReset.member_id}[user_type]
    q = q.filter(column == subject_id)
    q.update({"used_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
             synchronize_session=False)

    token = secrets.token_urlsafe(32)
    row = models.DBPasswordReset(
        user_type=user_type,
        token_hash=hash_reset_token(token),
        expires_at=(datetime.now() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
        requested_ip=ip,
    )
    setattr(row, {"client": "client_id", "employee": "employee_id",
                  "member": "member_id"}[user_type], subject_id)
    db.add(row)
    return token


def reset_email_bodies(link, who, minutes):
    """The same wording for both, so there is one thing to keep right."""
    text_body = (
        f"Hello,\n\nSomeone asked to reset the password for {who} on aniprotech.\n\n"
        f"Open this link to choose a new one:\n{link}\n\n"
        f"The link works once and expires in {minutes} minutes.\n"
        "If this was not you, ignore this email - your password has not changed.\n"
    )
    html_body = f"""
    <!DOCTYPE html>
    <html><body style="font-family:Arial,Helvetica,sans-serif;background:#f1f5f9;margin:0;padding:0;">
      <div style="max-width:520px;margin:0 auto;padding:40px 20px;">
        <div style="background:#fff;border-radius:12px;overflow:hidden;">
          <div style="background:#0f172a;padding:32px;text-align:center;">
            <div style="font-size:13px;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;">aniprotech</div>
            <div style="font-size:22px;font-weight:800;color:#fff;margin-top:6px;">Reset your password</div>
          </div>
          <div style="padding:28px;">
            <p style="font-size:15px;margin:0 0 18px;">
              Someone asked to reset the password for <strong>{esc(who)}</strong>.
            </p>
            <p style="margin:0 0 24px;">
              <a href="{esc(link)}" style="display:inline-block;background:#0f172a;color:#fff;text-decoration:none;padding:12px 22px;border-radius:8px;font-weight:700;">Choose a new password</a>
            </p>
            <p style="font-size:13px;color:#64748b;margin:0 0 8px;">
              The link works once and expires in {minutes} minutes.
            </p>
            <p style="font-size:13px;color:#64748b;margin:0;">
              If this was not you, ignore this email. Your password has not changed.
            </p>
          </div>
        </div>
      </div>
    </body></html>
    """
    return text_body, html_body


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    password: str


@app.post("/api/client/forgot-password")
def forgot_password(body: ForgotPasswordIn, background_tasks: BackgroundTasks,
                    request: Request, db: Session = Depends(get_db)):
    """Send a reset link.

    The reply is the same whether or not the address has an account. Saying
    "no such account" would turn this into a way to find out who banks here.
    """
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"forgot:{ip}", max_requests=5, window=300):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")

    generic = {"message": "If that email has an account, a reset link is on its way."}
    email = (body.email or "").strip().lower()
    if not email:
        return generic

    client = db.query(models.DBClient).filter(
        sqlfunc.lower(models.DBClient.email) == email).first()
    if not client or not client.is_active:
        return generic

    token = issue_reset_token(db, "client", client.id, ip)
    log_login(db, client.id, client.email, "client", "password_reset_requested",
              request, "requested")
    db.commit()

    base = (os.getenv("APP_BASE_URL") or str(request.base_url)).rstrip("/")
    link = f"{base}/reset-password.html?token={token}"
    company = client.company_name or "your account"
    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")

    text_body, html_body = reset_email_bodies(link, company, RESET_TOKEN_TTL_MINUTES)

    background_tasks.add_task(
        send_email_background, client.email, "Reset your aniprotech password",
        text_body, f"aniprotech <{from_email}>", html_body, None, "", "",
        client_id=client.id,
    )
    return generic


@app.get("/api/client/reset-password")
def check_reset_token(token: str = "", db: Session = Depends(get_db)):
    """So the page can say the link is dead before someone types a new password."""
    return {"valid": find_valid_reset(db, token) is not None}


@app.post("/api/client/reset-password")
def reset_password(body: ResetPasswordIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"reset:{ip}", max_requests=10, window=300):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")

    row = find_valid_reset(db, body.token)
    if not row:
        raise HTTPException(status_code=400, detail="That reset link is invalid or has expired")
    validate_password_strength(body.password)

    if row.user_type == "member":
        subject = db.query(models.DBTeamMember).filter(
            models.DBTeamMember.id == row.member_id).first()
        if not subject or not subject.is_active:
            raise HTTPException(status_code=400,
                                detail="That link is invalid or has expired")
        subject.password_hash = hash_password(body.password)
        # Setting a password is how an invite is accepted.
        if not subject.accepted_at:
            subject.accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        client_id, who = subject.client_id, subject.email
    elif row.user_type == "employee":
        subject = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == row.employee_id).first()
        if not subject or subject.status == "terminated":
            raise HTTPException(status_code=400,
                                detail="That reset link is invalid or has expired")
        subject.password_hash = models.hash_password(body.password)
        client_id, who = subject.client_id, subject.email
    else:
        subject = db.query(models.DBClient).filter(
            models.DBClient.id == row.client_id).first()
        if not subject:
            raise HTTPException(status_code=400,
                                detail="That reset link is invalid or has expired")
        subject.password_hash = hash_password(body.password)
        client_id, who = subject.id, subject.email

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row.used_at = now
    # Spend every other outstanding link for the same account as well.
    spent = db.query(models.DBPasswordReset).filter(
        models.DBPasswordReset.user_type == row.user_type,
        models.DBPasswordReset.used_at == "",
    )
    spent_column, spent_value = {
        "client": (models.DBPasswordReset.client_id, row.client_id),
        "employee": (models.DBPasswordReset.employee_id, row.employee_id),
        "member": (models.DBPasswordReset.member_id, row.member_id),
    }[row.user_type]
    spent = spent.filter(spent_column == spent_value)
    spent.update({"used_at": now}, synchronize_session=False)

    log_login(db, client_id, who, row.user_type, "password_reset", request, "success")
    log_audit(db, client_id, "password_reset", row.user_type,
              row.employee_id or row.client_id, who, "", request)
    db.commit()
    return {"message": "Password updated. You can sign in now."}


@app.post("/api/employee/forgot-password")
def employee_forgot_password(body: ForgotPasswordIn, background_tasks: BackgroundTasks,
                             request: Request, db: Session = Depends(get_db)):
    """Staff sign in with a password, so they are the ones who get locked out.
    Until now the only way back was to ask HR to set a new one by hand."""
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"emp_forgot:{ip}", max_requests=5, window=300):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")

    generic = {"message": "If that email has an account, a reset link is on its way."}
    email = (body.email or "").strip().lower()
    if not email:
        return generic

    emp = db.query(models.DBEmployee).filter(models.DBEmployee.email.ilike(email)).first()
    # Someone with no password set has never signed in; there is nothing to reset.
    if not emp or not emp.password_hash or emp.status == "terminated":
        return generic

    token = issue_reset_token(db, "employee", emp.id, ip)
    db.commit()

    base = (os.getenv("APP_BASE_URL") or str(request.base_url)).rstrip("/")
    link = f"{base}/reset-password.html?token={token}&portal=employee"
    who = f"{emp.first_name} {emp.last_name}".strip() or emp.email
    text_body, html_body = reset_email_bodies(link, who, RESET_TOKEN_TTL_MINUTES)
    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")

    background_tasks.add_task(
        send_email_background, emp.email, "Reset your aniprotech password",
        text_body, f"aniprotech <{from_email}>", html_body, None, "", "",
        client_id=emp.client_id,
    )
    return generic


# ============================================================================
# TEAM - more than one person per business
# ============================================================================

# owner  - everything, and the only role that can manage the team
# admin  - everything else, including billing and the wallet
# viewer - read-only
TEAM_ROLES = ("owner", "admin", "viewer")

def current_member(request: Request, db: Session):
    """The signed-in team member, or None when it is the account owner."""
    member_id = request.session.get("member_id")
    if not member_id:
        return None
    return db.query(models.DBTeamMember).filter(
        models.DBTeamMember.id == member_id).first()


def current_role(request: Request, db: Session) -> str:
    member = current_member(request, db)
    return (member.role if member else "owner")


def require_owner(request: Request, db: Session):
    if current_role(request, db) != "owner":
        raise HTTPException(status_code=403,
                            detail="Only the account owner can do that")


def member_to_dict(m, is_owner=False):
    return {
        "id": m.id if m else 0,
        "email": m.email if m else "",
        "name": (m.name if m else "") or "",
        "role": "owner" if is_owner else (m.role if m else "admin"),
        "is_active": bool(m.is_active) if m else True,
        "accepted": bool(m.accepted_at) if m else True,
        "last_login": (m.last_login if m else "") or "",
        "is_account_owner": is_owner,
    }


class TeamInvite(BaseModel):
    email: str
    name: Optional[str] = ""
    role: Optional[str] = "admin"


class TeamUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    name: Optional[str] = None


@app.get("/api/team")
def list_team(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    rows = db.query(models.DBTeamMember).filter(
        models.DBTeamMember.client_id == client.id
    ).order_by(models.DBTeamMember.id.asc()).all()

    # The owner is on DBClient, not in this table, but they are a person on the
    # team and leaving them out of the list would be confusing.
    owner = {
        "id": 0, "email": client.email, "name": client.contact_name or "",
        "role": "owner", "is_active": bool(client.is_active), "accepted": True,
        "last_login": client.last_login or "", "is_account_owner": True,
    }
    return {"members": [owner] + [member_to_dict(m) for m in rows],
            "your_role": current_role(request, db)}


@app.post("/api/team/invite")
def invite_member(body: TeamInvite, background_tasks: BackgroundTasks,
                  request: Request, db: Session = Depends(get_db)):
    """Add a colleague and email them a link to set their own password.

    Reuses the password-reset machinery rather than inventing a second kind of
    token, so an invite is single-use and expires like any other link, and no
    password ever travels by email.
    """
    client = get_client_user(request, db)
    require_owner(request, db)

    email = (body.email or "").strip().lower()
    if not email or not validate_email_address(email):
        raise HTTPException(status_code=400, detail="A valid email address is required")
    role = (body.role or "admin").strip().lower()
    if role not in ("admin", "viewer"):
        raise HTTPException(status_code=400,
                            detail="Role must be admin or viewer. There is one owner.")
    if email == (client.email or "").lower():
        raise HTTPException(status_code=400, detail="That is the account owner's address")
    if db.query(models.DBTeamMember).filter(
        models.DBTeamMember.client_id == client.id,
        sqlfunc.lower(models.DBTeamMember.email) == email,
    ).first():
        raise HTTPException(status_code=400, detail="They are already on the team")

    member = models.DBTeamMember(
        client_id=client.id, email=email, name=(body.name or "").strip(), role=role)
    db.add(member)
    db.flush()

    token = issue_reset_token(db, "member", member.id, request.client.host if request.client else "")
    log_audit(db, client.id, "team_invited", "team", member.id, email, role, request)
    db.commit()

    base = (os.getenv("APP_BASE_URL") or str(request.base_url)).rstrip("/")
    link = f"{base}/reset-password.html?token={token}&portal=team"
    who = client.company_name or "the team"
    text_body, html_body = reset_email_bodies(link, who, RESET_TOKEN_TTL_MINUTES)
    text_body = text_body.replace("Someone asked to reset the password for",
                                  "You have been invited to")
    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
    background_tasks.add_task(
        send_email_background, email, f"You have been added to {who} on aniprotech",
        text_body, f"aniprotech <{from_email}>", html_body, None, "", "",
        client_id=client.id)

    return member_to_dict(member)


@app.put("/api/team/{member_id}")
def update_member(member_id: int, body: TeamUpdate, request: Request,
                  db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    require_owner(request, db)
    member = db.query(models.DBTeamMember).filter(
        models.DBTeamMember.id == member_id,
        models.DBTeamMember.client_id == client.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    if body.role is not None:
        role = body.role.strip().lower()
        if role not in ("admin", "viewer"):
            raise HTTPException(status_code=400, detail="Role must be admin or viewer")
        member.role = role
    if body.is_active is not None:
        member.is_active = bool(body.is_active)
    if body.name is not None:
        member.name = body.name.strip()

    log_audit(db, client.id, "team_updated", "team", member.id, member.email,
              member.role, request)
    db.commit()
    db.refresh(member)
    return member_to_dict(member)


@app.delete("/api/team/{member_id}")
def remove_member(member_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    require_owner(request, db)
    member = db.query(models.DBTeamMember).filter(
        models.DBTeamMember.id == member_id,
        models.DBTeamMember.client_id == client.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    # Any outstanding invite or reset link for them dies with the account.
    db.query(models.DBPasswordReset).filter(
        models.DBPasswordReset.member_id == member.id,
        models.DBPasswordReset.used_at == "",
    ).update({"used_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
             synchronize_session=False)

    log_audit(db, client.id, "team_removed", "team", member.id, member.email, "", request)
    db.delete(member)
    db.commit()
    return {"message": "Removed from the team"}


# ============================================================================
# CUSTOMER DETAIL - everything about one customer in one place
# ============================================================================

@app.get("/api/contacts/{contact_id}/detail")
def customer_detail(contact_id: int, request: Request, db: Session = Depends(get_db)):
    """One customer's whole history: what they were quoted, what they were
    invoiced, what they have paid and what they still owe.

    Invoices and quotes reference a customer by the name written on them, not
    by a foreign key, so they are gathered by name. Matching is case-insensitive
    because "Bramley Works" and "bramley works" are the same company.
    """
    client = get_client_user(request, db)
    contact = db.query(models.DBContact).filter(
        models.DBContact.id == contact_id,
        models.DBContact.client_id == client.id,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Customer not found")

    name = (contact.name or "").strip().lower()
    today = datetime.now().date()

    invoices = [i for i in db.query(models.DBInvoice).filter(
        models.DBInvoice.client_id == client.id
    ).order_by(models.DBInvoice.id.desc()).all()
        if (i.to_contact or "").strip().lower() == name]

    quotes = [q for q in db.query(models.DBQuote).filter(
        models.DBQuote.client_id == client.id
    ).order_by(models.DBQuote.id.desc()).all()
        if (q.to_contact or "").strip().lower() == name]

    payments = []
    if invoices:
        by_id = {i.id: i for i in invoices}
        payments = [{
            "invoice_number": by_id[p.invoice_id].number,
            "amount": p.amount, "paid_on": p.paid_on,
            "method": p.method, "reference": p.reference or "",
        } for p in db.query(models.DBPayment).filter(
            models.DBPayment.invoice_id.in_(list(by_id))
        ).order_by(models.DBPayment.id.desc()).all()]

    open_invoices = [i for i in invoices if i.status in OPEN_INVOICE_STATUSES]
    overdue = [i for i in open_invoices if invoice_overdue_days(i, today) > 0]

    def totals(rows, amount):
        return totals_by_currency(
            [{"currency": r.currency, "total": amount(r)} for r in rows],
            fallback=client.currency or "GBP")

    return {
        "contact": {
            "id": contact.id, "name": contact.name or "",
            "email": contact.email or "", "phone_number": contact.phone_number or "",
        },
        "summary": {
            "invoice_count": len(invoices),
            "quote_count": len(quotes),
            "overdue_count": len(overdue),
            # Per currency, because a customer billed in two currencies has two
            # balances, not one meaningless sum.
            "billed": totals(invoices, lambda i: (i.paid or 0) + (i.due or 0)),
            "paid": totals(invoices, lambda i: i.paid or 0),
            "outstanding": totals(open_invoices, lambda i: i.due or 0),
        },
        "invoices": [{
            "number": i.number, "date": i.issue_date, "due_date": i.due_date,
            "status": i.status, "paid": i.paid or 0, "due": i.due or 0,
            "currency": i.currency or (client.currency or ""),
            "is_overdue": invoice_overdue_days(i, today) > 0,
            "days_overdue": invoice_overdue_days(i, today),
        } for i in invoices],
        "quotes": [{
            "number": q.number, "date": q.issue_date, "expiry_date": q.expiry_date,
            "status": quote_display_status(q), "title": q.title or "",
            "total": compute_invoice_totals(q.line_items, q.tax_type)[2],
            "currency": q.currency or (client.currency or ""),
            "invoice_number": q.invoice_number or "",
        } for q in quotes],
        "payments": payments,
    }


# ============================================================================
# SEARCH - one box that actually finds things
# ============================================================================

def _hit(kind, label, sub="", number="", record_id=None):
    return {"type": kind, "label": label, "sub": sub,
            "number": number, "id": record_id}


@app.get("/api/search")
def global_search(request: Request, q: str = "", limit: int = 8,
                  db: Session = Depends(get_db)):
    """Search everything the tenant owns, on the server.

    The old search ran in the browser over whatever lists happened to be
    loaded, so employees were unfindable until you had opened the Employees
    tab, and quotes and recurring invoices were never searched at all. It also
    matched invoices on fields the API does not return, which meant customer
    names never matched anything.
    """
    client = get_client_user(request, db)
    term = (q or "").strip()
    if len(term) < 2:
        return {"query": term, "results": []}

    like = f"%{term.lower()}%"
    cap = max(1, min(limit, 25))
    results = []

    def matches(*fields):
        return or_(*[sqlfunc.lower(sqlfunc.coalesce(f, "")).like(like) for f in fields])

    for inv in db.query(models.DBInvoice).filter(
        models.DBInvoice.client_id == client.id,
        matches(models.DBInvoice.number, models.DBInvoice.to_contact,
                models.DBInvoice.email, models.DBInvoice.ref, models.DBInvoice.status),
    ).order_by(models.DBInvoice.id.desc()).limit(cap).all():
        results.append(_hit("invoice", f"{inv.number} - {inv.to_contact or 'No customer'}",
                            f"{inv.status or ''}", inv.number, inv.id))

    for q_row in db.query(models.DBQuote).filter(
        models.DBQuote.client_id == client.id,
        matches(models.DBQuote.number, models.DBQuote.to_contact,
                models.DBQuote.email, models.DBQuote.title, models.DBQuote.ref),
    ).order_by(models.DBQuote.id.desc()).limit(cap).all():
        results.append(_hit("quote", f"{q_row.number} - {q_row.to_contact or 'No customer'}",
                            q_row.title or quote_display_status(q_row), q_row.number, q_row.id))

    for c in db.query(models.DBContact).filter(
        models.DBContact.client_id == client.id,
        matches(models.DBContact.name, models.DBContact.email,
                models.DBContact.phone_number),
    ).limit(cap).all():
        results.append(_hit("contact", c.name or c.email or "Unknown",
                            c.email or c.phone_number or "", "", c.id))

    for e in db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        matches(models.DBEmployee.first_name, models.DBEmployee.last_name,
                models.DBEmployee.email, models.DBEmployee.job_title,
                models.DBEmployee.employee_id),
    ).limit(cap).all():
        results.append(_hit("employee", f"{e.first_name} {e.last_name}".strip(),
                            e.job_title or e.email or "", e.employee_id or "", e.id))

    for r in db.query(models.DBRecurringInvoice).filter(
        models.DBRecurringInvoice.client_id == client.id,
        matches(models.DBRecurringInvoice.name, models.DBRecurringInvoice.to_contact,
                models.DBRecurringInvoice.email),
    ).limit(cap).all():
        results.append(_hit("recurring", r.name or r.to_contact or "Recurring",
                            f"every {r.frequency}", "", r.id))

    # Payslips carry an employee_id, not a name, so the name is searched
    # through the employee record rather than a column that does not exist.
    for p, emp in db.query(models.DBPayslip, models.DBEmployee).join(
        models.DBEmployee, models.DBPayslip.employee_id == models.DBEmployee.id
    ).filter(
        models.DBPayslip.client_id == client.id,
        matches(models.DBPayslip.number, models.DBPayslip.status,
                models.DBEmployee.first_name, models.DBEmployee.last_name),
    ).order_by(models.DBPayslip.id.desc()).limit(cap).all():
        who = f"{emp.first_name} {emp.last_name}".strip() or "Unknown"
        results.append(_hit("payslip", f"{who} - {p.number or ''}",
                            p.status or "", p.number or "", p.id))

    return {"query": term, "results": results}


# ============================================================================
# SALES PIPELINE - quotes and invoices as one flow instead of two lists
# ============================================================================

def totals_by_currency(cards, field="total", fallback="GBP"):
    """Sum per currency and return the biggest first.

    Deliberately not one number: adding GBP to INR needs an exchange rate, and
    guessing one would put a made-up figure in front of somebody making
    decisions with it.
    """
    buckets = {}
    for c in cards:
        code = (c.get("currency") or fallback or "").upper() or fallback
        buckets[code] = buckets.get(code, 0) + (c.get(field) or 0)
    return [{"currency": code, "value": money(v)}
            for code, v in sorted(buckets.items(), key=lambda kv: -abs(kv[1]))]


SALES_STAGES = [
    ("drafted",  "Drafted",   "Not sent to anyone yet"),
    ("sent",     "Sent",      "Waiting on the customer"),
    ("accepted", "Accepted",  "Agreed, not yet invoiced"),
    ("invoiced", "Invoiced",  "Owed but not paid"),
    ("paid",     "Paid",      "Money in"),
]


def sales_stage_for_quote(q):
    """Where a quote sits. A quote that has become an invoice leaves the quote
    stages entirely - its invoice carries it from there."""
    status = quote_display_status(q)
    if status == "Invoiced":
        return None
    if status == "Accepted":
        return "accepted"
    if status in ("Declined", "Expired"):
        return None          # off the board; still counted as lost
    if status == "Sent":
        return "sent"
    return "drafted"


def sales_stage_for_invoice(inv):
    if (inv.status or "") == "Void":
        return None
    if (inv.due or 0) <= 0 and (inv.paid or 0) > 0:
        return "paid"
    if (inv.status or "") == "Draft":
        return "drafted"
    return "invoiced"


@app.get("/api/sales/pipeline")
def sales_pipeline(request: Request, db: Session = Depends(get_db)):
    """The money flow in one place, worked out from the documents themselves.

    Nothing is dragged between columns: send a quote, accept it, convert it,
    take the payment, and the card moves because the document moved.
    """
    client = get_client_user(request, db)
    today = datetime.now().date()

    buckets = {key: [] for key, _, _ in SALES_STAGES}
    lost = []

    for q in db.query(models.DBQuote).filter(
            models.DBQuote.client_id == client.id).all():
        stage = sales_stage_for_quote(q)
        _, _, total = compute_invoice_totals(q.line_items, q.tax_type)
        card = {
            "kind": "quote", "number": q.number, "to": q.to_contact or "",
            "title": q.title or "", "total": total,
            "currency": q.currency or (client.currency or ""),
            "date": q.issue_date or "", "due_or_expiry": q.expiry_date or "",
            "status": quote_display_status(q),
            "invoice_number": q.invoice_number or "",
        }
        if stage:
            buckets[stage].append(card)
        elif card["status"] in ("Declined", "Expired"):
            lost.append(card)

    for inv in db.query(models.DBInvoice).filter(
            models.DBInvoice.client_id == client.id).all():
        stage = sales_stage_for_invoice(inv)
        if not stage:
            continue
        overdue_days = invoice_overdue_days(inv, today)
        buckets[stage].append({
            "kind": "invoice", "number": inv.number, "to": inv.to_contact or "",
            "title": inv.ref or "", "total": money((inv.paid or 0) + (inv.due or 0)),
            "outstanding": inv.due or 0,
            "currency": inv.currency or (client.currency or ""),
            "date": inv.issue_date or "", "due_or_expiry": inv.due_date or "",
            "status": inv.status or "", "is_overdue": overdue_days > 0,
            "days_overdue": overdue_days,
        })

    for rows in buckets.values():
        # Overdue first, then biggest, because that is the order you act in.
        rows.sort(key=lambda c: (not c.get("is_overdue"), -(c.get("total") or 0)))

    base = client.currency or "GBP"
    open_stages = ("drafted", "sent", "accepted")
    open_cards = [c for k in open_stages for c in buckets[k]]

    return {
        "stages": [{
            "key": key, "label": label, "hint": hint,
            "count": len(buckets[key]),
            "totals": totals_by_currency(buckets[key], fallback=base),
            # The board can be long; the columns say how many are not shown.
            "cards": buckets[key][:40],
            "shown": min(len(buckets[key]), 40),
        } for key, label, hint in SALES_STAGES],
        "lost": {"count": len(lost),
                 "totals": totals_by_currency(lost, fallback=base)},
        "pipeline": {"count": len(open_cards),
                     "totals": totals_by_currency(open_cards, fallback=base)},
        "outstanding": totals_by_currency(
            buckets["invoiced"], field="outstanding", fallback=base),
        "overdue_count": sum(1 for c in buckets["invoiced"] if c.get("is_overdue")),
        "base_currency": base,
    }


# ============================================================================
# ONBOARDING PIPELINE - hiring through to a working employee
# ============================================================================

DEFAULT_ONBOARDING_ITEMS = [
    ("Sign employment contract", "Legal", "HR"),
    ("Provide government-issued ID", "Legal", "HR"),
    ("Submit bank details for payroll", "Finance", "Finance"),
    ("Provide emergency contact information", "General", "HR"),
    ("Company policy acknowledgment", "Compliance", "HR"),
    ("IT equipment setup", "Technical", "IT"),
    ("Email and system access setup", "Technical", "IT"),
    ("Introduction to team members", "Social", "Manager"),
    ("Complete tax withholding forms (W-4)", "Finance", "Finance"),
    ("Review employee handbook", "Compliance", "HR"),
]


def start_onboarding(db, client_id, emp):
    """Give a new starter their checklist and their document requests.

    Both ways in have to do this. Hiring from recruitment used to create the
    employee and stop, so anyone who came through the pipeline arrived with an
    empty checklist and nothing asked of them, while the same person added by
    hand got both.
    """
    existing = db.query(models.DBOnboardingItem).filter(
        models.DBOnboardingItem.employee_id == emp.id).count()
    if not existing:
        for title, category, assignee in DEFAULT_ONBOARDING_ITEMS:
            db.add(models.DBOnboardingItem(
                client_id=client_id, employee_id=emp.id,
                title=title, category=category, assigned_to=assignee,
            ))
    seed_default_requirements(db, client_id)
    assign_document_requests(db, client_id, emp)


def onboarding_snapshot(db, emp, today=None):
    """Where one person has got to, worked out from their actual records
    rather than a status column that has to be kept in step."""
    today = today or datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")

    items = db.query(models.DBOnboardingItem).filter(
        models.DBOnboardingItem.employee_id == emp.id).all()
    done_items = sum(1 for i in items if i.is_completed)
    overdue_items = sum(
        1 for i in items
        if not i.is_completed and i.due_date and i.due_date < today_str)

    reqs = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.employee_id == emp.id).all()
    mandatory = [r for r in reqs if r.is_mandatory]
    awaiting_employee = [r for r in mandatory if r.status in ("pending", "rejected")]
    awaiting_hr = [r for r in reqs if r.status == "submitted"]
    approved = [r for r in mandatory if r.status == "approved"]
    overdue_docs = [
        r for r in awaiting_employee if r.due_date and r.due_date < today_str]

    checklist_done = bool(items) and done_items == len(items)
    documents_done = not awaiting_employee and not awaiting_hr

    # Ordered by who is being waited on: the new starter, then HR, then the
    # internal setup nobody outside the company can see.
    if awaiting_employee:
        stage = "paperwork"
    elif awaiting_hr:
        stage = "review"
    elif not checklist_done:
        stage = "setup"
    else:
        stage = "ready"

    started = _parse_date(emp.start_date)
    return {
        "stage": stage,
        "items_total": len(items),
        "items_done": done_items,
        "items_overdue": overdue_items,
        "docs_total": len(mandatory),
        "docs_approved": len(approved),
        "awaiting_employee": [r.name for r in awaiting_employee],
        "awaiting_hr": [r.name for r in awaiting_hr],
        "docs_overdue": [r.name for r in overdue_docs],
        "checklist_done": checklist_done,
        "documents_done": documents_done,
        "days_since_start": (today - started).days if started else None,
        "is_blocked": bool(overdue_items or overdue_docs),
    }


def maybe_complete_onboarding(db, emp):
    """Turn a starter into a working employee once nothing is outstanding.

    Completion used to depend on the checklist alone, so somebody could be made
    active with a mandatory document still missing. Both halves now have to be
    finished, and this runs after a checklist change and after a document is
    reviewed, so whichever finishes last is the one that completes it.
    """
    if not emp or emp.status != "onboarding":
        return False
    snap = onboarding_snapshot(db, emp)
    if not (snap["checklist_done"] and snap["documents_done"]):
        return False
    emp.onboarding_complete = True
    emp.status = "active"
    return True


ONBOARDING_STAGES = [
    ("paperwork", "Documents requested", "Waiting on the new starter"),
    ("review", "In review", "Waiting on HR"),
    ("setup", "Setup", "Checklist still running"),
    ("ready", "Ready to start", "Nothing outstanding"),
]


@app.get("/api/onboarding/pipeline")
def onboarding_pipeline(request: Request, db: Session = Depends(get_db)):
    """Everyone still onboarding, grouped by what they are waiting on."""
    client = get_client_user(request, db)
    employees = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        models.DBEmployee.status == "onboarding",
    ).all()

    hired_from = {
        s.hired_employee_id: s for s in db.query(models.DBFormSubmission).filter(
            models.DBFormSubmission.client_id == client.id,
            models.DBFormSubmission.hired_employee_id.isnot(None),
        ).all()
    }

    buckets = {key: [] for key, _, _ in ONBOARDING_STAGES}
    for emp in employees:
        snap = onboarding_snapshot(db, emp)
        sub = hired_from.get(emp.id)
        card = {
            "employee_id": emp.id,
            "name": f"{emp.first_name} {emp.last_name}".strip(),
            "employee_number": emp.employee_id or "",
            "job_title": emp.job_title or "",
            "department": emp.department.name if emp.department else "",
            "start_date": emp.start_date or "",
            "email": emp.email or "",
        }
        card.update(snap)
        # Where they came from, so the hire and the onboarding are one story.
        card["hired_from"] = ({
            "submission_id": sub.id,
            "candidate_name": sub.candidate_name or "",
            "hired_at": sub.hired_at or "",
        } if sub else None)
        buckets[snap["stage"]].append(card)

    for rows in buckets.values():
        # Anything blocked first, then whoever has been waiting longest.
        rows.sort(key=lambda c: (not c["is_blocked"], -(c["days_since_start"] or 0)))

    return {
        "stages": [
            {"key": key, "label": label, "hint": hint,
             "count": len(buckets[key]), "cards": buckets[key]}
            for key, label, hint in ONBOARDING_STAGES
        ],
        "total": len(employees),
        "blocked": sum(1 for rows in buckets.values() for c in rows if c["is_blocked"]),
    }


@app.post("/api/employees/{emp_id}/complete-onboarding")
def complete_onboarding(emp_id: int, request: Request, db: Session = Depends(get_db)):
    """Mark a starter as a working employee.

    Refuses while something is still outstanding, and says what, rather than
    quietly activating someone whose paperwork is not in.
    """
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if emp.status != "onboarding":
        raise HTTPException(status_code=400, detail="This employee is not onboarding")

    snap = onboarding_snapshot(db, emp)
    blockers = []
    if snap["awaiting_employee"]:
        blockers.append("waiting on " + ", ".join(snap["awaiting_employee"]))
    if snap["awaiting_hr"]:
        blockers.append("still to review " + ", ".join(snap["awaiting_hr"]))
    if not snap["checklist_done"]:
        blockers.append(
            f"{snap['items_total'] - snap['items_done']} checklist item(s) left")
    if blockers:
        raise HTTPException(status_code=400, detail="Not finished: " + "; ".join(blockers))

    emp.onboarding_complete = True
    emp.status = "active"
    log_audit(db, client.id, "onboarding_completed", "employee", emp.id,
              f"{emp.first_name} {emp.last_name}".strip(), "", request)
    db.commit()
    return {"message": "Onboarding complete", "status": emp.status}


@app.post("/api/employees/{emp_id}/nudge")
def nudge_onboarding(emp_id: int, request: Request, db: Session = Depends(get_db)):
    """Remind a starter what is still outstanding, in their own portal."""
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    snap = onboarding_snapshot(db, emp)
    if not snap["awaiting_employee"]:
        raise HTTPException(status_code=400, detail="Nothing is waiting on this person")
    db.add(models.DBNotification(
        client_id=client.id, employee_id=emp.id, type="warning",
        title="Documents still needed",
        message="Please upload: " + ", ".join(snap["awaiting_employee"]),
    ))
    db.commit()
    return {"message": "Reminder sent", "items": snap["awaiting_employee"]}


# ============================================================================
# TAX RATES - the list a tenant picks from when writing a line
# ============================================================================

# What every new tenant starts with. Chosen to render exactly the labels the
# app used before rates became editable, so nothing shifts under existing work.
DEFAULT_TAX_RATES = [
    ("VAT", 20.0, True),
    ("VAT", 5.0, False),
    ("Zero Rated", 0.0, False),
    ("No Tax", 0.0, False),
]


def tax_rate_label(name, percent):
    """The string stored on a line item.

    The percentage is always in the label, because parse_tax_rate reads the
    rate back out of it. A label of just "Consulting levy" would parse as the
    default 20%, silently taxing a line nobody meant to tax. The one exception
    is the plain no-tax entries, whose wording parse_tax_rate already knows and
    which would otherwise read as the odd "0% No Tax".
    """
    name = (name or "").strip()
    if not name:
        return f"{percent:g}%"
    if percent == 0 and name.lower() in ("no tax", "none", "exempt"):
        return name
    return f"{percent:g}% {name}"


def validate_tax_rate(name, percent):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Every tax rate needs a name")
    if len(name) > 60:
        raise HTTPException(status_code=400, detail="Tax rate names must be 60 characters or fewer")
    try:
        pct = float(percent)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"'{name}' needs a numeric percentage")
    # Same bound as payroll: a rate above 100 produces a negative total.
    if pct < 0 or pct > 100:
        raise HTTPException(status_code=400,
                            detail=f"'{name}' must be between 0 and 100 percent")
    return name, round(pct, 4)


def seed_default_tax_rates(db, client_id):
    """Give a tenant the standard list the first time they look."""
    existing = db.query(models.DBTaxRate).filter(
        models.DBTaxRate.client_id == client_id).count()
    if existing:
        return
    for order, (name, percent, is_default) in enumerate(DEFAULT_TAX_RATES):
        db.add(models.DBTaxRate(client_id=client_id, name=name, percent=percent,
                                sort_order=order, is_default=is_default))
    db.commit()


def tax_rate_to_dict(t):
    return {
        "id": t.id,
        "name": t.name,
        "percent": t.percent or 0.0,
        "label": tax_rate_label(t.name, t.percent or 0.0),
        "is_default": bool(t.is_default),
        "sort_order": t.sort_order or 0,
    }


class TaxRateIn(BaseModel):
    name: str
    percent: float = 0.0
    is_default: Optional[bool] = False


class TaxRatesIn(BaseModel):
    tax_rates: List[TaxRateIn]


@app.get("/api/tax-rates")
def list_tax_rates(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    seed_default_tax_rates(db, client.id)
    rows = db.query(models.DBTaxRate).filter(
        models.DBTaxRate.client_id == client.id
    ).order_by(models.DBTaxRate.sort_order.asc(), models.DBTaxRate.id.asc()).all()
    return [tax_rate_to_dict(t) for t in rows]


@app.put("/api/tax-rates")
def replace_tax_rates(body: TaxRatesIn, request: Request, db: Session = Depends(get_db)):
    """Save the whole list at once, which is how the settings screen edits it.

    Validated in full before anything is written, so a bad row cannot leave the
    tenant with half a list.
    """
    client = get_client_user(request, db)
    if not body.tax_rates:
        raise HTTPException(status_code=400, detail="Keep at least one tax rate")
    if len(body.tax_rates) > 40:
        raise HTTPException(status_code=400, detail="That is more tax rates than the picker can hold (40 max)")

    cleaned = []
    seen = set()
    for row in body.tax_rates:
        name, pct = validate_tax_rate(row.name, row.percent)
        label = tax_rate_label(name, pct)
        key = label.lower()
        if key in seen:
            raise HTTPException(status_code=400,
                                detail=f"'{label}' is in the list twice")
        seen.add(key)
        cleaned.append((name, pct, bool(row.is_default)))

    # Exactly one default, so the line editor always has something to preselect.
    if not any(d for _, _, d in cleaned):
        cleaned[0] = (cleaned[0][0], cleaned[0][1], True)
    else:
        first_default = next(i for i, (_, _, d) in enumerate(cleaned) if d)
        cleaned = [(n, p, i == first_default) for i, (n, p, _) in enumerate(cleaned)]

    db.query(models.DBTaxRate).filter(models.DBTaxRate.client_id == client.id).delete()
    for order, (name, pct, is_default) in enumerate(cleaned):
        db.add(models.DBTaxRate(client_id=client.id, name=name, percent=pct,
                                sort_order=order, is_default=is_default))
    log_audit(db, client.id, "tax_rates_updated", "settings", None, "Tax rates",
              f"{len(cleaned)} rates", request)
    db.commit()

    rows = db.query(models.DBTaxRate).filter(
        models.DBTaxRate.client_id == client.id
    ).order_by(models.DBTaxRate.sort_order.asc()).all()
    return [tax_rate_to_dict(t) for t in rows]




# ============================================================================
# BRANDING THEMES - how invoices and quotes are presented
#
# Presentation only: nothing here changes what is owed. A theme is stored once
# and applied at render time, so editing it restyles every past document too
# rather than leaving a trail of differently-shaped PDFs.
# ============================================================================

LOGO_POSITIONS = ("left", "center", "right")
TAX_BREAKDOWNS = ("combined", "separate_rates", "separate_components")
ADDRESS_POSITIONS = ("default", "window_envelope")
# jsPDF ships three core families. Offering a font the renderer does not have
# would silently fall back and quietly change every invoice.
THEME_FONTS = ("helvetica", "times", "courier")

THEME_BOOLS = (
    "show_item", "show_quantity", "show_price", "show_discount", "show_tax",
    "exclude_zero_rates", "always_show_currency_code", "show_conversion_rate",
    "show_text_links", "show_qr_code", "show_page_numbers",
)
THEME_STRINGS = (
    "label_item", "label_description", "label_quantity", "label_price",
    "label_discount", "label_tax", "label_amount",
    "approved_invoice_title", "draft_invoice_title", "quote_title",
    "payment_terms", "footer_note",
)


def valid_hex_colour(value: str, fallback: str = "#4F46E5") -> str:
    """Accept #rgb or #rrggbb only. This string is written straight into a PDF
    and into inline CSS in the preview, so it must never carry anything else."""
    v = (value or "").strip()
    if re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v):
        return v.lower()
    return fallback


def theme_to_dict(t) -> dict:
    out = {
        "id": t.id, "name": t.name, "is_default": bool(t.is_default),
        "logo_data": t.logo_data or "", "logo_position": t.logo_position or "right",
        "brand_color": t.brand_color or "#4F46E5", "font": t.font or "helvetica",
        "tax_breakdown": t.tax_breakdown or "separate_rates",
        "address_position": t.address_position or "default",
        "updated_at": t.updated_at or "",
    }
    for f in THEME_BOOLS:
        out[f] = bool(getattr(t, f))
    for f in THEME_STRINGS:
        out[f] = getattr(t, f) or ""
    return out


def apply_theme_fields(theme, body: dict):
    """Copy whatever the caller sent, ignoring anything it may not set.

    Deliberately a whitelist: a theme is rendered into a PDF and echoed into
    the preview, so an unexpected key must never reach either.
    """
    if "name" in body:
        name = (body.get("name") or "").strip()[:60]
        if not name:
            raise HTTPException(status_code=400, detail="A theme needs a name")
        theme.name = name
    if "logo_data" in body:
        logo = body.get("logo_data") or ""
        # Matched in full, not just by prefix. This string is written into an
        # <img src> and into a PDF, so a quote or an angle bracket smuggled in
        # after a valid-looking prefix must never be stored.
        if logo and not re.fullmatch(
                r"data:image/(png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+",
                logo):
            raise HTTPException(
                status_code=400,
                detail="The logo must be a base64 image (PNG, JPEG, GIF or WebP)")
        if len(logo) > 3_000_000:
            raise HTTPException(status_code=400,
                                detail="That logo is too large - keep it under about 2MB")
        theme.logo_data = logo
    if "logo_position" in body and body["logo_position"] in LOGO_POSITIONS:
        theme.logo_position = body["logo_position"]
    if "brand_color" in body:
        theme.brand_color = valid_hex_colour(body["brand_color"], theme.brand_color or "#4F46E5")
    if "font" in body and body["font"] in THEME_FONTS:
        theme.font = body["font"]
    if "tax_breakdown" in body and body["tax_breakdown"] in TAX_BREAKDOWNS:
        theme.tax_breakdown = body["tax_breakdown"]
    if "address_position" in body and body["address_position"] in ADDRESS_POSITIONS:
        theme.address_position = body["address_position"]
    for f in THEME_BOOLS:
        if f in body:
            setattr(theme, f, bool(body[f]))
    for f in THEME_STRINGS:
        if f in body:
            setattr(theme, f, str(body[f] or "")[:2000])
    theme.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_default_theme(db: Session, client_id: int):
    """Every account has at least one theme, so the PDF code never has to cope
    with there being none."""
    existing = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.client_id == client_id).count()
    if existing:
        return
    db.add(models.DBBrandingTheme(client_id=client_id, name="Standard", is_default=True))
    db.commit()


def default_theme_for(db: Session, client_id: int):
    ensure_default_theme(db, client_id)
    theme = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.client_id == client_id,
        models.DBBrandingTheme.is_default == True).first()  # noqa: E712
    if not theme:
        theme = db.query(models.DBBrandingTheme).filter(
            models.DBBrandingTheme.client_id == client_id
        ).order_by(models.DBBrandingTheme.id.asc()).first()
    return theme


@app.get("/api/branding-themes")
def list_branding_themes(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ensure_default_theme(db, client.id)
    rows = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.client_id == client.id
    ).order_by(models.DBBrandingTheme.is_default.desc(),
               models.DBBrandingTheme.name.asc()).all()
    return {"themes": [theme_to_dict(t) for t in rows],
            "fonts": list(THEME_FONTS)}


@app.get("/api/branding-themes/default")
def get_default_branding_theme(request: Request, db: Session = Depends(get_db)):
    """What the PDF renderer asks for. Always answers with a theme."""
    client = get_client_user(request, db)
    return theme_to_dict(default_theme_for(db, client.id))


@app.post("/api/branding-themes")
def create_branding_theme(request: Request, body: dict = None,
                          db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    body = body or {}
    ensure_default_theme(db, client.id)

    name = (body.get("name") or "").strip()[:60] or "New theme"
    clash = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.client_id == client.id,
        models.DBBrandingTheme.name == name).first()
    if clash:
        raise HTTPException(status_code=400,
                            detail=f"You already have a theme called '{name}'")

    theme = models.DBBrandingTheme(client_id=client.id, name=name)
    body = dict(body)
    body.pop("name", None)
    apply_theme_fields(theme, body)
    db.add(theme)
    db.commit()
    db.refresh(theme)
    log_audit(db, client.id, "branding_theme_created", "branding", theme.id,
              theme.name, "", request)
    db.commit()
    return theme_to_dict(theme)


@app.put("/api/branding-themes/{theme_id}")
def update_branding_theme(theme_id: int, request: Request, body: dict = None,
                          db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    theme = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.id == theme_id,
        models.DBBrandingTheme.client_id == client.id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    body = dict(body or {})
    new_name = (body.get("name") or "").strip()[:60]
    if new_name and new_name != theme.name:
        clash = db.query(models.DBBrandingTheme).filter(
            models.DBBrandingTheme.client_id == client.id,
            models.DBBrandingTheme.name == new_name,
            models.DBBrandingTheme.id != theme.id).first()
        if clash:
            raise HTTPException(status_code=400,
                                detail=f"You already have a theme called '{new_name}'")

    apply_theme_fields(theme, body)
    log_audit(db, client.id, "branding_theme_updated", "branding", theme.id,
              theme.name, "", request)
    db.commit()
    db.refresh(theme)
    return theme_to_dict(theme)


@app.post("/api/branding-themes/{theme_id}/default")
def set_default_branding_theme(theme_id: int, request: Request,
                               db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    theme = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.id == theme_id,
        models.DBBrandingTheme.client_id == client.id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.client_id == client.id
    ).update({models.DBBrandingTheme.is_default: False})
    theme.is_default = True
    db.commit()
    return theme_to_dict(theme)


@app.delete("/api/branding-themes/{theme_id}")
def delete_branding_theme(theme_id: int, request: Request,
                          db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    theme = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.id == theme_id,
        models.DBBrandingTheme.client_id == client.id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    remaining = db.query(models.DBBrandingTheme).filter(
        models.DBBrandingTheme.client_id == client.id).count()
    if remaining <= 1:
        raise HTTPException(status_code=400,
                            detail="This is your only theme, so it cannot be deleted")

    was_default = bool(theme.is_default)
    db.delete(theme)
    db.commit()
    if was_default:
        # Never leave an account with no default; the renderer relies on one.
        fallback = db.query(models.DBBrandingTheme).filter(
            models.DBBrandingTheme.client_id == client.id
        ).order_by(models.DBBrandingTheme.id.asc()).first()
        if fallback:
            fallback.is_default = True
            db.commit()
    return {"ok": True}


# ============================================================================
# QUOTES - priced proposals that can become invoices
# ============================================================================

class QuoteCreate(BaseModel):
    contact: str
    email: Optional[str] = ""
    phone_number: Optional[str] = ""
    issue_date: str
    expiry_date: str
    quote_number: Optional[str] = ""
    reference: Optional[str] = ""
    line_items: List[LineItem]
    tax_type: Optional[str] = "exclusive"
    status: Optional[str] = "Draft"
    currency: Optional[str] = ""
    title: Optional[str] = ""
    summary: Optional[str] = ""
    terms: Optional[str] = ""


class SendQuoteEmail(BaseModel):
    logo_data: Optional[str] = ""
    pdf_data: Optional[str] = ""


class QuoteDecision(BaseModel):
    status: str


class QuoteConvert(BaseModel):
    issue_date: Optional[str] = ""
    due_date: Optional[str] = ""


QUOTE_STATUSES = ("Draft", "Sent", "Accepted", "Declined", "Expired", "Invoiced")


def validate_quote_dates(issue_date, expiry_date):
    issue = _parse_date(issue_date)
    expiry = _parse_date(expiry_date)
    if issue_date and not issue:
        raise HTTPException(status_code=400, detail="Issue date must be in YYYY-MM-DD format")
    if expiry_date and not expiry:
        raise HTTPException(status_code=400, detail="Expiry date must be in YYYY-MM-DD format")
    if issue and expiry and expiry < issue:
        raise HTTPException(status_code=400, detail="Expiry date cannot be before the issue date")


def quote_is_expired(q, today=None):
    """A quote past its expiry that nobody has answered is dead.

    Derived rather than stored: a background job to flip the column would be
    one more thing to run, and the answer is a date comparison.
    """
    if q.status not in ("Sent", "Draft"):
        return False
    expiry = _parse_date(q.expiry_date)
    if not expiry:
        return False
    return expiry < (today or datetime.now().date())


def quote_display_status(q, today=None):
    return "Expired" if quote_is_expired(q, today) else q.status


def quote_to_dict(q, client, db, detail=False):
    subtotal, tax_total, grand_total = compute_invoice_totals(q.line_items, q.tax_type)
    data = {
        "id": q.id,
        "number": q.number,
        "ref": q.ref or "",
        "to": q.to_contact,
        "email": q.email or "",
        "phone_number": q.phone_number or "",
        "date": q.issue_date,
        "expiry_date": q.expiry_date,
        "title": q.title or "",
        "summary": q.summary or "",
        "terms": q.terms or "",
        "subtotal": subtotal,
        "tax_total": tax_total,
        "total": grand_total,
        "status": quote_display_status(q),
        "stored_status": q.status,
        "is_expired": quote_is_expired(q),
        "sent": q.sent or "",
        "tax_type": q.tax_type,
        "currency": q.currency or (client.currency if client else ""),
        "invoice_number": q.invoice_number or "",
        "decided_at": q.decided_at or "",
    }
    if not detail:
        return data

    settings_rows = db.query(models.DBSettings).filter(
        models.DBSettings.client_id == q.client_id).all() if q.client_id else []
    settings_map = {s.key: s.value for s in settings_rows}
    data["company"] = {
        "name": settings_map.get("company_name", "") or (client.company_name if client else ""),
        "email": settings_map.get("email", "") or (client.email if client else ""),
        "phone_number": settings_map.get("phone_number", "") or (client.phone_number if client else ""),
        "address": settings_map.get("company_address", "") or (client.address if client else ""),
        "website": settings_map.get("company_website", "") or (client.website if client else ""),
        "abn": settings_map.get("company_abn", "") or (client.abn if client else ""),
        "logo_url": client.logo_url if client else "",
    }
    data["line_items"] = [{
        "name": li.name or "",
        "description": li.description,
        "qty": li.qty,
        "price": li.price,
        "disc": li.disc,
        "account": li.account,
        "tax_rate": li.tax_rate,
        "tax_percent": round(parse_tax_rate(li.tax_rate) * 100, 4),
        "amount": money(line_net_amount(li.qty, li.price, li.disc)),
    } for li in q.line_items]
    return data


def get_quote_or_404(db, client, number):
    q = db.query(models.DBQuote).filter(
        models.DBQuote.number == number, models.DBQuote.client_id == client.id
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    return q


@app.get("/api/next-quote-number")
def get_next_quote_number(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    return {"next_number": next_sequence_number(db, models.DBQuote, client.id, "QU-")}


@app.get("/api/quotes")
def get_quotes(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    quotes = db.query(models.DBQuote).filter(
        models.DBQuote.client_id == client.id
    ).order_by(models.DBQuote.id.desc()).all()
    return [quote_to_dict(q, client, db) for q in quotes]


@app.get("/api/quotes/{number}")
def get_quote(number: str, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    return quote_to_dict(get_quote_or_404(db, client, number), client, db, detail=True)


@app.post("/api/quotes")
def create_quote(quote: QuoteCreate, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)

    validate_line_items(quote.line_items)
    validate_quote_dates(quote.issue_date, quote.expiry_date)

    subtotal, tax, total = compute_invoice_totals(quote.line_items, quote.tax_type)

    if quote.contact and quote.contact.strip():
        existing = db.query(models.DBContact).filter(
            models.DBContact.name == quote.contact, models.DBContact.client_id == client.id
        ).first()
        if existing:
            if quote.email and not existing.email:
                existing.email = quote.email
            if quote.phone_number and not existing.phone_number:
                existing.phone_number = quote.phone_number
        else:
            db.add(models.DBContact(
                name=quote.contact, email=quote.email or "",
                phone_number=quote.phone_number or "", client_id=client.id))

    if quote.quote_number and quote.quote_number.strip():
        number = quote.quote_number.strip()
    else:
        number = next_sequence_number(db, models.DBQuote, client.id, "QU-")

    clash = db.query(models.DBQuote).filter(
        models.DBQuote.client_id == client.id, models.DBQuote.number == number
    ).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"Quote number {number} already exists")

    status = quote.status if quote.status in QUOTE_STATUSES else "Draft"
    db_quote = models.DBQuote(
        client_id=client.id,
        number=number,
        ref=quote.reference or "",
        to_contact=quote.contact,
        email=quote.email or "",
        phone_number=quote.phone_number or "",
        issue_date=quote.issue_date,
        expiry_date=quote.expiry_date,
        total=round(total, 2),
        status=status,
        sent="",
        tax_type=quote.tax_type,
        currency=(quote.currency or "").upper() or (client.currency or ""),
        title=quote.title or "",
        summary=quote.summary or "",
        terms=quote.terms or "",
    )
    db.add(db_quote)
    db.flush()

    for item in quote.line_items:
        db.add(models.DBQuoteLineItem(
            quote_id=db_quote.id,
            name=item.name or "",
            description=item.description,
            qty=item.qty,
            price=item.price,
            disc=item.disc or 0.0,
            account=item.account,
            tax_rate=item.tax_rate,
        ))

    db.commit()
    db.refresh(db_quote)
    log_audit(db, client.id, "quote_created", "quote", db_quote.id, number,
              f"Total: {total:.2f}", request)
    db.commit()
    return quote_to_dict(db_quote, client, db, detail=True)


@app.put("/api/quotes/{number}")
def update_quote(number: str, quote: QuoteCreate, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    q = get_quote_or_404(db, client, number)
    if q.status == "Invoiced":
        raise HTTPException(status_code=400,
                            detail=f"Quote {number} has already been invoiced as {q.invoice_number}")

    validate_line_items(quote.line_items)
    validate_quote_dates(quote.issue_date, quote.expiry_date)
    subtotal, tax, total = compute_invoice_totals(quote.line_items, quote.tax_type)

    q.ref = quote.reference or ""
    q.to_contact = quote.contact
    q.email = quote.email or ""
    q.phone_number = quote.phone_number or ""
    q.issue_date = quote.issue_date
    q.expiry_date = quote.expiry_date
    q.tax_type = quote.tax_type
    q.currency = (quote.currency or "").upper() or q.currency
    q.title = quote.title or ""
    q.summary = quote.summary or ""
    q.terms = quote.terms or ""
    q.total = round(total, 2)
    if quote.status in QUOTE_STATUSES:
        q.status = quote.status

    db.query(models.DBQuoteLineItem).filter(models.DBQuoteLineItem.quote_id == q.id).delete()
    for item in quote.line_items:
        db.add(models.DBQuoteLineItem(
            quote_id=q.id,
            name=item.name or "",
            description=item.description,
            qty=item.qty,
            price=item.price,
            disc=item.disc or 0.0,
            account=item.account,
            tax_rate=item.tax_rate,
        ))

    log_audit(db, client.id, "quote_updated", "quote", q.id, q.number,
              f"Total: {total:.2f}", request)
    db.commit()
    db.refresh(q)
    return quote_to_dict(q, client, db, detail=True)


@app.delete("/api/quotes/{number}")
def delete_quote(number: str, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    q = get_quote_or_404(db, client, number)
    if q.status == "Invoiced":
        raise HTTPException(status_code=400,
                            detail=f"Quote {number} has been invoiced as {q.invoice_number} and cannot be deleted")
    db.query(models.DBQuoteLineItem).filter(models.DBQuoteLineItem.quote_id == q.id).delete()
    log_audit(db, client.id, "quote_deleted", "quote", q.id, q.number,
              f"Contact: {q.to_contact}", request)
    db.delete(q)
    db.commit()
    return {"message": "Quote deleted successfully"}


@app.post("/api/quotes/{number}/status")
def set_quote_status(number: str, body: QuoteDecision, request: Request, db: Session = Depends(get_db)):
    """Record the customer's answer."""
    client = get_client_user(request, db)
    q = get_quote_or_404(db, client, number)
    wanted = (body.status or "").strip().title()
    if wanted not in ("Accepted", "Declined", "Sent", "Draft"):
        raise HTTPException(status_code=400,
                            detail="Status must be one of: Draft, Sent, Accepted, Declined")
    if q.status == "Invoiced":
        raise HTTPException(status_code=400,
                            detail=f"Quote {number} has already been invoiced as {q.invoice_number}")
    q.status = wanted
    q.decided_at = (datetime.now().strftime("%Y-%m-%d")
                    if wanted in ("Accepted", "Declined") else "")
    log_audit(db, client.id, "quote_status_changed", "quote", q.id, q.number, wanted, request)
    db.commit()
    db.refresh(q)
    return quote_to_dict(q, client, db, detail=True)


@app.post("/api/quotes/{number}/convert")
def convert_quote_to_invoice(number: str, request: Request,
                             body: Optional[QuoteConvert] = None,
                             db: Session = Depends(get_db)):
    """Turn an accepted quote into an invoice, carrying the lines across.

    The quote is kept and marked Invoiced rather than replaced - it is the
    record of what was agreed, and the link runs both ways.
    """
    client = get_client_user(request, db)
    q = get_quote_or_404(db, client, number)
    if body is None:
        body = QuoteConvert()
    if q.status == "Invoiced":
        raise HTTPException(status_code=409,
                            detail=f"Quote {number} was already invoiced as {q.invoice_number}")
    if q.status == "Declined":
        raise HTTPException(status_code=400, detail="A declined quote cannot be invoiced")
    if not q.line_items:
        raise HTTPException(status_code=400, detail="Quote has no line items")

    issue_date = body.issue_date or datetime.now().strftime("%Y-%m-%d")
    if body.due_date:
        due_date = body.due_date
    else:
        base = _parse_date(issue_date) or datetime.now().date()
        due_date = (base + timedelta(days=14)).strftime("%Y-%m-%d")
    validate_invoice_dates(issue_date, due_date)

    subtotal, tax, total = compute_invoice_totals(q.line_items, q.tax_type)
    inv_number = next_sequence_number(db, models.DBInvoice, client.id, invoice_prefix_for(db, client.id))

    invoice = models.DBInvoice(
        client_id=client.id,
        number=inv_number,
        ref=q.ref or q.number,
        to_contact=q.to_contact,
        email=q.email or "",
        phone_number=q.phone_number or "",
        issue_date=issue_date,
        due_date=due_date,
        paid=0.00,
        due=round(total, 2),
        status="Draft",
        sent="",
        tax_type=q.tax_type,
        currency=q.currency or (client.currency or ""),
        bank_details="",
    )
    db.add(invoice)
    db.flush()

    for li in q.line_items:
        db.add(models.DBLineItem(
            invoice_id=invoice.id,
            name=li.name or "",
            description=li.description,
            qty=li.qty,
            price=li.price,
            disc=li.disc or 0.0,
            account=li.account,
            tax_rate=li.tax_rate,
        ))

    q.status = "Invoiced"
    q.invoice_number = inv_number
    log_audit(db, client.id, "quote_converted", "quote", q.id, q.number,
              f"Invoice {inv_number}", request)
    db.commit()
    return {"message": "Quote converted to invoice",
            "invoice_number": inv_number, "quote_number": q.number}


@app.post("/api/quotes/{number}/send")
def send_quote_email(number: str, background_tasks: BackgroundTasks, request: Request,
                     payload: Optional[SendQuoteEmail] = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if payload is None:
        payload = SendQuoteEmail()
    q = get_quote_or_404(db, client, number)
    if not q.email:
        raise HTTPException(status_code=400, detail="Quote has no email address associated with it")
    if not validate_email_address(q.email):
        raise HTTPException(status_code=400, detail=f"Invalid email address: {q.email}")

    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
    if not from_email:
        raise HTTPException(status_code=400, detail="No sender email configured.")

    settings_rows = db.query(models.DBSettings).filter(
        models.DBSettings.client_id == q.client_id).all()
    settings_map = {s.key: s.value for s in settings_rows}
    q_client = db.query(models.DBClient).filter(
        models.DBClient.id == q.client_id).first() if q.client_id else None
    company_name = (settings_map.get("company_name", "")
                    or (q_client.company_name if q_client else "") or "Accounting Platform")
    company_email = settings_map.get("email", "") or (q_client.email if q_client else "")
    company_phone = settings_map.get("phone_number", "") or (q_client.phone_number if q_client else "")
    company_address = settings_map.get("company_address", "") or (q_client.address if q_client else "")

    cur = (q.currency or settings_map.get("currency")
           or (q_client.currency if q_client else "") or "GBP").upper()
    cur_symbol = currency_symbol(cur)

    logo_data = payload.logo_data or ""
    if not logo_data and q_client and q_client.logo_url:
        logo_data = q_client.logo_url
    logo_html = (f'<div style="margin-bottom:24px;"><img src="{esc(logo_data)}" '
                 f'style="max-height:48px;max-width:200px;"></div>') if logo_data else ""

    subtotal, tax_total, total = compute_invoice_totals(q.line_items, q.tax_type)

    rows = ""
    for li in q.line_items:
        amount = line_net_amount(li.qty, li.price, li.disc)
        disc_val = li.disc or 0
        rows += f"""
            <div style="padding:16px 20px;border-bottom:1px solid #f1f5f9;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                <div style="font-size:15px;font-weight:700;color:#1e293b;">{esc(li.name) or 'Item'}</div>
                <div style="font-size:16px;font-weight:800;color:#0f172a;">{cur_symbol}{amount:.2f}</div>
              </div>
              {f'<div style="font-size:13px;color:#64748b;margin-bottom:8px;word-wrap:break-word;">{esc(li.description)}</div>' if li.description else ''}
              <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;">
                <span style="font-size:12px;color:#94a3b8;">Qty: <strong style="color:#475569;">{li.qty:g}</strong></span>
                <span style="font-size:12px;color:#94a3b8;">Price: <strong style="color:#475569;">{cur_symbol}{li.price:.2f}</strong></span>
                {f'<span style="font-size:12px;color:#94a3b8;">Discount: {disc_val:g}%</span>' if disc_val > 0 else ''}
              </div>
            </div>"""

    subject = f"Quote {q.number} from {company_name}"

    body = f"""Hello {q.to_contact},

Please find our quote {q.number} from {company_name} below.

Quote Number: {q.number}
Issue Date: {q.issue_date}
Valid Until: {q.expiry_date}
"""
    if q.title:
        body += f"For: {q.title}\n"
    body += "\nItems:\n"
    for li in q.line_items:
        item_label = f"{li.name} - {li.description}" if li.name else li.description
        disc_text = f" (Disc: {li.disc}%)" if li.disc else ""
        body += f"  - {item_label} x{li.qty:g} @ {cur_symbol}{li.price:.2f}{disc_text}\n"
    body += f"""
Total: {cur_symbol}{total:.2f}

This quote is valid until {q.expiry_date}. Reply to this email to accept it or
ask us anything about it.

Best regards,
{company_name}
{company_address or ''}
{company_email or ''}
{company_phone or ''}

Powered by Aniprotech"""

    html_body = f"""
    <!DOCTYPE html>
    <html>
      <body style="font-family: Arial, Helvetica, sans-serif; color:#1e293b; line-height:1.6; margin:0; padding:0; background-color:#f1f5f9;">
        <div style="max-width:600px; margin:0 auto; padding:40px 20px;">
          <div style="background:#ffffff; border-radius:12px; overflow:hidden;">
            <div style="background-color:#0f172a; padding:40px; text-align:center;">
              {logo_html}
              <div style="font-size:13px;letter-spacing:2px;text-transform:uppercase;color:#94a3b8;">Quote</div>
              <div style="font-size:30px;font-weight:800;color:#ffffff;margin-top:6px;">{esc(q.number)}</div>
              {f'<div style="font-size:15px;color:#cbd5e1;margin-top:8px;">{esc(q.title)}</div>' if q.title else ''}
            </div>
            <div style="padding:32px 28px;">
              <p style="margin:0 0 18px;font-size:15px;">Hello {esc(q.to_contact)},</p>
              <p style="margin:0 0 24px;font-size:15px;color:#475569;">
                {esc(q.summary) if q.summary else f'Thank you for your interest. Here is our quote from {esc(company_name)}.'}
              </p>

              <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap;">
                <div style="flex:1;min-width:150px;background:#f8fafc;border-radius:10px;padding:14px 16px;">
                  <div style="font-size:11px;text-transform:uppercase;color:#94a3b8;font-weight:700;">Issued</div>
                  <div style="font-size:15px;font-weight:700;color:#0f172a;">{esc(q.issue_date)}</div>
                </div>
                <div style="flex:1;min-width:150px;background:#fff7ed;border-radius:10px;padding:14px 16px;">
                  <div style="font-size:11px;text-transform:uppercase;color:#c2823a;font-weight:700;">Valid until</div>
                  <div style="font-size:15px;font-weight:700;color:#9a3412;">{esc(q.expiry_date)}</div>
                </div>
              </div>

              <div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:24px;">
                <div style="background-color:#f8fafc;padding:10px 20px;border-bottom:2px solid #e2e8f0;display:flex;justify-content:space-between;">
                  <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Item</span>
                  <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Amount</span>
                </div>
                {rows}
              </div>

              <div style="background:#0f172a;border-radius:10px;padding:20px 24px;margin-bottom:24px;">
                <div style="display:flex;justify-content:space-between;color:#94a3b8;font-size:13px;margin-bottom:6px;">
                  <span>Subtotal</span><span>{cur_symbol}{subtotal:.2f}</span>
                </div>
                <div style="display:flex;justify-content:space-between;color:#94a3b8;font-size:13px;margin-bottom:10px;">
                  <span>Tax</span><span>{cur_symbol}{tax_total:.2f}</span>
                </div>
                <div style="display:flex;justify-content:space-between;color:#ffffff;font-size:20px;font-weight:800;border-top:1px solid #334155;padding-top:12px;">
                  <span>Total</span><span>{cur_symbol}{total:.2f}</span>
                </div>
              </div>

              {f'<div style="border-left:3px solid #e2e8f0;padding:4px 0 4px 14px;color:#64748b;font-size:13px;margin-bottom:24px;white-space:pre-wrap;">{esc(q.terms)}</div>' if q.terms else ''}

              <p style="margin:0;font-size:14px;color:#475569;">
                Happy with this? Just reply to this email to accept, and we will raise the invoice.
              </p>
            </div>
            <div style="background:#f8fafc;padding:22px 28px;text-align:center;border-top:1px solid #e2e8f0;">
              <div style="font-size:14px;font-weight:700;color:#0f172a;">{esc(company_name)}</div>
              <div style="font-size:12px;color:#64748b;margin-top:4px;">
                {esc(company_address or '')}{' &middot; ' if company_address and company_email else ''}{esc(company_email or '')}{' &middot; ' if company_phone else ''}{esc(company_phone or '')}
              </div>
              <div style="font-size:11px;color:#94a3b8;margin-top:12px;">Powered by Aniprotech</div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    pdf_b64 = payload.pdf_data if payload.pdf_data else None
    pdf_filename = f"{q.number}.pdf" if pdf_b64 else "quote.pdf"

    # Charged before the send is queued, so a refused charge cannot still
    # deliver the email.
    require_credit(db, client.id, "quote_send", 1, q.number)

    background_tasks.add_task(send_email_background, q.email, subject, body,
                              f"{company_name} <{from_email}>", html_body, pdf_b64,
                              pdf_filename, logo_data, client_id=client.id)

    # Re-sending must not walk an answered quote back to merely Sent.
    if q.status in ("Draft", "Sent"):
        q.status = "Sent"
    q.sent = datetime.now().strftime("%Y-%m-%d")
    log_audit(db, client.id, "quote_sent", "quote", q.id, q.number, f"Sent to {q.email}", request)
    db.commit()
    return {"message": "Email sending initiated via Gmail API",
            "status": q.status, "sent_date": q.sent}


# ============================================================================
# HR MODULE - Departments, Employees, Payroll, Onboarding
# ============================================================================

from sqlalchemy import func as sqlfunc, or_

class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#00f0ff"
    icon: Optional[str] = "building"

class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = ""
    address: Optional[str] = ""
    department_id: Optional[int] = None
    reports_to: Optional[int] = None
    job_title: Optional[str] = ""
    role: Optional[str] = "employee"
    level: Optional[str] = ""
    employment_type: Optional[str] = "full_time"
    pay_frequency: Optional[str] = "monthly"
    salary: Optional[float] = 0.0
    hourly_rate: Optional[float] = 0.0
    tax_rate: Optional[float] = 0.0
    deductions: Optional[float] = 0.0
    allowances: Optional[float] = 0.0
    bonus: Optional[float] = 0.0
    bank_name: Optional[str] = ""
    bank_account: Optional[str] = ""
    tax_id: Optional[str] = ""
    emergency_contact: Optional[str] = ""
    emergency_phone: Optional[str] = ""
    start_date: Optional[str] = ""
    employee_id: Optional[str] = ""
    password: Optional[str] = ""

class PayslipCreate(BaseModel):
    employee_id: int
    period_start: str
    period_end: str
    pay_date: str
    hours_worked: Optional[float] = 0.0
    overtime_hours: Optional[float] = 0.0
    overtime_rate: Optional[float] = 0.0
    basic_salary: Optional[float] = 0.0
    overtime_pay: Optional[float] = 0.0
    bonus: Optional[float] = 0.0
    allowances: Optional[float] = 0.0
    tax_amount: Optional[float] = 0.0
    insurance: Optional[float] = 0.0
    retirement: Optional[float] = 0.0
    other_deductions: Optional[float] = 0.0
    notes: Optional[str] = ""

# --- Org hierarchy: levels and roles ---------------------------------------
# `level` is the seniority band; `role` is the person's place in the reporting
# line. They are deliberately separate: a senior engineer (L4) and a team lead
# can be the same band but different roles.

EMPLOYEE_LEVELS = [
    {"code": "L1", "label": "L1 - Intern / Trainee", "rank": 1},
    {"code": "L2", "label": "L2 - Junior", "rank": 2},
    {"code": "L3", "label": "L3 - Mid", "rank": 3},
    {"code": "L4", "label": "L4 - Senior", "rank": 4},
    {"code": "L5", "label": "L5 - Lead", "rank": 5},
    {"code": "L6", "label": "L6 - Principal / Manager", "rank": 6},
    {"code": "L7", "label": "L7 - Director", "rank": 7},
    {"code": "L8", "label": "L8 - Executive", "rank": 8},
]
LEVEL_CODES = {lvl["code"] for lvl in EMPLOYEE_LEVELS}
LEVEL_RANK = {lvl["code"]: lvl["rank"] for lvl in EMPLOYEE_LEVELS}

EMPLOYEE_ROLES = [
    {"code": "employee", "label": "Employee"},
    {"code": "team_lead", "label": "Team Lead"},
    {"code": "manager", "label": "Manager"},
    {"code": "department_head", "label": "Department Head"},
    {"code": "hr_admin", "label": "HR Admin"},
    {"code": "executive", "label": "Executive"},
]
ROLE_CODES = {r["code"] for r in EMPLOYEE_ROLES}


@app.get("/api/hr/levels")
def get_hr_levels(request: Request, db: Session = Depends(get_db)):
    """Catalogue the UI uses to populate level and role pickers."""
    get_client_user(request, db)
    return {"levels": EMPLOYEE_LEVELS, "roles": EMPLOYEE_ROLES}


DEFAULT_WORKING_DAYS = "1,2,3,4,5"          # Monday to Friday


def parse_working_days(raw):
    """ISO weekday numbers: Monday is 1, Sunday is 7.

    Anything unparseable falls back to a normal working week rather than an
    empty set, because an empty set would mean nobody is ever working and every
    day would silently look like a day off.
    """
    days = set()
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            continue
        if 1 <= n <= 7:
            days.add(n)
    return days or {1, 2, 3, 4, 5}


def clean_working_days(raw):
    """Normalise for storage, keeping the days in order."""
    if isinstance(raw, (list, tuple, set)):
        raw = ",".join(str(x) for x in raw)
    return ",".join(str(d) for d in sorted(parse_working_days(raw)))


def attendance_settings_for(db, client_id):
    return db.query(models.DBAttendanceSettings).filter(
        models.DBAttendanceSettings.client_id == client_id
    ).first()


def is_working_day(settings, on_date=None):
    on_date = on_date or datetime.now().date()
    raw = getattr(settings, "working_days", None) if settings else None
    return on_date.isoweekday() in parse_working_days(raw or DEFAULT_WORKING_DAYS)


def should_auto_clock_in(settings, on_date=None):
    """Signing in only starts a shift on a working day, and only if the tenant
    wants sign-in to count at all. Someone opening the portal on a Sunday to
    check a document is not at work."""
    if settings is not None and not bool(getattr(settings, "auto_clock_in", True)):
        return False
    return is_working_day(settings, on_date)


def validate_level(level):
    level = (level or "").strip().upper()
    if level and level not in LEVEL_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown level '{level}'. Expected one of: {', '.join(sorted(LEVEL_CODES))}",
        )
    return level


def validate_role(role):
    role = (role or "").strip().lower()
    if role and role not in ROLE_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown role '{role}'. Expected one of: {', '.join(sorted(ROLE_CODES))}",
        )
    return role or "employee"


def validate_manager(db, client_id, employee_id, manager_id):
    """A reporting line must stay a tree.

    Without this an admin could point A at B and B at A; the org chart renderer
    walks children recursively and would spin forever on the cycle.
    """
    if not manager_id:
        return None
    if employee_id and manager_id == employee_id:
        raise HTTPException(status_code=400, detail="An employee cannot report to themselves")
    manager = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == manager_id, models.DBEmployee.client_id == client_id
    ).first()
    if not manager:
        raise HTTPException(status_code=400, detail="Manager not found")
    # Walk up from the proposed manager; hitting this employee means a cycle.
    seen = set()
    cursor = manager
    while cursor and cursor.reports_to:
        if cursor.reports_to in seen:
            break  # pre-existing loop in the data; don't spin
        seen.add(cursor.reports_to)
        if employee_id and cursor.reports_to == employee_id:
            raise HTTPException(
                status_code=400,
                detail=f"{manager.first_name} {manager.last_name} already reports to this employee, "
                       "so this would create a reporting loop",
            )
        cursor = db.query(models.DBEmployee).filter(models.DBEmployee.id == cursor.reports_to).first()
    return manager_id



# --- Department / employee validation --------------------------------------
# These fields flow straight into payroll and the employee login, so bad values
# here surface later as wrong pay or an account nobody can sign into.

def clean_department_name(name):
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="A department name is required")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="Department name must be 80 characters or fewer")
    return name


def assert_department_name_free(db, client_id, name, exclude_id=None):
    """Case-insensitive: 'Engineering' and 'engineering' are the same team."""
    query = db.query(models.DBDepartment).filter(
        models.DBDepartment.client_id == client_id,
        sqlfunc.lower(models.DBDepartment.name) == name.lower(),
    )
    if exclude_id:
        query = query.filter(models.DBDepartment.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=400, detail=f"A department called '{name}' already exists")


def clean_employee_email(db, client_id, email, exclude_id=None):
    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="An email address is required")
    if not validate_email_address(email):
        raise HTTPException(status_code=400, detail=f"'{email}' is not a valid email address")
    query = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client_id,
        sqlfunc.lower(models.DBEmployee.email) == email,
    )
    if exclude_id:
        query = query.filter(models.DBEmployee.id != exclude_id)
    if query.first():
        # Case-variant duplicates also make the employee login ambiguous,
        # because it matches on email and takes the first row.
        raise HTTPException(status_code=400, detail="An employee with this email already exists")
    return email


def clean_person_name(value, label):
    value = (value or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{label} is required")
    if len(value) > 80:
        raise HTTPException(status_code=400, detail=f"{label} must be 80 characters or fewer")
    return value


EMPLOYEE_MONEY_FIELDS = {
    "salary": "Salary", "hourly_rate": "Hourly rate", "deductions": "Deductions",
    "allowances": "Allowances", "bonus": "Bonus",
}


def validate_employee_money(values):
    """Reject negatives and an out-of-range tax rate.

    A 500% tax rate previously produced a payslip with a large negative net,
    i.e. a payslip saying the employee owes the company money.
    """
    for field, label in EMPLOYEE_MONEY_FIELDS.items():
        if field not in values or values[field] is None:
            continue
        try:
            amount = float(values[field])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{label} must be a number")
        if amount < 0:
            raise HTTPException(status_code=400, detail=f"{label} cannot be negative")
        if amount > 100_000_000:
            raise HTTPException(status_code=400, detail=f"{label} is unrealistically large")
    if values.get("tax_rate") is not None:
        try:
            rate = float(values["tax_rate"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Tax rate must be a number")
        if rate < 0 or rate > 100:
            raise HTTPException(status_code=400, detail="Tax rate must be between 0 and 100 percent")


def assert_employee_code_free(db, client_id, code, exclude_id=None):
    code = (code or "").strip()
    if not code:
        return ""
    query = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client_id,
        models.DBEmployee.employee_id == code,
    )
    if exclude_id:
        query = query.filter(models.DBEmployee.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=400, detail=f"Employee ID '{code}' is already in use")
    return code


# --- Departments API ---

@app.get("/api/departments")
def get_departments(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    depts = db.query(models.DBDepartment).filter(models.DBDepartment.client_id == client.id).all()
    result = []
    for d in depts:
        employees = db.query(models.DBEmployee).filter(models.DBEmployee.department_id == d.id).all()
        emp_list = [{"id": e.id, "name": (e.first_name + " " + e.last_name).strip(), "job_title": e.job_title or "", "email": e.email or ""} for e in employees]
        result.append({
            "id": d.id, "name": d.name, "description": d.description,
            "color": d.color or "#00f0ff", "icon": d.icon or "building",
            "employee_count": len(employees), "employees": emp_list, "created_at": d.created_at,
        })
    return result

@app.get("/api/departments/{dept_id}")
def get_department(dept_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    d = db.query(models.DBDepartment).filter(models.DBDepartment.id == dept_id, models.DBDepartment.client_id == client.id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Department not found")
    employees = db.query(models.DBEmployee).filter(models.DBEmployee.department_id == d.id).all()
    emp_list = [{"id": e.id, "name": (e.first_name + " " + e.last_name).strip(), "job_title": e.job_title or "", "email": e.email or "", "status": e.status or ""} for e in employees]
    return {
        "id": d.id, "name": d.name, "description": d.description,
        "color": d.color or "#00f0ff", "icon": d.icon or "building",
        "employee_count": len(employees), "employees": emp_list, "created_at": d.created_at,
    }

@app.post("/api/departments")
def create_department(request: Request, body: DepartmentCreate, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    name = clean_department_name(body.name)
    assert_department_name_free(db, client.id, name)
    dept = models.DBDepartment(name=name, description=body.description, color=body.color, icon=body.icon, client_id=client.id)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return {"id": dept.id, "name": dept.name, "description": dept.description, "color": dept.color, "icon": dept.icon, "employee_count": 0}

@app.put("/api/departments/{dept_id}")
def update_department(dept_id: int, request: Request, body: DepartmentCreate, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == dept_id, models.DBDepartment.client_id == client.id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    name = clean_department_name(body.name)
    # Create checked for duplicates but update did not, so a rename could
    # produce two departments with the same name.
    assert_department_name_free(db, client.id, name, exclude_id=dept.id)
    dept.name = name
    dept.description = body.description
    dept.color = body.color
    dept.icon = body.icon
    db.commit()
    return {"id": dept.id, "name": dept.name, "description": dept.description, "color": dept.color, "icon": dept.icon}

@app.delete("/api/departments/{dept_id}")
def delete_department(dept_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == dept_id, models.DBDepartment.client_id == client.id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.query(models.DBEmployee).filter(models.DBEmployee.department_id == dept_id).update(
        {"department_id": None}, synchronize_session=False
    )
    # Goals hang off departments too and would block the delete on Postgres.
    db.query(models.DBDepartmentGoal).filter(models.DBDepartmentGoal.department_id == dept_id).delete(
        synchronize_session=False
    )
    db.query(models.DBEmployeeGoal).filter(models.DBEmployeeGoal.department_id == dept_id).update(
        {"department_id": None}, synchronize_session=False
    )
    log_audit(db, client.id, "department_deleted", "department", dept.id, dept.name, "", request)
    db.delete(dept)
    db.commit()
    return {"message": "Department deleted"}

# --- Employees API ---

@app.get("/api/employees")
def get_employees(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    query = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id)
    if status:
        query = query.filter(models.DBEmployee.status == status)
    if q:
        query = query.filter(or_(
            models.DBEmployee.first_name.ilike(f"%{q}%"),
            models.DBEmployee.last_name.ilike(f"%{q}%"),
            models.DBEmployee.email.ilike(f"%{q}%"),
            models.DBEmployee.job_title.ilike(f"%{q}%"),
        ))
    employees = query.order_by(models.DBEmployee.created_at.desc()).all()
    result = []
    for e in employees:
        dept_name = ""
        if e.department_id:
            dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == e.department_id).first()
            dept_name = dept.name if dept else ""
        manager_name = ""
        if e.reports_to:
            mgr = db.query(models.DBEmployee).filter(models.DBEmployee.id == e.reports_to).first()
            manager_name = f"{mgr.first_name} {mgr.last_name}" if mgr else ""
        result.append({
            "id": e.id, "employee_id": e.employee_id,
            "first_name": e.first_name, "last_name": e.last_name,
            "full_name": f"{e.first_name} {e.last_name}",
            "email": e.email, "phone": e.phone,
            "department_id": e.department_id, "department_name": dept_name,
            "reports_to": e.reports_to, "manager_name": manager_name,
            "job_title": e.job_title, "role": e.role, "level": e.level or "",
            "employment_type": e.employment_type,
            "pay_frequency": e.pay_frequency,
            "salary": e.salary, "hourly_rate": e.hourly_rate,
            "tax_rate": e.tax_rate, "deductions": e.deductions,
            "allowances": e.allowances, "bonus": e.bonus,
            "bank_name": e.bank_name, "bank_account": e.bank_account, "tax_id": e.tax_id,
            "emergency_contact": e.emergency_contact, "emergency_phone": e.emergency_phone,
            "start_date": e.start_date, "end_date": e.end_date,
            "status": e.status, "onboarding_complete": e.onboarding_complete,
            "offboarding_complete": e.offboarding_complete,
            "created_at": e.created_at,
        })
    return result

@app.post("/api/employees")
def create_employee(request: Request, body: EmployeeCreate, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    first_name = clean_person_name(body.first_name, "First name")
    last_name = clean_person_name(body.last_name, "Last name")
    email = clean_employee_email(db, client.id, body.email)
    validate_employee_money(body.model_dump())
    employee_code = assert_employee_code_free(db, client.id, body.employee_id)

    level = validate_level(body.level)
    role = validate_role(body.role)
    reports_to = validate_manager(db, client.id, None, body.reports_to)

    max_num = db.query(sqlfunc.coalesce(sqlfunc.max(models.DBEmployee.id), 0)).filter(models.DBEmployee.client_id == client.id).scalar()
    emp_number = employee_code or f"EMP-{max_num + 1:04d}"

    emp = models.DBEmployee(
        client_id=client.id, employee_id=emp_number,
        first_name=first_name, last_name=last_name,
        email=email, phone=body.phone, address=body.address,
        department_id=body.department_id, reports_to=reports_to,
        job_title=body.job_title, role=role, level=level,
        employment_type=body.employment_type, pay_frequency=body.pay_frequency,
        salary=body.salary, hourly_rate=body.hourly_rate,
        tax_rate=body.tax_rate, deductions=body.deductions,
        allowances=body.allowances, bonus=body.bonus,
        bank_name=body.bank_name, bank_account=body.bank_account,
        tax_id=body.tax_id,
        emergency_contact=body.emergency_contact, emergency_phone=body.emergency_phone,
        start_date=body.start_date, status="onboarding",
        password_hash=models.hash_password(body.password) if body.password else "",
    )
    db.add(emp)
    db.flush()

    # Create default onboarding checklist
    start_onboarding(db, client.id, emp)

    if body.department_id:
        pending_goals = db.query(models.DBDepartmentGoal).filter(
            models.DBDepartmentGoal.department_id == body.department_id,
            models.DBDepartmentGoal.client_id == client.id,
            models.DBDepartmentGoal.is_assigned == False,
        ).all()
        for dg in pending_goals:
            goal = models.DBEmployeeGoal(
                client_id=client.id, employee_id=emp.id, department_id=body.department_id,
                title=dg.title, description=dg.description,
                target_value=dg.target_value, current_value=0,
                unit=dg.unit, category=dg.category,
                priority=dg.priority, start_date=dg.start_date,
                due_date=dg.due_date, created_by="HR",
            )
            db.add(goal)
            note = models.DBNotification(
                client_id=client.id, employee_id=emp.id,
                title="New Goal Assigned", message=f"HR has assigned you a department goal: {dg.title}",
                type="info",
            )
            db.add(note)
            dg.is_assigned = True

    db.commit()
    db.refresh(emp)
    log_audit(db, client.id, "employee_created", "employee", emp.id, f"{emp.first_name} {emp.last_name}", f"Dept: {body.department_id or 'None'}", request)
    db.commit()
    return {
        "id": emp.id, "employee_id": emp.employee_id,
        "first_name": emp.first_name, "last_name": emp.last_name,
        "email": emp.email, "status": emp.status, "level": emp.level or "", "role": emp.role,
        "department_id": emp.department_id, "reports_to": emp.reports_to,
        "message": "Employee created. Onboarding checklist generated.",
    }

@app.get("/api/employees/{emp_id}")
def get_employee(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    dept_name = ""
    if emp.department_id:
        dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == emp.department_id).first()
        dept_name = dept.name if dept else ""
    manager_name = ""
    if emp.reports_to:
        mgr = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp.reports_to).first()
        manager_name = f"{mgr.first_name} {mgr.last_name}" if mgr else ""
    payslips = db.query(models.DBPayslip).filter(models.DBPayslip.employee_id == emp.id).order_by(models.DBPayslip.created_at.desc()).limit(12).all()
    onboarding = db.query(models.DBOnboardingItem).filter(models.DBOnboardingItem.employee_id == emp.id).all()

    # The profile is the one place HR looks up a person, so it answers every
    # question about them rather than sending the user hunting across tabs.
    leave_rows = db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.employee_id == emp.id
    ).order_by(models.DBLeaveRequest.id.desc()).limit(10).all()

    today = datetime.now().date()
    on_leave_today = False
    for l in leave_rows:
        if l.status != "approved":
            continue
        start, end = _parse_date(l.start_date), _parse_date(l.end_date)
        if start and end and start <= today <= end:
            on_leave_today = True
            break

    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    attendance = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp.id,
        models.DBAttendance.date >= since,
    ).order_by(models.DBAttendance.date.desc()).all()
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_row = next((a for a in attendance if a.date == today_str), None)

    goals = db.query(models.DBEmployeeGoal).filter(
        models.DBEmployeeGoal.employee_id == emp.id
    ).order_by(models.DBEmployeeGoal.id.desc()).limit(10).all()
    documents = db.query(models.DBDocument).filter(
        models.DBDocument.employee_id == emp.id
    ).order_by(models.DBDocument.id.desc()).all()
    doc_requests = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.employee_id == emp.id
    ).order_by(models.DBDocumentRequest.id.asc()).all()

    # Where this person came from, if they were hired through recruitment.
    origin = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.hired_employee_id == emp.id
    ).first()

    direct_reports = db.query(models.DBEmployee).filter(
        models.DBEmployee.reports_to == emp.id,
        models.DBEmployee.client_id == client.id,
    ).all()

    return {
        "id": emp.id, "employee_id": emp.employee_id,
        "first_name": emp.first_name, "last_name": emp.last_name,
        "full_name": f"{emp.first_name} {emp.last_name}",
        "email": emp.email, "phone": emp.phone, "address": emp.address,
        "department_id": emp.department_id, "department_name": dept_name,
        "reports_to": emp.reports_to, "manager_name": manager_name,
        "job_title": emp.job_title, "role": emp.role, "level": emp.level or "",
        "employment_type": emp.employment_type, "pay_frequency": emp.pay_frequency,
        "salary": emp.salary, "hourly_rate": emp.hourly_rate,
        "tax_rate": emp.tax_rate, "deductions": emp.deductions,
        "allowances": emp.allowances, "bonus": emp.bonus,
        "bank_name": emp.bank_name, "bank_account": emp.bank_account, "tax_id": emp.tax_id,
        "emergency_contact": emp.emergency_contact, "emergency_phone": emp.emergency_phone,
        "start_date": emp.start_date, "end_date": emp.end_date,
        "status": emp.status, "onboarding_complete": emp.onboarding_complete,
        "offboarding_complete": emp.offboarding_complete,
        "created_at": emp.created_at,
        "payslips": [{"id": p.id, "number": p.number, "period_start": p.period_start, "period_end": p.period_end,
                       "pay_date": p.pay_date, "gross_pay": p.gross_pay, "net_pay": p.net_pay,
                       "status": p.status, "sent": p.sent} for p in payslips],
        "onboarding_items": [{"id": o.id, "title": o.title, "description": o.description,
                               "category": o.category, "is_completed": o.is_completed,
                               "completed_at": o.completed_at, "assigned_to": o.assigned_to,
                               "due_date": o.due_date} for o in onboarding],
        "leave_balance": leave_balance_for(db, emp),
        "on_leave_today": on_leave_today,
        "leave_requests": [{
            "id": l.id, "leave_type": l.leave_type, "start_date": l.start_date,
            "end_date": l.end_date, "days": l.days, "status": l.status,
            "reason": l.reason, "created_at": l.created_at,
        } for l in leave_rows],
        "attendance_summary": {
            "days_present": sum(1 for a in attendance if a.clock_in),
            "days_late": sum(1 for a in attendance if a.status == "late"),
            "hours_30d": round(sum(a.total_hours or 0 for a in attendance), 2),
            "overtime_30d": round(sum(a.overtime_hours or 0 for a in attendance), 2),
            "clocked_in_today": bool(today_row and today_row.clock_in and not today_row.clock_out),
            "today_clock_in": today_row.clock_in if today_row else "",
            "today_clock_out": today_row.clock_out if today_row else "",
        },
        "goals": [{
            "id": g.id, "title": g.title, "status": g.status,
            "current_value": g.current_value, "target_value": g.target_value,
            "unit": g.unit, "due_date": g.due_date, "priority": g.priority,
        } for g in goals],
        "documents": [{
            "id": d.id, "title": d.title, "doc_type": d.doc_type,
            "file_name": d.file_name, "uploaded_by": d.uploaded_by,
            "created_at": d.created_at,
        } for d in documents],
        "document_requests": [request_to_dict(r) for r in doc_requests],
        "documents_outstanding": sum(
            1 for r in doc_requests if r.status in ("pending", "rejected")
        ),
        "direct_reports": [{
            "id": r.id, "full_name": f"{r.first_name} {r.last_name}",
            "job_title": r.job_title, "level": r.level or "", "status": r.status,
        } for r in direct_reports],
        "hired_from": {
            "submission_id": origin.id, "form_id": origin.form_id,
            "applied_on": origin.created_at,
        } if origin else None,
    }

@app.put("/api/employees/{emp_id}")
def update_employee(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    old_dept = emp.department_id
    body = body or {}
    # Everything a blind setattr would have accepted unchecked.
    if "first_name" in body:
        body["first_name"] = clean_person_name(body["first_name"], "First name")
    if "last_name" in body:
        body["last_name"] = clean_person_name(body["last_name"], "Last name")
    if "email" in body:
        body["email"] = clean_employee_email(db, client.id, body["email"], exclude_id=emp.id)
    validate_employee_money(body)
    # Hierarchy fields go through the same checks as on create; a blind
    # setattr let callers set an unknown level or build a reporting loop.
    if "level" in body:
        body["level"] = validate_level(body["level"])
    if "role" in body:
        body["role"] = validate_role(body["role"])
    if "reports_to" in body:
        body["reports_to"] = validate_manager(db, client.id, emp.id, body["reports_to"])
    for key, val in body.items():
        if hasattr(emp, key) and key not in ("id", "client_id", "created_at", "password_hash", "employee_id"):
            setattr(emp, key, val)
    new_dept = emp.department_id
    if new_dept and new_dept != old_dept:
        pending_goals = db.query(models.DBDepartmentGoal).filter(
            models.DBDepartmentGoal.department_id == new_dept,
            models.DBDepartmentGoal.client_id == client.id,
            models.DBDepartmentGoal.is_assigned == False,
        ).all()
        for dg in pending_goals:
            goal = models.DBEmployeeGoal(
                client_id=client.id, employee_id=emp.id, department_id=new_dept,
                title=dg.title, description=dg.description,
                target_value=dg.target_value, current_value=0,
                unit=dg.unit, category=dg.category,
                priority=dg.priority, start_date=dg.start_date,
                due_date=dg.due_date, created_by="HR",
            )
            db.add(goal)
            note = models.DBNotification(
                client_id=client.id, employee_id=emp.id,
                title="New Goal Assigned", message=f"HR has assigned you a department goal: {dg.title}",
                type="info",
            )
            db.add(note)
            dg.is_assigned = True
    log_audit(db, client.id, "employee_updated", "employee", emp.id, f"{emp.first_name} {emp.last_name}", f"Fields: {', '.join(body.keys()) if body else 'none'}", request)
    db.commit()
    return {"message": "Employee updated"}

@app.delete("/api/employees/{emp_id}")
def delete_employee(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp_name = f"{emp.first_name} {emp.last_name}"
    # Every table that points at employees must be cleared first, otherwise the
    # delete fails on a foreign key violation. Attendance, goals, leave,
    # documents, notifications and overtime were all being left behind.
    for model in (
        models.DBOnboardingItem, models.DBPayslip, models.DBAttendance,
        models.DBEmployeeGoal, models.DBLeaveRequest, models.DBDocument,
        models.DBNotification, models.DBOvertimeLog,
    ):
        db.query(model).filter(model.employee_id == emp_id).delete(synchronize_session=False)
    # Anyone reporting to this person would keep a dangling manager reference.
    db.query(models.DBEmployee).filter(models.DBEmployee.reports_to == emp_id).update(
        {"reports_to": None}, synchronize_session=False
    )
    log_audit(db, client.id, "employee_deleted", "employee", emp.id, emp_name, "", request)
    db.delete(emp)
    db.commit()
    return {"message": "Employee deleted"}

@app.post("/api/employees/{emp_id}/reset-password")
def reset_employee_password(emp_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    new_pass = body.get("password", "")
    if not new_pass or len(new_pass) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    emp.password_hash = models.hash_password(new_pass)
    db.commit()
    return {"message": "Password updated successfully"}

@app.post("/api/employees/{emp_id}/offboard")
def start_offboarding(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.status = "offboarding"
    db.commit()
    return {"message": "Offboarding started"}

@app.post("/api/employees/{emp_id}/complete-offboard")
def complete_offboarding(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    end_date = body.get("end_date", "") if body else ""
    emp.status = "terminated"
    emp.end_date = end_date
    emp.offboarding_complete = True
    db.commit()
    return {"message": "Employee offboarded"}

# --- Onboarding API ---

@app.get("/api/onboarding/hub")
def get_onboarding_hub(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    employees = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        models.DBEmployee.status.in_(["onboarding", "active"])
    ).all()
    result = []
    for emp in employees:
        items = db.query(models.DBOnboardingItem).filter(models.DBOnboardingItem.employee_id == emp.id).all()
        completed = sum(1 for i in items if i.is_completed)
        overdue = 0
        today = datetime.now().strftime("%Y-%m-%d")
        for i in items:
            if not i.is_completed and i.due_date and i.due_date < today:
                overdue += 1
        result.append({
            "id": emp.id, "name": (emp.first_name + " " + emp.last_name).strip(),
            "job_title": emp.job_title or "", "department": emp.department.name if emp.department else "",
            "status": emp.status or "", "start_date": emp.start_date or "",
            "total": len(items), "completed": completed,
            "progress": round((completed / len(items)) * 100) if items else 0,
            "overdue": overdue,
        })
    result.sort(key=lambda x: (-x["overdue"], x["progress"]))
    return result

@app.get("/api/employees/{emp_id}/onboarding")
def get_onboarding(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    items = db.query(models.DBOnboardingItem).filter(models.DBOnboardingItem.employee_id == emp_id).order_by(models.DBOnboardingItem.sort_order).all()
    completed = sum(1 for i in items if i.is_completed)
    return {
        "total": len(items), "completed": completed,
        "progress": round((completed / len(items)) * 100) if items else 0,
        "items": [{"id": i.id, "title": i.title, "description": i.description,
                    "category": i.category, "is_completed": i.is_completed,
                    "completed_at": i.completed_at, "assigned_to": i.assigned_to,
                    "due_date": i.due_date, "sort_order": i.sort_order} for i in items],
    }

@app.put("/api/onboarding/{item_id}")
def update_onboarding_item(item_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    item = db.query(models.DBOnboardingItem).filter(models.DBOnboardingItem.id == item_id, models.DBOnboardingItem.client_id == client.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if body:
        if "is_completed" in body:
            item.is_completed = body["is_completed"]
            if body["is_completed"]:
                item.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                item.completed_at = ""
        if "title" in body:
            item.title = body["title"]
        if "description" in body:
            item.description = body["description"]
        if "category" in body:
            item.category = body["category"]
        if "assigned_to" in body:
            item.assigned_to = body["assigned_to"]
        if "due_date" in body:
            item.due_date = body["due_date"]
    db.commit()
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == item.employee_id).first()
    if maybe_complete_onboarding(db, emp):
        db.commit()
    return {"message": "Item updated"}

@app.delete("/api/onboarding/{item_id}")
def delete_onboarding_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    item = db.query(models.DBOnboardingItem).filter(models.DBOnboardingItem.id == item_id, models.DBOnboardingItem.client_id == client.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return {"message": "Item deleted"}

@app.post("/api/employees/{emp_id}/onboarding")
def add_onboarding_item(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    max_order = db.query(func.max(models.DBOnboardingItem.sort_order)).filter(models.DBOnboardingItem.employee_id == emp_id).scalar() or 0
    item = models.DBOnboardingItem(
        client_id=client.id, employee_id=emp_id,
        title=body.get("title", ""), description=body.get("description", ""),
        category=body.get("category", "general"), assigned_to=body.get("assigned_to", ""),
        due_date=body.get("due_date", ""), sort_order=max_order + 1,
    )
    db.add(item)
    db.commit()
    return {"id": item.id, "title": item.title, "message": "Item added"}

@app.post("/api/employees/{emp_id}/onboarding/bulk")
def bulk_add_onboarding(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    items = body.get("items", []) if body else []
    max_order = db.query(func.max(models.DBOnboardingItem.sort_order)).filter(models.DBOnboardingItem.employee_id == emp_id).scalar() or 0
    added = []
    for i, item_data in enumerate(items):
        oitem = models.DBOnboardingItem(
            client_id=client.id, employee_id=emp_id,
            title=item_data.get("title", ""), description=item_data.get("description", ""),
            category=item_data.get("category", "general"), assigned_to=item_data.get("assigned_to", ""),
            due_date=item_data.get("due_date", ""), sort_order=max_order + i + 1,
        )
        db.add(oitem)
        added.append(item_data.get("title", ""))
    db.commit()
    return {"added": len(added), "message": f"Added {len(added)} items"}

@app.post("/api/onboarding/apply-template")
def apply_onboarding_template(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp_ids = body.get("employee_ids", []) if body else []
    template_items = body.get("items", []) if body else []
    count = 0
    for emp_id in emp_ids:
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
        if not emp:
            continue
        max_order = db.query(func.max(models.DBOnboardingItem.sort_order)).filter(models.DBOnboardingItem.employee_id == emp_id).scalar() or 0
        for i, item_data in enumerate(template_items):
            db.add(models.DBOnboardingItem(
                client_id=client.id, employee_id=emp_id,
                title=item_data.get("title", ""), description=item_data.get("description", ""),
                category=item_data.get("category", "general"), assigned_to=item_data.get("assigned_to", ""),
                due_date=item_data.get("due_date", ""), sort_order=max_order + i + 1,
            ))
            count += 1
    db.commit()
    return {"added": count, "message": f"Added {count} items to {len(emp_ids)} employees"}

@app.get("/api/onboarding/templates")
def get_onboarding_templates(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    templates = db.query(models.DBOnboardingTemplate).filter(models.DBOnboardingTemplate.client_id == client.id).all()
    return [{"id": t.id, "name": t.name, "items": json.loads(t.items_json) if t.items_json else [], "created_at": t.created_at} for t in templates]

@app.post("/api/onboarding/templates")
def create_onboarding_template(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body or not body.get("name"):
        raise HTTPException(status_code=400, detail="Name required")
    template = models.DBOnboardingTemplate(
        client_id=client.id, name=body["name"],
        items_json=json.dumps(body.get("items", [])),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "name": template.name, "message": "Template created"}

@app.delete("/api/onboarding/templates/{template_id}")
def delete_onboarding_template(template_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    template = db.query(models.DBOnboardingTemplate).filter(models.DBOnboardingTemplate.id == template_id, models.DBOnboardingTemplate.client_id == client.id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"message": "Template deleted"}

# --- Payroll API ---

@app.get("/api/payslips")
def get_payslips(request: Request, status: str = "", db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    query = db.query(models.DBPayslip).filter(models.DBPayslip.client_id == client.id)
    if status:
        query = query.filter(models.DBPayslip.status == status)
    payslips = query.order_by(models.DBPayslip.created_at.desc()).all()
    result = []
    for p in payslips:
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == p.employee_id).first()
        result.append({
            "id": p.id, "number": p.number,
            "employee_id": p.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "",
            "employee_email": emp.email if emp else "",
            "period_start": p.period_start, "period_end": p.period_end,
            "pay_date": p.pay_date, "gross_pay": p.gross_pay,
            "tax_amount": p.tax_amount, "total_deductions": p.total_deductions,
            "net_pay": p.net_pay, "status": p.status, "sent": p.sent,
            "created_at": p.created_at,
        })
    return result

@app.get("/api/employees/{emp_id}/pay-details")
def get_employee_pay_details(emp_id: int, request: Request, period_start: str = "", period_end: str = "", db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    hours_worked = 0.0
    if period_start and period_end:
        records = db.query(models.DBAttendance).filter(
            models.DBAttendance.employee_id == emp_id,
            models.DBAttendance.client_id == client.id,
            models.DBAttendance.date >= period_start,
            models.DBAttendance.date <= period_end,
        ).all()
        for r in records:
            hours_worked += r.total_hours or 0
        hours_worked = round(hours_worked, 2)

    overtime_hours = 0.0
    if period_start and period_end:
        ot_logs = db.query(models.DBOvertimeLog).filter(
            models.DBOvertimeLog.employee_id == emp_id,
            models.DBOvertimeLog.client_id == client.id,
            models.DBOvertimeLog.date >= period_start,
            models.DBOvertimeLog.date <= period_end,
            models.DBOvertimeLog.status == "announced",
        ).all()
        for log in ot_logs:
            overtime_hours += log.hours or 0
        overtime_hours = round(overtime_hours, 2)

    ot_rate = emp.hourly_rate or 0.0
    if ot_rate == 0 and (emp.salary or 0) > 0:
        ot_rate = round(emp.salary / 160 * 1.5, 2)

    # Hourly staff have salary == 0; paying them their (zero) salary produced a
    # blank payslip. Derive basic from the hours actually worked instead.
    basic = resolve_basic_pay(emp, None, hours_worked)
    ot_pay = money(overtime_hours * ot_rate) if overtime_hours > 0 else 0
    bonus = emp.bonus or 0.0
    allowances = emp.allowances or 0.0
    gross = money(basic + ot_pay + bonus + allowances)
    tax_rate = emp.tax_rate or 0.0
    tax_amount = money(gross * (tax_rate / 100)) if tax_rate > 0 else 0
    deductions = emp.deductions or 0.0
    total_deductions = money(tax_amount + deductions)
    net_pay = money(gross - total_deductions)

    return {
        "employee_id": emp.id,
        "full_name": f"{emp.first_name} {emp.last_name}",
        "employee_id_code": emp.employee_id,
        "job_title": emp.job_title,
        "pay_frequency": emp.pay_frequency,
        "bank_name": emp.bank_name,
        "bank_account": emp.bank_account,
        "tax_id": emp.tax_id,
        "salary": basic,
        "is_hourly": (emp.salary or 0) <= 0 and (emp.hourly_rate or 0) > 0,
        "hourly_rate": emp.hourly_rate or 0.0,
        "tax_rate": tax_rate,
        "deductions": deductions,
        "allowances": allowances,
        "bonus": bonus,
        "hours_worked": hours_worked,
        "overtime_hours": overtime_hours,
        "overtime_rate": ot_rate,
        "overtime_pay": ot_pay,
        "gross_pay": round(gross, 2),
        "tax_amount": tax_amount,
        "total_deductions": round(total_deductions, 2),
        "net_pay": net_pay,
    }

def resolve_basic_pay(emp, requested_basic, hours_worked):
    """Work out basic pay for a period.

    An explicit figure from the caller always wins. Otherwise a salaried
    employee gets their salary; an hourly employee is paid hours x rate.
    Falling through to `emp.salary` for hourly staff paid them zero.
    """
    if requested_basic and requested_basic > 0:
        return money(requested_basic)
    if (emp.salary or 0) > 0:
        return money(emp.salary)
    if (emp.hourly_rate or 0) > 0 and (hours_worked or 0) > 0:
        return money(emp.hourly_rate * hours_worked)
    return 0.0


def compute_payslip_figures(emp, data):
    """Single source of truth for payslip arithmetic, used by create, update and
    the bulk payroll run so the three can never drift apart.

    `data` is a dict of the editable inputs.
    """
    hours = float(data.get("hours_worked") or 0)
    ot_hours = float(data.get("overtime_hours") or 0)
    ot_rate = float(data.get("overtime_rate") or 0)
    if ot_hours > 0 and ot_rate <= 0:
        # Fall back to a 1.5x rate derived from the employee's own pay.
        ot_rate = emp.hourly_rate or (round((emp.salary or 0) / 160 * 1.5, 2) if emp.salary else 0)

    basic = resolve_basic_pay(emp, data.get("basic_salary"), hours)
    ot_pay = money(ot_hours * ot_rate) if ot_hours > 0 else 0.0
    bonus = money(data.get("bonus") or 0)
    allowances = money(data.get("allowances") or 0)
    gross = money(basic + ot_pay + bonus + allowances)

    tax = data.get("tax_amount")
    if tax is None or float(tax) <= 0:
        tax = money(gross * ((emp.tax_rate or 0) / 100)) if (emp.tax_rate or 0) > 0 else 0.0
    else:
        tax = money(tax)

    insurance = money(data.get("insurance") or 0)
    retirement = money(data.get("retirement") or 0)
    other = money(data.get("other_deductions") or 0)
    standing = money(emp.deductions or 0)
    total_deductions = money(tax + insurance + retirement + other + standing)
    net = money(gross - total_deductions)

    return {
        "hours_worked": hours, "overtime_hours": ot_hours, "overtime_rate": money(ot_rate),
        "basic_salary": basic, "overtime_pay": ot_pay, "bonus": bonus, "allowances": allowances,
        "gross_pay": gross, "tax_amount": tax, "insurance": insurance, "retirement": retirement,
        # Deliberately not returned here: this dict is splatted straight into
        # DBPayslip, which has no such column. It is derived on read instead,
        # which also makes payslips issued before this fix reconcile.
        "other_deductions": other, "total_deductions": total_deductions, "net_pay": net,
    }


def find_overlapping_payslip(db, client_id, employee_id, period_start, period_end, exclude_id=None):
    """Guard against paying the same person twice for the same period."""
    start = _parse_date(period_start)
    end = _parse_date(period_end)
    if not start or not end:
        return None
    query = db.query(models.DBPayslip).filter(
        models.DBPayslip.client_id == client_id,
        models.DBPayslip.employee_id == employee_id,
        models.DBPayslip.status != "Void",
    )
    if exclude_id:
        query = query.filter(models.DBPayslip.id != exclude_id)
    for existing in query.all():
        e_start = _parse_date(existing.period_start)
        e_end = _parse_date(existing.period_end)
        if e_start and e_end and start <= e_end and e_start <= end:
            return existing
    return None


@app.post("/api/payslips")
def create_payslip(request: Request, body: PayslipCreate, allow_overlap: bool = False, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == body.employee_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if body.period_start and body.period_end:
        p_start, p_end = _parse_date(body.period_start), _parse_date(body.period_end)
        if p_start and p_end and p_end < p_start:
            raise HTTPException(status_code=400, detail="Period end cannot be before period start")
    if not allow_overlap:
        clash = find_overlapping_payslip(db, client.id, emp.id, body.period_start, body.period_end)
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"Payslip {clash.number} already covers {clash.period_start} to {clash.period_end} for this employee",
            )

    ps_number = next_sequence_number(db, models.DBPayslip, client.id, "PS-")
    figures = compute_payslip_figures(emp, body.model_dump())

    ps = models.DBPayslip(
        client_id=client.id, employee_id=body.employee_id, number=ps_number,
        period_start=body.period_start, period_end=body.period_end, pay_date=body.pay_date,
        status="Draft", notes=body.notes, pay_frequency=emp.pay_frequency or "",
        **figures,
    )
    db.add(ps)
    log_audit(db, client.id, "payslip_created", "payslip", None, ps_number,
              f"{emp.first_name} {emp.last_name}: net {figures['net_pay']:.2f}", request)
    db.commit()
    db.refresh(ps)
    return {"id": ps.id, "number": ps.number, "gross_pay": ps.gross_pay, "net_pay": ps.net_pay, "message": "Payslip created"}


PAYROLL_EXCLUDED_STATUSES = ("terminated", "inactive")


class PayrollRunRequest(BaseModel):
    period_start: str
    period_end: str
    pay_date: str
    employee_ids: Optional[List[int]] = None
    include_attendance_hours: Optional[bool] = True
    skip_existing: Optional[bool] = True


@app.post("/api/payroll/run")
def run_payroll(request: Request, body: PayrollRunRequest, db: Session = Depends(get_db)):
    """Generate payslips for a whole pay period in one transaction.

    Replaces the browser looping one request per employee, which had no
    atomicity and silently swallowed per-employee failures.
    """
    client = get_client_user(request, db)
    if not body.period_start or not body.period_end or not body.pay_date:
        raise HTTPException(status_code=400, detail="Period start, period end and pay date are all required")
    p_start, p_end = _parse_date(body.period_start), _parse_date(body.period_end)
    if not p_start or not p_end:
        raise HTTPException(status_code=400, detail="Dates must be in YYYY-MM-DD format")
    if p_end < p_start:
        raise HTTPException(status_code=400, detail="Period end cannot be before period start")

    # Anyone still on the books gets paid. New starters sit in "onboarding" and
    # leavers in "offboarding" - both are still owed a payslip; only terminated
    # staff are excluded.
    query = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        models.DBEmployee.status.notin_(PAYROLL_EXCLUDED_STATUSES),
    )
    if body.employee_ids:
        query = query.filter(models.DBEmployee.id.in_(body.employee_ids))
    employees = query.all()
    if not employees:
        raise HTTPException(status_code=400, detail="No payable employees match this payroll run")

    created, skipped, warnings, total_net, total_gross = [], [], [], 0.0, 0.0
    next_number = next_sequence_number(db, models.DBPayslip, client.id, "PS-")
    seq = int(next_number.split("-")[1])

    for emp in employees:
        clash = find_overlapping_payslip(db, client.id, emp.id, body.period_start, body.period_end)
        if clash:
            if body.skip_existing:
                skipped.append({
                    "employee_id": emp.id, "name": f"{emp.first_name} {emp.last_name}",
                    "reason": f"already covered by {clash.number}",
                })
                continue
            raise HTTPException(
                status_code=409,
                detail=f"{emp.first_name} {emp.last_name} already has payslip {clash.number} for this period",
            )

        hours = 0.0
        if body.include_attendance_hours:
            records = db.query(models.DBAttendance).filter(
                models.DBAttendance.employee_id == emp.id,
                models.DBAttendance.client_id == client.id,
                models.DBAttendance.date >= body.period_start,
                models.DBAttendance.date <= body.period_end,
            ).all()
            hours = round(sum(r.total_hours or 0 for r in records), 2)

        ot_hours = round(sum(
            log.hours or 0 for log in db.query(models.DBOvertimeLog).filter(
                models.DBOvertimeLog.employee_id == emp.id,
                models.DBOvertimeLog.client_id == client.id,
                models.DBOvertimeLog.date >= body.period_start,
                models.DBOvertimeLog.date <= body.period_end,
                models.DBOvertimeLog.status == "announced",
            ).all()
        ), 2)

        figures = compute_payslip_figures(emp, {
            "hours_worked": hours, "overtime_hours": ot_hours,
            "bonus": emp.bonus or 0, "allowances": emp.allowances or 0,
        })
        ps = models.DBPayslip(
            client_id=client.id, employee_id=emp.id, number=f"PS-{seq:04d}",
            period_start=body.period_start, period_end=body.period_end, pay_date=body.pay_date,
            status="Draft", pay_frequency=emp.pay_frequency or "", **figures,
        )
        seq += 1
        db.add(ps)
        total_net += figures["net_pay"]
        total_gross += figures["gross_pay"]
        created.append({
            "employee_id": emp.id, "name": f"{emp.first_name} {emp.last_name}",
            "number": ps.number, "gross_pay": figures["gross_pay"], "net_pay": figures["net_pay"],
        })
        # A zero-value payslip is almost always missing data (an hourly worker
        # with no attendance logged) rather than a genuine nil payment. Surface
        # it instead of quietly paying someone nothing.
        if figures["gross_pay"] <= 0:
            warnings.append({
                "employee_id": emp.id, "name": f"{emp.first_name} {emp.last_name}",
                "number": ps.number,
                "reason": "no salary and no hours recorded for this period - payslip is zero",
            })

    if created:
        # Priced per payslip; charged once for the batch so a part-run cannot
        # be billed twice.
        require_credit(db, client.id, "payroll_run", len(created),
                       f"{body.period_start}..{body.period_end}")
    log_audit(db, client.id, "payroll_run", "payslip", None, f"{body.period_start}..{body.period_end}",
              f"{len(created)} payslips, net {total_net:.2f}", request)
    db.commit()
    return {
        "message": f"Generated {len(created)} payslip(s)",
        "created": created, "skipped": skipped, "warnings": warnings,
        "total_gross": money(total_gross), "total_net": money(total_net),
        "period_start": body.period_start, "period_end": body.period_end, "pay_date": body.pay_date,
    }


@app.get("/api/employees/{emp_id}/ytd")
def employee_ytd(emp_id: int, request: Request, year: str = "", db: Session = Depends(get_db)):
    """Year-to-date totals - required on most statutory payslip formats."""
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    year = year or datetime.now().strftime("%Y")
    slips = db.query(models.DBPayslip).filter(
        models.DBPayslip.client_id == client.id,
        models.DBPayslip.employee_id == emp_id,
        models.DBPayslip.status != "Void",
    ).all()
    in_year = [s for s in slips if (s.period_end or s.pay_date or "").startswith(year)]
    return {
        "year": year,
        "payslip_count": len(in_year),
        "gross_pay": money(sum(s.gross_pay or 0 for s in in_year)),
        "tax_amount": money(sum(s.tax_amount or 0 for s in in_year)),
        "total_deductions": money(sum(s.total_deductions or 0 for s in in_year)),
        "net_pay": money(sum(s.net_pay or 0 for s in in_year)),
    }

@app.get("/api/payslips/{ps_id}")
def get_payslip(ps_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ps = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps_id, models.DBPayslip.client_id == client.id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Payslip not found")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == ps.employee_id).first()
    settings_rows = db.query(models.DBSettings).filter(models.DBSettings.client_id == client.id).all()
    settings_map = {s.key: s.value for s in settings_rows}
    dept_name = ""
    if emp and emp.department_id:
        dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == emp.department_id).first()
        dept_name = dept.name if dept else ""
    ytd = employee_ytd(ps.employee_id, request, (ps.period_end or ps.pay_date or "")[:4], db) if emp else {}
    return {
        "id": ps.id, "number": ps.number,
        "employee_id": ps.employee_id,
        "ytd": ytd,
        "employee": {
            "full_name": f"{emp.first_name} {emp.last_name}" if emp else "",
            "employee_id": emp.employee_id if emp else "",
            "email": emp.email if emp else "",
            "job_title": emp.job_title if emp else "",
            "level": emp.level if emp else "",
            "department_name": dept_name, "bank_name": emp.bank_name if emp else "",
            "bank_account": emp.bank_account if emp else "", "tax_id": emp.tax_id if emp else "",
            "pay_frequency": emp.pay_frequency if emp else "",
        } if emp else {},
        "period_start": ps.period_start, "period_end": ps.period_end, "pay_date": ps.pay_date,
        "hours_worked": ps.hours_worked, "overtime_hours": ps.overtime_hours, "overtime_rate": ps.overtime_rate,
        "basic_salary": ps.basic_salary, "overtime_pay": ps.overtime_pay,
        "bonus": ps.bonus, "allowances": ps.allowances, "gross_pay": ps.gross_pay,
        "tax_amount": ps.tax_amount, "insurance": ps.insurance, "retirement": ps.retirement,
        "other_deductions": ps.other_deductions, "total_deductions": ps.total_deductions,
        # A standing deduction on the employee record is inside the total but
        # was never one of the shown lines, so a payslip did not add up.
        # Derived rather than stored, so payslips already issued reconcile too.
        "standing_deduction": money(
            (ps.total_deductions or 0) - (ps.tax_amount or 0) - (ps.insurance or 0)
            - (ps.retirement or 0) - (ps.other_deductions or 0)),
        "net_pay": ps.net_pay, "status": ps.status, "sent": ps.sent, "notes": ps.notes,
        "company": {
            "name": settings_map.get("company_name", "") or (client.company_name or ""),
            "address": settings_map.get("company_address", "") or (client.address or ""),
            "email": settings_map.get("email", "") or (client.email or ""),
            "phone": settings_map.get("phone_number", "") or (client.phone_number or ""),
            "abn": settings_map.get("company_abn", "") or (client.abn or ""),
            "logo_url": client.logo_url or "",
        },
    }

PAYSLIP_PAY_INPUTS = (
    "hours_worked", "overtime_hours", "overtime_rate", "basic_salary",
    "bonus", "allowances", "tax_amount", "insurance", "retirement", "other_deductions",
)
PAYSLIP_META_FIELDS = ("period_start", "period_end", "pay_date", "notes", "status")


@app.put("/api/payslips/{ps_id}")
def update_payslip(ps_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Edit a payslip and re-derive gross/net.

    Previously the totals were frozen while the components were editable, so an
    edited payslip reported a net figure that no longer matched its own lines.
    """
    client = get_client_user(request, db)
    ps = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps_id, models.DBPayslip.client_id == client.id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Payslip not found")
    if ps.status == "Paid":
        raise HTTPException(status_code=409, detail="A paid payslip cannot be edited")
    body = body or {}
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == ps.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    for key in PAYSLIP_META_FIELDS:
        if key in body and body[key] is not None:
            setattr(ps, key, body[key])

    inputs = {key: getattr(ps, key) for key in PAYSLIP_PAY_INPUTS}
    for key in PAYSLIP_PAY_INPUTS:
        if key in body and body[key] is not None:
            inputs[key] = body[key]

    for key, val in compute_payslip_figures(emp, inputs).items():
        setattr(ps, key, val)

    log_audit(db, client.id, "payslip_updated", "payslip", ps.id, ps.number, f"Net: {ps.net_pay:.2f}", request)
    db.commit()
    return {
        "message": "Payslip updated",
        "gross_pay": ps.gross_pay, "total_deductions": ps.total_deductions, "net_pay": ps.net_pay,
    }

@app.post("/api/payslips/{ps_id}/mark-paid")
def mark_payslip_paid(ps_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ps = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps_id, models.DBPayslip.client_id == client.id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Payslip not found")
    ps.status = "Paid"
    ps.pay_date = ps.pay_date or datetime.now().strftime("%Y-%m-%d")
    log_audit(db, client.id, "payslip_marked_paid", "payslip", ps.id, ps.number, f"Net: {ps.net_pay}", request)
    db.commit()
    return {"message": "Payslip marked as paid"}

@app.post("/api/payslips/{ps_id}/unmark-paid")
def unmark_payslip_paid(ps_id: int, request: Request, db: Session = Depends(get_db)):
    """Undo a mark-as-paid entered by mistake."""
    client = get_client_user(request, db)
    ps = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps_id, models.DBPayslip.client_id == client.id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Payslip not found")
    ps.status = "Sent" if ps.sent else "Draft"
    log_audit(db, client.id, "payslip_unmarked_paid", "payslip", ps.id, ps.number, "", request)
    db.commit()
    return {"message": "Payslip reopened", "status": ps.status}


@app.delete("/api/payslips/{ps_id}")
def delete_payslip(ps_id: int, request: Request, force: bool = False, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ps = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps_id, models.DBPayslip.client_id == client.id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Payslip not found")
    if ps.status == "Paid" and not force:
        raise HTTPException(
            status_code=409,
            detail="This payslip is marked as paid. Reopen it first, or pass force=true to delete anyway.",
        )
    log_audit(db, client.id, "payslip_deleted", "payslip", ps.id, ps.number, f"Net: {ps.net_pay}", request)
    db.delete(ps)
    db.commit()
    return {"message": "Payslip deleted"}

@app.post("/api/payslips/{ps_id}/send")
def send_payslip_email(ps_id: int, request: Request, background_tasks: BackgroundTasks, payload: Optional[SendInvoiceEmail] = None, db: Session = Depends(get_db)):
    if payload is None:
        payload = SendInvoiceEmail()
    client = get_client_user(request, db)
    ps = db.query(models.DBPayslip).filter(models.DBPayslip.id == ps_id, models.DBPayslip.client_id == client.id).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Payslip not found")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == ps.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not emp.email or not validate_email_address(emp.email):
        raise HTTPException(status_code=400, detail=f"Invalid employee email address")

    settings_rows = db.query(models.DBSettings).filter(models.DBSettings.client_id == client.id).all()
    settings_map = {s.key: s.value for s in settings_rows}
    company_name = settings_map.get("company_name", "") or client.company_name or "aniprotech"
    company_email = settings_map.get("email", "") or client.email or ""
    company_phone = settings_map.get("phone_number", "") or client.phone_number or ""
    company_address = settings_map.get("company_address", "") or client.address or ""

    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
    sender_name = os.getenv("FROM_NAME", "aniprotech")
    from_header = f"{sender_name} <{from_email}>"
    subject = f"Payslip {ps.number} from {company_name}"

    logo_data = client.logo_url or ""
    logo_html = f'<div style="margin-bottom:24px;"><img src="{esc(logo_data)}" style="max-height:48px;max-width:200px;"></div>' if logo_data else ""

    body_text = f"""Hello {esc(emp.first_name)},

Please find your payslip {ps.number} for the period {ps.period_start} to {ps.period_end}.

Pay Date: {ps.pay_date}
Gross Pay: \u00a3{ps.gross_pay:.2f}
Tax: \u00a3{ps.tax_amount:.2f}
Total Deductions: \u00a3{ps.total_deductions:.2f}
Net Pay: \u00a3{ps.net_pay:.2f}

Best regards,
{company_name}
{company_address}
{company_email}
{company_phone}"""

    html_body = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,Helvetica,sans-serif;color:#1e293b;margin:0;padding:0;background-color:#f1f5f9;">
<div style="max-width:600px;margin:0 auto;padding:40px 20px;">
<div style="background:#fff;border-radius:12px;overflow:hidden;">
<div style="background-color:#0f172a;padding:40px;text-align:center;">
{logo_html}
<h1 style="font-size:32px;font-weight:800;color:#fff;margin:0 0 8px 0;">PAYSLIP</h1>
<p style="font-size:16px;color:#94a3b8;margin:0;">{esc(ps.number)}</p>
<div style="margin-top:16px;display:inline-block;background-color:#0ea5e9;padding:8px 20px;border-radius:20px;">
<span style="font-size:14px;color:#fff;font-weight:600;">Net Pay: &pound;{ps.net_pay:.2f}</span>
</div>
</div>
<div style="background-color:#f8fafc;padding:16px 40px;border-bottom:1px solid #e2e8f0;">
<div style="font-size:13px;color:#475569;"><strong style="color:#1e293b;">{esc(company_name)}</strong>{f' &bull; {esc(company_address)}' if company_address else ''}{f' &bull; {esc(company_email)}' if company_email else ''}</div>
</div>
<div style="padding:40px;">
<p style="font-size:16px;color:#1e293b;margin:0 0 6px 0;">Hello <strong>{esc(emp.first_name)}</strong>,</p>
<p style="font-size:14px;color:#64748b;margin:0 0 24px 0;">Here's your payslip from <strong>{esc(company_name)}</strong> for the period {esc(ps.period_start)} to {esc(ps.period_end)}.</p>
<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:24px;">
<tr>
<td style="background-color:#f1f5f9;border-radius:10px;padding:16px;text-align:center;width:33%;">
<div style="font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Period Start</div>
<div style="font-size:14px;font-weight:600;">{ps.period_start}</div>
</td>
<td style="width:10px;"></td>
<td style="background-color:#f1f5f9;border-radius:10px;padding:16px;text-align:center;width:33%;">
<div style="font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Period End</div>
<div style="font-size:14px;font-weight:600;">{ps.period_end}</div>
</td>
<td style="width:10px;"></td>
<td style="background-color:#f1f5f9;border-radius:10px;padding:16px;text-align:center;width:33%;">
<div style="font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Pay Date</div>
<div style="font-size:14px;font-weight:600;">{ps.pay_date}</div>
</td>
</tr>
</table>
<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:24px;">
<tr style="background-color:#f8fafc;"><th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;border-bottom:2px solid #e2e8f0;">Description</th><th style="padding:10px 16px;text-align:right;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;border-bottom:2px solid #e2e8f0;">Amount</th></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;font-size:14px;">Basic Salary</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;font-weight:600;font-size:14px;">&pound;{ps.basic_salary:.2f}</td></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;font-size:14px;">Overtime Pay</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;font-weight:600;font-size:14px;">&pound;{ps.overtime_pay:.2f}</td></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;font-size:14px;">Bonus</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;font-weight:600;font-size:14px;">&pound;{ps.bonus:.2f}</td></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;font-size:14px;">Allowances</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;font-weight:600;font-size:14px;">&pound;{ps.allowances:.2f}</td></tr>
<tr style="font-weight:700;background-color:#f0fdf4;"><td style="padding:12px 16px;font-size:14px;">Gross Pay</td><td style="padding:12px 16px;text-align:right;color:#16a34a;font-size:14px;">&pound;{ps.gross_pay:.2f}</td></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">Tax</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">-&pound;{ps.tax_amount:.2f}</td></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">Insurance</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">-&pound;{ps.insurance:.2f}</td></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">Retirement</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">-&pound;{ps.retirement:.2f}</td></tr>
<tr><td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">Other Deductions</td><td style="padding:10px 16px;text-align:right;border-bottom:1px solid #f1f5f9;color:#dc2626;font-size:14px;">-&pound;{ps.other_deductions:.2f}</td></tr>
<tr style="font-weight:700;background-color:#fef2f2;"><td style="padding:12px 16px;font-size:14px;">Total Deductions</td><td style="padding:12px 16px;text-align:right;color:#dc2626;font-size:14px;">-&pound;{ps.total_deductions:.2f}</td></tr>
</table>
<div style="background-color:#0f172a;border-radius:12px;padding:24px;text-align:right;">
<div style="font-size:13px;color:#94a3b8;margin-bottom:4px;">NET PAY</div>
<div style="font-size:32px;font-weight:800;color:#10b981;">&pound;{ps.net_pay:.2f}</div>
</div>
</div>
<div style="padding:24px 40px;background-color:#f8fafc;border-top:1px solid #e2e8f0;text-align:center;">
<p style="font-size:13px;color:#94a3b8;margin:0;">Thank you for your hard work!</p>
<p style="font-size:12px;color:#64748b;margin:4px 0 0 0;">{esc(company_name)}</p>
<p style="font-size:11px;color:#94a3b8;margin:12px 0 0 0;"><a href="mailto:hello@keyroutes.co?subject=unsubscribe" style="color:#94a3b8;">Unsubscribe</a> from these notifications</p>
</div>
</div>
</div><img src="{request.base_url}api/payslip/track/open/{ps.tracking_id}" width="1" height="1" style="display:none;" alt="">
</body></html>
"""

    pdf_b64 = payload.pdf_data if payload.pdf_data else None
    pdf_filename = f"{ps.number}.pdf" if pdf_b64 else "payslip.pdf"

    require_credit(db, client.id, "payslip_send", 1, ps.number)

    background_tasks.add_task(send_email_background, emp.email, subject, body_text, from_header, html_body, pdf_b64, pdf_filename, logo_data, client_id=client.id)
    ps.status = "Sent" if ps.status == "Draft" else ps.status
    ps.sent = datetime.now().strftime("%Y-%m-%d")
    db.commit()
    return {"message": "Payslip email sent", "status": ps.status}

@app.get("/api/payslip/track/open/{tracking_id}")
def track_payslip_open(tracking_id: str, db: Session = Depends(get_db)):
    ps = db.query(models.DBPayslip).filter(models.DBPayslip.tracking_id == tracking_id).first()
    if ps:
        ps.open_count = (ps.open_count or 0) + 1
        ps.last_opened = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
    response = Response(content=TRACKING_PIXEL, media_type="image/gif")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

# --- Org Chart API ---

@app.get("/api/org-chart")
def get_org_chart(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    employees = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        models.DBEmployee.status.in_(["active", "onboarding"])
    ).all()
    departments = db.query(models.DBDepartment).filter(models.DBDepartment.client_id == client.id).all()

    emp_map = {}
    for e in employees:
        dept_name = ""
        if e.department_id:
            dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == e.department_id).first()
            dept_name = dept.name if dept else ""
        emp_map[e.id] = {
            "id": e.id, "employee_id": e.employee_id,
            "name": f"{e.first_name} {e.last_name}",
            "job_title": e.job_title, "email": e.email,
            "level": e.level or "", "role": e.role or "employee",
            "department": dept_name, "reports_to": e.reports_to,
            "status": e.status,
        }

    roots = []
    for e_id, e_data in emp_map.items():
        if e_data["reports_to"] and e_data["reports_to"] in emp_map:
            parent = emp_map[e_data["reports_to"]]
            if "children" not in parent:
                parent["children"] = []
            parent["children"].append(e_data)
        else:
            roots.append(e_data)

    dept_groups = {}
    for d in departments:
        dept_employees = [e for e in emp_map.values() if e["department"] == d.name]
        if dept_employees:
            dept_groups[d.name] = dept_employees

    return {"roots": roots, "departments": dept_groups, "total_employees": len(employees)}

# --- HR Dashboard Stats ---

@app.get("/api/hr/stats")
def get_hr_stats(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    total = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id).count()
    active = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id, models.DBEmployee.status == "active").count()
    onboarding = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id, models.DBEmployee.status == "onboarding").count()
    offboarding = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id, models.DBEmployee.status == "offboarding").count()
    terminated = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id, models.DBEmployee.status == "terminated").count()
    depts = db.query(models.DBDepartment).filter(models.DBDepartment.client_id == client.id).count()
    total_payroll = db.query(sqlfunc.coalesce(sqlfunc.sum(models.DBPayslip.net_pay), 0)).filter(models.DBPayslip.client_id == client.id, models.DBPayslip.status == "Paid").scalar()
    pending_payroll = db.query(sqlfunc.coalesce(sqlfunc.sum(models.DBPayslip.net_pay), 0)).filter(models.DBPayslip.client_id == client.id, models.DBPayslip.status != "Paid").scalar()
    return {
        "total_employees": total, "active": active, "onboarding": onboarding,
        "offboarding": offboarding, "terminated": terminated,
        "departments": depts,
        "total_payroll": round(float(total_payroll), 2),
        "pending_payroll": round(float(pending_payroll), 2),
    }

@app.get("/api/hr/dashboard")
def get_hr_dashboard(request: Request, db: Session = Depends(get_db)):
    """The HR portal had no landing page - it opened on the employee list, so
    anything waiting on a decision was only found by going looking for it.

    Built around what is outstanding rather than what is impressive: who is
    missing today, and what queues have somebody waiting at the other end.
    """
    client = get_client_user(request, db)
    cid = client.id
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    def emps(*statuses):
        q = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == cid)
        return q.filter(models.DBEmployee.status.in_(statuses)) if statuses else q

    def name_of(emp):
        return f"{emp.first_name} {emp.last_name}".strip() or emp.email or "Unknown"

    headcount = {
        "total": emps().count(),
        "active": emps("active").count(),
        "onboarding": emps("onboarding").count(),
        "offboarding": emps("offboarding").count(),
    }

    # --- today ---------------------------------------------------------------
    expected = emps("active", "onboarding").all()
    present_ids = {
        a.employee_id for a in db.query(models.DBAttendance).filter(
            models.DBAttendance.client_id == cid,
            models.DBAttendance.date == today,
            models.DBAttendance.clock_in != "",
        ).all() if a.clock_in
    }
    # A leave that straddles today counts, not only one that starts on it.
    on_leave = db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.client_id == cid,
        models.DBLeaveRequest.status == "approved",
        models.DBLeaveRequest.start_date <= today,
        models.DBLeaveRequest.end_date >= today,
    ).all()
    leave_ids = {lv.employee_id for lv in on_leave}
    by_id = {e.id: e for e in expected}

    unaccounted = [name_of(e) for e in expected
                   if e.id not in present_ids and e.id not in leave_ids]

    today_block = {
        "date": today,
        "expected": len(expected),
        "clocked_in": len([e for e in expected if e.id in present_ids]),
        "on_leave": [
            {"name": name_of(by_id[lv.employee_id]), "type": lv.leave_type,
             "until": lv.end_date}
            for lv in on_leave if lv.employee_id in by_id
        ],
        # Not called "absent" - nobody has said they are, only that nothing has
        # been recorded either way.
        "unaccounted_for": unaccounted[:8],
        "unaccounted_count": len(unaccounted),
    }

    # --- queues with somebody waiting ---------------------------------------
    pending_leave = db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.client_id == cid,
        models.DBLeaveRequest.status == "pending").count()
    open_requests = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.client_id == cid,
        models.DBStaffRequest.status == "open").count()
    docs_to_review = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == cid,
        models.DBDocumentRequest.status == "submitted").count()
    docs_outstanding = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == cid,
        models.DBDocumentRequest.status == "pending").count()
    unpaid = db.query(models.DBPayslip).filter(
        models.DBPayslip.client_id == cid,
        models.DBPayslip.status != "Paid").all()
    bank_changes = db.query(models.DBProfileChange).filter(
        models.DBProfileChange.client_id == cid,
        models.DBProfileChange.status == "pending").count()

    waiting = [
        {"key": "leave", "label": "Leave requests to decide", "count": pending_leave,
         "view": "leave-view"},
        {"key": "requests", "label": "Staff requests unanswered", "count": open_requests,
         "view": "staff-requests-view"},
        # Somebody's wages are waiting on this one.
        {"key": "bank_changes", "label": "Bank detail changes to approve",
         "count": bank_changes, "view": "staff-requests-view"},
        {"key": "documents", "label": "Documents to review", "count": docs_to_review,
         "view": "onboarding-hub-view"},
        {"key": "chasing", "label": "Documents not sent in yet", "count": docs_outstanding,
         "view": "onboarding-hub-view"},
        {"key": "payroll", "label": "Payslips not paid", "count": len(unpaid),
         "view": "payroll-view"},
    ]

    # --- what lands soon -----------------------------------------------------
    in_14 = (now + timedelta(days=14)).strftime("%Y-%m-%d")
    in_7 = (now + timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    in_30 = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    starting = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == cid,
        models.DBEmployee.start_date >= today,
        models.DBEmployee.start_date <= in_14,
    ).order_by(models.DBEmployee.start_date).limit(5).all()

    interviews = db.query(models.DBInterview).filter(
        models.DBInterview.client_id == cid,
        models.DBInterview.status == "scheduled",
        models.DBInterview.scheduled_at >= now.strftime("%Y-%m-%d %H:%M"),
        models.DBInterview.scheduled_at <= in_7,
    ).order_by(models.DBInterview.scheduled_at).limit(5).all()

    expiring = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == cid,
        models.DBDocumentRequest.expires_on != "",
        models.DBDocumentRequest.expires_on >= today,
        models.DBDocumentRequest.expires_on <= in_30,
    ).order_by(models.DBDocumentRequest.expires_on).limit(5).all()

    all_emp = {e.id: e for e in emps().all()}
    coming_up = {
        "starting": [{"name": name_of(e), "date": e.start_date,
                      "title": e.job_title or ""} for e in starting],
        "interviews": [{"round": i.round_name, "at": i.scheduled_at,
                        "interviewer": i.interviewer_name or ""} for i in interviews],
        "expiring_documents": [
            {"name": d.name, "expires_on": d.expires_on,
             "employee": name_of(all_emp[d.employee_id]) if d.employee_id in all_emp else ""}
            for d in expiring],
    }

    return {
        "headcount": headcount,
        "today": today_block,
        "waiting_on_you": waiting,
        # Summed here so the page does not have to know which ones count.
        "waiting_total": sum(w["count"] for w in waiting),
        "coming_up": coming_up,
    }


# --- Attendance API ---

@app.post("/api/attendance/clock-in")
def clock_in(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body or not body.get("employee_id"):
        raise HTTPException(status_code=400, detail="employee_id required")
    emp_id = body["employee_id"]
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    today = datetime.now().strftime("%Y-%m-%d")
    existing = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client.id,
    ).first()
    if existing:
        if existing.clock_in:
            raise HTTPException(status_code=400, detail="Already clocked in today")
        existing.clock_in = datetime.now().strftime("%H:%M:%S")
        existing.status = "present"
        db.commit()
        return {"message": "Clocked in", "clock_in": existing.clock_in}
    att = models.DBAttendance(
        client_id=client.id, employee_id=emp_id, date=today,
        clock_in=datetime.now().strftime("%H:%M:%S"), status="present",
    )
    db.add(att)
    db.commit()
    return {"message": "Clocked in", "clock_in": att.clock_in}

@app.post("/api/attendance/clock-out")
def clock_out(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body or not body.get("employee_id"):
        raise HTTPException(status_code=400, detail="employee_id required")
    emp_id = body["employee_id"]
    today = datetime.now().strftime("%Y-%m-%d")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client.id,
    ).first()
    if not att or not att.clock_in:
        raise HTTPException(status_code=400, detail="Not clocked in today")
    if att.clock_out:
        raise HTTPException(status_code=400, detail="Already clocked out today")
    att.clock_out = datetime.now().strftime("%H:%M:%S")
    try:
        cin = datetime.strptime(att.clock_in, "%H:%M:%S")
        cout = datetime.strptime(att.clock_out, "%H:%M:%S")
        att.total_hours = round((cout - cin).total_seconds() / 3600, 2)
    except Exception:
        att.total_hours = 0.0
    att.status = "completed"
    db.commit()
    return {"message": "Clocked out", "clock_out": att.clock_out, "total_hours": att.total_hours}

@app.get("/api/attendance")
def get_attendance(request: Request, employee_id: int = 0, date: str = "", db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    query = db.query(models.DBAttendance).filter(models.DBAttendance.client_id == client.id)
    if employee_id:
        query = query.filter(models.DBAttendance.employee_id == employee_id)
    if date:
        query = query.filter(models.DBAttendance.date == date)
    records = query.order_by(models.DBAttendance.date.desc(), models.DBAttendance.clock_in.desc()).limit(200).all()

    # One query for the people, not one per row. This loop used to issue a
    # lookup per record, so a full page was 201 queries for 200 rows.
    emp_ids = {a.employee_id for a in records}
    emps = {}
    if emp_ids:
        emps = {e.id: e for e in db.query(models.DBEmployee).filter(
            models.DBEmployee.id.in_(emp_ids)).all()}

    result = []
    for a in records:
        emp = emps.get(a.employee_id)
        result.append({
            "id": a.id, "employee_id": a.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "",
            "employee_email": emp.email if emp else "",
            "date": a.date, "clock_in": a.clock_in, "clock_out": a.clock_out,
            "total_hours": a.total_hours, "status": a.status, "notes": a.notes,
            "created_at": a.created_at,
            # The history table has had Type and Location columns all along and
            # they were never sent, so both read "-" on every row for everyone.
            "check_type": a.check_type, "location_label": a.location_label,
            "break_minutes": a.break_minutes, "overtime_hours": a.overtime_hours,
        })
    return result

@app.get("/api/attendance/today")
def get_today_attendance(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    today = datetime.now().strftime("%Y-%m-%d")
    records = db.query(models.DBAttendance).filter(
        models.DBAttendance.client_id == client.id,
        models.DBAttendance.date == today,
    ).all()
    result = []
    for a in records:
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == a.employee_id).first()
        result.append({
            "id": a.id, "employee_id": a.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "",
            "date": a.date, "clock_in": a.clock_in, "clock_out": a.clock_out,
            "total_hours": a.total_hours, "status": a.status,
        })
    return result

@app.get("/api/attendance/stats")
def get_attendance_stats(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    today = datetime.now().strftime("%Y-%m-%d")
    total_employees = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        models.DBEmployee.status.in_(["active", "onboarding"]),
    ).count()
    today_records = db.query(models.DBAttendance).filter(
        models.DBAttendance.client_id == client.id,
        models.DBAttendance.date == today,
    ).all()
    present = sum(1 for r in today_records if r.status in ("present", "completed"))
    absent = total_employees - present
    avg_hours = 0.0
    if today_records:
        avg_hours = round(sum(r.total_hours for r in today_records) / len(today_records), 2)
    return {
        "total_employees": total_employees,
        "present": present,
        "absent": max(0, absent),
        "avg_hours": avg_hours,
        "date": today,
    }

@app.get("/api/attendance/live")
def get_live_attendance(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    today = datetime.now().strftime("%Y-%m-%d")
    all_active = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        models.DBEmployee.status.in_(["active", "onboarding"]),
    ).all()
    today_records = db.query(models.DBAttendance).filter(
        models.DBAttendance.client_id == client.id,
        models.DBAttendance.date == today,
    ).all()
    record_map = {r.employee_id: r for r in today_records}
    result = []
    for emp in all_active:
        rec = record_map.get(emp.id)
        dept_name = ""
        if emp.department_id:
            dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == emp.department_id).first()
            dept_name = dept.name if dept else ""
        result.append({
            "id": emp.id, "employee_id": emp.employee_id,
            "full_name": f"{emp.first_name} {emp.last_name}",
            "email": emp.email, "job_title": emp.job_title,
            "department": dept_name, "status": emp.status,
            "clock_in": rec.clock_in if rec else "",
            "clock_out": rec.clock_out if rec else "",
            "total_hours": rec.total_hours if rec else 0,
            "attendance_status": rec.status if rec else "absent",
            "location_label": rec.location_label if rec else "",
            "ip_address": rec.ip_address if rec else "",
            "check_type": rec.check_type if rec else "",
        })
    return result

@app.get("/api/attendance/analytics")
def get_attendance_analytics(request: Request, days: int = 30, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    from datetime import timedelta
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    records = db.query(models.DBAttendance).filter(
        models.DBAttendance.client_id == client.id,
        models.DBAttendance.date >= start_date,
    ).all()
    total_employees = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id,
        models.DBEmployee.status.in_(["active", "onboarding"]),
    ).count()
    daily_stats = {}
    late_count = 0
    overtime_count = 0
    total_hours_all = 0
    remote_count = 0
    for r in records:
        d = r.date
        if d not in daily_stats:
            daily_stats[d] = {"present": 0, "absent": 0, "hours": 0}
        daily_stats[d]["present"] += 1
        daily_stats[d]["hours"] += r.total_hours or 0
        total_hours_all += r.total_hours or 0
        if r.clock_in and r.clock_in > "09:15":
            late_count += 1
        if r.overtime_hours and r.overtime_hours > 0:
            overtime_count += 1
        if r.location_label and "remote" in r.location_label.lower():
            remote_count += 1
    days_with_data = max(len(daily_stats), 1)
    for d in daily_stats:
        daily_stats[d]["absent"] = total_employees - daily_stats[d]["present"]
    return {
        "period_days": days,
        "total_records": len(records),
        "avg_daily_hours": round(total_hours_all / max(len(records), 1), 2),
        "late_arrivals": late_count,
        "overtime_sessions": overtime_count,
        "remote_sessions": remote_count,
        "avg_attendance_rate": round(sum(d["present"] for d in daily_stats.values()) / (days_with_data * max(total_employees, 1)) * 100, 1),
        "daily": dict(sorted(daily_stats.items())),
    }

@app.get("/api/attendance/export")
def export_attendance(request: Request, start_date: str = "", end_date: str = "", db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    query = db.query(models.DBAttendance).filter(models.DBAttendance.client_id == client.id)
    if start_date:
        query = query.filter(models.DBAttendance.date >= start_date)
    if end_date:
        query = query.filter(models.DBAttendance.date <= end_date)
    records = query.order_by(models.DBAttendance.date.desc()).limit(1000).all()
    rows = []
    for r in records:
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == r.employee_id).first()
        rows.append({
            "Employee": f"{emp.first_name} {emp.last_name}" if emp else "",
            "Email": emp.email if emp else "",
            "Date": r.date, "Clock In": r.clock_in, "Clock Out": r.clock_out,
            "Hours": r.total_hours, "Status": r.status, "Type": r.check_type,
            "Location": r.location_label, "IP": r.ip_address,
            "Overtime": r.overtime_hours, "Notes": r.notes,
        })
    return rows

@app.post("/api/attendance/overtime/announce")
def announce_overtime(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body or not body.get("employee_id") or not body.get("hours"):
        raise HTTPException(status_code=400, detail="employee_id and hours required")
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == body["employee_id"],
        models.DBEmployee.client_id == client.id,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    date = body.get("date", datetime.now().strftime("%Y-%m-%d"))
    hours = float(body["hours"])
    reason = body.get("reason", "")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp.id,
        models.DBAttendance.date == date,
        models.DBAttendance.client_id == client.id,
    ).first()
    if att:
        att.overtime_hours = hours
        att.overtime_announced = True
        att.overtime_announced_by = client.company_name or client.contact_name or "HR"
    log = models.DBOvertimeLog(
        client_id=client.id, employee_id=emp.id, date=date,
        hours=hours, reason=reason,
        announced_by=client.company_name or client.contact_name or "HR",
        status="announced",
    )
    db.add(log)
    db.commit()
    return {"message": f"Overtime of {hours}h announced for {emp.first_name} {emp.last_name}"}

@app.get("/api/attendance/overtime/logs")
def get_overtime_logs(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    logs = db.query(models.DBOvertimeLog).filter(
        models.DBOvertimeLog.client_id == client.id
    ).order_by(models.DBOvertimeLog.created_at.desc()).limit(100).all()
    result = []
    for l in logs:
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == l.employee_id).first()
        result.append({
            "id": l.id, "employee_id": l.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "",
            "date": l.date, "hours": l.hours, "reason": l.reason,
            "announced_by": l.announced_by, "status": l.status,
            "created_at": l.created_at,
        })
    return result

@app.put("/api/attendance/settings")
def update_attendance_settings(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    settings = db.query(models.DBAttendanceSettings).filter(models.DBAttendanceSettings.client_id == client.id).first()
    if not settings:
        settings = models.DBAttendanceSettings(client_id=client.id)
        db.add(settings)
    if body:
        for key, val in body.items():
            if not hasattr(settings, key) or key in ("id", "client_id", "created_at"):
                continue
            if key == "working_days":
                # Normalised, so a stray value cannot leave a tenant with no
                # working days at all.
                val = clean_working_days(val)
            elif key == "auto_clock_in":
                val = bool(val)
            setattr(settings, key, val)
    db.commit()
    return {"message": "Settings saved"}

@app.get("/api/attendance/settings")
def get_attendance_settings(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    settings = db.query(models.DBAttendanceSettings).filter(models.DBAttendanceSettings.client_id == client.id).first()
    if not settings:
        return {
            "office_name": "Head Office", "office_lat": 0.0, "office_lng": 0.0,
            "geofence_radius": 200.0, "work_start": "09:00", "work_end": "17:30",
            "grace_minutes": 15.0, "auto_clockout_hours": 10.0, "max_overtime_hours": 4.0,
            "allow_remote": True, "require_location": True,
            "working_days": DEFAULT_WORKING_DAYS, "auto_clock_in": True,
        }
    return {
        "office_name": settings.office_name, "office_lat": settings.office_lat,
        "office_lng": settings.office_lng, "geofence_radius": settings.geofence_radius,
        "work_start": settings.work_start, "work_end": settings.work_end,
        "grace_minutes": settings.grace_minutes,
        "auto_clockout_hours": settings.auto_clockout_hours,
        "max_overtime_hours": settings.max_overtime_hours,
        "allow_remote": settings.allow_remote, "require_location": settings.require_location,
        "working_days": clean_working_days(settings.working_days),
        "auto_clock_in": bool(settings.auto_clock_in),
    }

@app.put("/api/employees/{emp_id}/set-password")
def set_employee_password(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not body or not body.get("password"):
        raise HTTPException(status_code=400, detail="Password required")
    emp.password_hash = models.hash_password(body["password"])
    db.commit()
    return {"message": "Password set successfully"}

@app.post("/api/employee/auth/login")
def employee_login(request: Request, body: dict = None, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"emp_login:{ip}", max_requests=10, window=60):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    if not body or not body.get("email") or not body.get("password"):
        raise HTTPException(status_code=400, detail="Email and password required")
    email = body["email"].strip().lower()
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.email.ilike(email)).first()
    if not emp:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not emp.password_hash:
        raise HTTPException(status_code=401, detail="Password not set. Contact your administrator.")
    if not models.verify_password(body["password"], emp.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if emp.status in ("terminated",):
        raise HTTPException(status_code=403, detail="Account deactivated")
    start_employee_session(request, emp)

    today = datetime.now().strftime("%Y-%m-%d")
    who = {"id": emp.id, "name": f"{emp.first_name} {emp.last_name}", "email": emp.email}
    existing = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp.id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == emp.client_id,
    ).first()
    if existing and existing.clock_in:
        return {"message": "Already clocked in today", "employee": who,
                "clock_in": existing.clock_in}

    settings = attendance_settings_for(db, emp.client_id)
    working_day = is_working_day(settings)

    # The same helper the Google callback uses, so both ways of signing in
    # record attendance identically instead of drifting apart.
    att = auto_clock_in_on_sign_in(
        db, emp, request,
        lat=body.get("latitude", 0.0), lng=body.get("longitude", 0.0),
        device=body.get("device_info", ""),
        loc_label=body.get("location_label", ""))
    if not att:
        # Opening the portal on a day off - to read a payslip or upload a
        # document - is not a shift. The Clock In button is still there for
        # anyone who really is working.
        return {
            "message": "Signed in", "employee": who, "clock_in": "",
            "auto_clock_in": False, "is_working_day": working_day,
        }

    db.commit()
    return {
        "message": "Clocked in automatically",
        "employee": who,
        "clock_in": att.clock_in, "check_type": att.check_type,
        "auto_clock_in": True, "is_working_day": working_day,
    }

@app.post("/api/employee/auth/logout")
def employee_logout(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    client_id = request.session.get('employee_client_id')
    if not emp_id:
        return {"message": "Not logged in"}
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M:%S")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client_id,
    ).first()
    hours = 0.0
    if att and att.clock_in and not att.clock_out:
        if att.is_on_break and att.break_start:
            try:
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                bs = datetime.strptime(today_str + " " + att.break_start, "%Y-%m-%d %H:%M:%S")
                att.break_minutes = (att.break_minutes or 0) + round((now - bs).total_seconds() / 60, 1)
            except Exception:
                pass
            att.is_on_break = False
            att.break_start = ""
        att.clock_out = now_str
        try:
            cin = datetime.strptime(today + " " + att.clock_in, "%Y-%m-%d %H:%M:%S")
            cout = datetime.strptime(today + " " + now_str, "%Y-%m-%d %H:%M:%S")
            raw_hours = (cout - cin).total_seconds() / 3600
            break_hours = (att.break_minutes or 0) / 60
            att.total_hours = round(raw_hours - break_hours, 2)
            hours = att.total_hours
            att.status = "completed"
        except Exception:
            pass
        db.commit()
    request.session.pop('employee_id', None)
    request.session.pop('employee_client_id', None)
    return {"message": "Logged out", "total_hours": hours, "break_minutes": att.break_minutes if att else 0}

@app.get("/api/employee/auth/me")
def employee_me(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    dept_name = ""
    if emp.department_id:
        dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == emp.department_id).first()
        dept_name = dept.name if dept else ""
    today = datetime.now().strftime("%Y-%m-%d")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp.id,
        models.DBAttendance.date == today,
    ).first()
    return {
        "id": emp.id, "employee_id": emp.employee_id,
        "full_name": f"{emp.first_name} {emp.last_name}",
        "email": emp.email, "job_title": emp.job_title,
        "department": dept_name, "phone": emp.phone,
        "status": emp.status, "work_location": emp.work_location,
        "today_clock_in": att.clock_in if att else "",
        "today_clock_out": att.clock_out if att else "",
        "today_hours": att.total_hours if att else 0,
        "today_status": att.status if att else "absent",
        "today_is_on_break": att.is_on_break if att else False,
        "today_break_minutes": (att.break_minutes or 0) if att else 0,
    }

@app.post("/api/employee/attendance/clock-in")
def employee_clock_in(request: Request, body: dict = None, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    client_id = request.session.get('employee_client_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M:%S")
    existing = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client_id,
    ).first()
    if existing and existing.clock_in:
        raise HTTPException(status_code=400, detail="Already clocked in today")
    ip = request.client.host if request and request.client else ""
    device = ""
    lat = lng = 0.0
    loc_label = ""
    if body:
        ip = body.get("ip_address", ip)
        device = body.get("device_info", "")
        lat = body.get("latitude", 0.0)
        lng = body.get("longitude", 0.0)
        loc_label = body.get("location_label", "")
    check_type = "manual"
    if lat and lng:
        settings = db.query(models.DBAttendanceSettings).filter(models.DBAttendanceSettings.client_id == client_id).first()
        if settings and settings.office_lat and settings.office_lng:
            from math import radians, cos, sin, asin, sqrt
            dlat = radians(lat - settings.office_lat)
            dlng = radians(lng - settings.office_lng)
            a = sin(dlat/2)**2 + cos(radians(settings.office_lat)) * cos(radians(lat)) * sin(dlng/2)**2
            dist = 2 * 6371000 * asin(sqrt(a))
            if dist <= settings.geofence_radius:
                check_type = "office"
            else:
                check_type = "field"

    # Flag lateness against the configured start time + grace period. The
    # settings already existed but nothing ever read them.
    status = "present"
    minutes_late = 0
    att_settings = db.query(models.DBAttendanceSettings).filter(
        models.DBAttendanceSettings.client_id == client_id
    ).first()
    if att_settings and att_settings.work_start:
        try:
            expected = datetime.strptime(f"{today} {att_settings.work_start}", "%Y-%m-%d %H:%M")
            actual = datetime.strptime(f"{today} {now_str}", "%Y-%m-%d %H:%M:%S")
            grace = att_settings.grace_minutes or 0
            late_by = (actual - expected).total_seconds() / 60
            if late_by > grace:
                status = "late"
                minutes_late = int(round(late_by))
        except (ValueError, TypeError):
            pass

    if existing:
        # A row may already exist for today (e.g. marked absent); reuse it
        # rather than creating a duplicate for the same employee and date.
        existing.clock_in = now_str
        existing.status = status
        existing.check_type = check_type
        existing.ip_address = ip
        existing.device_info = device
        existing.location_lat = lat
        existing.location_lng = lng
        existing.location_label = loc_label
        att = existing
    else:
        att = models.DBAttendance(
            client_id=client_id, employee_id=emp_id, date=today,
            clock_in=now_str, status=status, check_type=check_type,
            ip_address=ip, device_info=device,
            location_lat=lat, location_lng=lng, location_label=loc_label,
        )
        db.add(att)
    db.commit()
    return {
        "message": "Clocked in", "clock_in": now_str, "check_type": check_type,
        "status": status, "minutes_late": minutes_late,
    }

@app.post("/api/employee/attendance/clock-out")
def employee_clock_out(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    client_id = request.session.get('employee_client_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M:%S")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client_id,
    ).first()
    if not att or not att.clock_in:
        raise HTTPException(status_code=400, detail="No clock-in found for today")
    if att.clock_out:
        raise HTTPException(status_code=400, detail="Already clocked out")
    if att.is_on_break:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            break_start = datetime.strptime(today_str + " " + att.break_start, "%Y-%m-%d %H:%M:%S")
            att.break_minutes += round((now - break_start).total_seconds() / 60, 1)
        except Exception:
            pass
        att.is_on_break = False
        att.break_start = ""
    att.clock_out = now_str
    try:
        from datetime import timedelta
        cin = datetime.strptime(today + " " + att.clock_in, "%Y-%m-%d %H:%M:%S")
        cout = datetime.strptime(today + " " + now_str, "%Y-%m-%d %H:%M:%S")
        # A clock-out earlier than the clock-in means the shift ran past
        # midnight. Without this, total_hours went negative and silently
        # corrupted the hours that payroll reads.
        if cout < cin:
            cout += timedelta(days=1)
        raw_hours = (cout - cin).total_seconds() / 3600
        break_hours = (att.break_minutes or 0) / 60
        att.total_hours = max(0.0, round(raw_hours - break_hours, 2))
        settings = db.query(models.DBAttendanceSettings).filter(models.DBAttendanceSettings.client_id == client_id).first()
        if settings:
            try:
                wh_start = datetime.strptime(settings.work_start, "%H:%M")
                wh_end = datetime.strptime(settings.work_end, "%H:%M")
                work_hours = (wh_end - wh_start).total_seconds() / 3600
            except Exception:
                work_hours = 8.0
            if att.total_hours > work_hours:
                overtime = round(att.total_hours - work_hours, 2)
                # Respect the configured overtime ceiling so a forgotten
                # clock-out cannot book an unbounded overtime claim.
                cap = settings.max_overtime_hours or 0
                att.overtime_hours = min(overtime, cap) if cap > 0 else overtime
        att.status = "completed"
    except Exception:
        logger.exception("Failed to compute hours for attendance %s", att.id)
    db.commit()
    return {"message": "Clocked out", "total_hours": att.total_hours, "overtime_hours": att.overtime_hours, "break_minutes": att.break_minutes}

@app.post("/api/employee/attendance/break-start")
def employee_break_start(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    client_id = request.session.get('employee_client_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%H:%M:%S")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client_id,
    ).first()
    if not att or not att.clock_in:
        raise HTTPException(status_code=400, detail="Not clocked in")
    if att.clock_out:
        raise HTTPException(status_code=400, detail="Already clocked out")
    if att.is_on_break:
        raise HTTPException(status_code=400, detail="Already on break")
    att.is_on_break = True
    att.break_start = now_str
    db.commit()
    return {"message": "Break started", "break_start": now_str}

@app.post("/api/employee/attendance/break-stop")
def employee_break_stop(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    client_id = request.session.get('employee_client_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    today = datetime.now().strftime("%Y-%m-%d")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client_id,
    ).first()
    if not att or not att.is_on_break:
        raise HTTPException(status_code=400, detail="Not on break")
    try:
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        break_start = datetime.strptime(today_str + " " + att.break_start, "%Y-%m-%d %H:%M:%S")
        elapsed = round((now - break_start).total_seconds() / 60, 1)
        att.break_minutes = (att.break_minutes or 0) + elapsed
    except Exception:
        logger.error(f"Failed to calculate break duration for attendance {att.id}")
    att.is_on_break = False
    att.break_start = ""
    db.commit()
    return {"message": "Break ended", "break_minutes": att.break_minutes}

@app.get("/api/employee/attendance/today")
def employee_today_attendance(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    client_id = request.session.get('employee_client_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    today = datetime.now().strftime("%Y-%m-%d")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
        models.DBAttendance.client_id == client_id,
    ).first()
    # The portal says why the Clock In button is waiting rather than filled in.
    working_day = is_working_day(attendance_settings_for(db, client_id))
    if not att:
        return {"clocked_in": False, "is_working_day": working_day}
    now_str = datetime.now().strftime("%H:%M:%S")
    elapsed = 0
    if att.clock_in and not att.clock_out:
        try:
            cin = datetime.strptime(today + " " + att.clock_in, "%Y-%m-%d %H:%M:%S")
            now_t = datetime.strptime(today + " " + now_str, "%Y-%m-%d %H:%M:%S")
            elapsed = round((now_t - cin).total_seconds() / 3600, 2)
            if att.is_on_break and att.break_start:
                bs = datetime.strptime(today + " " + att.break_start, "%Y-%m-%d %H:%M:%S")
                elapsed -= round((now_t - bs).total_seconds() / 3600, 2)
            elapsed -= (att.break_minutes or 0) / 60
            elapsed = round(max(0, elapsed), 2)
        except Exception:
            pass
    return {
        "clocked_in": bool(att.clock_in),
        "clock_in": att.clock_in,
        "clock_out": att.clock_out,
        "total_hours": att.total_hours,
        "is_on_break": att.is_on_break,
        "break_start": att.break_start,
        "break_minutes": att.break_minutes or 0,
        "overtime_hours": att.overtime_hours,
        "elapsed_hours": elapsed,
        "status": att.status,
    }

@app.get("/api/employee/dashboard")
def employee_dashboard(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    client_id = request.session.get('employee_client_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    from datetime import timedelta
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    records = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date >= thirty_days_ago,
    ).order_by(models.DBAttendance.date.desc()).limit(30).all()
    attendance = [{
        # The row id, so the portal can name the day it is asking to correct.
        # Without it the Fix button had nothing to send.
        "id": r.id,
        "date": r.date, "clock_in": r.clock_in, "clock_out": r.clock_out,
        "total_hours": r.total_hours, "status": r.status, "check_type": r.check_type,
        "break_minutes": r.break_minutes or 0, "overtime_hours": r.overtime_hours or 0,
        "is_on_break": r.is_on_break,
    } for r in records]
    payslips = db.query(models.DBPayslip).filter(models.DBPayslip.employee_id == emp_id).order_by(models.DBPayslip.created_at.desc()).limit(6).all()
    payslip_list = [{
        "number": p.number, "period_start": p.period_start, "period_end": p.period_end,
        "pay_date": p.pay_date, "net_pay": p.net_pay, "status": p.status,
    } for p in payslips]
    onboarding = db.query(models.DBOnboardingItem).filter(models.DBOnboardingItem.employee_id == emp_id).all()
    onboarding_list = [{
        "id": o.id, "title": o.title, "is_completed": o.is_completed,
        "category": o.category, "assigned_to": o.assigned_to,
    } for o in onboarding]
    ot_logs = db.query(models.DBOvertimeLog).filter(
        models.DBOvertimeLog.employee_id == emp_id,
        models.DBOvertimeLog.client_id == client_id,
    ).order_by(models.DBOvertimeLog.created_at.desc()).limit(10).all()
    overtime_list = [{
        "date": l.date, "hours": l.hours, "reason": l.reason,
        "announced_by": l.announced_by, "status": l.status,
    } for l in ot_logs]
    days_present = sum(1 for r in records if r.status in ("present", "completed"))
    total_hours = sum(max(r.total_hours, 0) for r in records if r.total_hours)
    total_breaks = sum(r.break_minutes or 0 for r in records)
    avg_hours = round(total_hours / max(len(records), 1), 2)
    return {
        "employee": {
            "full_name": f"{emp.first_name} {emp.last_name}", "email": emp.email,
            "job_title": emp.job_title, "salary": emp.salary, "pay_frequency": emp.pay_frequency,
            "bank_name": emp.bank_name, "bank_account": emp.bank_account, "tax_id": emp.tax_id,
        },
        "attendance_summary": {
            "days_present": days_present, "total_hours": round(total_hours, 2),
            "avg_hours": avg_hours, "total_break_minutes": round(total_breaks, 1),
        },
        "attendance": attendance,
        "payslips": payslip_list,
        "onboarding": onboarding_list,
        "overtime": overtime_list,
    }

@app.post("/api/employee/heartbeat")
def employee_heartbeat(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        return {"status": "no_session"}
    today = datetime.now().strftime("%Y-%m-%d")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date == today,
    ).first()
    if att and att.clock_in and not att.clock_out:
        try:
            cin = datetime.strptime(att.clock_in, "%H:%M:%S")
            now_time = datetime.strptime(datetime.now().strftime("%H:%M:%S"), "%H:%M:%S")
            elapsed = (now_time - cin).total_seconds() / 3600
            settings = db.query(models.DBAttendanceSettings).filter(models.DBAttendanceSettings.client_id == att.client_id).first()
            max_hours = settings.auto_clockout_hours if settings else 10.0
            if elapsed >= max_hours:
                att.clock_out = datetime.now().strftime("%H:%M:%S")
                att.total_hours = round(elapsed, 2)
                att.status = "completed"
                att.notes = "Auto clocked out"
                db.commit()
                return {"status": "auto_clocked_out", "total_hours": att.total_hours}
        except Exception:
            pass
    return {"status": "ok"}

# ============ JOB REQUISITIONS ============
# A requisition is the role being hired for. Application forms hang off it, so
# one job can have several intake forms (careers page, referral, agency) while
# reporting still rolls up to a single opening.

JOB_STATUSES = ("draft", "open", "on_hold", "closed", "filled")
WORK_MODES = ("onsite", "hybrid", "remote")


class JobRequisitionIn(BaseModel):
    title: str
    department_id: Optional[int] = None
    hiring_manager_id: Optional[int] = None
    description: Optional[str] = ""
    requirements: Optional[str] = ""
    location: Optional[str] = ""
    work_mode: Optional[str] = "onsite"
    employment_type: Optional[str] = "full_time"
    level: Optional[str] = ""
    salary_min: Optional[float] = 0.0
    salary_max: Optional[float] = 0.0
    show_salary: Optional[bool] = True
    openings: Optional[int] = 1
    closing_date: Optional[str] = ""
    status: Optional[str] = "draft"


def job_to_dict(job, db=None, counts=None):
    dept_name = job.department.name if job.department else ""
    manager_name = ""
    if job.hiring_manager:
        manager_name = f"{job.hiring_manager.first_name} {job.hiring_manager.last_name}"
    data = {
        "id": job.id, "reference": job.reference, "title": job.title,
        "department_id": job.department_id, "department_name": dept_name,
        "hiring_manager_id": job.hiring_manager_id, "hiring_manager_name": manager_name,
        "description": job.description or "", "requirements": job.requirements or "",
        "location": job.location or "", "work_mode": job.work_mode or "onsite",
        "employment_type": job.employment_type or "full_time", "level": job.level or "",
        "salary_min": job.salary_min or 0, "salary_max": job.salary_max or 0,
        "salary_currency": job.salary_currency or "", "show_salary": bool(job.show_salary),
        "openings": job.openings or 1, "status": job.status,
        "is_published": bool(job.is_published), "closing_date": job.closing_date or "",
        "opened_at": job.opened_at or "", "closed_at": job.closed_at or "",
        "created_at": job.created_at,
    }
    if counts is not None:
        data.update(counts)
    return data


def validate_job_payload(body, db, client_id):
    if not (body.title or "").strip():
        raise HTTPException(status_code=400, detail="A job title is required")
    status = (body.status or "draft").strip().lower()
    if status not in JOB_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(JOB_STATUSES)}")
    mode = (body.work_mode or "onsite").strip().lower()
    if mode not in WORK_MODES:
        raise HTTPException(status_code=400, detail=f"Work mode must be one of: {', '.join(WORK_MODES)}")
    # `or 1` would quietly turn an explicit 0 into 1 instead of rejecting it.
    try:
        openings = int(body.openings if body.openings is not None else 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Openings must be a whole number")
    if openings < 1 or openings > 999:
        raise HTTPException(status_code=400, detail="Openings must be between 1 and 999")
    lo, hi = float(body.salary_min or 0), float(body.salary_max or 0)
    if lo < 0 or hi < 0:
        raise HTTPException(status_code=400, detail="Salary cannot be negative")
    if lo and hi and lo > hi:
        raise HTTPException(status_code=400, detail="Minimum salary cannot exceed the maximum")
    if body.department_id:
        dept = db.query(models.DBDepartment).filter(
            models.DBDepartment.id == body.department_id,
            models.DBDepartment.client_id == client_id,
        ).first()
        if not dept:
            raise HTTPException(status_code=400, detail="Department not found")
    if body.hiring_manager_id:
        mgr = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == body.hiring_manager_id,
            models.DBEmployee.client_id == client_id,
        ).first()
        if not mgr:
            raise HTTPException(status_code=400, detail="Hiring manager not found")
    return status, mode, openings, validate_level(body.level)


@app.get("/api/recruitment/jobs")
def list_jobs(request: Request, status: str = "", db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    query = db.query(models.DBJobRequisition).filter(models.DBJobRequisition.client_id == client.id)
    if status:
        query = query.filter(models.DBJobRequisition.status == status)
    jobs = query.order_by(models.DBJobRequisition.id.desc()).all()

    # Applicant and hire counts per job, in two queries rather than per row.
    form_rows = db.query(models.DBRecruitmentForm.id, models.DBRecruitmentForm.job_id).filter(
        models.DBRecruitmentForm.client_id == client.id
    ).all()
    form_to_job = {fid: jid for fid, jid in form_rows if jid}
    applicants, hires = defaultdict(int), defaultdict(int)
    if form_to_job:
        subs = db.query(
            models.DBFormSubmission.form_id, models.DBFormSubmission.hired_employee_id
        ).filter(models.DBFormSubmission.form_id.in_(list(form_to_job.keys()))).all()
        for form_id, hired in subs:
            job_id = form_to_job.get(form_id)
            if not job_id:
                continue
            applicants[job_id] += 1
            if hired:
                hires[job_id] += 1
    return [job_to_dict(j, counts={
        "applicant_count": applicants.get(j.id, 0),
        "hired_count": hires.get(j.id, 0),
        "remaining_openings": max(0, (j.openings or 1) - hires.get(j.id, 0)),
    }) for j in jobs]


@app.post("/api/recruitment/jobs")
def create_job(request: Request, body: JobRequisitionIn, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    status, mode, openings, level = validate_job_payload(body, db, client.id)
    reference = next_sequence_number(db, models.DBJobRequisition, client.id, "JOB-", field="reference")
    now = datetime.now().strftime("%Y-%m-%d")
    job = models.DBJobRequisition(
        client_id=client.id, reference=reference, title=body.title.strip(),
        department_id=body.department_id, hiring_manager_id=body.hiring_manager_id,
        description=body.description or "", requirements=body.requirements or "",
        location=body.location or "", work_mode=mode,
        employment_type=body.employment_type or "full_time", level=level,
        salary_min=float(body.salary_min or 0), salary_max=float(body.salary_max or 0),
        salary_currency=client.currency or "", show_salary=bool(body.show_salary),
        openings=openings, status=status,
        is_published=(status == "open"),
        closing_date=body.closing_date or "",
        opened_at=now if status == "open" else "",
    )
    db.add(job)
    log_audit(db, client.id, "job_created", "job", None, f"{reference} {body.title}", "", request)
    db.commit()
    db.refresh(job)
    return job_to_dict(job)


@app.get("/api/recruitment/jobs/{job_id}")
def get_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    job = db.query(models.DBJobRequisition).filter(
        models.DBJobRequisition.id == job_id, models.DBJobRequisition.client_id == client.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    forms = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.job_id == job_id
    ).all()
    data = job_to_dict(job)
    data["forms"] = [{
        "id": f.id, "title": f.title, "form_token": f.form_token, "is_active": f.is_active
    } for f in forms]
    return data


@app.put("/api/recruitment/jobs/{job_id}")
def update_job(job_id: int, request: Request, body: JobRequisitionIn, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    job = db.query(models.DBJobRequisition).filter(
        models.DBJobRequisition.id == job_id, models.DBJobRequisition.client_id == client.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status, mode, openings, level = validate_job_payload(body, db, client.id)
    now = datetime.now().strftime("%Y-%m-%d")
    if status == "open" and job.status != "open":
        job.opened_at = job.opened_at or now
        job.closed_at = ""
    if status in ("closed", "filled") and job.status not in ("closed", "filled"):
        job.closed_at = now
    job.title = body.title.strip()
    job.department_id = body.department_id
    job.hiring_manager_id = body.hiring_manager_id
    job.description = body.description or ""
    job.requirements = body.requirements or ""
    job.location = body.location or ""
    job.work_mode = mode
    job.employment_type = body.employment_type or "full_time"
    job.level = level
    job.salary_min = float(body.salary_min or 0)
    job.salary_max = float(body.salary_max or 0)
    job.show_salary = bool(body.show_salary)
    job.openings = openings
    job.status = status
    job.is_published = status == "open"
    job.closing_date = body.closing_date or ""
    log_audit(db, client.id, "job_updated", "job", job.id, job.reference, f"Status: {status}", request)
    db.commit()
    return job_to_dict(job)


@app.delete("/api/recruitment/jobs/{job_id}")
def delete_job(job_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    job = db.query(models.DBJobRequisition).filter(
        models.DBJobRequisition.id == job_id, models.DBJobRequisition.client_id == client.id
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    linked = db.query(models.DBRecruitmentForm).filter(models.DBRecruitmentForm.job_id == job_id).count()
    if linked:
        raise HTTPException(
            status_code=409,
            detail=f"{linked} application form(s) are attached to this job. Detach or delete them first.",
        )
    log_audit(db, client.id, "job_deleted", "job", job.id, job.reference, "", request)
    db.delete(job)
    db.commit()
    return {"message": "Job deleted"}


@app.get("/api/public/jobs/{client_ref}")
def public_job_board(client_ref: str, db: Session = Depends(get_db)):
    """Open roles for a company's careers page. Public: only published jobs,
    and never anything that identifies internal staff."""
    try:
        client_id = int(client_ref)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Not found")
    client = db.query(models.DBClient).filter(
        models.DBClient.id == client_id, models.DBClient.is_active == True
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail="Not found")
    jobs = db.query(models.DBJobRequisition).filter(
        models.DBJobRequisition.client_id == client_id,
        models.DBJobRequisition.status == "open",
        models.DBJobRequisition.is_published == True,
    ).order_by(models.DBJobRequisition.id.desc()).all()

    today = datetime.now().date()
    listings = []
    for job in jobs:
        closing = _parse_date(job.closing_date)
        if closing and closing < today:
            continue
        form = db.query(models.DBRecruitmentForm).filter(
            models.DBRecruitmentForm.job_id == job.id,
            models.DBRecruitmentForm.is_active == True,
        ).first()
        listings.append({
            "id": job.id, "reference": job.reference, "title": job.title,
            "department": job.department.name if job.department else "",
            "location": job.location or "", "work_mode": job.work_mode,
            "employment_type": job.employment_type, "level": job.level or "",
            "description": job.description or "", "requirements": job.requirements or "",
            "salary_min": job.salary_min if job.show_salary else None,
            "salary_max": job.salary_max if job.show_salary else None,
            "salary_currency": job.salary_currency or client.currency or "",
            "closing_date": job.closing_date or "",
            "apply_token": form.form_token if form else None,
        })
    return {
        "company": client.company_name or "",
        "logo_url": client.logo_url or "",
        "jobs": listings,
    }


# ============ INTERVIEWS ============

INTERVIEW_MODES = ("video", "phone", "onsite")
INTERVIEW_STATUSES = ("scheduled", "completed", "cancelled", "no_show")
INTERVIEW_OUTCOMES = ("", "pass", "fail", "hold")


class InterviewIn(BaseModel):
    round_name: Optional[str] = "Interview"
    scheduled_at: str
    duration_minutes: Optional[int] = 45
    mode: Optional[str] = "video"
    location: Optional[str] = ""
    meeting_link: Optional[str] = ""
    interviewer_id: Optional[int] = None
    interviewer_name: Optional[str] = ""


def _get_submission_for_client(db, client_id, sub_id):
    sub = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.id == sub_id,
        models.DBFormSubmission.client_id == client_id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return sub


def interview_to_dict(iv):
    return {
        "id": iv.id, "submission_id": iv.submission_id, "round_name": iv.round_name,
        "scheduled_at": iv.scheduled_at, "duration_minutes": iv.duration_minutes,
        "mode": iv.mode, "location": iv.location, "meeting_link": iv.meeting_link,
        "interviewer_id": iv.interviewer_id, "interviewer_name": iv.interviewer_name,
        "status": iv.status, "outcome": iv.outcome, "score": iv.score,
        "feedback": iv.feedback, "created_at": iv.created_at,
    }


def _parse_datetime_minutes(value):
    """Accept 'YYYY-MM-DD HH:MM' or the HTML datetime-local 'YYYY-MM-DDTHH:MM'."""
    if not value:
        return None
    text_val = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text_val, fmt)
        except ValueError:
            continue
    return None


@app.get("/api/recruitment/submissions/{sub_id}/interviews")
def list_interviews(sub_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    _get_submission_for_client(db, client.id, sub_id)
    rows = db.query(models.DBInterview).filter(
        models.DBInterview.submission_id == sub_id
    ).order_by(models.DBInterview.scheduled_at.asc()).all()
    return [interview_to_dict(r) for r in rows]


@app.post("/api/recruitment/submissions/{sub_id}/interviews")
def schedule_interview(sub_id: int, request: Request, body: InterviewIn, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = _get_submission_for_client(db, client.id, sub_id)

    when = _parse_datetime_minutes(body.scheduled_at)
    if not when:
        raise HTTPException(status_code=400, detail="Scheduled time must look like YYYY-MM-DD HH:MM")
    mode = (body.mode or "video").strip().lower()
    if mode not in INTERVIEW_MODES:
        raise HTTPException(status_code=400, detail=f"Mode must be one of: {', '.join(INTERVIEW_MODES)}")
    duration = int(body.duration_minutes or 45)
    if duration < 5 or duration > 480:
        raise HTTPException(status_code=400, detail="Duration must be between 5 and 480 minutes")

    interviewer_name = (body.interviewer_name or "").strip()
    if body.interviewer_id:
        emp = db.query(models.DBEmployee).filter(
            models.DBEmployee.id == body.interviewer_id,
            models.DBEmployee.client_id == client.id,
        ).first()
        if not emp:
            raise HTTPException(status_code=400, detail="Interviewer not found")
        interviewer_name = interviewer_name or f"{emp.first_name} {emp.last_name}"
        # Warn on a clash rather than silently double-booking someone.
        window_start = (when - timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M")
        window_end = (when + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M")
        clash = db.query(models.DBInterview).filter(
            models.DBInterview.client_id == client.id,
            models.DBInterview.interviewer_id == body.interviewer_id,
            models.DBInterview.status == "scheduled",
            models.DBInterview.scheduled_at > window_start,
            models.DBInterview.scheduled_at < window_end,
        ).first()
        if clash:
            raise HTTPException(
                status_code=409,
                detail=f"{interviewer_name} already has an interview at {clash.scheduled_at}",
            )

    iv = models.DBInterview(
        client_id=client.id, submission_id=sub_id,
        round_name=body.round_name or "Interview",
        scheduled_at=when.strftime("%Y-%m-%d %H:%M"),
        duration_minutes=duration, mode=mode,
        location=body.location or "", meeting_link=body.meeting_link or "",
        interviewer_id=body.interviewer_id, interviewer_name=interviewer_name,
    )
    db.add(iv)
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=sub_id,
        from_stage=sub.current_stage or "", to_stage=sub.current_stage or "",
        actor="HR", note=f"{iv.round_name} scheduled for {iv.scheduled_at}",
    ))
    db.commit()
    db.refresh(iv)
    return interview_to_dict(iv)


@app.put("/api/recruitment/interviews/{iv_id}")
def update_interview(iv_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Record the outcome, reschedule, or cancel."""
    client = get_client_user(request, db)
    body = body or {}
    iv = db.query(models.DBInterview).filter(
        models.DBInterview.id == iv_id, models.DBInterview.client_id == client.id
    ).first()
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")

    if "status" in body:
        status = (body["status"] or "").strip().lower()
        if status not in INTERVIEW_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(INTERVIEW_STATUSES)}")
        iv.status = status
    if "outcome" in body:
        outcome = (body["outcome"] or "").strip().lower()
        if outcome not in INTERVIEW_OUTCOMES:
            raise HTTPException(status_code=400, detail="Outcome must be pass, fail or hold")
        iv.outcome = outcome
    if "score" in body:
        try:
            score = int(body["score"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Score must be a whole number")
        if score < 0 or score > 5:
            raise HTTPException(status_code=400, detail="Score must be between 0 and 5")
        iv.score = score
    if "scheduled_at" in body and body["scheduled_at"]:
        when = _parse_datetime_minutes(body["scheduled_at"])
        if not when:
            raise HTTPException(status_code=400, detail="Scheduled time must look like YYYY-MM-DD HH:MM")
        iv.scheduled_at = when.strftime("%Y-%m-%d %H:%M")
    for field in ("feedback", "meeting_link", "location", "round_name", "interviewer_name"):
        if field in body and body[field] is not None:
            setattr(iv, field, body[field])

    if iv.outcome and iv.status == "scheduled":
        iv.status = "completed"   # recording an outcome implies it happened
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=iv.submission_id,
        from_stage="", to_stage="", actor="HR",
        note=f"{iv.round_name}: {iv.status}" + (f" ({iv.outcome})" if iv.outcome else ""),
    ))
    db.commit()
    return interview_to_dict(iv)


@app.delete("/api/recruitment/interviews/{iv_id}")
def delete_interview(iv_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    iv = db.query(models.DBInterview).filter(
        models.DBInterview.id == iv_id, models.DBInterview.client_id == client.id
    ).first()
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    db.delete(iv)
    db.commit()
    return {"message": "Interview removed"}


@app.get("/api/recruitment/interviews/upcoming")
def upcoming_interviews(request: Request, days: int = 14, db: Session = Depends(get_db)):
    """Everything scheduled in the next N days, for the recruiter's day view."""
    client = get_client_user(request, db)
    now = datetime.now()
    horizon = (now + timedelta(days=max(1, min(days, 90)))).strftime("%Y-%m-%d %H:%M")
    rows = db.query(models.DBInterview).filter(
        models.DBInterview.client_id == client.id,
        models.DBInterview.status == "scheduled",
        models.DBInterview.scheduled_at >= now.strftime("%Y-%m-%d 00:00"),
        models.DBInterview.scheduled_at <= horizon,
    ).order_by(models.DBInterview.scheduled_at.asc()).all()
    out = []
    for iv in rows:
        sub = db.query(models.DBFormSubmission).filter(
            models.DBFormSubmission.id == iv.submission_id
        ).first()
        data = interview_to_dict(iv)
        data["candidate_name"] = sub.candidate_name if sub else ""
        data["candidate_email"] = sub.candidate_email if sub else ""
        out.append(data)
    return out


# ============ OFFERS ============

OFFER_STATUSES = ("draft", "sent", "accepted", "declined", "withdrawn")


class OfferIn(BaseModel):
    job_title: Optional[str] = ""
    level: Optional[str] = ""
    salary: Optional[float] = 0.0
    start_date: Optional[str] = ""
    expires_on: Optional[str] = ""
    notes: Optional[str] = ""


def offer_to_dict(o):
    return {
        "id": o.id, "submission_id": o.submission_id, "job_title": o.job_title,
        "level": o.level, "salary": o.salary, "currency": o.currency,
        "start_date": o.start_date, "expires_on": o.expires_on, "notes": o.notes,
        "status": o.status, "sent_at": o.sent_at, "responded_at": o.responded_at,
        "decline_reason": o.decline_reason, "created_at": o.created_at,
    }


@app.get("/api/recruitment/submissions/{sub_id}/offers")
def list_offers(sub_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    _get_submission_for_client(db, client.id, sub_id)
    rows = db.query(models.DBOffer).filter(
        models.DBOffer.submission_id == sub_id
    ).order_by(models.DBOffer.id.desc()).all()
    return [offer_to_dict(o) for o in rows]


@app.post("/api/recruitment/submissions/{sub_id}/offers")
def create_offer(sub_id: int, request: Request, body: OfferIn, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = _get_submission_for_client(db, client.id, sub_id)
    live = db.query(models.DBOffer).filter(
        models.DBOffer.submission_id == sub_id,
        models.DBOffer.status.in_(["draft", "sent", "accepted"]),
    ).first()
    if live:
        raise HTTPException(
            status_code=409,
            detail=f"This candidate already has a {live.status} offer. Withdraw it before creating another.",
        )
    salary = float(body.salary or 0)
    if salary < 0:
        raise HTTPException(status_code=400, detail="Salary cannot be negative")
    for label, value in (("Start date", body.start_date), ("Expiry date", body.expires_on)):
        if value and not _parse_date(value):
            raise HTTPException(status_code=400, detail=f"{label} must be in YYYY-MM-DD format")
    start, expires = _parse_date(body.start_date), _parse_date(body.expires_on)
    if start and expires and expires > start:
        raise HTTPException(status_code=400, detail="The offer would expire after the start date")

    offer = models.DBOffer(
        client_id=client.id, submission_id=sub_id,
        job_title=body.job_title or "", level=validate_level(body.level),
        salary=money(salary), currency=client.currency or "",
        start_date=body.start_date or "", expires_on=body.expires_on or "",
        notes=body.notes or "", status="draft",
    )
    db.add(offer)
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=sub_id,
        from_stage="", to_stage="", actor="HR",
        note=f"Offer drafted at {money(salary):.2f}",
    ))
    db.commit()
    db.refresh(offer)
    return offer_to_dict(offer)


@app.put("/api/recruitment/offers/{offer_id}")
def update_offer(offer_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    body = body or {}
    offer = db.query(models.DBOffer).filter(
        models.DBOffer.id == offer_id, models.DBOffer.client_id == client.id
    ).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    if "status" in body:
        status = (body["status"] or "").strip().lower()
        if status not in OFFER_STATUSES:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(OFFER_STATUSES)}")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if status == "sent" and offer.status != "sent":
            offer.sent_at = now
        if status in ("accepted", "declined") and offer.status not in ("accepted", "declined"):
            offer.responded_at = now
        offer.status = status
    if "decline_reason" in body:
        offer.decline_reason = body["decline_reason"] or ""
    for field in ("job_title", "start_date", "expires_on", "notes"):
        if field in body and body[field] is not None:
            setattr(offer, field, body[field])
    if "salary" in body:
        try:
            offer.salary = money(float(body["salary"]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Salary must be a number")
    if "level" in body:
        offer.level = validate_level(body["level"])

    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=offer.submission_id,
        from_stage="", to_stage="", actor="HR",
        note=f"Offer {offer.status}" + (f": {offer.decline_reason}" if offer.decline_reason else ""),
    ))
    log_audit(db, client.id, f"offer_{offer.status}", "offer", offer.id, offer.job_title, "", request)
    db.commit()
    return offer_to_dict(offer)


# ============ REJECTION & CANDIDATE EMAIL ============

class CandidateEmailIn(BaseModel):
    template: Optional[str] = "custom"     # interview | offer | rejection | custom
    subject: Optional[str] = ""
    body: Optional[str] = ""


@app.post("/api/recruitment/submissions/{sub_id}/reject")
def reject_candidate(sub_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    body = body or {}
    sub = _get_submission_for_client(db, client.id, sub_id)
    if sub.hired_employee_id:
        raise HTTPException(status_code=409, detail="This candidate has already been hired")
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Please give a reason so the pipeline data stays useful")
    sub.status = "rejected"
    sub.rejected_reason = reason
    sub.rejected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=sub_id,
        from_stage=sub.current_stage or "", to_stage="Rejected",
        actor="HR", note=reason,
    ))
    log_audit(db, client.id, "candidate_rejected", "candidate", sub.id,
              sub.candidate_name or sub.candidate_email, reason, request)
    db.commit()
    return {"message": "Candidate rejected", "status": sub.status}


@app.post("/api/recruitment/submissions/{sub_id}/reopen")
def reopen_candidate(sub_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = _get_submission_for_client(db, client.id, sub_id)
    sub.status = "new"
    sub.rejected_reason = ""
    sub.rejected_at = ""
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=sub_id,
        from_stage="Rejected", to_stage=sub.current_stage or "Applied",
        actor="HR", note="Application reopened",
    ))
    db.commit()
    return {"message": "Candidate reopened"}


def build_candidate_email(template, sub, client, job=None, interview=None, offer=None):
    """Default wording for the three moments a candidate hears from you."""
    company = client.company_name or "our team"
    name = (sub.candidate_name or "there").split()[0] if sub.candidate_name else "there"
    role = (job.title if job else "") or "the role"
    if template == "interview" and interview:
        subject = f"Interview invitation - {role} at {company}"
        when = interview.scheduled_at or "a time we will confirm"
        where = interview.meeting_link or interview.location or f"{interview.mode} call"
        body = (
            f"Hi {name},\n\n"
            f"Thank you for applying for {role} at {company}. We would like to invite you to "
            f"a {interview.round_name.lower()}.\n\n"
            f"When: {when}\n"
            f"Duration: {interview.duration_minutes} minutes\n"
            f"Where: {where}\n\n"
            f"If that time does not suit, reply to this email and we will rearrange.\n\n"
            f"Best regards,\n{company}"
        )
    elif template == "offer" and offer:
        subject = f"Offer of employment - {offer.job_title or role} at {company}"
        sym = currency_symbol(offer.currency or client.currency or "GBP")
        body = (
            f"Hi {name},\n\n"
            f"We are delighted to offer you the position of {offer.job_title or role} at {company}.\n\n"
            f"Salary: {sym}{offer.salary:,.2f}\n"
            f"Start date: {offer.start_date or 'to be agreed'}\n"
            + (f"This offer is open until {offer.expires_on}.\n" if offer.expires_on else "")
            + (f"\n{offer.notes}\n" if offer.notes else "")
            + f"\nPlease reply to confirm whether you would like to accept.\n\n"
            f"Best regards,\n{company}"
        )
    elif template == "rejection":
        subject = f"Your application for {role} at {company}"
        body = (
            f"Hi {name},\n\n"
            f"Thank you for taking the time to apply for {role} at {company} and for talking with us.\n\n"
            f"On this occasion we have decided to progress other candidates. It was a competitive "
            f"process and this is not a reflection of your ability.\n\n"
            f"We will keep your details on file and would welcome an application from you in future.\n\n"
            f"Best regards,\n{company}"
        )
    else:
        subject = f"An update on your application - {company}"
        body = f"Hi {name},\n\nWe wanted to give you an update on your application.\n\nBest regards,\n{company}"
    return subject, body


@app.get("/api/recruitment/submissions/{sub_id}/email-preview")
def preview_candidate_email(sub_id: int, request: Request, template: str = "custom", db: Session = Depends(get_db)):
    """Let the recruiter read and edit the wording before anything is sent."""
    client = get_client_user(request, db)
    sub = _get_submission_for_client(db, client.id, sub_id)
    form = db.query(models.DBRecruitmentForm).filter(models.DBRecruitmentForm.id == sub.form_id).first()
    job = db.query(models.DBJobRequisition).filter(
        models.DBJobRequisition.id == form.job_id
    ).first() if form and form.job_id else None
    interview = db.query(models.DBInterview).filter(
        models.DBInterview.submission_id == sub_id, models.DBInterview.status == "scheduled"
    ).order_by(models.DBInterview.scheduled_at.asc()).first()
    offer = db.query(models.DBOffer).filter(
        models.DBOffer.submission_id == sub_id
    ).order_by(models.DBOffer.id.desc()).first()
    subject, body = build_candidate_email(template, sub, client, job, interview, offer)
    return {"to": sub.candidate_email or "", "subject": subject, "body": body}


@app.post("/api/recruitment/submissions/{sub_id}/email")
def email_candidate(sub_id: int, request: Request, background_tasks: BackgroundTasks,
                    body: CandidateEmailIn, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = _get_submission_for_client(db, client.id, sub_id)
    if not sub.candidate_email:
        raise HTTPException(status_code=400, detail="This candidate has no email address on file")
    if not validate_email_address(sub.candidate_email):
        raise HTTPException(status_code=400, detail=f"'{sub.candidate_email}' is not a valid email address")

    subject = (body.subject or "").strip()
    text_body = (body.body or "").strip()
    if not subject or not text_body:
        form = db.query(models.DBRecruitmentForm).filter(models.DBRecruitmentForm.id == sub.form_id).first()
        job = db.query(models.DBJobRequisition).filter(
            models.DBJobRequisition.id == form.job_id
        ).first() if form and form.job_id else None
        interview = db.query(models.DBInterview).filter(
            models.DBInterview.submission_id == sub_id, models.DBInterview.status == "scheduled"
        ).order_by(models.DBInterview.scheduled_at.asc()).first()
        offer = db.query(models.DBOffer).filter(
            models.DBOffer.submission_id == sub_id
        ).order_by(models.DBOffer.id.desc()).first()
        default_subject, default_body = build_candidate_email(
            body.template or "custom", sub, client, job, interview, offer
        )
        subject = subject or default_subject
        text_body = text_body or default_body

    from_email = os.getenv("FROM_EMAIL", "hello@keyroutes.co")
    company = client.company_name or "Recruitment"
    html_body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#1e293b;line-height:1.6;'
        'max-width:600px;margin:0 auto;padding:24px;">'
        + "".join(f"<p>{esc(p)}</p>" for p in text_body.split("\n\n") if p.strip())
        + "</div>"
    )
    require_credit(db, client.id, "candidate_email", 1, sub.candidate_email)
    background_tasks.add_task(
        send_email_background, sub.candidate_email, subject, text_body,
        f"{company} <{from_email}>", html_body, None, "attachment.pdf", "", client.id,
    )
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=sub_id,
        from_stage="", to_stage="", actor="HR",
        note=f"Email sent: {subject}",
    ))
    log_audit(db, client.id, "candidate_emailed", "candidate", sub.id,
              sub.candidate_name or sub.candidate_email, subject, request)
    db.commit()
    return {"message": f"Email queued to {sub.candidate_email}", "subject": subject}


# ============ ANALYTICS & TALENT POOL ============

@app.get("/api/recruitment/analytics")
def recruitment_analytics(request: Request, job_id: int = 0, db: Session = Depends(get_db)):
    """Funnel, time-to-hire and offer acceptance - the numbers a head of talent
    is asked for."""
    client = get_client_user(request, db)
    form_query = db.query(models.DBRecruitmentForm).filter(models.DBRecruitmentForm.client_id == client.id)
    if job_id:
        form_query = form_query.filter(models.DBRecruitmentForm.job_id == job_id)
    forms = form_query.all()
    form_ids = [f.id for f in forms]

    subs = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.client_id == client.id,
        models.DBFormSubmission.form_id.in_(form_ids or [0]),
    ).all()

    stage_counts = defaultdict(int)
    source_counts = defaultdict(int)
    for s in subs:
        stage_counts[s.current_stage or "Applied"] += 1
        source_counts[s.source or "direct"] += 1

    hired = [s for s in subs if s.hired_employee_id]
    rejected = [s for s in subs if s.status == "rejected"]

    # Time to hire, measured from application to the hire event.
    durations = []
    for s in hired:
        applied = _parse_date((s.created_at or "")[:10])
        hired_on = _parse_date((getattr(s, "hired_at", "") or "")[:10])
        if not hired_on:
            # Records created before hired_at existed fall back to the event log.
            event = db.query(models.DBSubmissionEvent).filter(
                models.DBSubmissionEvent.submission_id == s.id,
                models.DBSubmissionEvent.to_stage == "Hired",
            ).order_by(models.DBSubmissionEvent.id.desc()).first()
            hired_on = _parse_date((event.created_at or "")[:10]) if event else None
        if applied and hired_on and hired_on >= applied:
            durations.append((hired_on - applied).days)

    offers = db.query(models.DBOffer).filter(models.DBOffer.client_id == client.id).all()
    if job_id:
        sub_ids = {s.id for s in subs}
        offers = [o for o in offers if o.submission_id in sub_ids]
    sent_offers = [o for o in offers if o.status in ("sent", "accepted", "declined")]
    accepted = [o for o in offers if o.status == "accepted"]

    interviews = db.query(models.DBInterview).filter(models.DBInterview.client_id == client.id).all()
    if job_id:
        sub_ids = {s.id for s in subs}
        interviews = [i for i in interviews if i.submission_id in sub_ids]

    total = len(subs)
    return {
        "total_applicants": total,
        "by_stage": dict(stage_counts),
        "by_source": dict(source_counts),
        "hired": len(hired),
        "rejected": len(rejected),
        "in_progress": total - len(hired) - len(rejected),
        "interviews_scheduled": sum(1 for i in interviews if i.status == "scheduled"),
        "interviews_completed": sum(1 for i in interviews if i.status == "completed"),
        "offers_sent": len(sent_offers),
        "offers_accepted": len(accepted),
        "offer_acceptance_rate": round(len(accepted) / len(sent_offers) * 100, 1) if sent_offers else 0.0,
        "conversion_rate": round(len(hired) / total * 100, 1) if total else 0.0,
        "avg_days_to_hire": round(sum(durations) / len(durations), 1) if durations else 0.0,
        "open_jobs": db.query(models.DBJobRequisition).filter(
            models.DBJobRequisition.client_id == client.id,
            models.DBJobRequisition.status == "open",
        ).count(),
    }


@app.get("/api/recruitment/talent-pool")
def talent_pool(request: Request, q: str = "", stage: str = "", limit: int = 100,
                db: Session = Depends(get_db)):
    """Every candidate across every job, so a strong applicant for one role can
    be found again for another."""
    client = get_client_user(request, db)
    query = db.query(models.DBFormSubmission).filter(models.DBFormSubmission.client_id == client.id)
    if stage:
        query = query.filter(models.DBFormSubmission.current_stage == stage)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            models.DBFormSubmission.candidate_name.ilike(like),
            models.DBFormSubmission.candidate_email.ilike(like),
            models.DBFormSubmission.answers.ilike(like),
        ))
    rows = query.order_by(models.DBFormSubmission.id.desc()).limit(max(1, min(limit, 500))).all()

    form_titles = {
        f.id: f.title for f in db.query(models.DBRecruitmentForm).filter(
            models.DBRecruitmentForm.client_id == client.id
        ).all()
    }
    # Flag people who have applied more than once so a recruiter sees the
    # history instead of treating each application as a new person.
    email_counts = defaultdict(int)
    for r in db.query(models.DBFormSubmission.candidate_email).filter(
        models.DBFormSubmission.client_id == client.id
    ).all():
        if r.candidate_email:
            email_counts[r.candidate_email.lower()] += 1

    return [{
        "id": s.id, "candidate_name": s.candidate_name, "candidate_email": s.candidate_email,
        "candidate_phone": getattr(s, "candidate_phone", "") or "",
        "form_id": s.form_id, "form_title": form_titles.get(s.form_id, ""),
        "current_stage": s.current_stage, "status": s.status,
        "rating": getattr(s, "rating", 0) or 0,
        "applications": email_counts.get((s.candidate_email or "").lower(), 1),
        "hired_employee_id": getattr(s, "hired_employee_id", None),
        "created_at": s.created_at,
    } for s in rows]

# ============================================================================
# WALLET & METERED BILLING
# Tenants hold a prepaid balance. Actions that cost the platform real money
# (sending mail, WhatsApp, AI calls, payroll processing) are metered against
# it. The operator sets the prices; tenants can only top up and spend.
#
# All arithmetic is in integer minor units. A running balance must reconcile
# exactly, and repeated float addition drifts.
# ============================================================================

CURRENCY_MINOR_UNITS = {"JPY": 1, "KRW": 1, "VND": 1, "CLP": 1, "ISK": 1}


def minor_units(currency):
    """How many minor units make one major unit. Most currencies are 100."""
    return CURRENCY_MINOR_UNITS.get((currency or "GBP").upper(), 100)


def to_minor(amount, currency="GBP"):
    """Decimal amount -> integer minor units, rounded half-up."""
    try:
        d = Decimal(str(amount or 0))
    except (InvalidOperation, ValueError, TypeError):
        return 0
    return int((d * minor_units(currency)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_major(amount_minor, currency="GBP"):
    """Integer minor units -> decimal amount for display."""
    return round((amount_minor or 0) / minor_units(currency), 2)


# The catalogue of things that can be charged for. Prices are set by the
# operator; these are only the starting values and the wording tenants see.
DEFAULT_PRICING = [
    ("invoice_send",      "Send invoice by email",   "invoicing", 5,  50,
     "Charged when an invoice is emailed to a customer."),
    ("invoice_whatsapp",  "Send invoice on WhatsApp", "invoicing", 15, 0,
     "Charged per WhatsApp message delivered."),
    ("quote_send",        "Send quote by email",     "invoicing", 5,  50,
     "Charged when a quote is emailed to a customer."),
    ("payslip_send",      "Send payslip by email",   "hr",        5,  50,
     "Charged when a payslip is emailed to an employee."),
    ("payroll_run",       "Payroll run (per payslip)", "hr",      10, 10,
     "Charged for each payslip generated in a payroll run."),
    ("candidate_email",   "Email a candidate",       "hr",        5,  25,
     "Charged per interview invitation, offer or rejection sent."),
    ("ai_resume_screen",  "AI resume screening",     "hr",        40, 5,
     "Charged per candidate screened by AI."),
    ("ai_onboarding",     "AI onboarding checklist", "hr",        30, 5,
     "Charged per generated onboarding plan."),
    ("ai_email_draft",    "AI email drafting",       "invoicing", 25, 10,
     "Charged per AI-written email."),
    ("ai_attendance_summary", "AI attendance summary", "hr",      30, 5,
     "Charged per attendance summary generated."),
    ("ai_assistant",      "AI assistant question",   "platform",  10, 30,
     "Charged per question answered by the in-app assistant."),
    ("ai_insights",       "AI business insights",    "platform",  25, 10,
     "Charged per dashboard insight generated."),
    ("ai_job_description","AI job description",      "hr",        30, 5,
     "Charged per job advert drafted."),
    ("ai_interview_questions", "AI interview questions", "hr",    30, 5,
     "Charged per interview question set."),
    ("ai_describe_item",  "AI line item wording",    "invoicing", 10, 20,
     "Charged per invoice description rewritten."),
    ("ai_brand_theme",    "AI branding theme",       "invoicing", 25, 5,
     "Charged per invoice theme designed."),
]

PLATFORM_CURRENCY = os.getenv("PLATFORM_CURRENCY", "GBP").upper()


def seed_pricing_rules(db):
    """Make sure every known action has a price row, without disturbing any the
    operator has already edited."""
    existing = {r.action_key for r in db.query(models.DBPricingRule).all()}
    created = []
    for order, (key, label, module, price, allowance, desc) in enumerate(DEFAULT_PRICING):
        if key in existing:
            continue
        row = models.DBPricingRule(
            action_key=key, label=label, description=desc, module=module,
            unit_price_minor=price, currency=PLATFORM_CURRENCY,
            free_allowance=allowance, is_active=True, sort_order=order,
        )
        db.add(row)
        created.append(row)
    if created:
        db.flush()
    return created


def get_wallet(db, client_id, create=True):
    wallet = db.query(models.DBWallet).filter(models.DBWallet.client_id == client_id).first()
    if wallet or not create:
        return wallet
    wallet = models.DBWallet(
        client_id=client_id, balance_minor=0, currency=PLATFORM_CURRENCY,
        low_balance_minor=to_minor(os.getenv("WALLET_LOW_BALANCE", "5"), PLATFORM_CURRENCY),
    )
    db.add(wallet)
    db.flush()
    return wallet


def month_usage(db, client_id, action_key):
    """Units of one action already consumed this calendar month, for the free
    allowance."""
    prefix = datetime.now().strftime("%Y-%m")
    rows = db.query(models.DBWalletTransaction).filter(
        models.DBWalletTransaction.client_id == client_id,
        models.DBWalletTransaction.action_key == action_key,
        models.DBWalletTransaction.direction == "debit",
        models.DBWalletTransaction.created_at.like(prefix + "%"),
    ).all()
    return sum(r.quantity or 1 for r in rows)


def quote_action(db, client_id, action_key, quantity=1):
    """What an action would cost right now, after any free allowance.

    Returns (rule, chargeable_units, cost_minor). An unpriced or disabled
    action costs nothing, so metering can be rolled out gradually without
    blocking anyone.
    """
    rule = db.query(models.DBPricingRule).filter(
        models.DBPricingRule.action_key == action_key
    ).first()
    if not rule or not rule.is_active or rule.unit_price_minor <= 0:
        return rule, 0, 0
    quantity = max(1, int(quantity or 1))
    used = month_usage(db, client_id, action_key)
    remaining_free = max(0, (rule.free_allowance or 0) - used)
    chargeable = max(0, quantity - remaining_free)
    return rule, chargeable, chargeable * rule.unit_price_minor


class InsufficientCredit(Exception):
    def __init__(self, needed_minor, balance_minor, currency, label):
        self.needed_minor = needed_minor
        self.balance_minor = balance_minor
        self.currency = currency
        self.label = label
        super().__init__("Insufficient wallet balance")


def charge_wallet(db, client_id, action_key, quantity=1, reference="", performed_by=""):
    """Debit the wallet for one action.

    Raises InsufficientCredit when the balance will not cover it, so callers
    can refuse the action *before* doing the work rather than after.
    """
    rule, chargeable, cost = quote_action(db, client_id, action_key, quantity)
    if cost <= 0:
        return None

    wallet = get_wallet(db, client_id)
    if wallet.balance_minor < cost:
        raise InsufficientCredit(cost, wallet.balance_minor, wallet.currency, rule.label)

    wallet.balance_minor -= cost
    wallet.lifetime_spent_minor = (wallet.lifetime_spent_minor or 0) + cost
    wallet.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tx = models.DBWalletTransaction(
        client_id=client_id, wallet_id=wallet.id, direction="debit",
        amount_minor=cost, balance_after_minor=wallet.balance_minor,
        currency=wallet.currency, action_key=action_key,
        module=rule.module if rule else "", description=rule.label if rule else action_key,
        reference=reference, quantity=chargeable, performed_by=performed_by,
    )
    db.add(tx)
    return tx


def credit_wallet(db, client_id, amount_minor, description, reference="",
                  performed_by="", action_key="topup"):
    """Add credit. Used by successful payments and by operator adjustments."""
    amount_minor = int(amount_minor or 0)
    if amount_minor <= 0:
        raise HTTPException(status_code=400, detail="Credit amount must be greater than zero")
    wallet = get_wallet(db, client_id)
    wallet.balance_minor += amount_minor
    if action_key == "topup":
        wallet.lifetime_topped_up_minor = (wallet.lifetime_topped_up_minor or 0) + amount_minor
    wallet.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tx = models.DBWalletTransaction(
        client_id=client_id, wallet_id=wallet.id, direction="credit",
        amount_minor=amount_minor, balance_after_minor=wallet.balance_minor,
        currency=wallet.currency, action_key=action_key, module="platform",
        description=description, reference=reference, quantity=1,
        performed_by=performed_by,
    )
    db.add(tx)
    return tx


def insufficient_credit_response(exc):
    """One consistent 402 so the UI can always offer a top-up."""
    return HTTPException(
        status_code=402,
        detail=(
            f"Not enough wallet credit for {exc.label}. "
            f"Needs {currency_symbol(exc.currency)}{to_major(exc.needed_minor, exc.currency):.2f}, "
            f"balance is {currency_symbol(exc.currency)}{to_major(exc.balance_minor, exc.currency):.2f}. "
            "Top up your wallet to continue."
        ),
    )


def require_credit(db, client_id, action_key, quantity=1, reference="", performed_by=""):
    """Charge, converting the shortfall into the standard 402."""
    try:
        return charge_wallet(db, client_id, action_key, quantity, reference, performed_by)
    except InsufficientCredit as exc:
        raise insufficient_credit_response(exc)


def wallet_state(db, client, include_rules=True):
    wallet = get_wallet(db, client.id)
    data = {
        "balance": to_major(wallet.balance_minor, wallet.currency),
        "balance_minor": wallet.balance_minor,
        "currency": wallet.currency,
        "symbol": currency_symbol(wallet.currency),
        "low_balance": to_major(wallet.low_balance_minor, wallet.currency),
        "is_low": wallet.balance_minor <= (wallet.low_balance_minor or 0),
        "is_empty": wallet.balance_minor <= 0,
        "is_suspended": bool(wallet.is_suspended),
        "lifetime_topped_up": to_major(wallet.lifetime_topped_up_minor, wallet.currency),
        "lifetime_spent": to_major(wallet.lifetime_spent_minor, wallet.currency),
    }
    if include_rules:
        rules = db.query(models.DBPricingRule).filter(
            models.DBPricingRule.is_active == True
        ).order_by(models.DBPricingRule.sort_order.asc()).all()
        if not rules:
            rules = seed_pricing_rules(db)
            db.commit()
        data["pricing"] = [{
            "action_key": r.action_key, "label": r.label, "description": r.description,
            "module": r.module,
            "unit_price": to_major(r.unit_price_minor, r.currency),
            "free_allowance": r.free_allowance,
            "used_this_month": month_usage(db, client.id, r.action_key),
        } for r in rules]
    return data



def ensure_can_afford(db, client_id, action_key, quantity=1):
    """Check the wallet covers an action without debiting it.

    Used before work that can fail (an LLM call, an external API). Charging up
    front would bill the tenant for a failure; charging without checking first
    would let a tenant with no credit consume the upstream call anyway.
    """
    rule, chargeable, cost = quote_action(db, client_id, action_key, quantity)
    if cost <= 0:
        return 0
    wallet = get_wallet(db, client_id)
    if wallet.balance_minor < cost:
        raise insufficient_credit_response(
            InsufficientCredit(cost, wallet.balance_minor, wallet.currency,
                               rule.label if rule else action_key)
        )
    return cost


def charge_after_success(db, client_id, action_key, quantity=1, reference="", performed_by=""):
    """Debit and commit once the work has actually produced something.

    The AI endpoints previously charged before calling the model and never
    committed, so the debit was rolled back at the end of the request and the
    action was billed to nobody.
    """
    try:
        charge_wallet(db, client_id, action_key, quantity, reference, performed_by)
        db.commit()
    except InsufficientCredit:
        # Affordability was checked before the work; a shortfall here means the
        # balance moved underneath us. The work is already done, so log it
        # rather than failing the response.
        db.rollback()
        logger.warning("Could not bill %s for %s: balance changed mid-request", client_id, action_key)


# --- Tenant-facing wallet ---------------------------------------------------

@app.get("/api/wallet")
def get_my_wallet(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    state = wallet_state(db, client)
    db.commit()
    return state


@app.get("/api/wallet/transactions")
def wallet_transactions(request: Request, limit: int = 100, direction: str = "",
                        db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    query = db.query(models.DBWalletTransaction).filter(
        models.DBWalletTransaction.client_id == client.id
    )
    if direction in ("credit", "debit"):
        query = query.filter(models.DBWalletTransaction.direction == direction)
    rows = query.order_by(models.DBWalletTransaction.id.desc()).limit(
        max(1, min(limit, 500))
    ).all()
    return [{
        "id": t.id, "direction": t.direction,
        "amount": to_major(t.amount_minor, t.currency),
        "balance_after": to_major(t.balance_after_minor, t.currency),
        "currency": t.currency, "action_key": t.action_key, "module": t.module,
        "description": t.description, "reference": t.reference,
        "quantity": t.quantity, "created_at": t.created_at,
    } for t in rows]


@app.get("/api/wallet/usage")
def wallet_usage(request: Request, months: int = 3, db: Session = Depends(get_db)):
    """What the tenant has actually spent, grouped by action and by month."""
    client = get_client_user(request, db)
    wallet = get_wallet(db, client.id)
    months = max(1, min(months, 12))
    cutoff = (datetime.now() - timedelta(days=31 * months)).strftime("%Y-%m")
    rows = db.query(models.DBWalletTransaction).filter(
        models.DBWalletTransaction.client_id == client.id,
        models.DBWalletTransaction.direction == "debit",
        models.DBWalletTransaction.created_at >= cutoff,
    ).all()

    by_action, by_month = defaultdict(lambda: {"units": 0, "spent_minor": 0}), defaultdict(int)
    for r in rows:
        slot = by_action[r.action_key or "other"]
        slot["units"] += r.quantity or 1
        slot["spent_minor"] += r.amount_minor or 0
        by_month[(r.created_at or "")[:7]] += r.amount_minor or 0

    return {
        "currency": wallet.currency,
        "symbol": currency_symbol(wallet.currency),
        "total_spent": to_major(sum(v["spent_minor"] for v in by_action.values()), wallet.currency),
        "by_action": [{
            "action_key": k, "units": v["units"],
            "spent": to_major(v["spent_minor"], wallet.currency),
        } for k, v in sorted(by_action.items(), key=lambda kv: -kv[1]["spent_minor"])],
        "by_month": [{"month": m, "spent": to_major(v, wallet.currency)}
                     for m, v in sorted(by_month.items())],
    }


@app.get("/api/wallet/quote")
def wallet_quote(request: Request, action: str, quantity: int = 1,
                 db: Session = Depends(get_db)):
    """What would this cost, and can I afford it? Lets the UI warn before the
    user commits to a bulk action such as a payroll run."""
    client = get_client_user(request, db)
    wallet = get_wallet(db, client.id)
    rule, chargeable, cost = quote_action(db, client.id, action, quantity)
    db.commit()
    return {
        "action": action,
        "label": rule.label if rule else action,
        "quantity": max(1, int(quantity or 1)),
        "chargeable_units": chargeable,
        "cost": to_major(cost, wallet.currency),
        "currency": wallet.currency,
        "symbol": currency_symbol(wallet.currency),
        "balance": to_major(wallet.balance_minor, wallet.currency),
        "affordable": wallet.balance_minor >= cost,
        "free_remaining": max(0, (rule.free_allowance or 0) - month_usage(db, client.id, action)) if rule else 0,
    }


# --- Operator: pricing ------------------------------------------------------

@app.get("/api/superadmin/migration-warnings")
def superadmin_migration_warnings(request: Request):
    """The schema steps that failed at boot.

    /api/health reports only a count, because the messages carry table and
    column names and it is a public endpoint. The operator needs the actual
    errors to tell an expected failure (dropping an index that was already
    dropped) from a migration that genuinely did not run.
    """
    require_superadmin(request)
    try:
        from database import migration_report
        problems = migration_report()
    except Exception:
        problems = []
    return {"count": len(problems), "warnings": problems}


@app.get("/api/superadmin/environment")
def superadmin_environment(request: Request):
    """Which settings production is actually running with.

    Never returns a value, only whether one is present - this is a page an
    operator reads to answer "did that variable take effect?", and secrets do
    not belong in an HTTP response even behind an admin check.
    """
    require_superadmin(request)

    def state(name, ok, why, fix):
        return {"name": name, "ok": bool(ok), "detail": why, "fix": fix}

    checks = [
        state("SECRET_KEY", bool(os.getenv("SECRET_KEY")),
              "Sessions survive a redeploy."
              if os.getenv("SECRET_KEY") else
              "Not set, so a new key is generated on every boot and every "
              "signed-in user is signed out on each redeploy.",
              "Set SECRET_KEY to a long random string in the host environment."),
        state("GROQ_API_KEY", bool(os.getenv("GROQ_API_KEY")),
              "The AI features can reach the model."
              if os.getenv("GROQ_API_KEY") else
              "Not set, so every AI feature fails at the point of use.",
              "Set GROQ_API_KEY in the host environment."),
        state("DATABASE_URL", bool(os.getenv("DATABASE_URL")),
              "Using the configured database."
              if os.getenv("DATABASE_URL") else
              "Not set, so the app is on a local SQLite file that a redeploy "
              "discards along with all of its data.",
              "Point DATABASE_URL at the Postgres instance."),
        state("Payment gateways",
              any(os.getenv(k) for k in
                  ("STRIPE_SECRET_KEY", "RAZORPAY_KEY_SECRET", "PAYPAL_SECRET")),
              "At least one gateway is configured.",
              "Set the keys for whichever gateway you intend to take money with."),
    ]
    return {
        "checks": checks,
        "ready": all(c["ok"] for c in checks),
        "outstanding": [c["name"] for c in checks if not c["ok"]],
    }


class PricingRuleIn(BaseModel):
    action_key: Optional[str] = ""
    label: Optional[str] = ""
    description: Optional[str] = ""
    module: Optional[str] = "platform"
    unit_price: Optional[float] = 0.0
    free_allowance: Optional[int] = 0
    is_active: Optional[bool] = True
    sort_order: Optional[int] = 0


@app.get("/api/superadmin/ai-status")
def ai_status(request: Request):
    """Whether the AI features can actually run, without exposing the key.

    All five AI endpoints degrade to a canned response when the key is absent,
    which is safe but indistinguishable from a broken model - this says which.
    """
    require_superadmin(request)
    import llm
    key = llm.GROQ_API_KEY or ""
    configured = bool(key)
    looks_valid = key.startswith("gsk_") and len(key) > 20

    reachable, detail = False, "Not configured"
    if configured:
        try:
            probe = llm.llm_chat([{"role": "user", "content": "ping"}], max_tokens=5)
            reachable = probe is not None
            if reachable:
                detail = "Model responded"
            elif llm.llm_last_error() == "model_gone":
                # The one failure an operator can fix in a minute, so it says
                # exactly that instead of "the API call failed".
                detail = llm.llm_error_message()
            else:
                detail = "Key set but the API call failed - check the key and quota"
        except Exception as exc:
            detail = f"Call failed: {exc}"[:160]

    # Hosted models get retired. Listing what this key can actually use means
    # the replacement is chosen from reality rather than from memory.
    models = llm.available_models() if configured else []

    return {
        "provider": "groq",
        "model": llm.MODEL,
        "model_default": llm.DEFAULT_MODEL,
        "model_is_available": (llm.MODEL in models) if models else None,
        "available_models": models[:40],
        "model_env_var": "GROQ_MODEL",
        "configured": configured,
        "key_format_ok": looks_valid,
        "reachable": reachable,
        "detail": detail if configured else "GROQ_API_KEY is not set. AI features return a fallback response.",
        "env_var": "GROQ_API_KEY",
        "key_hint": "Groq keys begin with gsk_ and are issued at console.groq.com/keys",
        "features": [
            "AI resume screening", "AI onboarding checklist",
            "AI invoice email drafting", "AI payment follow-up",
            "AI attendance summary",
        ],
    }


@app.get("/api/superadmin/pricing")
def list_pricing(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    rows = db.query(models.DBPricingRule).order_by(
        models.DBPricingRule.sort_order.asc(), models.DBPricingRule.id.asc()
    ).all()
    if not rows:
        rows = seed_pricing_rules(db)
        db.commit()
    return [{
        "id": r.id, "action_key": r.action_key, "label": r.label,
        "description": r.description, "module": r.module,
        "unit_price": to_major(r.unit_price_minor, r.currency),
        "unit_price_minor": r.unit_price_minor, "currency": r.currency,
        "free_allowance": r.free_allowance, "is_active": bool(r.is_active),
        "sort_order": r.sort_order, "updated_at": r.updated_at,
    } for r in rows]


@app.put("/api/superadmin/pricing/{rule_id}")
def update_pricing(rule_id: int, request: Request, body: PricingRuleIn,
                   db: Session = Depends(get_db), _: int = SuperAdmin):
    # See create_pricing: the dependency runs before `body` is validated, so
    # the refusal is a 401 rather than a 422 handing out the schema.
    rule = db.query(models.DBPricingRule).filter(models.DBPricingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    if body.unit_price is not None:
        price = float(body.unit_price)
        if price < 0:
            raise HTTPException(status_code=400, detail="Price cannot be negative")
        if price > 1000:
            raise HTTPException(status_code=400, detail="That price looks wrong - over 1000 per action")
        rule.unit_price_minor = to_minor(price, rule.currency)
    if body.free_allowance is not None:
        allowance = int(body.free_allowance)
        if allowance < 0 or allowance > 100000:
            raise HTTPException(status_code=400, detail="Free allowance must be between 0 and 100000")
        rule.free_allowance = allowance
    if body.label:
        rule.label = body.label.strip()
    if body.description is not None:
        rule.description = body.description
    if body.is_active is not None:
        rule.is_active = bool(body.is_active)
    if body.sort_order is not None:
        rule.sort_order = int(body.sort_order)
    rule.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    return {"message": f"{rule.label} updated", "unit_price": to_major(rule.unit_price_minor, rule.currency)}


@app.post("/api/superadmin/pricing")
def create_pricing(request: Request, body: PricingRuleIn, db: Session = Depends(get_db),
                   _: int = SuperAdmin):
    # Guarded by dependency rather than a call in the body: FastAPI validates
    # `body` before the handler runs, so a signed-out caller posting nothing
    # used to get a 422 describing PricingRuleIn instead of being turned away.
    key = (body.action_key or "").strip().lower().replace(" ", "_")
    if not key:
        raise HTTPException(status_code=400, detail="An action key is required")
    if db.query(models.DBPricingRule).filter(models.DBPricingRule.action_key == key).first():
        raise HTTPException(status_code=400, detail=f"'{key}' already has a price")
    price = float(body.unit_price or 0)
    if price < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative")
    rule = models.DBPricingRule(
        action_key=key, label=(body.label or key).strip(),
        description=body.description or "", module=body.module or "platform",
        unit_price_minor=to_minor(price, PLATFORM_CURRENCY), currency=PLATFORM_CURRENCY,
        free_allowance=int(body.free_allowance or 0), is_active=bool(body.is_active),
        sort_order=int(body.sort_order or 0),
    )
    db.add(rule)
    db.commit()
    return {"message": f"{rule.label} added", "id": rule.id}


# --- Operator: wallets ------------------------------------------------------

@app.get("/api/superadmin/wallets")
def list_wallets(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    clients = db.query(models.DBClient).all()
    wallets = {w.client_id: w for w in db.query(models.DBWallet).all()}
    out = []
    for c in clients:
        w = wallets.get(c.id)
        out.append({
            "client_id": c.id,
            "company_name": c.company_name or c.email,
            "email": c.email,
            "balance": to_major(w.balance_minor, w.currency) if w else 0.0,
            "currency": w.currency if w else PLATFORM_CURRENCY,
            "is_low": bool(w and w.balance_minor <= (w.low_balance_minor or 0)),
            "lifetime_topped_up": to_major(w.lifetime_topped_up_minor, w.currency) if w else 0.0,
            "lifetime_spent": to_major(w.lifetime_spent_minor, w.currency) if w else 0.0,
            "is_suspended": bool(w and w.is_suspended),
        })
    out.sort(key=lambda r: r["balance"])
    return out


@app.post("/api/superadmin/wallets/{client_id}/adjust")
def adjust_wallet(client_id: int, request: Request, body: dict = None,
                  db: Session = Depends(get_db)):
    """Operator credit or debit: refunds, goodwill, corrections. Every
    adjustment is a ledger row, never a silent balance edit."""
    require_superadmin(request)
    body = body or {}
    client = db.query(models.DBClient).filter(models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number")
    if amount == 0:
        raise HTTPException(status_code=400, detail="Amount cannot be zero")
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Give a reason - this lands on the tenant's statement")

    wallet = get_wallet(db, client_id)
    amount_minor = to_minor(abs(amount), wallet.currency)
    if amount > 0:
        credit_wallet(db, client_id, amount_minor, reason, performed_by="superadmin",
                      action_key="adjustment")
    else:
        if wallet.balance_minor < amount_minor:
            raise HTTPException(status_code=400, detail="That would take the balance below zero")
        wallet.balance_minor -= amount_minor
        wallet.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.add(models.DBWalletTransaction(
            client_id=client_id, wallet_id=wallet.id, direction="debit",
            amount_minor=amount_minor, balance_after_minor=wallet.balance_minor,
            currency=wallet.currency, action_key="adjustment", module="platform",
            description=reason, performed_by="superadmin",
        ))
    log_audit(db, client_id, "wallet_adjusted", "wallet", client_id,
              client.company_name or client.email, f"{amount:+.2f}: {reason}",
              request, user_type="superadmin", user_name="superadmin")
    db.commit()
    return {
        "message": "Wallet adjusted",
        "balance": to_major(wallet.balance_minor, wallet.currency),
    }


@app.get("/api/superadmin/wallets/{client_id}/transactions")
def wallet_history(client_id: int, request: Request, limit: int = 40,
                   db: Session = Depends(get_db)):
    """What this tenant's wallet has actually done.

    Crediting an account without seeing why it is empty is how a mistake gets
    repeated, so the operator can read the ledger from the same screen they
    top up from.
    """
    require_superadmin(request)
    client = db.query(models.DBClient).filter(
        models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    wallet = get_wallet(db, client_id)
    rows = db.query(models.DBWalletTransaction).filter(
        models.DBWalletTransaction.client_id == client_id
    ).order_by(models.DBWalletTransaction.id.desc()).limit(max(1, min(limit, 200))).all()

    return {
        "client": {"id": client.id,
                   "name": client.company_name or client.email,
                   "email": client.email},
        "balance": to_major(wallet.balance_minor, wallet.currency),
        "currency": wallet.currency,
        "transactions": [{
            "id": t.id,
            "direction": t.direction,
            "amount": to_major(t.amount_minor, t.currency),
            "balance_after": to_major(t.balance_after_minor, t.currency),
            "description": t.description or "",
            "action_key": t.action_key or "",
            "module": t.module or "",
            "reference": t.reference or "",
            "performed_by": t.performed_by or "",
            "created_at": t.created_at or "",
        } for t in rows],
    }


@app.put("/api/superadmin/wallets/{client_id}/currency")
def set_wallet_currency(client_id: int, request: Request, body: dict = None,
                        db: Session = Depends(get_db)):
    """Change which currency a wallet is denominated in.

    Only while it is empty. A balance is a number of minor units of one
    currency, so relabelling GBP as INR would either restate the balance at a
    rate nobody chose or quietly change what it is worth. This app does not
    invent exchange rates anywhere else and will not start here: take the
    balance to zero first, switch, then put it back.
    """
    require_superadmin(request)
    code = ((body or {}).get("currency") or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise HTTPException(status_code=400, detail="Use a three letter currency code")

    client = db.query(models.DBClient).filter(
        models.DBClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    wallet = get_wallet(db, client_id)
    if wallet.currency == code:
        return {"currency": wallet.currency, "balance": 0.0, "changed": False}

    if (wallet.balance_minor or 0) != 0:
        raise HTTPException(
            status_code=409,
            detail=(f"This wallet holds {to_major(wallet.balance_minor, wallet.currency)} "
                    f"{wallet.currency}. Adjust it to zero first - converting it "
                    "would need an exchange rate, and a made-up one is worse "
                    "than asking."))

    previous = wallet.currency
    wallet.currency = code
    wallet.low_balance_minor = to_minor(
        to_major(wallet.low_balance_minor or 0, previous), code)
    wallet.auto_topup_threshold_minor = 0
    wallet.auto_topup_amount_minor = 0
    wallet.auto_topup_enabled = False
    wallet.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_audit(db, client_id, "wallet_currency_changed", "wallet", client_id,
              client.company_name or client.email, f"{previous} to {code}",
              request, user_type="superadmin", user_name="superadmin")
    db.commit()
    return {"currency": wallet.currency, "balance": 0.0, "changed": True,
            "previous": previous,
            "note": "Auto top-up was switched off - the amounts were in the old currency."}


@app.get("/api/superadmin/revenue")
def platform_revenue(request: Request, months: int = 6, db: Session = Depends(get_db)):
    """What the platform has actually earned, by month and by action."""
    require_superadmin(request)
    months = max(1, min(months, 24))
    cutoff = (datetime.now() - timedelta(days=31 * months)).strftime("%Y-%m")
    rows = db.query(models.DBWalletTransaction).filter(
        models.DBWalletTransaction.created_at >= cutoff
    ).all()

    spend_by_month, topup_by_month, by_action = defaultdict(int), defaultdict(int), defaultdict(int)
    for r in rows:
        month = (r.created_at or "")[:7]
        if r.direction == "debit" and r.action_key != "adjustment":
            spend_by_month[month] += r.amount_minor or 0
            by_action[r.action_key or "other"] += r.amount_minor or 0
        elif r.direction == "credit" and r.action_key == "topup":
            topup_by_month[month] += r.amount_minor or 0

    all_months = sorted(set(spend_by_month) | set(topup_by_month))
    outstanding = db.query(sqlfunc.coalesce(sqlfunc.sum(models.DBWallet.balance_minor), 0)).scalar() or 0
    return {
        "currency": PLATFORM_CURRENCY,
        "symbol": currency_symbol(PLATFORM_CURRENCY),
        "total_topped_up": to_major(sum(topup_by_month.values()), PLATFORM_CURRENCY),
        "total_consumed": to_major(sum(spend_by_month.values()), PLATFORM_CURRENCY),
        "outstanding_liability": to_major(outstanding, PLATFORM_CURRENCY),
        "months": [{
            "month": m,
            "topped_up": to_major(topup_by_month.get(m, 0), PLATFORM_CURRENCY),
            "consumed": to_major(spend_by_month.get(m, 0), PLATFORM_CURRENCY),
        } for m in all_months],
        "by_action": [{"action_key": k, "revenue": to_major(v, PLATFORM_CURRENCY)}
                      for k, v in sorted(by_action.items(), key=lambda kv: -kv[1])],
    }

# ============================================================================
# PAYMENT GATEWAYS
# Top-ups go through Stripe, Razorpay or PayPal. Keys come from the
# environment; with none set the endpoints say so plainly rather than
# pretending to work.
#
# Crediting only ever happens from a verified provider callback, never from
# the browser. A client-side "payment succeeded" is not proof of payment.
# ============================================================================

TOPUP_MIN_MAJOR = float(os.getenv("TOPUP_MIN", "5"))
TOPUP_MAX_MAJOR = float(os.getenv("TOPUP_MAX", "5000"))


def _env_key(name: str) -> str:
    """A key as pasted, minus the whitespace that comes with pasting.

    A trailing space or newline in a dashboard variable is invisible and makes
    basic auth fail as surely as a wrong key, which is indistinguishable from
    the outside: both come back 401.
    """
    return (os.getenv(name, "") or "").strip()


def gateway_config():
    """Which providers are usable right now, based on the keys present."""
    return {
        "stripe": {
            "secret": _env_key("STRIPE_SECRET_KEY"),
            "publishable": _env_key("STRIPE_PUBLISHABLE_KEY"),
            "webhook_secret": _env_key("STRIPE_WEBHOOK_SECRET"),
        },
        "razorpay": {
            "key_id": _env_key("RAZORPAY_KEY_ID"),
            "key_secret": _env_key("RAZORPAY_KEY_SECRET"),
            "webhook_secret": _env_key("RAZORPAY_WEBHOOK_SECRET"),
        },
        "paypal": {
            "client_id": _env_key("PAYPAL_CLIENT_ID"),
            "secret": _env_key("PAYPAL_SECRET"),
            "mode": (os.getenv("PAYPAL_MODE", "sandbox") or "sandbox").strip(),
        },
    }


def razorpay_key_shape(key_id: str, key_secret: str):
    """What can be said about a key pair without asking Razorpay.

    Never returns the values. The point is to describe them well enough to spot
    the common mistakes - a mismatched pair after a rotation, a test id with a
    live secret, whitespace that survived the paste.
    """
    raw_id = os.getenv("RAZORPAY_KEY_ID", "") or ""
    raw_secret = os.getenv("RAZORPAY_KEY_SECRET", "") or ""
    notes = []
    if raw_id != raw_id.strip() or raw_secret != raw_secret.strip():
        notes.append("There was whitespace around a value; it is being trimmed, "
                     "but tidy it in the dashboard too.")
    if key_id and not key_id.startswith(("rzp_test_", "rzp_live_")):
        notes.append("The key id does not start with rzp_test_ or rzp_live_, "
                     "so it may not be a key id.")
    if key_secret.startswith("rzp_"):
        notes.append("The secret looks like a key id. These two are different "
                     "values and the secret is shown only once, when generated.")
    # Razorpay secrets are 24 characters. A different length usually means a
    # partial paste or the wrong value entirely, and looks identical to a wrong
    # key from the outside.
    if key_secret and len(key_secret) != 24:
        notes.append(f"The secret is {len(key_secret)} characters; Razorpay "
                     "secrets are 24. Check the whole value was pasted.")
    return {
        "mode": ("test" if key_id.startswith("rzp_test_")
                 else "live" if key_id.startswith("rzp_live_") else "unknown"),
        "key_id_tail": key_id[-4:] if key_id else "",
        "secret_length": len(key_secret),
        "notes": notes,
    }


@app.get("/api/superadmin/razorpay-check")
def razorpay_check(request: Request):
    """Ask Razorpay whether these credentials work, and say what it answered.

    Finding out through a failed top-up means guessing at which of several
    things went wrong. This asks directly, with a call that moves no money.
    """
    require_superadmin(request)
    cfg = gateway_config()["razorpay"]
    shape = razorpay_key_shape(cfg["key_id"], cfg["key_secret"])

    if not (cfg["key_id"] and cfg["key_secret"]):
        return {
            "ok": False,
            "reason": "Both RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set.",
            "shape": shape,
        }

    try:
        # Reading a page of orders touches nothing and needs the same auth a
        # payment would.
        resp = httpx.get("https://api.razorpay.com/v1/orders?count=1",
                         auth=(cfg["key_id"], cfg["key_secret"]), timeout=20)
    except Exception as exc:      # noqa: BLE001
        return {"ok": False,
                "reason": f"Could not reach Razorpay: {str(exc)[:160]}",
                "shape": shape}

    if resp.status_code == 200:
        return {
            "ok": True,
            "reason": f"These {shape['mode']} keys work.",
            "shape": shape,
            "next": ("Razorpay accounts take INR unless international payments "
                     "are enabled, so keep the wallet and invoices in INR."),
        }

    return {
        "ok": False,
        "status": resp.status_code,
        "reason": razorpay_complaint(resp),
        "shape": shape,
        "hint": ("Regenerating a key replaces both halves. Using a new id with "
                 "the previous secret fails exactly like a wrong key."),
    }


def enabled_providers():
    cfg = gateway_config()
    return {
        "stripe": bool(cfg["stripe"]["secret"]),
        "razorpay": bool(cfg["razorpay"]["key_id"] and cfg["razorpay"]["key_secret"]),
        "paypal": bool(cfg["paypal"]["client_id"] and cfg["paypal"]["secret"]),
    }


# Which provider will take which currency. Offering one that will not is how
# a top-up gets as far as the gateway before failing - which is exactly what
# happened with a GBP wallet and a Razorpay account.
#
# PayPal publishes a fixed list of balance currencies; INR is not one of them.
# Razorpay settles in INR and takes nothing else unless the account has
# international payments turned on. Stripe takes far more than anyone here is
# likely to bill in, so it is treated as open.
PAYPAL_CURRENCIES = {
    "AUD", "BRL", "CAD", "CNY", "CZK", "DKK", "EUR", "HKD", "HUF", "ILS",
    "JPY", "MYR", "MXN", "TWD", "NZD", "NOK", "PHP", "PLN", "GBP", "RUB",
    "SGD", "SEK", "CHF", "THB", "USD",
}
RAZORPAY_CURRENCIES = {"INR"}

# Set when the Razorpay account has international payments enabled, which lets
# it charge in other currencies while still settling in INR.
RAZORPAY_INTERNATIONAL = os.getenv("RAZORPAY_INTERNATIONAL", "").strip().lower() in (
    "1", "true", "yes", "on")


def provider_takes_currency(provider: str, currency: str) -> bool:
    code = (currency or "").upper()
    if provider == "stripe":
        return True
    if provider == "paypal":
        return code in PAYPAL_CURRENCIES
    if provider == "razorpay":
        return RAZORPAY_INTERNATIONAL or code in RAZORPAY_CURRENCIES
    return False


def why_not_available(provider: str, currency: str, configured: bool) -> str:
    """One short sentence a person can act on, or empty when it is usable."""
    if not configured:
        return "Not set up on this server yet."
    if provider_takes_currency(provider, currency):
        return ""
    code = (currency or "").upper()
    if provider == "razorpay":
        return (f"Razorpay accounts take INR. Set the wallet to INR, or turn on "
                f"international payments and set RAZORPAY_INTERNATIONAL=true.")
    if provider == "paypal":
        return f"PayPal does not hold balances in {code}."
    return f"Does not take {code}."


@app.get("/api/wallet/providers")
def wallet_providers(request: Request, db: Session = Depends(get_db)):
    """What the top-up screen should offer. Being explicit about what is not
    configured beats a button that fails on click."""
    client = get_client_user(request, db)
    wallet = get_wallet(db, client.id)
    db.commit()
    enabled = enabled_providers()
    cfg = gateway_config()
    currency = wallet.currency

    def entry(key, label, extra=None):
        configured = enabled[key]
        usable = configured and provider_takes_currency(key, currency)
        row = {
            "key": key, "label": label,
            "enabled": usable,
            "configured": configured,
            "takes_currency": provider_takes_currency(key, currency),
            # Empty when it can be used, so the page has nothing to explain.
            "unavailable_because": why_not_available(key, currency, configured),
        }
        # A key is only handed over for a provider that can actually be used.
        if usable and extra:
            row.update(extra)
        return row

    providers = [
        entry("stripe", "Card (Stripe)",
              {"publishable_key": cfg["stripe"]["publishable"]}),
        entry("razorpay", "Razorpay (UPI, cards, netbanking)",
              {"key_id": cfg["razorpay"]["key_id"]}),
        entry("paypal", "PayPal"),
    ]
    return {
        "currency": currency,
        "symbol": currency_symbol(currency),
        "min_amount": TOPUP_MIN_MAJOR,
        "max_amount": TOPUP_MAX_MAJOR,
        "suggested": [10, 25, 50, 100, 250],
        "providers": providers,
        "any_enabled": any(p["enabled"] for p in providers),
        # Said once rather than three times, when nothing can take this money.
        "none_take_currency": (
            f"Nothing set up here takes {currency}."
            if any(p["configured"] for p in providers)
            and not any(p["enabled"] for p in providers) else ""),
    }


def validate_topup_amount(amount, currency):
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Amount must be a number")
    if amount < TOPUP_MIN_MAJOR:
        raise HTTPException(status_code=400, detail=f"Minimum top-up is {currency_symbol(currency)}{TOPUP_MIN_MAJOR:.2f}")
    if amount > TOPUP_MAX_MAJOR:
        raise HTTPException(status_code=400, detail=f"Maximum top-up is {currency_symbol(currency)}{TOPUP_MAX_MAJOR:.2f}")
    return to_minor(amount, currency)


def provider_unavailable(name, missing):
    return HTTPException(
        status_code=503,
        detail=f"{name} is not configured on this server. Missing: {', '.join(missing)}.",
    )


class TopUpIn(BaseModel):
    amount: float
    provider: str
    # Which portal the person is topping up from. Both live behind the same
    # API, and sending an HR user back to the invoicing app is disorienting.
    return_page: Optional[str] = ""


# Only these, and never whatever the browser asked for: a return_url is a
# redirect target, and an open one is somebody else's phishing page.
RETURN_PAGES = ("app.html", "hr.html")


def topup_return_page(requested: str) -> str:
    name = (requested or "").strip().lstrip("/")
    return name if name in RETURN_PAGES else "app.html"


@app.post("/api/wallet/topup")
def create_topup(body: TopUpIn, request: Request, db: Session = Depends(get_db)):
    """Create a payment at the chosen provider and hand back what the browser
    needs to complete it. No credit is added here."""
    client = get_client_user(request, db)
    wallet = get_wallet(db, client.id)
    amount_minor = validate_topup_amount(body.amount, wallet.currency)
    provider = (body.provider or "").strip().lower()
    if provider not in ("stripe", "razorpay", "paypal"):
        raise HTTPException(status_code=400, detail="Choose Stripe, Razorpay or PayPal")

    # Checked here as well as on the page, because a tab left open across a
    # currency change would otherwise start a payment certain to be refused.
    if not provider_takes_currency(provider, wallet.currency):
        raise HTTPException(
            status_code=400,
            detail=why_not_available(provider, wallet.currency, configured=True))

    order = models.DBTopUpOrder(
        client_id=client.id, provider=provider, amount_minor=amount_minor,
        currency=wallet.currency, status="created",
    )
    db.add(order)
    db.flush()

    try:
        if provider == "stripe":
            result = _create_stripe_checkout(order, client, request)
        elif provider == "razorpay":
            result = _create_razorpay_order(order, client)
        else:
            result = _create_paypal_order(
                order, client, request, topup_return_page(body.return_page))
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        logger.exception("Top-up creation failed at %s", provider)
        order.status = "failed"
        order.failure_reason = str(exc)[:200]
        db.commit()
        raise HTTPException(status_code=502, detail=f"{provider.title()} could not start the payment. Please try again.")

    order.status = "pending"
    db.commit()
    result.update({
        "order_id": order.id,
        "amount": to_major(amount_minor, wallet.currency),
        "currency": wallet.currency,
    })
    return result


def _create_stripe_checkout(order, client, request):
    cfg = gateway_config()["stripe"]
    if not cfg["secret"]:
        raise provider_unavailable("Stripe", ["STRIPE_SECRET_KEY"])
    base = str(request.base_url).rstrip("/")
    resp = httpx.post(
        "https://api.stripe.com/v1/checkout/sessions",
        auth=(cfg["secret"], ""),
        data={
            "mode": "payment",
            "success_url": f"{base}/app.html?topup=success",
            "cancel_url": f"{base}/app.html?topup=cancelled",
            "client_reference_id": str(order.id),
            "metadata[order_id]": str(order.id),
            "metadata[client_id]": str(client.id),
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": order.currency.lower(),
            "line_items[0][price_data][unit_amount]": str(order.amount_minor),
            "line_items[0][price_data][product_data][name]": "Wallet top-up",
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        logger.error("Stripe session failed: %s", resp.text[:400])
        raise HTTPException(status_code=502, detail="Stripe rejected the payment request.")
    data = resp.json()
    order.provider_order_id = data.get("id", "")
    order.checkout_url = data.get("url", "")
    return {"provider": "stripe", "checkout_url": data.get("url", ""), "session_id": data.get("id", "")}


def razorpay_complaint(resp, currency="") -> str:
    """Turn a Razorpay rejection into something the person reading it can act on.

    The reason was being logged and thrown away, so every failure looked
    identical: "Razorpay rejected the payment request." The most common one by
    far is the currency - a test account, and most Indian accounts, will only
    take INR - so that gets named outright rather than left to be guessed.
    """
    description = ""
    try:
        description = (resp.json().get("error", {}).get("description") or "").strip()
    except Exception:      # noqa: BLE001 - a non-JSON body is still a rejection
        description = ""

    haystack = f"{description} {(resp.text or '')[:300]}".lower()
    if "currency" in haystack or "international" in haystack:
        return (f"Razorpay would not take {currency or 'that currency'}. "
                "Razorpay accounts take INR unless international payments are "
                "enabled, so set the amount in INR or enable them on the account.")
    if "authentication" in haystack or resp.status_code in (401, 403):
        return ("Razorpay rejected the keys. Check RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET are the pair from the same account and mode.")
    if description:
        return f"Razorpay refused it: {description}"
    return "Razorpay rejected the payment request."


def _create_razorpay_order(order, client):
    cfg = gateway_config()["razorpay"]
    missing = [k for k, v in (("RAZORPAY_KEY_ID", cfg["key_id"]), ("RAZORPAY_KEY_SECRET", cfg["key_secret"])) if not v]
    if missing:
        raise provider_unavailable("Razorpay", missing)
    resp = httpx.post(
        "https://api.razorpay.com/v1/orders",
        auth=(cfg["key_id"], cfg["key_secret"]),
        json={
            "amount": order.amount_minor,
            "currency": order.currency.upper(),
            "receipt": f"wallet-{order.id}",
            "notes": {"order_id": str(order.id), "client_id": str(client.id)},
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        logger.error("Razorpay order failed: %s", resp.text[:400])
        raise HTTPException(
            status_code=502,
            detail=razorpay_complaint(resp, order.currency.upper()))
    data = resp.json()
    order.provider_order_id = data.get("id", "")
    return {
        "provider": "razorpay",
        "razorpay_order_id": data.get("id", ""),
        "key_id": cfg["key_id"],
        "amount_minor": order.amount_minor,
        "name": client.company_name or "Wallet top-up",
        "prefill_email": client.email,
    }


def _paypal_base():
    return ("https://api-m.paypal.com" if gateway_config()["paypal"]["mode"] == "live"
            else "https://api-m.sandbox.paypal.com")


def _paypal_token():
    cfg = gateway_config()["paypal"]
    resp = httpx.post(
        f"{_paypal_base()}/v1/oauth2/token",
        auth=(cfg["client_id"], cfg["secret"]),
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    if resp.status_code >= 400:
        logger.error("PayPal token failed: %s", resp.text[:300])
        # The likeliest failure with brand new keys, and the one worth naming:
        # sandbox credentials against live is indistinguishable from a typo.
        raise HTTPException(status_code=502, detail=paypal_complaint(resp))
    token = resp.json().get("access_token", "")
    if not token:
        raise HTTPException(
            status_code=502,
            detail="PayPal accepted the credentials but returned no token. Try again.")
    return token


def paypal_complaint(resp, currency="") -> str:
    """Turn a PayPal rejection into something actionable.

    PayPal nests the useful part under details[].issue, so the top-level
    message alone ("Request is not well-formed") says almost nothing.
    """
    name, message, issues = "", "", []
    try:
        data = resp.json()
        name = (data.get("name") or "").strip()
        message = (data.get("message") or "").strip()
        issues = [d.get("issue", "") for d in (data.get("details") or [])]
    except Exception:      # noqa: BLE001 - a non-JSON body is still a rejection
        pass

    haystack = f"{name} {message} {' '.join(issues)} {(resp.text or '')[:300]}".upper()

    if "CURRENCY_NOT_SUPPORTED" in haystack or "CURRENCY" in haystack:
        return (f"PayPal does not take {currency or 'that currency'} on this "
                "account. PayPal supports GBP, USD, EUR and INR among others, "
                "but the account has to be set up for the one being charged.")
    if "AUTHENTICATION" in haystack or resp.status_code in (401, 403):
        return ("PayPal rejected the credentials. Check PAYPAL_CLIENT_ID and "
                "PAYPAL_SECRET are from the same app, and that PAYPAL_MODE "
                "matches where they came from - sandbox keys do not work live.")
    if issues:
        return f"PayPal refused it: {issues[0]}"
    if message:
        return f"PayPal refused it: {message}"
    return "PayPal rejected the payment request."


def _create_paypal_order(order, client, request, return_page="app.html"):
    cfg = gateway_config()["paypal"]
    missing = [k for k, v in (("PAYPAL_CLIENT_ID", cfg["client_id"]), ("PAYPAL_SECRET", cfg["secret"])) if not v]
    if missing:
        raise provider_unavailable("PayPal", missing)
    token = _paypal_token()
    base = str(request.base_url).rstrip("/")
    resp = httpx.post(
        f"{_paypal_base()}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": str(order.id),
                "custom_id": str(order.id),
                "description": "Wallet top-up",
                "amount": {
                    "currency_code": order.currency.upper(),
                    "value": f"{to_major(order.amount_minor, order.currency):.2f}",
                },
            }],
            "application_context": {
                # The order id travels with the redirect, so the page that
                # receives it captures the payment it was actually made for
                # rather than the newest one that happens to be pending.
                "return_url": f"{base}/{return_page}?topup=success&order={order.id}",
                "cancel_url": f"{base}/{return_page}?topup=cancelled",
            },
        },
        timeout=20,
    )
    if resp.status_code >= 400:
        logger.error("PayPal order failed: %s", resp.text[:400])
        raise HTTPException(status_code=502,
                            detail=paypal_complaint(resp, order.currency.upper()))
    data = resp.json()
    order.provider_order_id = data.get("id", "")
    approve = next((l.get("href") for l in data.get("links", []) if l.get("rel") == "approve"), "")
    order.checkout_url = approve
    return {"provider": "paypal", "paypal_order_id": data.get("id", ""), "approve_url": approve}


def credit_topup_once(db, order, payment_id=""):
    """Credit a paid order exactly once.

    Gateways retry webhooks and users refresh return pages, so this is the
    single place that moves money and it is guarded by `credited`.
    """
    if order.credited:
        return False
    order.status = "paid"
    order.provider_payment_id = payment_id or order.provider_payment_id
    order.credited = True
    order.credited_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    credit_wallet(
        db, order.client_id, order.amount_minor,
        f"Top-up via {order.provider.title()}",
        reference=order.provider_payment_id or order.provider_order_id,
        performed_by=order.provider,
    )
    return True


# --- Provider callbacks -----------------------------------------------------
# Only these add credit. Each verifies the message really came from the
# provider before touching a balance.

@app.post("/api/wallet/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    cfg = gateway_config()["stripe"]
    raw = await request.body()
    signature = request.headers.get("stripe-signature", "")

    if not cfg["webhook_secret"]:
        # Without the secret the message cannot be trusted, and an unverified
        # webhook would let anyone credit their own wallet.
        logger.error("Stripe webhook rejected: STRIPE_WEBHOOK_SECRET is not set")
        raise HTTPException(status_code=503, detail="Stripe webhooks are not configured")

    try:
        parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p)
        timestamp, sent_sig = parts.get("t", ""), parts.get("v1", "")
        expected = hmac.new(
            cfg["webhook_secret"].encode(),
            f"{timestamp}.".encode() + raw,
            hashlib.sha256,
        ).hexdigest()
        if not sent_sig or not hmac.compare_digest(expected, sent_sig):
            raise ValueError("signature mismatch")
        # Reject anything older than five minutes, so a captured webhook
        # cannot be replayed later.
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError("timestamp outside tolerance")
    except Exception as exc:
        logger.warning("Stripe webhook verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(raw or b"{}")
    if event.get("type") not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return {"received": True, "ignored": event.get("type")}

    session = event.get("data", {}).get("object", {})
    order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
    order = db.query(models.DBTopUpOrder).filter(models.DBTopUpOrder.id == int(order_id or 0)).first()
    if not order:
        logger.warning("Stripe webhook for unknown order %s", order_id)
        return {"received": True, "ignored": "unknown order"}
    if session.get("payment_status") != "paid":
        return {"received": True, "ignored": "not paid"}

    credited = credit_topup_once(db, order, session.get("payment_intent", ""))
    db.commit()
    return {"received": True, "credited": credited}


@app.post("/api/wallet/webhook/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    cfg = gateway_config()["razorpay"]
    raw = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    if not cfg["webhook_secret"]:
        logger.error("Razorpay webhook rejected: RAZORPAY_WEBHOOK_SECRET is not set")
        raise HTTPException(status_code=503, detail="Razorpay webhooks are not configured")

    expected = hmac.new(cfg["webhook_secret"].encode(), raw, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        logger.warning("Razorpay webhook signature mismatch")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(raw or b"{}")
    if event.get("event") not in ("payment.captured", "order.paid"):
        return {"received": True, "ignored": event.get("event")}

    payload = event.get("payload", {})
    payment = (payload.get("payment") or {}).get("entity", {})
    provider_order_id = payment.get("order_id") or (payload.get("order") or {}).get("entity", {}).get("id")
    order = db.query(models.DBTopUpOrder).filter(
        models.DBTopUpOrder.provider_order_id == (provider_order_id or "")
    ).first()
    if not order:
        logger.warning("Razorpay webhook for unknown order %s", provider_order_id)
        return {"received": True, "ignored": "unknown order"}

    # Never credit more than the order was for, whatever the callback claims.
    if payment.get("amount") and int(payment["amount"]) < order.amount_minor:
        logger.error("Razorpay paid %s but order was %s", payment.get("amount"), order.amount_minor)
        return {"received": True, "ignored": "amount mismatch"}

    credited = credit_topup_once(db, order, payment.get("id", ""))
    db.commit()
    return {"received": True, "credited": credited}


@app.post("/api/wallet/topup/{order_id}/capture-paypal")
def capture_paypal(order_id: int, request: Request, db: Session = Depends(get_db)):
    """PayPal returns the buyer to us; the capture call to PayPal is what
    proves payment, not the redirect."""
    client = get_client_user(request, db)
    order = db.query(models.DBTopUpOrder).filter(
        models.DBTopUpOrder.id == order_id,
        models.DBTopUpOrder.client_id == client.id,
        models.DBTopUpOrder.provider == "paypal",
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Top-up not found")
    if order.credited:
        wallet = get_wallet(db, client.id)
        return {"message": "Already credited", "balance": to_major(wallet.balance_minor, wallet.currency)}

    token = _paypal_token()
    resp = httpx.post(
        f"{_paypal_base()}/v2/checkout/orders/{order.provider_order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=25,
    )
    if resp.status_code >= 400:
        logger.error("PayPal capture failed: %s", resp.text[:400])
        why = paypal_complaint(resp, order.currency.upper())
        order.failure_reason = why[:300]
        db.commit()
        raise HTTPException(status_code=502, detail=why)
    data = resp.json()
    if data.get("status") != "COMPLETED":
        return {"message": f"Payment is {data.get('status', 'incomplete')}", "credited": False}

    capture_id = ""
    try:
        capture_id = data["purchase_units"][0]["payments"]["captures"][0]["id"]
    except (KeyError, IndexError):
        pass
    credit_topup_once(db, order, capture_id)
    db.commit()
    wallet = get_wallet(db, client.id)
    return {
        "message": "Wallet topped up",
        "credited": True,
        "balance": to_major(wallet.balance_minor, wallet.currency),
    }


@app.get("/api/wallet/topups")
def list_topups(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    rows = db.query(models.DBTopUpOrder).filter(
        models.DBTopUpOrder.client_id == client.id
    ).order_by(models.DBTopUpOrder.id.desc()).limit(max(1, min(limit, 200))).all()
    return [{
        "id": o.id, "provider": o.provider,
        "amount": to_major(o.amount_minor, o.currency), "currency": o.currency,
        "status": o.status, "credited": bool(o.credited),
        "checkout_url": o.checkout_url if o.status == "pending" else "",
        "failure_reason": o.failure_reason, "created_at": o.created_at,
    } for o in rows]


@app.get("/api/superadmin/gateways")
def superadmin_gateways(request: Request):
    """Which providers this deployment can actually take money with, so the
    operator can see what still needs keys."""
    require_superadmin(request)
    cfg = gateway_config()
    enabled = enabled_providers()
    return {
        "platform_currency": PLATFORM_CURRENCY,
        "providers": [
            {"key": "stripe", "enabled": enabled["stripe"],
             "webhook_ready": bool(cfg["stripe"]["webhook_secret"]),
             "required_env": ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET"],
             "webhook_url": "/api/wallet/webhook/stripe"},
            {"key": "razorpay", "enabled": enabled["razorpay"],
             "webhook_ready": bool(cfg["razorpay"]["webhook_secret"]),
             "required_env": ["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET"],
             "webhook_url": "/api/wallet/webhook/razorpay"},
            {"key": "paypal", "enabled": enabled["paypal"],
             "webhook_ready": True,   # capture is verified server-side, no webhook needed
             "required_env": ["PAYPAL_CLIENT_ID", "PAYPAL_SECRET", "PAYPAL_MODE"],
             "webhook_url": ""},
        ],
    }

# ============ ONBOARDING DOCUMENT REQUIREMENTS ============
# HR decides what a new starter must provide; the employee uploads it from
# their own portal; HR reviews it. The requirement is the template, the request
# is one person's obligation against it.

DOC_REQUEST_STATUSES = ("pending", "submitted", "approved", "rejected")
DEFAULT_DOCUMENT_REQUIREMENTS = [
    ("Photo ID", "Passport or driving licence", "identity", True, 3),
    ("Proof of right to work", "Visa, share code or citizenship document", "compliance", True, 3),
    ("Bank details", "So payroll can pay you", "finance", True, 5),
    ("Signed contract", "Your countersigned employment contract", "contract", True, 7),
    ("Proof of address", "Utility bill or bank statement from the last 3 months", "identity", False, 14),
]


class DocumentRequirementIn(BaseModel):
    name: str
    description: Optional[str] = ""
    doc_type: Optional[str] = "other"
    is_mandatory: Optional[bool] = True
    due_days: Optional[int] = 7
    requires_expiry: Optional[bool] = False
    expiry_reminder_days: Optional[int] = 30
    applies_to: Optional[str] = "all"
    department_id: Optional[int] = None
    level: Optional[str] = ""
    is_active: Optional[bool] = True
    sort_order: Optional[int] = 0


def requirement_to_dict(r):
    return {
        "id": r.id, "name": r.name, "description": r.description or "",
        "doc_type": r.doc_type, "is_mandatory": bool(r.is_mandatory),
        "due_days": r.due_days, "applies_to": r.applies_to,
        "requires_expiry": bool(r.requires_expiry),
        "expiry_reminder_days": r.expiry_reminder_days or 30,
        "has_template": bool(r.template_file_data),
        "template_file_name": r.template_file_name or "",
        "department_id": r.department_id,
        "department_name": r.department.name if r.department else "",
        "level": r.level or "", "is_active": bool(r.is_active),
        "sort_order": r.sort_order, "created_at": r.created_at,
    }


def request_to_dict(req, include_file=False):
    data = {
        "id": req.id, "employee_id": req.employee_id,
        "requirement_id": req.requirement_id, "document_id": req.document_id,
        "name": req.name, "description": req.description or "",
        "doc_type": req.doc_type, "is_mandatory": bool(req.is_mandatory),
        "due_date": req.due_date or "", "status": req.status,
        "submitted_at": req.submitted_at or "", "reviewed_at": req.reviewed_at or "",
        "reviewed_by": req.reviewed_by or "", "review_note": req.review_note or "",
        "created_at": req.created_at,
    }
    # The employee needs to know a blank form exists before they can fetch it.
    rule = getattr(req, "requirement", None)
    data["has_template"] = bool(rule is not None and rule.template_file_data)

    doc = req.document
    if doc:
        data["file_name"] = doc.file_name
        data["file_type"] = doc.file_type
        data["file_size"] = doc.file_size or 0
        if include_file:
            data["file_data"] = doc.file_data
    # Overdue and expiry are derived, never stored, so they cannot go stale.
    today = datetime.now().date()
    due = _parse_date(req.due_date)
    data["is_overdue"] = bool(
        due and req.status in ("pending", "rejected") and due < today
    )

    data["requires_expiry"] = bool(getattr(req, "requires_expiry", False))
    data["expires_on"] = getattr(req, "expires_on", "") or ""
    expires = _parse_date(data["expires_on"])
    data["is_expired"] = bool(expires and expires < today)
    data["days_until_expiry"] = (expires - today).days if expires else None
    reminder = 30
    if req.requirement_id:
        rule = getattr(req, "requirement", None)
        if rule is not None:
            reminder = rule.expiry_reminder_days or 30
    data["expiring_soon"] = bool(
        expires and not data["is_expired"] and (expires - today).days <= reminder
    )
    return data


def validate_requirement(body, db, client_id):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="A document name is required")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Document name must be 120 characters or fewer")
    applies = (body.applies_to or "all").strip().lower()
    if applies not in ("all", "department", "level"):
        raise HTTPException(status_code=400, detail="Applies to must be all, department or level")
    try:
        due_days = int(body.due_days if body.due_days is not None else 7)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Due days must be a whole number")
    if due_days < 0 or due_days > 365:
        raise HTTPException(status_code=400, detail="Due days must be between 0 and 365")
    if applies == "department":
        if not body.department_id:
            raise HTTPException(status_code=400, detail="Choose a department for this rule")
        dept = db.query(models.DBDepartment).filter(
            models.DBDepartment.id == body.department_id,
            models.DBDepartment.client_id == client_id,
        ).first()
        if not dept:
            raise HTTPException(status_code=400, detail="Department not found")
    level = validate_level(body.level)
    if applies == "level" and not level:
        raise HTTPException(status_code=400, detail="Choose a level for this rule")
    try:
        reminder = int(body.expiry_reminder_days if body.expiry_reminder_days is not None else 30)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Expiry reminder must be a whole number of days")
    if reminder < 0 or reminder > 365:
        raise HTTPException(status_code=400, detail="Expiry reminder must be between 0 and 365 days")
    return name, applies, due_days, level, reminder


def requirement_applies_to_employee(req, emp):
    if not req.is_active:
        return False
    if req.applies_to == "department":
        return bool(req.department_id) and emp.department_id == req.department_id
    if req.applies_to == "level":
        return bool(req.level) and (emp.level or "") == req.level
    return True


def sync_requirement_to_requests(db, client_id, req):
    """Push a requirement change out to the people already holding it.

    Requests are copies, taken at the moment they were assigned, so an edit in
    HR's settings otherwise never reached anyone already on the system. That is
    how "this document now needs an expiry date" could be switched on and no
    employee was ever asked for one.

    Only outstanding requests are touched. Anything already submitted keeps the
    terms it was handed in under - restating those would reopen settled work and
    could mark an approved document as missing a date nobody was asked for.
    """
    outstanding = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == client_id,
        models.DBDocumentRequest.requirement_id == req.id,
        models.DBDocumentRequest.status.in_(("pending", "rejected")),
    ).all()
    if not outstanding:
        return 0

    employees = {
        e.id: e for e in db.query(models.DBEmployee).filter(
            models.DBEmployee.id.in_([r.employee_id for r in outstanding])
        ).all()
    }

    touched = 0
    for row in outstanding:
        emp = employees.get(row.employee_id)
        # Narrowing a requirement to a department or level should stop asking
        # the people it no longer covers.
        if emp is not None and not requirement_applies_to_employee(req, emp):
            db.delete(row)
            touched += 1
            continue
        row.name = req.name
        row.description = req.description or ""
        row.doc_type = req.doc_type
        row.is_mandatory = bool(req.is_mandatory)
        row.requires_expiry = bool(req.requires_expiry)
        if emp is not None:
            start = _parse_date(emp.start_date) or datetime.now().date()
            row.due_date = (start + timedelta(days=req.due_days or 0)).strftime("%Y-%m-%d")
        touched += 1
    return touched


def assign_document_requests(db, client_id, emp, requirements=None):
    """Create the outstanding requests for one employee, skipping any they
    already have so this is safe to re-run after a department or level change."""
    if requirements is None:
        requirements = db.query(models.DBDocumentRequirement).filter(
            models.DBDocumentRequirement.client_id == client_id,
            models.DBDocumentRequirement.is_active == True,
        ).order_by(models.DBDocumentRequirement.sort_order.asc()).all()

    existing = {
        r.requirement_id for r in db.query(models.DBDocumentRequest).filter(
            models.DBDocumentRequest.employee_id == emp.id
        ).all() if r.requirement_id
    }
    start = _parse_date(emp.start_date) or datetime.now().date()
    created = []
    for req in requirements:
        if req.id in existing or not requirement_applies_to_employee(req, emp):
            continue
        created.append(models.DBDocumentRequest(
            client_id=client_id, employee_id=emp.id, requirement_id=req.id,
            name=req.name, description=req.description or "", doc_type=req.doc_type,
            is_mandatory=bool(req.is_mandatory),
            requires_expiry=bool(req.requires_expiry),
            due_date=(start + timedelta(days=req.due_days or 0)).strftime("%Y-%m-%d"),
        ))
    for row in created:
        db.add(row)
    return created


def seed_default_requirements(db, client_id):
    """First time HR opens the settings there is something sensible to edit,
    rather than an empty screen that looks broken."""
    existing = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.client_id == client_id
    ).count()
    if existing:
        return []
    rows = []
    for order, (name, desc, dtype, mandatory, days) in enumerate(DEFAULT_DOCUMENT_REQUIREMENTS):
        row = models.DBDocumentRequirement(
            client_id=client_id, name=name, description=desc, doc_type=dtype,
            is_mandatory=mandatory, due_days=days, sort_order=order,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


# --- HR: manage requirements ------------------------------------------------

@app.get("/api/onboarding/requirements")
def list_document_requirements(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    rows = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.client_id == client.id
    ).order_by(models.DBDocumentRequirement.sort_order.asc(),
               models.DBDocumentRequirement.id.asc()).all()
    if not rows:
        rows = seed_default_requirements(db, client.id)
        db.commit()
    return [requirement_to_dict(r) for r in rows]


@app.post("/api/onboarding/requirements")
def create_document_requirement(request: Request, body: DocumentRequirementIn, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    name, applies, due_days, level, reminder = validate_requirement(body, db, client.id)
    clash = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.client_id == client.id,
        sqlfunc.lower(models.DBDocumentRequirement.name) == name.lower(),
    ).first()
    if clash:
        raise HTTPException(status_code=400, detail=f"'{name}' is already on the list")
    row = models.DBDocumentRequirement(
        client_id=client.id, name=name, description=body.description or "",
        doc_type=body.doc_type or "other", is_mandatory=bool(body.is_mandatory),
        due_days=due_days, applies_to=applies,
        requires_expiry=bool(body.requires_expiry), expiry_reminder_days=reminder,
        department_id=body.department_id if applies == "department" else None,
        level=level if applies == "level" else "",
        is_active=bool(body.is_active), sort_order=int(body.sort_order or 0),
    )
    db.add(row)
    log_audit(db, client.id, "doc_requirement_created", "requirement", None, name, "", request)
    db.commit()
    db.refresh(row)
    return requirement_to_dict(row)


@app.put("/api/onboarding/requirements/{req_id}")
def update_document_requirement(req_id: int, request: Request, body: DocumentRequirementIn, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    row = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.id == req_id,
        models.DBDocumentRequirement.client_id == client.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    name, applies, due_days, level, reminder = validate_requirement(body, db, client.id)
    clash = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.client_id == client.id,
        models.DBDocumentRequirement.id != req_id,
        sqlfunc.lower(models.DBDocumentRequirement.name) == name.lower(),
    ).first()
    if clash:
        raise HTTPException(status_code=400, detail=f"'{name}' is already on the list")
    row.name = name
    row.description = body.description or ""
    row.doc_type = body.doc_type or "other"
    row.is_mandatory = bool(body.is_mandatory)
    row.due_days = due_days
    row.requires_expiry = bool(body.requires_expiry)
    row.expiry_reminder_days = reminder
    row.applies_to = applies
    row.department_id = body.department_id if applies == "department" else None
    row.level = level if applies == "level" else ""
    row.is_active = bool(body.is_active)
    row.sort_order = int(body.sort_order or 0)
    db.flush()
    # Otherwise the change only applies to people hired after it.
    sync_requirement_to_requests(db, client.id, row)
    # Widening the rule should also reach anyone it now covers for the first time.
    if row.is_active:
        for emp in db.query(models.DBEmployee).filter(
            models.DBEmployee.client_id == client.id,
            models.DBEmployee.status != "offboarded",
        ).all():
            assign_document_requests(db, client.id, emp, requirements=[row])
    db.commit()
    return requirement_to_dict(row)


@app.delete("/api/onboarding/requirements/{req_id}")
def delete_document_requirement(req_id: int, request: Request, db: Session = Depends(get_db)):
    """Outstanding requests go with it; anything already submitted is kept so
    the record of what someone provided is not destroyed."""
    client = get_client_user(request, db)
    row = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.id == req_id,
        models.DBDocumentRequirement.client_id == client.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.requirement_id == req_id,
        models.DBDocumentRequest.status == "pending",
    ).delete(synchronize_session=False)
    db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.requirement_id == req_id
    ).update({"requirement_id": None}, synchronize_session=False)
    log_audit(db, client.id, "doc_requirement_deleted", "requirement", row.id, row.name, "", request)
    db.delete(row)
    db.commit()
    return {"message": "Requirement removed"}


@app.post("/api/employees/{emp_id}/document-requests/sync")
def sync_employee_document_requests(emp_id: int, request: Request, db: Session = Depends(get_db)):
    """Apply the current requirements to one employee - used after their
    department or level changes, or for staff who predate a new rule."""
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    created = assign_document_requests(db, client.id, emp)
    db.commit()
    return {"message": f"{len(created)} document request(s) added", "added": len(created)}


@app.get("/api/employees/{emp_id}/document-requests")
def list_employee_document_requests(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    rows = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.employee_id == emp_id
    ).order_by(models.DBDocumentRequest.id.asc()).all()
    return [request_to_dict(r) for r in rows]


# --- HR: the review queue ---------------------------------------------------

@app.get("/api/onboarding/document-queue")
def document_review_queue(request: Request, status: str = "submitted", db: Session = Depends(get_db)):
    """What employees have sent in, waiting on HR. This is the auto-fetch the
    employee portal feeds."""
    client = get_client_user(request, db)
    query = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == client.id
    )
    if status and status != "all":
        query = query.filter(models.DBDocumentRequest.status == status)
    rows = query.order_by(models.DBDocumentRequest.submitted_at.desc(),
                          models.DBDocumentRequest.id.desc()).all()

    emp_names = {
        e.id: f"{e.first_name} {e.last_name}"
        for e in db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id).all()
    }
    out = []
    for r in rows:
        data = request_to_dict(r)
        data["employee_name"] = emp_names.get(r.employee_id, "")
        out.append(data)
    return out


@app.get("/api/onboarding/document-requests/{req_id}/file")
def download_document_request_file(req_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    row = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.id == req_id,
        models.DBDocumentRequest.client_id == client.id,
    ).first()
    if not row or not row.document:
        raise HTTPException(status_code=404, detail="No file submitted for this document")
    return {
        "file_name": row.document.file_name, "file_type": row.document.file_type,
        "file_data": row.document.file_data, "name": row.name,
    }


@app.post("/api/onboarding/document-requests/{req_id}/review")
def review_document_request(req_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    body = body or {}
    row = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.id == req_id,
        models.DBDocumentRequest.client_id == client.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document request not found")
    if row.status not in ("submitted", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="Nothing has been submitted for this document yet")

    decision = (body.get("decision") or "").strip().lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Decision must be approve or reject")
    note = (body.get("note") or "").strip()
    if decision == "reject" and not note:
        raise HTTPException(
            status_code=400,
            detail="Give a reason so the employee knows what to resubmit",
        )

    row.status = "approved" if decision == "approve" else "rejected"
    row.reviewed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row.reviewed_by = body.get("reviewed_by") or "HR"
    row.review_note = note

    db.add(models.DBNotification(
        client_id=client.id, employee_id=row.employee_id,
        title=f"Document {row.status}: {row.name}",
        message=note or (f"Your {row.name} has been approved." if decision == "approve"
                         else f"Your {row.name} needs resubmitting."),
        type="success" if decision == "approve" else "warning",
    ))
    log_audit(db, client.id, f"document_{row.status}", "document_request", row.id,
              row.name, f"Employee {row.employee_id}", request)
    # Approving the last outstanding document can be what finishes onboarding,
    # so completion is checked here as well as on the checklist.
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == row.employee_id).first()
    maybe_complete_onboarding(db, emp)
    db.commit()
    return request_to_dict(row)



class RequirementTemplateIn(BaseModel):
    file_name: str
    file_type: Optional[str] = ""
    file_data: str


@app.post("/api/onboarding/requirements/{req_id}/template")
def upload_requirement_template(req_id: int, body: RequirementTemplateIn, request: Request,
                                db: Session = Depends(get_db)):
    """Attach a blank form for the employee to download, fill in and return."""
    client = get_client_user(request, db)
    row = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.id == req_id,
        models.DBDocumentRequirement.client_id == client.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    validate_candidate_document(body)
    row.template_file_name = body.file_name
    row.template_file_type = body.file_type or ""
    row.template_file_data = body.file_data
    db.commit()
    return {"message": f"Template attached to {row.name}", "template_file_name": row.template_file_name}


@app.delete("/api/onboarding/requirements/{req_id}/template")
def delete_requirement_template(req_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    row = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.id == req_id,
        models.DBDocumentRequirement.client_id == client.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Requirement not found")
    row.template_file_name = ""
    row.template_file_type = ""
    row.template_file_data = ""
    db.commit()
    return {"message": "Template removed"}


@app.get("/api/onboarding/requirements/{req_id}/template")
def download_requirement_template(req_id: int, request: Request, db: Session = Depends(get_db)):
    """Readable by HR and by any employee who has been asked for it."""
    client_id = None
    if request.session.get("client_id"):
        client_id = request.session["client_id"]
    elif request.session.get("employee_id"):
        client_id = request.session.get("employee_client_id")
    if not client_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    row = db.query(models.DBDocumentRequirement).filter(
        models.DBDocumentRequirement.id == req_id,
        models.DBDocumentRequirement.client_id == client_id,
    ).first()
    if not row or not row.template_file_data:
        raise HTTPException(status_code=404, detail="No template attached to this document")
    return {
        "file_name": row.template_file_name,
        "file_type": row.template_file_type,
        "file_data": row.template_file_data,
    }


@app.get("/api/onboarding/expiring-documents")
def expiring_documents(request: Request, days: int = 60, db: Session = Depends(get_db)):
    """Approved documents that have expired or are about to.

    Right-to-work and DBS checks lapse quietly; this is what stops a company
    finding out during an audit.
    """
    client = get_client_user(request, db)
    days = max(1, min(days, 365))
    horizon = (datetime.now().date() + timedelta(days=days))
    today = datetime.now().date()

    rows = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == client.id,
        models.DBDocumentRequest.status == "approved",
        models.DBDocumentRequest.expires_on != "",
    ).all()

    emp_names = {
        e.id: f"{e.first_name} {e.last_name}"
        for e in db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id).all()
    }
    out = []
    for r in rows:
        expires = _parse_date(r.expires_on)
        if not expires or expires > horizon:
            continue
        data = request_to_dict(r)
        data["employee_name"] = emp_names.get(r.employee_id, "")
        out.append(data)
    out.sort(key=lambda d: d["expires_on"])
    return {
        "expired": [d for d in out if d["is_expired"]],
        "expiring": [d for d in out if not d["is_expired"]],
        "window_days": days,
    }

# --- Employee portal: see and satisfy your own requirements ------------------

@app.get("/api/employee/document-requests")
def employee_document_requests(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    rows = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.employee_id == emp_id
    ).order_by(models.DBDocumentRequest.id.asc()).all()
    outstanding = sum(1 for r in rows if r.status in ("pending", "rejected"))
    return {
        "requests": [request_to_dict(r) for r in rows],
        "outstanding": outstanding,
        "complete": len(rows) > 0 and outstanding == 0,
        "limits": {
            "max_mb": MAX_DOCUMENT_BYTES // 1048576,
            "allowed": sorted(ALLOWED_DOCUMENT_EXTENSIONS),
        },
    }


class EmployeeDocumentUpload(BaseModel):
    file_name: str
    file_type: Optional[str] = ""
    file_data: str
    expires_on: Optional[str] = ""


@app.post("/api/employee/document-requests/{req_id}/upload")
def employee_upload_document(req_id: int, body: EmployeeDocumentUpload, request: Request,
                             db: Session = Depends(get_db)):
    """The employee satisfies one requirement. Reuses the same size and type
    checks as candidate uploads, since this is also a file from outside HR."""
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    row = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.id == req_id,
        models.DBDocumentRequest.employee_id == emp_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document request not found")
    if row.status == "approved":
        raise HTTPException(status_code=409, detail="This document has already been approved")

    size = validate_candidate_document(body)

    # HR decides which documents expire; the employee supplies the date.
    expires_on = (body.expires_on or "").strip()
    if row.requires_expiry:
        if not expires_on:
            raise HTTPException(
                status_code=400,
                detail=f"{row.name} needs an expiry date. Enter the date shown on the document.",
            )
        parsed = _parse_date(expires_on)
        if not parsed:
            raise HTTPException(status_code=400, detail="Expiry date must be in YYYY-MM-DD format")
        if parsed <= datetime.now().date():
            raise HTTPException(
                status_code=400,
                detail="That document has already expired. Please upload a current one.",
            )
    else:
        # HR did not ask for a date on this one, so nothing the client sends is
        # kept. Storing it anyway would let a stale value from another upload
        # put a document into the expiring-soon queue nobody set a date for.
        expires_on = ""

    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()

    doc = models.DBDocument(
        client_id=row.client_id, employee_id=emp_id,
        title=row.name, doc_type=row.doc_type,
        file_name=body.file_name, file_type=body.file_type or "",
        file_size=size, file_data=body.file_data,
        uploaded_by=f"{emp.first_name} {emp.last_name}" if emp else "Employee",
    )
    db.add(doc)
    db.flush()

    row.document_id = doc.id
    row.expires_on = expires_on
    row.status = "submitted"
    row.submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row.reviewed_at = ""
    row.reviewed_by = ""
    row.review_note = ""
    log_audit(db, row.client_id, "document_submitted", "document_request", row.id,
              row.name, f"Employee {emp_id}", request, user_type="employee",
              user_name=f"{emp.first_name} {emp.last_name}" if emp else "")
    db.commit()
    return {"message": f"{row.name} submitted for review", "status": row.status}

# ============ RECRUITMENT ============

class RecruitmentFormCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    fields: Optional[str] = "[]"
    job_id: Optional[int] = None
    pipeline_stages: Optional[str] = '["Applied","Screening","Interview","Offer","Hired"]'

class CandidateDocumentIn(BaseModel):
    doc_type: Optional[str] = "other"
    file_name: str
    file_type: Optional[str] = ""
    file_data: str


class FormSubmissionCreate(BaseModel):
    answers: Optional[str] = "{}"
    file_name: Optional[str] = ""
    file_type: Optional[str] = ""
    file_data: Optional[str] = ""
    candidate_name: Optional[str] = ""
    candidate_email: Optional[str] = ""
    candidate_phone: Optional[str] = ""
    documents: Optional[List[CandidateDocumentIn]] = None


# --- Candidate file handling ------------------------------------------------
# The application form is public, so uploads are the one place an anonymous
# visitor can put bytes in the database. Everything is bounded.

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024      # 5 MB per file
MAX_DOCUMENTS_PER_APPLICATION = 6
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png", "image/jpeg", "image/webp",
    "text/plain",
}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".txt"}


def decoded_size(data_uri_or_b64: str) -> int:
    """Byte size of a base64 payload without materialising it."""
    if not data_uri_or_b64:
        return 0
    raw = data_uri_or_b64.split(",", 1)[-1]
    padding = raw[-2:].count("=") if len(raw) >= 2 else 0
    return max(0, (len(raw) * 3) // 4 - padding)


def validate_candidate_document(doc, index=1):
    name = (doc.file_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=f"Document {index}: a file name is required")
    ext = os.path.splitext(name)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"'{name}' is not an accepted file type. Allowed: "
                   + ", ".join(sorted(ALLOWED_DOCUMENT_EXTENSIONS)),
        )
    mime = (doc.file_type or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"'{name}' has an unsupported content type ({mime})")
    size = decoded_size(doc.file_data)
    if size == 0:
        raise HTTPException(status_code=400, detail=f"'{name}' appears to be empty")
    if size > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"'{name}' is {size / 1048576:.1f} MB; the limit is "
                   f"{MAX_DOCUMENT_BYTES // 1048576} MB per file",
        )
    return size

@app.get("/api/recruitment/forms")
def list_recruitment_forms(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    forms = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.client_id == client.id
    ).order_by(models.DBRecruitmentForm.created_at.desc()).all()
    result = []
    for f in forms:
        sub_count = db.query(models.DBFormSubmission).filter(models.DBFormSubmission.form_id == f.id).count()
        hired_count = db.query(models.DBFormSubmission).filter(models.DBFormSubmission.form_id == f.id, models.DBFormSubmission.current_stage == 'Hired').count()
        pipeline_count = db.query(models.DBFormSubmission).filter(models.DBFormSubmission.form_id == f.id, models.DBFormSubmission.current_stage.notin_(['Hired', 'Rejected'])).count()
        result.append({
            "id": f.id, "title": f.title, "description": f.description,
            "fields": f.fields, "is_active": f.is_active,
            "form_token": f.form_token, "pipeline_stages": f.pipeline_stages,
            "job_id": f.job_id, "job_title": f.job.title if f.job else "",
            "created_at": f.created_at, "submission_count": sub_count,
            "hired_count": hired_count, "pipeline_count": pipeline_count
        })
    return result

@app.post("/api/recruitment/forms")
def create_recruitment_form(request: Request, body: RecruitmentFormCreate, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if body.job_id:
        job = db.query(models.DBJobRequisition).filter(
            models.DBJobRequisition.id == body.job_id,
            models.DBJobRequisition.client_id == client.id,
        ).first()
        if not job:
            raise HTTPException(status_code=400, detail="Job not found")
    form = models.DBRecruitmentForm(
        client_id=client.id, title=body.title, description=body.description, fields=body.fields,
        pipeline_stages=body.pipeline_stages, job_id=body.job_id,
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return {"id": form.id, "form_token": form.form_token, "job_id": form.job_id, "message": "Form created"}

@app.put("/api/recruitment/forms/{form_id}")
def update_recruitment_form(form_id: int, request: Request, body: dict, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    form = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.id == form_id, models.DBRecruitmentForm.client_id == client.id
    ).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    if "title" in body: form.title = body["title"]
    if "description" in body: form.description = body["description"]
    if "fields" in body: form.fields = body["fields"]
    if "is_active" in body: form.is_active = body["is_active"]
    if "pipeline_stages" in body: form.pipeline_stages = body["pipeline_stages"]
    db.commit()
    return {"message": "Form updated"}

@app.delete("/api/recruitment/forms/{form_id}")
def delete_recruitment_form(form_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    form = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.id == form_id, models.DBRecruitmentForm.client_id == client.id
    ).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    # Documents and pipeline history reference the submissions, so they must go
    # first or the delete fails on a foreign key.
    sub_ids = [s.id for s in db.query(models.DBFormSubmission.id).filter(
        models.DBFormSubmission.form_id == form_id
    ).all()]
    if sub_ids:
        for model in (models.DBCandidateDocument, models.DBSubmissionEvent,
                      models.DBInterview, models.DBOffer):
            db.query(model).filter(model.submission_id.in_(sub_ids)).delete(synchronize_session=False)
    db.query(models.DBFormSubmission).filter(models.DBFormSubmission.form_id == form_id).delete()
    log_audit(db, client.id, "recruitment_form_deleted", "form", form.id, form.title,
              f"{len(sub_ids)} application(s) removed", request)
    db.delete(form)
    db.commit()
    return {"message": "Form deleted"}

@app.get("/api/recruitment/forms/{form_id}/submissions")
def list_form_submissions(form_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    form = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.id == form_id, models.DBRecruitmentForm.client_id == client.id
    ).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    subs = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.form_id == form_id
    ).order_by(models.DBFormSubmission.created_at.desc()).all()
    # File payloads are deliberately omitted: a list of 200 candidates each
    # carrying a base64 CV is tens of megabytes. Documents are fetched per
    # candidate from /api/recruitment/submissions/{id}/documents.
    doc_counts = dict(
        db.query(models.DBCandidateDocument.submission_id, sqlfunc.count(models.DBCandidateDocument.id))
        .filter(models.DBCandidateDocument.submission_id.in_([s.id for s in subs] or [0]))
        .group_by(models.DBCandidateDocument.submission_id).all()
    )
    return [{
        "id": s.id, "form_id": s.form_id, "answers": s.answers, "file_name": s.file_name,
        "file_type": s.file_type,
        "has_resume": bool(s.file_data) or doc_counts.get(s.id, 0) > 0,
        "document_count": doc_counts.get(s.id, 0) or (1 if s.file_data else 0),
        "candidate_name": s.candidate_name,
        "candidate_email": s.candidate_email,
        "candidate_phone": getattr(s, 'candidate_phone', '') or '',
        "status": s.status,
        "rating": getattr(s, 'rating', 0) or 0,
        "hired_employee_id": getattr(s, 'hired_employee_id', None),
        "source": getattr(s, 'source', 'direct') or 'direct',
        "rejected_reason": getattr(s, 'rejected_reason', '') or '',
        "current_stage": getattr(s, 'current_stage', 'Applied'),
        "stage_order": getattr(s, 'stage_order', 0),
        "notes": s.notes, "created_at": s.created_at,
    } for s in subs]

@app.put("/api/recruitment/submissions/{sub_id}")
def update_submission(sub_id: int, request: Request, body: dict, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = db.query(models.DBFormSubmission).join(models.DBRecruitmentForm).filter(
        models.DBFormSubmission.id == sub_id,
        models.DBRecruitmentForm.client_id == client.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if "status" in body: sub.status = body["status"]
    if "notes" in body: sub.notes = body["notes"]
    db.commit()
    return {"message": "Submission updated"}

@app.get("/api/recruitment/forms/{form_id}/pipeline")
def get_form_pipeline(form_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    form = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.id == form_id, models.DBRecruitmentForm.client_id == client.id
    ).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    import json
    stages_str = form.pipeline_stages or '["Applied","Screening","Interview","Offer","Hired"]'
    try:
        stages = json.loads(stages_str)
    except Exception:
        stages = ["Applied","Screening","Interview","Offer","Hired"]
    subs = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.form_id == form_id
    ).order_by(models.DBFormSubmission.stage_order.asc(), models.DBFormSubmission.created_at.desc()).all()
    pipeline = {}
    for s in subs:
        stage = getattr(s, 'current_stage', 'Applied') or 'Applied'
        if stage not in pipeline:
            pipeline[stage] = []
        pipeline[stage].append({
            "id": s.id, "answers": s.answers, "file_name": s.file_name,
            "file_type": s.file_type, "candidate_name": s.candidate_name,
            "candidate_email": s.candidate_email, "status": s.status,
            "rating": getattr(s, 'rating', 0) or 0,
            "hired_employee_id": getattr(s, 'hired_employee_id', None),
            "current_stage": stage, "stage_order": getattr(s, 'stage_order', 0),
            "notes": s.notes, "created_at": s.created_at,
        })
    # Stages with no candidates must still render as empty columns.
    for st in stages:
        pipeline.setdefault(st, [])
    return {"stages": stages, "pipeline": pipeline}

@app.put("/api/recruitment/submissions/{sub_id}/stage")
def move_submission_stage(sub_id: int, request: Request, body: dict, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = db.query(models.DBFormSubmission).join(models.DBRecruitmentForm).filter(
        models.DBFormSubmission.id == sub_id,
        models.DBRecruitmentForm.client_id == client.id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    new_stage = body.get("stage")
    stage_order = body.get("stage_order", 0)
    if not new_stage:
        raise HTTPException(status_code=400, detail="stage is required")
    # Only stages the form actually defines, so a typo cannot strand a
    # candidate in a column the board never renders.
    form = db.query(models.DBRecruitmentForm).filter(models.DBRecruitmentForm.id == sub.form_id).first()
    try:
        valid_stages = json.loads(form.pipeline_stages or "[]") if form else []
    except (ValueError, TypeError):
        valid_stages = []
    if valid_stages and new_stage not in valid_stages:
        raise HTTPException(
            status_code=400,
            detail=f"'{new_stage}' is not a stage on this form. Valid stages: {', '.join(valid_stages)}",
        )
    previous = sub.current_stage
    if previous == new_stage:
        return {"message": f"Candidate already in {new_stage}", "stage": new_stage}
    sub.current_stage = new_stage
    sub.stage_order = stage_order
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=sub.id,
        from_stage=previous or "", to_stage=new_stage,
        note=body.get("note", ""), actor=body.get("actor", "HR"),
    ))
    log_audit(db, client.id, "candidate_stage_changed", "candidate", sub.id,
              sub.candidate_name or sub.candidate_email, f"{previous} -> {new_stage}", request)
    db.commit()
    return {"message": f"Candidate moved to {new_stage}", "stage": new_stage, "from_stage": previous}


@app.get("/api/recruitment/submissions/{sub_id}/documents")
def list_candidate_documents(sub_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.id == sub_id, models.DBFormSubmission.client_id == client.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    docs = db.query(models.DBCandidateDocument).filter(
        models.DBCandidateDocument.submission_id == sub_id
    ).order_by(models.DBCandidateDocument.id.asc()).all()
    # Metadata only; the payload is fetched per file so a candidate list with
    # many CVs does not ship megabytes of base64.
    return [{
        "id": d.id, "doc_type": d.doc_type, "file_name": d.file_name,
        "file_type": d.file_type, "file_size": d.file_size, "created_at": d.created_at,
    } for d in docs]


@app.get("/api/recruitment/documents/{doc_id}")
def get_candidate_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    doc = db.query(models.DBCandidateDocument).filter(
        models.DBCandidateDocument.id == doc_id, models.DBCandidateDocument.client_id == client.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": doc.id, "file_name": doc.file_name, "file_type": doc.file_type,
        "doc_type": doc.doc_type, "file_size": doc.file_size, "file_data": doc.file_data,
    }


@app.post("/api/recruitment/submissions/{sub_id}/documents")
def add_candidate_document(sub_id: int, body: CandidateDocumentIn, request: Request, db: Session = Depends(get_db)):
    """Let HR attach a document to an existing application (signed offer,
    interview scorecard, reference)."""
    client = get_client_user(request, db)
    sub = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.id == sub_id, models.DBFormSubmission.client_id == client.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    existing = db.query(models.DBCandidateDocument).filter(
        models.DBCandidateDocument.submission_id == sub_id
    ).count()
    if existing >= MAX_DOCUMENTS_PER_APPLICATION * 2:
        raise HTTPException(status_code=400, detail="This candidate already has the maximum number of documents")
    size = validate_candidate_document(body)
    doc = models.DBCandidateDocument(
        client_id=client.id, submission_id=sub_id,
        doc_type=body.doc_type or "other", file_name=body.file_name,
        file_type=body.file_type or "", file_size=size, file_data=body.file_data,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"id": doc.id, "message": "Document attached"}


@app.delete("/api/recruitment/documents/{doc_id}")
def delete_candidate_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    doc = db.query(models.DBCandidateDocument).filter(
        models.DBCandidateDocument.id == doc_id, models.DBCandidateDocument.client_id == client.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()
    return {"message": "Document removed"}


@app.get("/api/recruitment/submissions/{sub_id}/history")
def get_submission_history(sub_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    sub = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.id == sub_id, models.DBFormSubmission.client_id == client.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    events = db.query(models.DBSubmissionEvent).filter(
        models.DBSubmissionEvent.submission_id == sub_id
    ).order_by(models.DBSubmissionEvent.id.asc()).all()
    return [{
        "id": e.id, "from_stage": e.from_stage, "to_stage": e.to_stage,
        "note": e.note, "actor": e.actor, "created_at": e.created_at,
    } for e in events]


@app.post("/api/recruitment/submissions/{sub_id}/hire")
def hire_candidate(sub_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Turn a successful candidate into an employee.

    Previously a hire had to be retyped by hand into the employee form, which
    is where names, emails and start dates get transcribed wrongly.
    """
    client = get_client_user(request, db)
    body = body or {}
    sub = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.id == sub_id, models.DBFormSubmission.client_id == client.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.hired_employee_id:
        raise HTTPException(status_code=409, detail="This candidate has already been converted to an employee")
    if sub.status == "rejected":
        raise HTTPException(
            status_code=409,
            detail="This candidate was rejected. Reopen the application before hiring them.",
        )

    email = (body.get("email") or sub.candidate_email or "").strip()
    if not email or not validate_email_address(email):
        raise HTTPException(status_code=400, detail="A valid email address is required to create the employee record")
    if db.query(models.DBEmployee).filter(
        models.DBEmployee.email == email, models.DBEmployee.client_id == client.id
    ).first():
        raise HTTPException(status_code=400, detail="An employee with this email already exists")

    full_name = (body.get("full_name") or sub.candidate_name or "").strip()
    parts = full_name.split()
    first_name = body.get("first_name") or (parts[0] if parts else "New")
    last_name = body.get("last_name") or (" ".join(parts[1:]) if len(parts) > 1 else "Starter")

    level = validate_level(body.get("level"))
    role = validate_role(body.get("role"))
    reports_to = validate_manager(db, client.id, None, body.get("reports_to"))

    max_num = db.query(sqlfunc.coalesce(sqlfunc.max(models.DBEmployee.id), 0)).filter(
        models.DBEmployee.client_id == client.id
    ).scalar()
    emp = models.DBEmployee(
        client_id=client.id, employee_id=f"EMP-{max_num + 1:04d}",
        first_name=first_name, last_name=last_name, email=email,
        phone=body.get("phone") or sub.candidate_phone or "",
        job_title=body.get("job_title", ""), department_id=body.get("department_id"),
        reports_to=reports_to, level=level, role=role,
        employment_type=body.get("employment_type", "full_time"),
        pay_frequency=body.get("pay_frequency", "monthly"),
        salary=float(body.get("salary") or 0),
        start_date=body.get("start_date", ""),
        status="onboarding",
    )
    db.add(emp)
    db.flush()

    # Carry the application's files across so the new starter's record already
    # holds their CV and right-to-work documents.
    for doc in db.query(models.DBCandidateDocument).filter(
        models.DBCandidateDocument.submission_id == sub.id
    ).all():
        db.add(models.DBDocument(
            client_id=client.id, employee_id=emp.id,
            title=doc.file_name or doc.doc_type, doc_type=doc.doc_type,
            file_name=doc.file_name, file_type=doc.file_type,
            file_data=doc.file_data, uploaded_by="Recruitment",
        ))

    # Same start as anyone added by hand: a checklist and the documents HR
    # asks new starters for. Without this a hire arrived with nothing to do
    # and nothing asked of them.
    start_onboarding(db, client.id, emp)

    sub.hired_employee_id = emp.id
    sub.status = "hired"
    sub.hired_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    form = db.query(models.DBRecruitmentForm).filter(models.DBRecruitmentForm.id == sub.form_id).first()
    try:
        stages = json.loads(form.pipeline_stages or "[]") if form else []
    except (ValueError, TypeError):
        stages = []
    sub.current_stage = stages[-1] if stages else "Hired"
    db.add(models.DBSubmissionEvent(
        client_id=client.id, submission_id=sub.id,
        from_stage=sub.current_stage or "", to_stage="Hired",
        actor="HR", note=f"Converted to employee {emp.employee_id}",
    ))
    log_audit(db, client.id, "candidate_hired", "candidate", sub.id,
              full_name or email, f"Employee {emp.employee_id}", request)
    db.commit()
    db.refresh(emp)
    return {
        "message": f"{first_name} {last_name} added as {emp.employee_id}",
        "employee_id": emp.id, "employee_number": emp.employee_id,
    }


@app.put("/api/recruitment/submissions/{sub_id}/rating")
def rate_candidate(sub_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    body = body or {}
    sub = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.id == sub_id, models.DBFormSubmission.client_id == client.id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    try:
        rating = int(body.get("rating", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Rating must be a whole number")
    if rating < 0 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 0 and 5")
    sub.rating = rating
    db.commit()
    return {"message": "Rating saved", "rating": rating}

@app.get("/api/recruitment/form/{token}")
def get_public_form(token: str, db: Session = Depends(get_db)):
    form = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.form_token == token,
        models.DBRecruitmentForm.is_active == True,
    ).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found or inactive")
    return {"title": form.title, "description": form.description, "fields": form.fields}

@app.post("/api/recruitment/form/{token}/submit")
def submit_application(token: str, body: FormSubmissionCreate, request: Request, db: Session = Depends(get_db)):
    """Public endpoint - anyone with the form link can post here, so it is rate
    limited and every attachment is size- and type-checked."""
    ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"apply:{ip}", max_requests=5, window=600):
        raise HTTPException(status_code=429, detail="Too many applications submitted. Please try again later.")

    form = db.query(models.DBRecruitmentForm).filter(
        models.DBRecruitmentForm.form_token == token,
        models.DBRecruitmentForm.is_active == True,
    ).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found or inactive")

    if body.candidate_email and not validate_email_address(body.candidate_email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")

    docs = list(body.documents or [])
    # Fold the single legacy attachment into the document list.
    if body.file_data and body.file_name:
        docs.insert(0, CandidateDocumentIn(
            doc_type="resume", file_name=body.file_name,
            file_type=body.file_type or "", file_data=body.file_data,
        ))
    if len(docs) > MAX_DOCUMENTS_PER_APPLICATION:
        raise HTTPException(
            status_code=400,
            detail=f"Please attach at most {MAX_DOCUMENTS_PER_APPLICATION} files",
        )
    sizes = [validate_candidate_document(d, i + 1) for i, d in enumerate(docs)]
    if sum(sizes) > MAX_DOCUMENT_BYTES * 2:
        raise HTTPException(status_code=413, detail="The attachments are too large in total")

    first_stage = "Applied"
    try:
        stages = json.loads(form.pipeline_stages or "[]")
        if stages:
            first_stage = stages[0]
    except (ValueError, TypeError):
        pass

    sub = models.DBFormSubmission(
        client_id=form.client_id, form_id=form.id,
        answers=body.answers,
        file_name=docs[0].file_name if docs else "",
        file_type=docs[0].file_type if docs else "",
        file_data=docs[0].file_data if docs else "",
        candidate_name=body.candidate_name, candidate_email=body.candidate_email,
        candidate_phone=body.candidate_phone or "",
        current_stage=first_stage, stage_order=0,
    )
    db.add(sub)
    db.flush()

    for doc, size in zip(docs, sizes):
        db.add(models.DBCandidateDocument(
            client_id=form.client_id, submission_id=sub.id,
            doc_type=doc.doc_type or "other", file_name=doc.file_name,
            file_type=doc.file_type or "", file_size=size, file_data=doc.file_data,
        ))
    db.add(models.DBSubmissionEvent(
        client_id=form.client_id, submission_id=sub.id,
        from_stage="", to_stage=first_stage, actor="Candidate",
        note="Application received",
    ))
    db.commit()
    return {
        "message": "Application submitted successfully",
        "documents_received": len(docs),
        "stage": first_stage,
    }


@app.get("/api/employee/goals")
def get_employee_goals(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    goals = db.query(models.DBEmployeeGoal).filter(models.DBEmployeeGoal.employee_id == emp_id).order_by(models.DBEmployeeGoal.created_at.desc()).all()
    return [{"id": g.id, "title": g.title, "description": g.description, "target_value": g.target_value, "current_value": g.current_value, "unit": g.unit, "category": g.category, "priority": g.priority, "start_date": g.start_date, "due_date": g.due_date, "status": g.status, "created_by": g.created_by} for g in goals]


@app.get("/api/employee/notifications")
def get_employee_notifications(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    notes = db.query(models.DBNotification).filter(models.DBNotification.employee_id == emp_id).order_by(models.DBNotification.created_at.desc()).limit(50).all()
    unread = db.query(models.DBNotification).filter(models.DBNotification.employee_id == emp_id, models.DBNotification.is_read == False).count()
    return {"notifications": [{"id": n.id, "title": n.title, "message": n.message, "type": n.type, "is_read": n.is_read, "link": n.link, "created_at": n.created_at, "sent_by": n.sent_by or ""} for n in notes], "unread_count": unread}


@app.patch("/api/employee/notifications/{note_id}/read")
def mark_notification_read(note_id: int, request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    note = db.query(models.DBNotification).filter(models.DBNotification.id == note_id, models.DBNotification.employee_id == emp_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Not found")
    note.is_read = True
    db.commit()
    return {"message": "Marked as read"}


@app.post("/api/employee/notifications/read-all")
def mark_all_notifications_read(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db.query(models.DBNotification).filter(models.DBNotification.employee_id == emp_id, models.DBNotification.is_read == False).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}


def working_days_between(start_date, end_date, settings=None) -> float:
    """Inclusive count of the tenant's own working days.

    Leave is booked in working days, so a Mon-Fri request is 5 days, not the 7
    a raw date subtraction would give. This used to hardcode Monday to Friday
    and ignore the working days the business had configured, so anyone open on
    a Saturday could not book Saturday leave at all - it came back as a range
    containing no working days - and every count was wrong for them.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if not start or not end or end < start:
        return 0.0
    from datetime import timedelta
    days = 0
    cursor = start
    while cursor <= end:
        if is_working_day(settings, cursor):
            days += 1
        cursor += timedelta(days=1)
    return float(days)


def leave_balance_for(db, emp) -> dict:
    """Entitlement and usage per leave type for one employee."""
    leaves = db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.employee_id == emp.id
    ).all()

    def taken(kind, statuses):
        return round(sum(l.days or 0 for l in leaves if l.leave_type == kind and l.status in statuses), 2)

    annual_total = emp.annual_leave_entitlement if emp.annual_leave_entitlement is not None else 25.0
    sick_total = emp.sick_leave_entitlement if emp.sick_leave_entitlement is not None else 10.0
    annual_taken = taken("annual", ("approved",))
    annual_pending = taken("annual", ("pending",))
    sick_taken = taken("sick", ("approved",))
    return {
        "annual_total": annual_total,
        "annual_taken": annual_taken,
        "annual_pending": annual_pending,
        "annual_remaining": round(annual_total - annual_taken - annual_pending, 2),
        "sick_total": sick_total,
        "sick_taken": sick_taken,
        "sick_remaining": round(sick_total - sick_taken, 2),
    }


@app.get("/api/employee/leave")
def get_employee_leave(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    leaves = db.query(models.DBLeaveRequest).filter(models.DBLeaveRequest.employee_id == emp_id).order_by(models.DBLeaveRequest.created_at.desc()).all()
    return {
        "requests": [{"id": l.id, "leave_type": l.leave_type, "start_date": l.start_date, "end_date": l.end_date, "days": l.days, "reason": l.reason, "status": l.status, "approved_by": l.approved_by, "created_at": l.created_at} for l in leaves],
        "balance": leave_balance_for(db, emp),
    }


@app.post("/api/employee/leave")
def request_leave(request: Request, body: dict, db: Session = Depends(get_db)):
    """Book leave. Days are computed server-side and checked against the
    remaining balance and existing bookings rather than trusted from the form."""
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    leave_type = (body.get("leave_type") or "annual").strip().lower()
    start_date = body.get("start_date", "")
    end_date = body.get("end_date", "")
    start, end = _parse_date(start_date), _parse_date(end_date)
    if not start or not end:
        raise HTTPException(status_code=400, detail="Start and end dates are required (YYYY-MM-DD)")
    if end < start:
        raise HTTPException(status_code=400, detail="End date cannot be before the start date")

    # Counted against this business's own working days, not a fixed Mon-Fri.
    att_settings = db.query(models.DBAttendanceSettings).filter(
        models.DBAttendanceSettings.client_id == emp.client_id).first()
    days = working_days_between(start_date, end_date, att_settings)
    if days <= 0:
        raise HTTPException(status_code=400, detail="That range contains no working days")

    for existing in db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.employee_id == emp_id,
        models.DBLeaveRequest.status.in_(["pending", "approved"]),
    ).all():
        e_start, e_end = _parse_date(existing.start_date), _parse_date(existing.end_date)
        if e_start and e_end and start <= e_end and e_start <= end:
            raise HTTPException(
                status_code=409,
                detail=f"This overlaps an existing {existing.status} request ({existing.start_date} to {existing.end_date})",
            )

    balance = leave_balance_for(db, emp)
    if leave_type == "annual" and days > balance["annual_remaining"]:
        raise HTTPException(
            status_code=400,
            detail=f"Only {balance['annual_remaining']:g} day(s) of annual leave remaining; you requested {days:g}",
        )
    if leave_type == "sick" and days > balance["sick_remaining"]:
        raise HTTPException(
            status_code=400,
            detail=f"Only {balance['sick_remaining']:g} day(s) of sick leave remaining; you requested {days:g}",
        )

    leave = models.DBLeaveRequest(
        client_id=emp.client_id, employee_id=emp_id,
        leave_type=leave_type, start_date=start_date, end_date=end_date,
        days=days, reason=body.get("reason", ""),
    )
    db.add(leave)
    db.add(models.DBNotification(
        client_id=emp.client_id, employee_id=emp_id,
        title="Leave Request Submitted",
        message=f"Your {leave_type} leave request for {days:g} day(s) has been submitted.",
        type="info",
    ))
    db.commit()
    return {"message": "Leave request submitted", "days": days, "balance": leave_balance_for(db, emp)}


@app.get("/api/employee/documents")
def get_employee_documents(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    docs = db.query(models.DBDocument).filter(models.DBDocument.employee_id == emp_id).order_by(models.DBDocument.created_at.desc()).all()
    return [{"id": d.id, "title": d.title, "doc_type": d.doc_type, "file_name": d.file_name, "uploaded_by": d.uploaded_by, "created_at": d.created_at} for d in docs]


@app.get("/api/employee/documents/{doc_id}/download")
def download_document(doc_id: int, request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    doc = db.query(models.DBDocument).filter(models.DBDocument.id == doc_id, models.DBDocument.employee_id == emp_id).first()
    if not doc or not doc.file_data:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"file_name": doc.file_name, "file_type": doc.file_type, "file_data": doc.file_data}


@app.get("/api/employee/profile")
def get_employee_profile(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == emp.department_id).first() if emp.department_id else None
    manager = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp.reports_to).first() if emp.reports_to else None
    team = db.query(models.DBEmployee).filter(models.DBEmployee.department_id == emp.department_id, models.DBEmployee.status == "active", models.DBEmployee.id != emp_id).all() if emp.department_id else []
    goals = db.query(models.DBEmployeeGoal).filter(models.DBEmployeeGoal.employee_id == emp_id).all()
    goal_progress = 0
    if goals:
        goal_progress = round(sum(min(g.current_value / g.target_value * 100, 100) for g in goals) / len(goals), 1)
    return {
        "full_name": f"{emp.first_name} {emp.last_name}",
        "first_name": emp.first_name,
        "last_name": emp.last_name,
        "email": emp.email,
        "phone": emp.phone,
        "address": emp.address,
        "job_title": emp.job_title,
        "role": emp.role,
        "level": emp.level or "",
        "employment_type": emp.employment_type,
        "department": dept.name if dept else "",
        "department_id": emp.department_id,
        "manager": f"{manager.first_name} {manager.last_name}" if manager else "",
        "start_date": emp.start_date,
        "work_location": emp.work_location,
        "emergency_contact": emp.emergency_contact,
        "emergency_phone": emp.emergency_phone,
        "employee_id_code": emp.employee_id,
        "bank_name": emp.bank_name or "",
        # Enough to tell whether the account on file is the right one, never
        # enough to use it, and never prefilled into an editable field.
        "bank_account_masked": mask_secret(emp.bank_account or ""),
        "goals_count": len(goals),
        "goal_progress": goal_progress,
        "team": [{"id": t.id, "name": f"{t.first_name} {t.last_name}", "job_title": t.job_title, "email": t.email} for t in team],
    }


@app.get("/api/employee/analytics")
def get_employee_analytics(request: Request, days: int = 30, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from datetime import timedelta
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    records = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp_id,
        models.DBAttendance.date >= start,
    ).order_by(models.DBAttendance.date.asc()).all()
    daily = []
    for r in records:
        daily.append({"date": r.date, "hours": r.total_hours or 0, "break": r.break_minutes or 0, "status": r.status, "check_type": r.check_type})
    total_hours = sum(d["hours"] for d in daily)
    days_present = len([d for d in daily if d["hours"] > 0])
    avg_hours = round(total_hours / max(days_present, 1), 1)
    late_days = 0
    for r in records:
        if r.clock_in:
            try:
                ci = datetime.strptime(r.clock_in, "%H:%M:%S")
                if ci.hour > 9 or (ci.hour == 9 and ci.minute > 15):
                    late_days += 1
            except: pass
    return {"daily": daily, "total_hours": round(total_hours, 1), "days_present": days_present, "avg_hours": avg_hours, "late_days": late_days, "period_days": days}


@app.get("/api/employee/team-presence")
def get_team_presence(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
    if not emp or not emp.department_id:
        return []
    today = datetime.now().strftime("%Y-%m-%d")
    team = db.query(models.DBEmployee).filter(models.DBEmployee.department_id == emp.department_id, models.DBEmployee.status == "active").all()
    result = []
    for t in team:
        att = db.query(models.DBAttendance).filter(models.DBAttendance.employee_id == t.id, models.DBAttendance.date == today).first()
        is_online = att and att.clock_in and not att.clock_out
        result.append({
            "id": t.id, "name": f"{t.first_name} {t.last_name}", "job_title": t.job_title,
            "is_online": is_online, "clock_in": att.clock_in if att else "",
            "is_on_break": att.is_on_break if att else False,
        })
    return result


@app.get("/api/employee/weekly-chart")
def get_weekly_chart(request: Request, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from datetime import timedelta
    today = datetime.now()
    start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    week_days = []
    for i in range(7):
        d = (today - timedelta(days=today.weekday() - i)).strftime("%Y-%m-%d")
        att = db.query(models.DBAttendance).filter(models.DBAttendance.employee_id == emp_id, models.DBAttendance.date == d).first()
        week_days.append({"date": d, "day": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i], "hours": att.total_hours if att else 0, "is_today": d == today.strftime("%Y-%m-%d")})
    return week_days


@app.post("/api/employee/goals/{goal_id}/update")
def update_goal_progress(goal_id: int, request: Request, body: dict, db: Session = Depends(get_db)):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    goal = db.query(models.DBEmployeeGoal).filter(models.DBEmployeeGoal.id == goal_id, models.DBEmployeeGoal.employee_id == emp_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    goal.current_value = body.get("current_value", goal.current_value)
    if goal.current_value >= goal.target_value:
        goal.status = "completed"
    db.commit()
    return {"message": "Goal updated"}


# HR-side: Create goal for employee
@app.post("/api/employees/{emp_id}/goals")
def create_employee_goal(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body: body = {}
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    goal = models.DBEmployeeGoal(
        client_id=client.id, employee_id=emp_id,
        title=body.get("title", ""), description=body.get("description", ""),
        target_value=body.get("target_value", 100), current_value=body.get("current_value", 0),
        unit=body.get("unit", "%"), category=body.get("category", "performance"),
        priority=body.get("priority", "medium"), start_date=body.get("start_date", ""),
        due_date=body.get("due_date", ""), created_by="HR",
    )
    db.add(goal)
    note = models.DBNotification(
        client_id=client.id, employee_id=emp_id,
        title="New Goal Assigned", message=f"HR has assigned you a new goal: {goal.title}",
        type="info",
    )
    db.add(note)
    db.commit()
    return {"message": "Goal created", "id": goal.id}


@app.post("/api/goals/assign-department")
def assign_department_goal(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body: body = {}
    dept_id = body.get("department_id")
    if not dept_id:
        raise HTTPException(status_code=400, detail="department_id required")
    dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == dept_id, models.DBDepartment.client_id == client.id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    employees = db.query(models.DBEmployee).filter(models.DBEmployee.department_id == dept_id, models.DBEmployee.client_id == client.id, models.DBEmployee.status == "active").all()
    created = []
    for emp in employees:
        goal = models.DBEmployeeGoal(
            client_id=client.id, employee_id=emp.id, department_id=dept_id,
            title=body.get("title", ""), description=body.get("description", ""),
            target_value=body.get("target_value", 100), current_value=0,
            unit=body.get("unit", "%"), category=body.get("category", "performance"),
            priority=body.get("priority", "medium"), start_date=body.get("start_date", ""),
            due_date=body.get("due_date", ""), created_by="HR",
        )
        db.add(goal)
        note = models.DBNotification(
            client_id=client.id, employee_id=emp.id,
            title="New Goal Assigned", message=f"HR has assigned you a new goal: {goal.title}",
            type="info",
        )
        db.add(note)
        created.append(emp.id)
    if not employees:
        dept_goal = models.DBDepartmentGoal(
            client_id=client.id, department_id=dept_id,
            title=body.get("title", ""), description=body.get("description", ""),
            target_value=body.get("target_value", 100),
            unit=body.get("unit", "%"), category=body.get("category", "performance"),
            priority=body.get("priority", "medium"), start_date=body.get("start_date", ""),
            due_date=body.get("due_date", ""), created_by="HR",
        )
        db.add(dept_goal)
        log_audit(db, client.id, "goal_saved_for_dept", "goal", None, body.get("title", ""), f"Dept: {dept.name} (pending)", request)
        db.commit()
        return {"message": f"Goal saved for {dept.name}. It will be assigned to employees when they join.", "count": 0, "department": dept.name, "pending": True}
    log_audit(db, client.id, "goal_assigned_dept", "goal", None, body.get("title", ""), f"Dept: {dept.name}, {len(created)} employees", request)
    db.commit()
    return {"message": f"Goal assigned to {len(created)} employees in {dept.name}", "count": len(created), "department": dept.name}


@app.get("/api/goals/department-pending")
def get_pending_department_goals(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    goals = db.query(models.DBDepartmentGoal).filter(
        models.DBDepartmentGoal.client_id == client.id,
        models.DBDepartmentGoal.is_assigned == False,
    ).all()
    result = []
    for g in goals:
        dept = db.query(models.DBDepartment).filter(models.DBDepartment.id == g.department_id).first()
        result.append({
            "id": g.id, "department_id": g.department_id, "department_name": dept.name if dept else "",
            "title": g.title, "description": g.description,
            "target_value": g.target_value, "unit": g.unit,
            "category": g.category, "priority": g.priority,
            "due_date": g.due_date, "created_at": g.created_at,
        })
    return result


@app.get("/api/leave/requests")
def get_all_leave_requests(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    leaves = db.query(models.DBLeaveRequest).filter(models.DBLeaveRequest.client_id == client.id).order_by(models.DBLeaveRequest.created_at.desc()).all()
    result = []
    for l in leaves:
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == l.employee_id).first()
        result.append({
            "id": l.id, "employee_id": l.employee_id,
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "",
            "leave_type": l.leave_type, "start_date": l.start_date, "end_date": l.end_date,
            "days": l.days, "reason": l.reason, "status": l.status,
            "approved_by": l.approved_by, "created_at": l.created_at,
        })
    return result


@app.post("/api/leave/requests/{leave_id}/action")
def action_leave_simple(leave_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body: body = {}
    leave = db.query(models.DBLeaveRequest).filter(models.DBLeaveRequest.id == leave_id, models.DBLeaveRequest.client_id == client.id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave request not found")
    action = (body.get("action") or "").strip().lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'reject'")
    if leave.status != "pending":
        raise HTTPException(status_code=409, detail=f"This request has already been {leave.status}")

    if action == "approve":
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == leave.employee_id).first()
        if emp:
            balance = leave_balance_for(db, emp)
            # Pending days include this request, so compare against taken only.
            if leave.leave_type == "annual" and (leave.days or 0) > (balance["annual_total"] - balance["annual_taken"]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Approving this would exceed the annual entitlement ({balance['annual_total']:g} days)",
                )
            if leave.leave_type == "sick" and (leave.days or 0) > (balance["sick_total"] - balance["sick_taken"]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Approving this would exceed the sick leave entitlement ({balance['sick_total']:g} days)",
                )

    leave.status = "approved" if action == "approve" else "rejected"
    leave.approved_by = body.get("approved_by", "HR")
    leave.decided_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.add(models.DBNotification(
        client_id=client.id, employee_id=leave.employee_id,
        title=f"Leave Request {leave.status.title()}",
        message=f"Your {leave.leave_type} leave request for {leave.start_date} to {leave.end_date} has been {leave.status}.",
        type="success" if leave.status == "approved" else "warning",
    ))
    log_audit(db, client.id, f"leave_{leave.status}", "leave", leave.id, f"{leave.leave_type} ({leave.days}d)", f"Employee ID: {leave.employee_id}", request)
    db.commit()
    return {"message": f"Leave {leave.status}", "status": leave.status}


@app.get("/api/employees/{emp_id}/leave-balance")
def get_employee_leave_balance(emp_id: int, request: Request, db: Session = Depends(get_db)):
    """Entitlement vs. usage, for the HR-side employee record."""
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return leave_balance_for(db, emp)


@app.put("/api/employees/{emp_id}/leave-entitlement")
def set_employee_leave_entitlement(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Entitlements were hard-coded at 25/10 for everyone; make them per-person."""
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    body = body or {}
    for field, attr in (("annual_days", "annual_leave_entitlement"), ("sick_days", "sick_leave_entitlement")):
        if body.get(field) is not None:
            try:
                value = float(body[field])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{field} must be a number")
            if value < 0 or value > 365:
                raise HTTPException(status_code=400, detail=f"{field} must be between 0 and 365")
            setattr(emp, attr, value)
    log_audit(db, client.id, "leave_entitlement_updated", "employee", emp.id,
              f"{emp.first_name} {emp.last_name}", "", request)
    db.commit()
    return leave_balance_for(db, emp)


@app.get("/api/employees/{emp_id}/goals")
def get_goals_for_employee(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    goals = db.query(models.DBEmployeeGoal).filter(models.DBEmployeeGoal.employee_id == emp_id, models.DBEmployeeGoal.client_id == client.id).order_by(models.DBEmployeeGoal.created_at.desc()).all()
    return [{"id": g.id, "title": g.title, "description": g.description, "target_value": g.target_value, "current_value": g.current_value, "unit": g.unit, "category": g.category, "priority": g.priority, "start_date": g.start_date, "due_date": g.due_date, "status": g.status, "created_by": g.created_by, "department_id": g.department_id} for g in goals]


@app.get("/api/employees/{emp_id}/documents")
def get_documents_for_employee(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    docs = db.query(models.DBDocument).filter(models.DBDocument.employee_id == emp_id, models.DBDocument.client_id == client.id).order_by(models.DBDocument.created_at.desc()).all()
    return [{"id": d.id, "title": d.title, "doc_type": d.doc_type, "file_name": d.file_name, "uploaded_by": d.uploaded_by, "created_at": d.created_at} for d in docs]


@app.get("/api/employees/{emp_id}/leave")
def get_leave_for_employee(emp_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    leaves = db.query(models.DBLeaveRequest).filter(models.DBLeaveRequest.employee_id == emp_id, models.DBLeaveRequest.client_id == client.id).order_by(models.DBLeaveRequest.created_at.desc()).all()
    return [{"id": l.id, "leave_type": l.leave_type, "start_date": l.start_date, "end_date": l.end_date, "days": l.days, "reason": l.reason, "status": l.status, "approved_by": l.approved_by, "created_at": l.created_at} for l in leaves]


@app.post("/api/employees/{emp_id}/documents")
def upload_document(emp_id: int, request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    if not body: body = {}
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id, models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    doc = models.DBDocument(
        client_id=client.id, employee_id=emp_id,
        title=body.get("title", ""), doc_type=body.get("doc_type", "other"),
        file_name=body.get("file_name", ""), file_type=body.get("file_type", ""),
        file_data=body.get("file_data", ""), uploaded_by="HR",
    )
    db.add(doc)
    note = models.DBNotification(
        client_id=client.id, employee_id=emp_id,
        title="New Document Uploaded", message=f"HR has uploaded a document: {doc.title}",
        type="info",
    )
    db.add(note)
    db.commit()
    return {"message": "Document uploaded", "id": doc.id}


# ============================================================================
# AI ENDPOINTS (Groq / Llama 3.3)
# ============================================================================

import llm
from llm import llm_chat, llm_json, llm_configured, llm_error_message


@app.get("/api/ai/status")
def ai_status(request: Request, db: Session = Depends(get_db)):
    """Whether the AI is usable at all.

    The UI asks once and hides its AI buttons if not, rather than offering
    something that fails the moment anyone presses it.
    """
    get_client_user(request, db)
    configured = llm_configured()
    # A key being set is not the same as the AI working - a retired model looks
    # identical from here. So the reason the last call failed is carried too,
    # rather than probing the model on every page load.
    last = llm.llm_last_error()
    return {
        "configured": configured,
        "message": "" if configured else llm_error_message(),
        # Set when something has actually failed since the last restart, so the
        # page can say which of the six it was instead of guessing at the key.
        "last_error": last,
        "last_error_message": llm_error_message() if last else "",
    }


@app.post("/api/ai/screen-resume")
def screen_resume(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ensure_can_afford(db, client.id, "ai_resume_screen")
    if not body or not body.get("job_title"):
        raise HTTPException(status_code=400, detail="job_title required")
    job_title = body["job_title"]
    job_description = body.get("job_description", "")
    resume_text = body.get("resume_text", "")
    candidate_name = body.get("candidate_name", "Candidate")
    if not resume_text:
        return {"score": 0, "summary": "No resume text provided to analyze.", "strengths": [], "weaknesses": [], "recommendation": "Cannot screen without resume content."}
    messages = [
        {"role": "system", "content": "You are an expert HR recruiter. Analyze the resume against the job requirements and return JSON with: score (0-100), summary (1 sentence), strengths (list of up to 5), weaknesses (list of up to 5), recommendation (Hire/Interview/Reject with 1 sentence reason). Return ONLY valid JSON."},
        {"role": "user", "content": f"Job Title: {job_title}\nJob Description: {job_description}\n\nCandidate: {candidate_name}\nResume:\n{resume_text[:4000]}"}
    ]
    result = llm_json(messages)
    if not result:
        return {"score": 0, "summary": llm_error_message(), "strengths": [],
                "weaknesses": [], "recommendation": "Unable to screen at this time.",
                "available": False, "reason": llm.llm_last_error()}
    charge_after_success(db, client.id, "ai_resume_screen", 1, candidate_name)
    return {
        "score": result.get("score", 0),
        "summary": result.get("summary", ""),
        "strengths": result.get("strengths", []),
        "weaknesses": result.get("weaknesses", []),
        "recommendation": result.get("recommendation", ""),
    }


@app.post("/api/ai/generate-onboarding")
def generate_onboarding_checklist(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ensure_can_afford(db, client.id, "ai_onboarding")
    if not body or not body.get("job_title"):
        raise HTTPException(status_code=400, detail="job_title required")
    job_title = body["job_title"]
    department = body.get("department", "")
    seniority = body.get("seniority", "mid-level")
    messages = [
        {"role": "system", "content": "You are an HR onboarding specialist. Generate a custom onboarding checklist for a new hire. Return JSON with: items (list of objects with title, category, description, due_days from start). Categories: Legal, IT, HR, Social, Compliance, Training. Include 8-15 items. Return ONLY valid JSON."},
        {"role": "user", "content": f"Job Title: {job_title}\nDepartment: {department}\nSeniority: {seniority}"}
    ]
    result = llm_json(messages)
    if not result:
        return {"items": [
            {"title": "Sign employment contract", "category": "Legal", "description": "Review and sign employment agreement", "due_days": 1},
            {"title": "Provide government-issued ID", "category": "Legal", "description": "Submit ID for verification", "due_days": 1},
            {"title": "Submit bank details for payroll", "category": "Finance", "description": "Provide banking information", "due_days": 3},
            {"title": "IT equipment setup", "category": "IT", "description": "Laptop, email, system access", "due_days": 1},
            {"title": "Company policy acknowledgment", "category": "Compliance", "description": "Read and acknowledge policies", "due_days": 7},
        ]}
    charge_after_success(db, client.id, "ai_onboarding", 1, job_title)
    return {"items": result.get("items", [])}


@app.post("/api/ai/personalize-email")
def personalize_invoice_email(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ensure_can_afford(db, client.id, "ai_email_draft")
    if not body or not body.get("client_name"):
        raise HTTPException(status_code=400, detail="client_name required")
    client_name = body["client_name"]
    invoice_number = body.get("invoice_number", "")
    total = body.get("total", 0)
    due_date = body.get("due_date", "")
    is_first_time = body.get("is_first_time", False)
    tone = body.get("tone", "professional")
    messages = [
        {"role": "system", "content": f"You are a professional accounts receivable email writer. Write a short, {tone} invoice email. Include: greeting, invoice reference, amount, due date, payment link mention, and closing. Keep it under 100 words. Return ONLY the email body text, no subject line."},
        {"role": "user", "content": f"Client: {client_name}\nInvoice: {invoice_number}\nAmount: £{total}\nDue: {due_date}\nFirst time client: {is_first_time}"}
    ]
    result = llm_chat(messages)
    if not result:
        return {"subject": f"Invoice {invoice_number}", "body": f"Dear {client_name},\n\nPlease find invoice {invoice_number} for £{total}, due {due_date}.\n\nKind regards,\n{client.company_name or 'Accounts Team'}"}
    subject = f"Invoice {invoice_number}" if invoice_number else "Invoice"
    lines = result.strip().split("\n")
    for line in lines:
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            result = result.replace(line, "").strip()
            break
    charge_after_success(db, client.id, "ai_email_draft", 1, invoice_number)
    return {"subject": subject, "body": result}


@app.post("/api/ai/generate-followup")
def generate_followup_email(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ensure_can_afford(db, client.id, "ai_email_draft")
    if not body or not body.get("client_name"):
        raise HTTPException(status_code=400, detail="client_name required")
    client_name = body["client_name"]
    invoice_number = body.get("invoice_number", "")
    total = body.get("total", 0)
    days_overdue = body.get("days_overdue", 0)
    tone = body.get("tone", "polite")
    messages = [
        {"role": "system", "content": f"You are an accounts receivable specialist. Write a {tone} payment follow-up email for an overdue invoice. Be concise, professional, and clear about the amount owed and urgency. Keep under 80 words. Return ONLY the email body text."},
        {"role": "user", "content": f"Client: {client_name}\nInvoice: {invoice_number}\nAmount: £{total}\nDays overdue: {days_overdue}"}
    ]
    result = llm_chat(messages)
    if not result:
        return {"subject": f"Payment Reminder - {invoice_number}", "body": f"Dear {client_name},\n\nThis is a friendly reminder that invoice {invoice_number} for £{total} is now {days_overdue} days overdue.\n\nPlease arrange payment at your earliest convenience.\n\nKind regards,\n{client.company_name or 'Accounts Team'}"}
    subject = f"Payment Reminder - {invoice_number}" if invoice_number else "Payment Reminder"
    charge_after_success(db, client.id, "ai_email_draft", 1, invoice_number)
    return {"subject": subject, "body": result}


@app.get("/api/ai/payroll-anomalies")
def detect_payroll_anomalies(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    payslips = db.query(models.DBPayslip).filter(
        models.DBPayslip.client_id == client.id
    ).order_by(models.DBPayslip.employee_id, models.DBPayslip.period_start.desc()).all()
    by_emp = {}
    for p in payslips:
        if p.employee_id not in by_emp:
            by_emp[p.employee_id] = []
        by_emp[p.employee_id].append(p)
    anomalies = []
    for emp_id, ps_list in by_emp.items():
        if len(ps_list) < 2:
            continue
        latest = ps_list[0]
        prev = ps_list[1]
        if prev.net_pay and prev.net_pay > 0 and latest.net_pay:
            pct_change = abs(latest.net_pay - prev.net_pay) / prev.net_pay * 100
            if pct_change > 20:
                emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
                emp_name = f"{emp.first_name} {emp.last_name}" if emp else f"Employee #{emp_id}"
                direction = "increased" if latest.net_pay > prev.net_pay else "decreased"
                anomalies.append({
                    "employee_id": emp_id, "employee_name": emp_name,
                    "latest_net": round(float(latest.net_pay), 2),
                    "previous_net": round(float(prev.net_pay), 2),
                    "change_pct": round(pct_change, 1), "direction": direction,
                    "latest_period": latest.period_start or "",
                })
    anomalies.sort(key=lambda x: x["change_pct"], reverse=True)
    return {"anomalies": anomalies, "total_checked": len(by_emp)}


@app.get("/api/ai/attendance-alerts")
def detect_attendance_alerts(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    from datetime import timedelta
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    records = db.query(models.DBAttendance).filter(
        models.DBAttendance.client_id == client.id,
        models.DBAttendance.date >= thirty_days_ago,
    ).all()
    by_emp = {}
    for r in records:
        if r.employee_id not in by_emp:
            by_emp[r.employee_id] = []
        by_emp[r.employee_id].append(r)
    alerts = []
    for emp_id, recs in by_emp.items():
        emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
        if not emp:
            continue
        emp_name = f"{emp.first_name} {emp.last_name}"
        late_count = 0
        absent_days = 0
        long_breaks = 0
        no_clockout = 0
        total_hours = 0
        for r in recs:
            if r.clock_in and r.clock_in > "09:15:00":
                late_count += 1
            if r.status == "absent" or (not r.clock_in and not r.clock_out):
                absent_days += 1
            if r.break_minutes and r.break_minutes > 90:
                long_breaks += 1
            if r.clock_in and not r.clock_out:
                no_clockout += 1
            if r.total_hours:
                total_hours += float(r.total_hours)
        emp_alerts = []
        if late_count >= 5:
            emp_alerts.append({"type": "late", "message": f"Late {late_count} times in 30 days", "severity": "warning"})
        if absent_days >= 5:
            emp_alerts.append({"type": "absent", "message": f"{absent_days} absent days in 30 days", "severity": "critical"})
        if long_breaks >= 3:
            emp_alerts.append({"type": "break", "message": f"{long_breaks} extended breaks (>90 min)", "severity": "warning"})
        if no_clockout >= 2:
            emp_alerts.append({"type": "clockout", "message": f"{no_clockout} missed clock-outs", "severity": "warning"})
        if recs and total_hours / len(recs) > 10:
            emp_alerts.append({"type": "overtime", "message": f"Avg {round(total_hours/len(recs), 1)}h/day — burnout risk", "severity": "critical"})
        if emp_alerts:
            alerts.append({"employee_id": emp_id, "employee_name": emp_name, "department": emp.department_id, "alerts": emp_alerts, "total_hours_30d": round(total_hours, 1)})
    alerts.sort(key=lambda x: len(x["alerts"]), reverse=True)
    return {"alerts": alerts, "period": "30 days", "employees_checked": len(by_emp)}


@app.post("/api/ai/summarize-attendance")
def summarize_attendance(request: Request, body: dict = None, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    ensure_can_afford(db, client.id, "ai_attendance_summary")
    from datetime import timedelta
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    records = db.query(models.DBAttendance).filter(
        models.DBAttendance.client_id == client.id,
        models.DBAttendance.date >= thirty_days_ago,
    ).all()
    total_employees = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id, models.DBEmployee.status == "active"
    ).count()
    total_records = len(records)
    present_days = sum(1 for r in records if r.status == "present")
    avg_hours = sum(float(r.total_hours or 0) for r in records) / max(total_records, 1)
    remote_count = sum(1 for r in records if r.check_type == "remote")
    office_count = sum(1 for r in records if r.check_type == "office")
    context = f"Period: last 30 days. Active employees: {total_employees}. Total attendance records: {total_records}. Present days: {present_days}. Avg hours/day: {round(avg_hours,1)}. Remote check-ins: {remote_count}. Office check-ins: {office_count}."
    messages = [
        {"role": "system", "content": "You are an HR analytics assistant. Summarize the attendance data in 2-3 bullet points. Be specific with numbers. Focus on actionable insights."},
        {"role": "user", "content": context}
    ]
    result = llm_chat(messages)
    if not result:
        result = f"• {present_days} present days recorded across {total_employees} employees.\n• Average daily hours: {round(avg_hours, 1)}h.\n• Remote: {remote_count}, Office: {office_count}."
    charge_after_success(db, client.id, "ai_attendance_summary")
    return {"summary": result, "stats": {"total_employees": total_employees, "total_records": total_records, "present_days": present_days, "avg_hours": round(avg_hours, 1), "remote": remote_count, "office": office_count}}


# ============================================================
# VIDEO MEETINGS - WebRTC Signaling Server
# ============================================================
from collections import defaultdict

meeting_rooms = defaultdict(lambda: {
    "participants": {},
    "host": None,
    "waiting": {},
    "locked": False,
    "created_at": datetime.utcnow().isoformat()
})

class MeetingSignaling:
    def __init__(self):
        self.connections = defaultdict(list)

    async def connect(self, websocket: WebSocket, room_id: str, user_id: str):
        await websocket.accept()
        self.connections[room_id].append({
            "ws": websocket,
            "user_id": user_id
        })

    def disconnect(self, room_id: str, user_id: str):
        self.connections[room_id] = [
            c for c in self.connections[room_id] if c["user_id"] != user_id
        ]
        if room_id in meeting_rooms:
            meeting_rooms[room_id]["participants"].pop(user_id, None)
            meeting_rooms[room_id]["waiting"].pop(user_id, None)
            if not meeting_rooms[room_id]["participants"]:
                del meeting_rooms[room_id]
            elif meeting_rooms[room_id]["host"] == user_id:
                # Reassign host to the next participant if possible
                new_host = next(iter(meeting_rooms[room_id]["participants"].keys()), None)
                meeting_rooms[room_id]["host"] = new_host
                
        if not self.connections[room_id]:
            if room_id in self.connections:
                del self.connections[room_id]

    async def broadcast(self, room_id: str, message: dict, exclude_user: str = None):
        dead = []
        for conn in self.connections.get(room_id, []):
            if conn["user_id"] == exclude_user:
                continue
            try:
                await conn["ws"].send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            if d in self.connections.get(room_id, []):
                self.connections[room_id].remove(d)

    async def send_to(self, room_id: str, user_id: str, message: dict):
        for conn in self.connections.get(room_id, []):
            if conn["user_id"] == user_id:
                try:
                    await conn["ws"].send_json(message)
                except Exception:
                    pass
                return

    def get_participants(self, room_id: str):
        return list(meeting_rooms.get(room_id, {}).get("participants", {}).keys())

signaling = MeetingSignaling()

@app.get("/meeting", response_class=HTMLResponse)
async def meeting_page():
    html_path = os.path.join(frontend_path, "meeting.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Meeting page not found</h1>", status_code=404)

@app.get("/api/meet/ice")
def meet_ice_servers():
    """What the browser should use to find a path to the other side.

    STUN alone only works when both ends can be reached directly. Behind
    symmetric NAT, a corporate firewall, or some mobile carriers, it cannot -
    and the failure is the worst kind: the call appears to connect, the UI
    shows the other person, and no audio or video ever arrives. Somewhere
    between a tenth and a fifth of real connections need a relay, and our
    users are office staff, which is exactly the population sitting behind
    restrictive firewalls.

    TURN credentials are served from here rather than written into the page,
    so they are not sitting in a static file for anyone to lift, and so
    rotating them is an environment change rather than a deploy.

    Configure with:
        TURN_URLS=turn:host:3478,turns:host:5349   (comma separated)
        TURN_USERNAME=...
        TURN_PASSWORD=...

    Works with a self-hosted coturn or any hosted provider. With none set
    this still returns STUN, so meetings keep working for everyone whose
    network allows a direct path - it just cannot rescue those it cannot.
    """
    stun = [{"urls": [
        "stun:stun.l.google.com:19302",
        "stun:stun1.l.google.com:19302",
    ]}]

    urls = [u.strip() for u in os.getenv("TURN_URLS", "").split(",") if u.strip()]
    username = os.getenv("TURN_USERNAME", "")
    password = os.getenv("TURN_PASSWORD", "")

    if urls and username and password:
        return {
            "iceServers": stun + [{
                "urls": urls, "username": username, "credential": password,
            }],
            "relay_configured": True,
        }

    # Said plainly rather than hidden, because "some people cannot join" is
    # otherwise diagnosed one confused user at a time.
    logger.warning(
        "No TURN relay configured. Anyone behind symmetric NAT or a "
        "restrictive firewall will fail to connect. Set TURN_URLS, "
        "TURN_USERNAME and TURN_PASSWORD.")
    return {"iceServers": stun, "relay_configured": False}


@app.websocket("/ws/meeting/{room_id}")
async def meeting_websocket(websocket: WebSocket, room_id: str):
    user_id = websocket.query_params.get("user_id", str(uuid.uuid4())[:8])
    display_name = websocket.query_params.get("name", "Guest")

    await signaling.connect(websocket, room_id, user_id)
    room = meeting_rooms[room_id]

    # Host assignment logic
    if not room.get("host"):
        room["host"] = user_id
    
    is_host = room["host"] == user_id

    # Waiting room logic
    if room.get("locked") and not is_host:
        room["waiting"][user_id] = {"name": display_name, "ws": websocket}
        await signaling.send_to(room_id, user_id, {"type": "waiting"})
        await signaling.send_to(room_id, room["host"], {
            "type": "join-request",
            "user_id": user_id,
            "name": display_name
        })
        # Keep connection open but don't join yet
    else:
        # Join immediately
        room["participants"][user_id] = {"joined_at": datetime.utcnow().isoformat(), "name": display_name}
        participants = signaling.get_participants(room_id)
        
        await signaling.send_to(room_id, user_id, {
            "type": "welcome",
            "user_id": user_id,
            "is_host": is_host,
            "host_id": room["host"],
            "participants": [p for p in participants if p != user_id]
        })
        
        await signaling.broadcast(room_id, {
            "type": "user-joined",
            "user_id": user_id,
            "name": display_name,
            "participants": participants
        }, exclude_user=user_id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            # Host controls
            if msg_type == "admit-user" and room["host"] == user_id:
                target_id = data.get("target")
                if target_id in room["waiting"]:
                    del room["waiting"][target_id]
                    room["participants"][target_id] = {"joined_at": datetime.utcnow().isoformat(), "name": data.get("name")}
                    await signaling.send_to(room_id, target_id, {
                        "type": "welcome",
                        "user_id": target_id,
                        "is_host": False,
                        "host_id": room["host"],
                        "participants": [p for p in signaling.get_participants(room_id) if p != target_id]
                    })
                    await signaling.broadcast(room_id, {
                        "type": "user-joined",
                        "user_id": target_id,
                        "name": data.get("name"),
                        "participants": signaling.get_participants(room_id)
                    }, exclude_user=target_id)
            
            elif msg_type == "deny-user" and room["host"] == user_id:
                target_id = data.get("target")
                if target_id in room["waiting"]:
                    del room["waiting"][target_id]
                    await signaling.send_to(room_id, target_id, {"type": "denied"})
            
            elif msg_type == "mute-all" and room["host"] == user_id:
                await signaling.broadcast(room_id, {"type": "force-mute"}, exclude_user=user_id)
                
            elif msg_type == "remove-user" and room["host"] == user_id:
                await signaling.send_to(room_id, data.get("target"), {"type": "removed"})
                
            elif msg_type == "toggle-lock" and room["host"] == user_id:
                room["locked"] = data.get("locked", False)
                await signaling.broadcast(room_id, {"type": "room-locked", "locked": room["locked"]})

            # Meeting Features
            elif msg_type == "raise-hand":
                await signaling.broadcast(room_id, {
                    "type": "raise-hand",
                    "user_id": user_id,
                    "name": display_name
                }, exclude_user=user_id)
                
            elif msg_type == "caption":
                await signaling.broadcast(room_id, {
                    "type": "caption",
                    "user_id": user_id,
                    "name": display_name,
                    "text": data.get("text", "")
                }, exclude_user=user_id)

            # Standard WebRTC Signaling
            elif msg_type == "offer":
                await signaling.send_to(room_id, data.get("target"), {
                    "type": "offer",
                    "offer": data.get("offer"),
                    "from": user_id,
                    "name": display_name
                })
            elif msg_type == "answer":
                await signaling.send_to(room_id, data.get("target"), {
                    "type": "answer",
                    "answer": data.get("answer"),
                    "from": user_id
                })
            elif msg_type == "ice-candidate":
                await signaling.send_to(room_id, data.get("target"), {
                    "type": "ice-candidate",
                    "candidate": data.get("candidate"),
                    "from": user_id
                })
            elif msg_type == "chat":
                await signaling.broadcast(room_id, {
                    "type": "chat",
                    "from": user_id,
                    "name": display_name,
                    "message": data.get("message", "")
                })
            elif msg_type == "toggle-media":
                await signaling.broadcast(room_id, {
                    "type": "toggle-media",
                    "user_id": user_id,
                    "kind": data.get("kind"),
                    "muted": data.get("muted")
                }, exclude_user=user_id)
            elif msg_type == "screen-share-started":
                await signaling.broadcast(room_id, {
                    "type": "screen-share-started",
                    "user_id": user_id,
                    "name": display_name
                }, exclude_user=user_id)
            elif msg_type == "screen-share-stopped":
                await signaling.broadcast(room_id, {
                    "type": "screen-share-stopped",
                    "user_id": user_id
                }, exclude_user=user_id)

    except WebSocketDisconnect:
        signaling.disconnect(room_id, user_id)
        if user_id in room.get("participants", {}):
            participants = signaling.get_participants(room_id)
            await signaling.broadcast(room_id, {
                "type": "user-left",
                "user_id": user_id,
                "name": display_name,
                "participants": participants,
                "new_host": room.get("host")
            })
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        signaling.disconnect(room_id, user_id)
        participants = signaling.get_participants(room_id)
        await signaling.broadcast(room_id, {
            "type": "user-left",
            "user_id": user_id,
            "name": display_name,
            "participants": participants
        })

# ============================================================================
# AI ASSISTANT
# A general assistant over a tenant's own data.
#
# The important constraint: it is *grounded*. Real figures are gathered first
# and passed in as context, and the model is told to answer only from them. An
# ungrounded chatbot pointed at business data will confidently invent balances
# and headcounts, which is worse than having no assistant at all.
# ============================================================================


# ---------------------------------------------------------------------------
# Assistant retrieval
#
# The standing context is a summary: totals, and the top few of anything. Ask
# about one invoice, one customer or one person and it genuinely was not there,
# so the assistant answered "I do not have that information" about data sitting
# in the database. This looks up whatever the question actually names and puts
# the records in front of the model.
#
# Every query is scoped to the tenant. There is no path here by which one
# business can be shown another's records.
# ---------------------------------------------------------------------------

DOC_NUMBER_RE = re.compile(r"\b((?:INV|QUO|BILL|PS)[-\s]?\d{1,8})\b", re.I)
LOOKUP_LIMIT = 6            # records of each kind, to keep the prompt small
NAME_MIN = 3                # shorter words match far too much


def _norm_doc_number(raw: str) -> str:
    return re.sub(r"[\s-]+", "-", (raw or "").strip().upper())


def money_by_currency(rows, amount, base: str) -> str:
    """Totals per currency, never added together - the same rule the reports
    follow, because an assistant quoting one figure across currencies is
    quoting a number that does not exist."""
    buckets = {}
    for r in rows:
        code = ((getattr(r, "currency", "") or "") or base).upper() or base
        buckets[code] = buckets.get(code, 0) + (amount(r) or 0)
    if not buckets:
        return f"{currency_symbol(base)}0.00"
    return ", ".join(
        f"{currency_symbol(code)}{value:.2f} {code}"
        for code, value in sorted(buckets.items(), key=lambda kv: -abs(kv[1]))
    )


def _words_in(question: str):
    """Words worth matching a name against."""
    stop = {
        "the", "and", "for", "with", "what", "when", "who", "how", "much", "many",
        "does", "did", "has", "have", "was", "are", "is", "owe", "owes", "owed",
        "invoice", "invoices", "quote", "quotes", "bill", "bills", "employee",
        "employees", "customer", "customers", "about", "show", "tell", "list",
        "status", "from", "this", "that", "their", "them", "our", "any", "all",
    }
    words = re.findall(r"[A-Za-z][A-Za-z'&.]{2,}", question or "")
    return [w for w in words if len(w) >= NAME_MIN and w.lower() not in stop]


def assistant_lookup(db: Session, client, question: str) -> str:
    """Records this question appears to be about, or an empty string."""
    blocks = []
    sym = currency_symbol(client.currency or "GBP")
    base = (client.currency or "GBP").upper()

    # --- documents named outright ------------------------------------------
    numbers = {_norm_doc_number(m) for m in DOC_NUMBER_RE.findall(question or "")}
    for number in list(numbers)[:LOOKUP_LIMIT]:
        inv = db.query(models.DBInvoice).filter(
            models.DBInvoice.client_id == client.id,
            models.DBInvoice.number == number).first()
        if inv:
            sub, tax, total = compute_invoice_totals(inv.line_items, inv.tax_type)
            cur = currency_symbol((inv.currency or base))
            days = invoice_overdue_days(inv, datetime.now().date())
            blocks.append(
                f"INVOICE {inv.number} for {inv.to_contact or 'unnamed customer'}\n"
                f"  status {inv.status}, issued {inv.issue_date}, due {inv.due_date}\n"
                f"  total {cur}{total:.2f}, paid {cur}{inv.paid or 0:.2f}, "
                f"outstanding {cur}{inv.due or 0:.2f}"
                + (f", {days} days overdue" if days > 0 else "")
                + "\n  lines: " + "; ".join(
                    f"{li.description} x{li.qty} at {cur}{li.price:.2f}"
                    for li in (inv.line_items or [])[:8]))
            continue

        quote = db.query(models.DBQuote).filter(
            models.DBQuote.client_id == client.id,
            models.DBQuote.number == number).first()
        if quote:
            sub, tax, total = compute_invoice_totals(quote.line_items, quote.tax_type)
            cur = currency_symbol((quote.currency or base))
            blocks.append(
                f"QUOTE {quote.number} for {quote.to_contact or 'unnamed customer'}\n"
                f"  status {quote_display_status(quote)}, issued {quote.issue_date}, "
                f"expires {quote.expiry_date}, total {cur}{total:.2f}")
            continue

        bill = db.query(models.DBBill).filter(
            models.DBBill.client_id == client.id,
            models.DBBill.number == number).first()
        if bill:
            blocks.append(
                f"BILL {bill.number} from {bill.vendor_name or 'unnamed supplier'}\n"
                f"  status {bill.status}, due {bill.due_date}, total {sym}{bill.total or 0:.2f}, "
                f"paid {sym}{bill.amount_paid or 0:.2f}")

    words = _words_in(question)
    if not words:
        return "\n\n".join(blocks)

    # --- people named in the question ---------------------------------------
    employees = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id).all()
    for emp in employees:
        full = f"{emp.first_name or ''} {emp.last_name or ''}".strip()
        if not full:
            continue
        if not any(w.lower() in full.lower() for w in words):
            continue
        leave = db.query(models.DBLeaveRequest).filter(
            models.DBLeaveRequest.client_id == client.id,
            models.DBLeaveRequest.employee_id == emp.id).all()
        pending = [l for l in leave if l.status == "pending"]
        blocks.append(
            f"EMPLOYEE {full}\n"
            f"  {emp.job_title or 'no job title'}, status {emp.status}, "
            f"started {emp.start_date or 'unknown'}\n"
            f"  email {emp.email or 'none'}, leave requests {len(leave)} "
            f"({len(pending)} pending)")
        if len(blocks) >= LOOKUP_LIMIT * 2:
            break

    # --- customers named in the question ------------------------------------
    invoices = db.query(models.DBInvoice).filter(
        models.DBInvoice.client_id == client.id).all()
    names = {}
    for inv in invoices:
        if not inv.to_contact:
            continue
        if any(w.lower() in inv.to_contact.lower() for w in words):
            names.setdefault(inv.to_contact, []).append(inv)
    for name, rows in list(names.items())[:LOOKUP_LIMIT]:
        open_rows = [i for i in rows if i.status in OPEN_INVOICE_STATUSES]
        blocks.append(
            f"CUSTOMER {name}\n"
            f"  {len(rows)} invoice(s), {len(open_rows)} still open\n"
            f"  outstanding {money_by_currency(open_rows, lambda i: i.due or 0, base)}\n"
            f"  paid to date {money_by_currency(rows, lambda i: i.paid or 0, base)}\n"
            f"  most recent: " + ", ".join(
                f"{i.number} ({i.status})" for i in sorted(
                    rows, key=lambda x: x.issue_date or "", reverse=True)[:5]))

    return "\n\n".join(blocks)


def build_business_context(db, client):
    """A compact, factual snapshot of this tenant. Everything the assistant is
    allowed to reason about."""
    today = datetime.now().date()
    sym = currency_symbol(client.currency or "GBP")

    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client.id).all()
    overdue = [i for i in invoices if invoice_overdue_days(i, today) > 0]
    outstanding = sum(i.due or 0 for i in invoices if i.status in OPEN_INVOICE_STATUSES)
    collected = sum(i.paid or 0 for i in invoices)

    employees = db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id).all()
    active = [e for e in employees if e.status == "active"]
    onboarding = [e for e in employees if e.status == "onboarding"]

    pending_leave = db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.client_id == client.id,
        models.DBLeaveRequest.status == "pending",
    ).all()
    on_leave_today = []
    for l in db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.client_id == client.id,
        models.DBLeaveRequest.status == "approved",
    ).all():
        start, end = _parse_date(l.start_date), _parse_date(l.end_date)
        if start and end and start <= today <= end:
            emp = next((e for e in employees if e.id == l.employee_id), None)
            if emp:
                on_leave_today.append(f"{emp.first_name} {emp.last_name}")

    payslips = db.query(models.DBPayslip).filter(models.DBPayslip.client_id == client.id).all()
    unpaid_payslips = [p for p in payslips if p.status != "Paid"]

    # Added when quotes and recurring billing were built. Without these the
    # assistant answered questions about them by denying they existed.
    quotes = db.query(models.DBQuote).filter(models.DBQuote.client_id == client.id).all()
    open_quotes = [q for q in quotes if quote_display_status(q) in ("Draft", "Sent")]
    accepted_quotes = [q for q in quotes if quote_display_status(q) == "Accepted"]
    quote_value = sum(compute_invoice_totals(q.line_items, q.tax_type)[2] for q in open_quotes)
    recurring = db.query(models.DBRecurringInvoice).filter(
        models.DBRecurringInvoice.client_id == client.id,
        models.DBRecurringInvoice.is_active == True,      # noqa: E712
    ).all()

    open_jobs = db.query(models.DBJobRequisition).filter(
        models.DBJobRequisition.client_id == client.id,
        models.DBJobRequisition.status == "open",
    ).all()
    applications = db.query(models.DBFormSubmission).filter(
        models.DBFormSubmission.client_id == client.id
    ).all()

    wallet = get_wallet(db, client.id)
    outstanding_docs = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == client.id,
        models.DBDocumentRequest.status.in_(["pending", "rejected"]),
    ).count()
    awaiting_review = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == client.id,
        models.DBDocumentRequest.status == "submitted",
    ).count()

    lines = [
        f"Company: {client.company_name or client.email}",
        f"Today: {today.isoformat()}",
        f"Currency: {client.currency or 'GBP'} ({sym})",
        "",
        "INVOICING",
        f"- Invoices: {len(invoices)} total, {sum(1 for i in invoices if i.status == 'Paid')} paid, "
        f"{sum(1 for i in invoices if i.status == 'Draft')} draft",
        f"- Outstanding: {money_by_currency([i for i in invoices if i.status in OPEN_INVOICE_STATUSES], lambda i: i.due or 0, client.currency or 'GBP')}",
        f"- Collected all time: {money_by_currency(invoices, lambda i: i.paid or 0, client.currency or 'GBP')}",
        f"- Overdue: {len(overdue)} invoice(s), {sym}{sum(i.due or 0 for i in overdue):.2f}",
    ]
    for i in sorted(overdue, key=lambda x: invoice_overdue_days(x, today), reverse=True)[:5]:
        lines.append(f"  - {i.number} to {i.to_contact}: {sym}{i.due:.2f}, "
                     f"{invoice_overdue_days(i, today)} days overdue, due {i.due_date}")

    lines += [
        "",
        "QUOTES AND RECURRING BILLING",
        f"- Quotes: {len(quotes)} total, {len(open_quotes)} still open "
        f"({sym}{quote_value:.2f}), {len(accepted_quotes)} accepted but not yet invoiced",
        f"- Recurring invoices running: {len(recurring)}",
        "",
        "PEOPLE",
        f"- Employees: {len(employees)} ({len(active)} active, {len(onboarding)} onboarding)",
        f"- Departments: {db.query(models.DBDepartment).filter(models.DBDepartment.client_id == client.id).count()}",
        f"- Pending leave requests: {len(pending_leave)}",
        # Worded the way the question gets asked - "who is off today" did not
        # match a line that only said "on approved leave".
        f"- Off today / on approved leave today ({today.isoformat()}): "
        f"{', '.join(on_leave_today) if on_leave_today else 'nobody is off today'}",
        f"- Payslips: {len(payslips)} total, {len(unpaid_payslips)} not yet marked paid",
        f"- Onboarding documents outstanding: {outstanding_docs}, awaiting HR review: {awaiting_review}",
    ]
    for l in pending_leave[:5]:
        emp = next((e for e in employees if e.id == l.employee_id), None)
        if emp:
            lines.append(f"  - {emp.first_name} {emp.last_name}: {l.leave_type} "
                         f"{l.start_date} to {l.end_date} ({l.days} days)")

    lines += [
        "",
        "RECRUITMENT",
        f"- Open roles: {len(open_jobs)}",
        f"- Applications: {len(applications)}, hired: {sum(1 for a in applications if a.hired_employee_id)}",
    ]
    for j in open_jobs[:5]:
        lines.append(f"  - {j.reference} {j.title} ({j.location or 'no location set'})")

    # Money the business owes, which the assistant could not see at all.
    bills = db.query(models.DBBill).filter(models.DBBill.client_id == client.id).all()
    unpaid_bills = [b for b in bills if (b.total or 0) > (b.amount_paid or 0)]
    contacts = db.query(models.DBContact).filter(
        models.DBContact.client_id == client.id).count()

    # Who owes the most, which is the question people actually ask.
    owed_by = {}
    for i in invoices:
        if i.status in OPEN_INVOICE_STATUSES and i.to_contact:
            owed_by[i.to_contact] = owed_by.get(i.to_contact, 0) + (i.due or 0)
    top_debtors = sorted(owed_by.items(), key=lambda kv: -kv[1])[:5]

    team = db.query(models.DBTeamMember).filter(
        models.DBTeamMember.client_id == client.id,
        models.DBTeamMember.is_active == True,      # noqa: E712
    ).all()
    tax_rates = db.query(models.DBTaxRate).filter(
        models.DBTaxRate.client_id == client.id
    ).order_by(models.DBTaxRate.sort_order.asc()).all()

    # By name, with the time. "Who is in today" was answered with a bare count,
    # which is not an answer to "who".
    todays_attendance = db.query(models.DBAttendance).filter(
        models.DBAttendance.client_id == client.id,
        models.DBAttendance.date == today.isoformat(),
        models.DBAttendance.clock_in != "",
    ).all()
    by_id = {e.id: e for e in employees}
    present, still_in = [], []
    for a in todays_attendance:
        emp = by_id.get(a.employee_id)
        if not emp:
            continue
        name = f"{emp.first_name or ''} {emp.last_name or ''}".strip() or emp.email
        present.append(f"{name} (in {a.clock_in}"
                       + (f", out {a.clock_out}" if a.clock_out else ", still in")
                       + ")")
        if not a.clock_out:
            still_in.append(name)
    on_leave_names = set(on_leave_today)
    absent = [
        f"{e.first_name or ''} {e.last_name or ''}".strip()
        for e in active
        if e.id not in {a.employee_id for a in todays_attendance}
        and f"{e.first_name or ''} {e.last_name or ''}".strip() not in on_leave_names
    ]
    clocked_in = len(todays_attendance)

    lines += [
        "",
        "MONEY OUT",
        f"- Bills: {len(bills)} total, {len(unpaid_bills)} unpaid "
        f"({sym}{sum((b.total or 0) - (b.amount_paid or 0) for b in unpaid_bills):.2f})",
        "",
        "CUSTOMERS",
        f"- Contacts on file: {contacts}",
    ]
    for name, amount in top_debtors:
        lines.append(f"  - {name} owes {sym}{amount:.2f}")

    lines += [
        "",
        "ATTENDANCE",
        f"- Clocked in today ({today.isoformat()}): {clocked_in} of {len(active)} active employees",
        f"- Who clocked in today: {'; '.join(present[:25]) if present else 'nobody has clocked in today'}",
        f"- Still clocked in right now: {', '.join(still_in[:25]) if still_in else 'nobody'}",
        f"- Active employees with no clock-in and not on leave: "
        f"{', '.join(absent[:25]) if absent else 'none'}",
        "",
        "ACCOUNT",
        f"- Wallet balance: {currency_symbol(wallet.currency)}{to_major(wallet.balance_minor, wallet.currency):.2f}",
        f"- Team members with a login: {len(team)}",
        f"- Tax rates set up: " + (", ".join(
            f"{t.name} {t.percent}%" for t in tax_rates) or "none"),
    ]
    return "\n".join(lines)



def as_text(value, separator=None):
    """Models legitimately return a multi-paragraph field as either a string
    or a list of strings. Accept both rather than dropping the content."""
    if separator is None:
        separator = chr(10) + chr(10)
    if isinstance(value, list):
        return separator.join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def as_list(value):
    """Same tolerance for fields that should be a list of short strings."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [line.strip(" -*") for line in text.splitlines() if line.strip(" -*")]


ASSISTANT_SYSTEM = (
    "You are the assistant inside a combined invoicing and HR platform. "
    "Answer using ONLY the CONTEXT below, which contains this company's real, current data. "
    "CONTEXT has a summary of the whole business, and where the question named a "
    "particular invoice, quote, bill, customer or person, a MATCHED RECORDS section "
    "with the detail of exactly those. Prefer the matched records when answering "
    "about one thing. "
    "Never invent numbers, names, dates or totals. "
    "An empty answer is still an answer: if the context says nobody, none, or zero, "
    "say so directly - 'nobody is off today' - and do NOT say you lack the information. "
    "Only say you do not have something when the context genuinely has no line about it, "
    "and then name the screen where the user can find it "
    "(Invoices, Employees, Leave, Payroll, Recruitment, Wallet). "
    "Be brief and concrete: two or three sentences, or a short list. Quote figures exactly as given. "
    "Do not give legal, tax or financial advice; suggest a qualified professional instead."
)


class AssistantQuery(BaseModel):
    question: str


@app.post("/api/ai/assistant")
def ai_assistant(body: AssistantQuery, request: Request, db: Session = Depends(get_db)):
    """Answer a question about this tenant's own data."""
    client = get_client_user(request, db)
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Ask a question")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Please keep the question under 500 characters")

    ensure_can_afford(db, client.id, "ai_assistant")

    context = build_business_context(db, client)
    # Whatever the question names is fetched and put in front of the model, so
    # a question about one invoice is not answered from a summary that only
    # carries totals.
    matched = assistant_lookup(db, client, question)
    if matched:
        context = f"{context}\n\nMATCHED RECORDS\n{matched}"

    answer = llm_chat([
        {"role": "system", "content": ASSISTANT_SYSTEM},
        {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
    ], temperature=0.2, max_tokens=400)

    if not answer:
        # Whichever of the six it was. Telling somebody to configure a key that
        # is already configured is worse than saying nothing.
        return {"answer": llm_error_message(), "available": False,
                "reason": llm.llm_last_error()}
    charge_after_success(db, client.id, "ai_assistant", 1, question[:60])
    return {"answer": answer, "available": True}


@app.get("/api/ai/suggestions")
def ai_suggestions(request: Request, db: Session = Depends(get_db)):
    """Starter questions worth asking, chosen from what is actually going on
    rather than a fixed list."""
    client = get_client_user(request, db)
    today = datetime.now().date()
    out = []

    invoices = db.query(models.DBInvoice).filter(models.DBInvoice.client_id == client.id).all()
    if any(invoice_overdue_days(i, today) > 0 for i in invoices):
        out.append("Which invoices are overdue and by how long?")
    if invoices:
        out.append("How much am I owed in total?")

    if db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.client_id == client.id,
        models.DBLeaveRequest.status == "pending",
    ).count():
        out.append("Who has leave waiting for approval?")
    if db.query(models.DBEmployee).filter(models.DBEmployee.client_id == client.id).count():
        out.append("Who is off today?")
    if db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.client_id == client.id,
        models.DBDocumentRequest.status == "submitted",
    ).count():
        out.append("Which onboarding documents need reviewing?")
    if db.query(models.DBJobRequisition).filter(
        models.DBJobRequisition.client_id == client.id,
        models.DBJobRequisition.status == "open",
    ).count():
        out.append("What roles am I hiring for?")

    out.append("Summarise where the business stands today")
    return {"suggestions": out[:5]}


@app.get("/api/ai/insights")
def ai_insights(request: Request, db: Session = Depends(get_db)):
    """A short read on the business for the dashboard, from real figures."""
    client = get_client_user(request, db)
    ensure_can_afford(db, client.id, "ai_insights")

    context = build_business_context(db, client)
    result = llm_json([
        {"role": "system", "content":
            "You are a business analyst. Using ONLY the context, return JSON with: "
            "headline (one sentence on where the business stands), "
            "actions (list of up to 4 objects with 'text' and 'priority' of high|medium|low, "
            "each naming a specific figure or name from the context). "
            "Never invent data. Return ONLY valid JSON."},
        {"role": "user", "content": context},
    ])
    if not result:
        return {"available": False, "headline": "", "actions": [],
                "message": llm_error_message(), "reason": llm.llm_last_error()}
    charge_after_success(db, client.id, "ai_insights")
    return {
        "available": True,
        "headline": result.get("headline", ""),
        "actions": (result.get("actions") or [])[:4],
    }


# --- Recruitment writing help ----------------------------------------------

@app.post("/api/ai/job-description")
def ai_job_description(request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Draft a job advert from the requisition details."""
    client = get_client_user(request, db)
    body = body or {}
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="A job title is required")
    ensure_can_afford(db, client.id, "ai_job_description")

    detail = ", ".join(filter(None, [
        f"department: {body.get('department')}" if body.get("department") else "",
        f"level: {body.get('level')}" if body.get("level") else "",
        f"location: {body.get('location')}" if body.get("location") else "",
        f"work mode: {body.get('work_mode')}" if body.get("work_mode") else "",
        f"employment type: {body.get('employment_type')}" if body.get("employment_type") else "",
    ]))
    result = llm_json([
        {"role": "system", "content":
            "You write job adverts. Return ONLY valid JSON with keys: "
            "description (2-3 short paragraphs about the role and the team), "
            "requirements (list of 5-8 short bullet strings). "
            "Write plainly, avoid cliches, and do not invent salary, benefits or company history."},
        {"role": "user", "content":
            f"Company: {client.company_name or 'our company'}\nRole: {title}\n{detail}"},
    ])
    if not result:
        return {"available": False, "description": "", "requirements": []}
    charge_after_success(db, client.id, "ai_job_description", 1, title)
    return {
        "available": True,
        "description": as_text(result.get("description")),
        "requirements": as_list(result.get("requirements")),
    }


@app.post("/api/ai/brand-theme")
def ai_brand_theme(request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Propose a whole branding theme instead of making somebody choose thirty
    settings one at a time.

    The colours come from the logo, not from the model - a palette sampled from
    the actual artwork is always closer than a guessed hex code, and it costs
    nothing. The model is used only for the wording, which is the part that
    genuinely needs writing: document titles, payment terms, a footer line.
    """
    client = get_client_user(request, db)
    body = body or {}

    # Sampled in the browser from the uploaded logo and posted here.
    palette = [valid_hex_colour(c, "") for c in (body.get("logo_colors") or [])]
    palette = [c for c in palette if c]

    industry = (body.get("industry") or client.industry or "").strip()[:80]
    tone = (body.get("tone") or "professional").strip()[:40]
    company = (client.company_name or "our company").strip()

    ensure_can_afford(db, client.id, "ai_brand_theme")

    result = llm_json([
        {"role": "system", "content":
            "You set the wording on a business's invoices. Return ONLY valid JSON "
            "with keys: approved_invoice_title, draft_invoice_title, quote_title, "
            "payment_terms, footer_note, rationale. "
            "Titles are short and conventional for the country and trade - most "
            "businesses want 'TAX INVOICE' or 'INVOICE', so do not be inventive. "
            "payment_terms is one or two plain sentences telling the customer how "
            "and by when to pay. footer_note is a single short line of thanks or "
            "contact detail. rationale is one sentence on why these suit the trade. "
            "Never invent a bank account, a registration number, a discount, or a "
            "number of days that was not given to you."},
        {"role": "user", "content":
            f"Business: {company}\nTrade: {industry or 'not stated'}\n"
            f"Tone wanted: {tone}"},
    ])

    if not result:
        return {"available": False, "reason": llm_error_message()}

    charge_after_success(db, client.id, "ai_brand_theme", 1, company)

    # The model never picks the colour. Sampling the logo keeps the invoice
    # matching the artwork the customer already recognises.
    suggestion = {
        "approved_invoice_title": as_text(result.get("approved_invoice_title"))[:60] or "TAX INVOICE",
        "draft_invoice_title": as_text(result.get("draft_invoice_title"))[:60] or "DRAFT INVOICE",
        "quote_title": as_text(result.get("quote_title"))[:60] or "QUOTE",
        "payment_terms": as_text(result.get("payment_terms"))[:600],
        "footer_note": as_text(result.get("footer_note"))[:200],
        "rationale": as_text(result.get("rationale"))[:300],
    }
    if palette:
        suggestion["brand_color"] = palette[0]
        suggestion["palette"] = palette[:5]

    return {"available": True, "suggestion": suggestion}


@app.post("/api/ai/interview-questions")
def ai_interview_questions(request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Questions tailored to one candidate against one role."""
    client = get_client_user(request, db)
    body = body or {}
    job_title = (body.get("job_title") or "").strip()
    if not job_title:
        raise HTTPException(status_code=400, detail="A job title is required")
    ensure_can_afford(db, client.id, "ai_interview_questions")

    candidate = ""
    sub_id = body.get("submission_id")
    if sub_id:
        sub = db.query(models.DBFormSubmission).filter(
            models.DBFormSubmission.id == sub_id,
            models.DBFormSubmission.client_id == client.id,
        ).first()
        if sub:
            try:
                answers = json.loads(sub.answers or "{}")
                candidate = "\n".join(f"{k}: {v}" for k, v in answers.items())[:1500]
            except (ValueError, TypeError):
                candidate = ""

    result = llm_json([
        {"role": "system", "content":
            "You are an interviewer. Return ONLY valid JSON with key 'questions': a list of 6-8 objects, "
            "each with 'question', 'area' (technical|experience|behavioural|role fit) and "
            "'looking_for' (one line on what a good answer shows). "
            "Base them on the role and, where given, the candidate's own answers. "
            "Avoid anything touching age, health, family, religion or nationality."},
        {"role": "user", "content":
            f"Role: {job_title}\nRound: {body.get('round_name') or 'general interview'}\n"
            + (f"Candidate said:\n{candidate}" if candidate else "No candidate detail provided.")},
    ])
    if not result:
        return {"available": False, "questions": []}
    charge_after_success(db, client.id, "ai_interview_questions", 1, job_title)
    questions = result.get("questions") or []
    normalised = []
    for q in questions[:8]:
        if isinstance(q, dict):
            normalised.append({
                "question": as_text(q.get("question")),
                "area": as_text(q.get("area")),
                "looking_for": as_text(q.get("looking_for")),
            })
        else:
            normalised.append({"question": as_text(q), "area": "", "looking_for": ""})
    return {"available": True, "questions": normalised}


@app.post("/api/ai/describe-item")
def ai_describe_item(request: Request, body: dict = None, db: Session = Depends(get_db)):
    """Turn a rough note into a presentable invoice line description."""
    client = get_client_user(request, db)
    body = body or {}
    rough = (body.get("text") or "").strip()
    if not rough:
        raise HTTPException(status_code=400, detail="Write a few words first")
    ensure_can_afford(db, client.id, "ai_describe_item")

    answer = llm_chat([
        {"role": "system", "content":
            "Rewrite the user's rough note as a single clear invoice line description. "
            "One sentence, under 20 words, factual. Return only the description, no quotes or preamble. "
            "Do not invent quantities, prices or dates."},
        {"role": "user", "content": rough},
    ], temperature=0.3, max_tokens=60)
    if not answer:
        return {"available": False, "description": ""}
    charge_after_success(db, client.id, "ai_describe_item", 1, rough[:40])
    return {"available": True, "description": answer.strip().strip('"')}



# ============================================================================
# HR TO EMPLOYEE MESSAGES
#
# Every notification an employee saw was raised by the system - a goal
# assigned, a document reviewed, leave actioned. HR had no way to say anything
# themselves, so anything that did not fit one of those events happened over
# email and left no trace in the portal.
#
# These reuse the notification the portal already renders rather than adding a
# second inbox next to it.
# ============================================================================

ANNOUNCEMENT_AUDIENCES = ("everyone", "department", "employee", "onboarding")


def notify_employee(db: Session, emp, title: str, message: str,
                    kind: str = "info", link: str = "", sent_by: str = ""):
    """One notification, for one person. Everything that talks to an employee
    goes through here so a new caller cannot forget the tenant id."""
    note = models.DBNotification(
        client_id=emp.client_id, employee_id=emp.id,
        title=title[:200], message=message[:2000], type=kind,
        link=link, sent_by=sent_by[:120],
    )
    db.add(note)
    return note


def announcement_recipients(db: Session, client_id: int, audience: str,
                            department_id=None, employee_id=None):
    """Who a message is for. Nobody terminated: they cannot sign in, so a
    notification for them is one nobody will ever read."""
    q = db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client_id,
        models.DBEmployee.status != "terminated",
    )
    if audience == "employee":
        q = q.filter(models.DBEmployee.id == employee_id)
    elif audience == "department":
        q = q.filter(models.DBEmployee.department_id == department_id)
    elif audience == "onboarding":
        q = q.filter(models.DBEmployee.status == "onboarding")
    return q.all()


@app.post("/api/hr/announcements")
def send_announcement(request: Request, body: dict = None,
                      db: Session = Depends(get_db)):
    """HR writes to one person, a department, everyone still onboarding, or
    the whole company."""
    client = get_client_user(request, db)
    body = body or {}

    title = (body.get("title") or "").strip()
    message = (body.get("message") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Give the message a subject")
    if not message:
        raise HTTPException(status_code=400, detail="Write something to send")

    audience = (body.get("audience") or "everyone").strip().lower()
    if audience not in ANNOUNCEMENT_AUDIENCES:
        raise HTTPException(
            status_code=400,
            detail="Send to everyone, a department, one employee, or those onboarding")
    if audience == "employee" and not body.get("employee_id"):
        raise HTTPException(status_code=400, detail="Choose who to send it to")
    if audience == "department" and not body.get("department_id"):
        raise HTTPException(status_code=400, detail="Choose a department")

    people = announcement_recipients(
        db, client.id, audience,
        department_id=body.get("department_id"),
        employee_id=body.get("employee_id"))
    if not people:
        # Said plainly rather than reporting that nothing was sent to nobody.
        raise HTTPException(status_code=400,
                            detail="Nobody matches that - the message was not sent")

    sender = client.company_name or client.contact_name or "HR"
    for emp in people:
        notify_employee(db, emp, title, message, kind="announcement",
                        sent_by=sender)
    log_audit(db, client.id, "announcement_sent", "notification", None,
              title, f"{len(people)} recipient(s)", request)
    db.commit()
    return {"sent": len(people), "audience": audience,
            "recipients": [f"{e.first_name} {e.last_name}".strip() for e in people[:25]]}


@app.post("/api/hr/employees/{employee_id}/chase-documents")
def chase_outstanding_documents(employee_id: int, request: Request,
                                body: dict = None, db: Session = Depends(get_db)):
    """Ask one employee for the paperwork still missing, naming it.

    A general "please send your documents" makes somebody go and work out which
    ones. This lists exactly what is outstanding and what was rejected, with
    the reason it was rejected, so the reply can be right first time.
    """
    client = get_client_user(request, db)
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == employee_id,
        models.DBEmployee.client_id == client.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    outstanding = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.employee_id == emp.id,
        models.DBDocumentRequest.client_id == client.id,
        models.DBDocumentRequest.status.in_(["pending", "rejected"]),
    ).all()
    if not outstanding:
        raise HTTPException(status_code=400,
                            detail="Nothing is outstanding for this employee")

    lines = []
    for row in outstanding:
        bit = row.name
        if row.is_mandatory:
            bit += " (required)"
        if row.due_date:
            bit += f", due {row.due_date}"
        if row.status == "rejected" and row.review_note:
            bit += f" - returned: {row.review_note}"
        elif row.status == "rejected":
            bit += " - returned, please send another"
        lines.append(bit)

    note = (body or {}).get("note", "").strip()
    message = "Still needed:\n- " + "\n- ".join(lines)
    if note:
        message += f"\n\n{note}"

    sender = client.company_name or client.contact_name or "HR"
    notify_employee(db, emp, f"{len(outstanding)} document(s) still needed",
                    message, kind="warning", link="/employee-dashboard.html",
                    sent_by=sender)
    db.commit()
    return {"sent": True, "outstanding": len(outstanding),
            "documents": [r.name for r in outstanding]}




# ============================================================================
# STAFF REQUESTS
#
# The portal only ever talked at an employee: they could read that a document
# had been returned, but not ask why. And leave was the only thing they could
# raise, so a payslip query or a broken laptop happened somewhere this system
# never saw.
#
# One thread covers both. A reply is a message on an existing thread; anything
# new is a thread of its own.
# ============================================================================

REQUEST_CATEGORIES = ("question", "document", "payroll", "equipment",
                      "personal_details", "other")
REQUEST_STATUSES = ("open", "answered", "closed")
MAX_MESSAGE = 4000


def current_employee(request: Request, db: Session):
    emp_id = request.session.get('employee_id')
    if not emp_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    emp = db.query(models.DBEmployee).filter(models.DBEmployee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return emp


def staff_message_to_dict(m):
    return {"id": m.id, "author": m.author, "author_name": m.author_name or "",
            "body": m.body, "created_at": m.created_at}


def staff_request_to_dict(req, employee=None, with_messages=False):
    out = {
        "id": req.id, "subject": req.subject, "category": req.category,
        "status": req.status, "created_at": req.created_at,
        "updated_at": req.updated_at, "closed_at": req.closed_at or "",
        "about_document_id": req.about_document_id,
        "message_count": len(req.messages or []),
    }
    if employee is not None:
        out["employee"] = {
            "id": employee.id,
            "name": f"{employee.first_name or ''} {employee.last_name or ''}".strip(),
            "email": employee.email or "",
        }
    if with_messages:
        out["messages"] = [staff_message_to_dict(m) for m in
                           sorted(req.messages or [], key=lambda x: x.id)]
    else:
        # The queue shows enough to triage without loading every thread.
        last = max(req.messages or [], key=lambda x: x.id, default=None)
        out["last_message"] = staff_message_to_dict(last) if last else None
    return out


def add_staff_message(db: Session, req, author: str, name: str, body: str):
    body = (body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Write a message first")
    msg = models.DBStaffMessage(
        client_id=req.client_id, request_id=req.id, author=author,
        author_name=name[:120], body=body[:MAX_MESSAGE])
    db.add(msg)
    req.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return msg


# --- what a person can see and change about themselves -----------------------

# Their own record is theirs to correct. These are the fields where a stale
# value is only ever the employee's own problem, so making them ask HR is how
# the numbers on file go out of date.
SELF_SERVICE_FIELDS = ("phone", "address", "emergency_contact", "emergency_phone")

# Where the money goes. A change to one of these is a change to where somebody's
# wages land, so it is proposed rather than applied.
APPROVAL_FIELDS = ("bank_name", "bank_account", "tax_id")


@app.get("/api/employee/leave-balance")
def employee_leave_balance(request: Request, db: Session = Depends(get_db)):
    """What is left, from the employee's own side.

    The figures existed but only on the HR record, so leave was requested by
    people who could not see what they had - and refused by HR for a reason the
    form could have shown before it was submitted.
    """
    emp = current_employee(request, db)
    return leave_balance_for(db, emp)


@app.get("/api/employee/payslips")
def employee_payslips(request: Request, db: Session = Depends(get_db)):
    """Every payslip issued to this person, newest first."""
    emp = current_employee(request, db)
    rows = db.query(models.DBPayslip).filter(
        models.DBPayslip.employee_id == emp.id
    ).order_by(models.DBPayslip.pay_date.desc(), models.DBPayslip.id.desc()).all()
    return [{
        "id": r.id, "number": r.number,
        "period_start": r.period_start, "period_end": r.period_end,
        "pay_date": r.pay_date, "net_pay": round(r.net_pay or 0, 2),
        "gross_pay": round(r.gross_pay or 0, 2), "status": r.status,
    } for r in rows]


@app.get("/api/employee/payslips/{ps_id}")
def employee_payslip(ps_id: int, request: Request, db: Session = Depends(get_db)):
    """Everything on one payslip, so the portal can build the document.

    The figures were on the dashboard already; what was missing was anything a
    person could keep. A payslip is what a landlord or a lender asks for, and
    until now getting one meant emailing HR.
    """
    emp = current_employee(request, db)
    ps = db.query(models.DBPayslip).filter(
        models.DBPayslip.id == ps_id,
        # Scoped to the person asking, not merely to the tenant - one employee
        # must never be able to read another's pay by changing the number.
        models.DBPayslip.employee_id == emp.id,
    ).first()
    if not ps:
        raise HTTPException(status_code=404, detail="Payslip not found")

    client = db.query(models.DBClient).filter(
        models.DBClient.id == ps.client_id).first()
    settings_map = {r.key: r.value for r in db.query(models.DBSettings).filter(
        models.DBSettings.client_id == ps.client_id).all()}

    return {
        "id": ps.id, "number": ps.number,
        "period_start": ps.period_start, "period_end": ps.period_end,
        "pay_date": ps.pay_date, "status": ps.status,
        "hours_worked": ps.hours_worked or 0, "overtime_hours": ps.overtime_hours or 0,
        "basic_salary": round(ps.basic_salary or 0, 2),
        "overtime_pay": round(ps.overtime_pay or 0, 2),
        "bonus": round(ps.bonus or 0, 2),
        "allowances": round(ps.allowances or 0, 2),
        "gross_pay": round(ps.gross_pay or 0, 2),
        "tax_amount": round(ps.tax_amount or 0, 2),
        "insurance": round(ps.insurance or 0, 2),
        "retirement": round(ps.retirement or 0, 2),
        "other_deductions": round(ps.other_deductions or 0, 2),
        "total_deductions": round(ps.total_deductions or 0, 2),
        "net_pay": round(ps.net_pay or 0, 2),
        "employee": {
            "name": f"{emp.first_name} {emp.last_name}".strip(),
            "employee_id": emp.employee_id or "",
            "job_title": emp.job_title or "",
            # Enough to identify the account, never enough to use it.
            "bank_account": mask_secret(emp.bank_account or ""),
        },
        "company": {
            "name": settings_map.get("company_name") or (client.company_name if client else "") or "",
            "address": settings_map.get("company_address") or (client.address if client else "") or "",
            "email": settings_map.get("email") or (client.email if client else "") or "",
        },
        "currency": base_currency(client) if client else "GBP",
    }


@app.put("/api/employee/profile")
def update_employee_profile(request: Request, body: dict = None,
                            db: Session = Depends(get_db)):
    """Let people correct their own details.

    Two kinds of field. Contact details apply straight away - a new phone
    number is nobody's decision but the person's own. Bank details are proposed
    and wait for HR, because whatever is stored there is where the wages go.
    """
    emp = current_employee(request, db)
    body = body or {}

    applied, proposed, unchanged = [], [], []

    for field in SELF_SERVICE_FIELDS:
        if field not in body:
            continue
        value = str(body[field] or "").strip()[:300]
        if value == (getattr(emp, field) or ""):
            unchanged.append(field)
            continue
        setattr(emp, field, value)
        applied.append(field)

    for field in APPROVAL_FIELDS:
        if field not in body:
            continue
        value = str(body[field] or "").strip()[:120]
        current = getattr(emp, field) or ""
        if not value or value == current:
            unchanged.append(field)
            continue
        # One open request per field: asking twice should revise the ask, not
        # queue a second one for HR to work out the order of.
        existing = db.query(models.DBProfileChange).filter(
            models.DBProfileChange.employee_id == emp.id,
            models.DBProfileChange.field == field,
            models.DBProfileChange.status == "pending",
        ).first()
        if existing:
            existing.new_value = value
            existing.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            db.add(models.DBProfileChange(
                client_id=emp.client_id, employee_id=emp.id, field=field,
                old_value=current, new_value=value))
        proposed.append(field)

    if applied:
        log_audit(db, emp.client_id, "profile_self_updated", "employee", emp.id,
                  f"{emp.first_name} {emp.last_name}", ", ".join(applied), request,
                  user_type="employee", user_name=emp.email or "")
    db.commit()

    return {
        "applied": applied,
        "awaiting_approval": proposed,
        "unchanged": unchanged,
        "message": ("Saved." if applied and not proposed else
                    "Sent to HR to approve." if proposed and not applied else
                    "Saved. Bank details are with HR to approve." if applied and proposed
                    else "Nothing to change."),
    }


@app.get("/api/employee/profile-changes")
def employee_profile_changes(request: Request, db: Session = Depends(get_db)):
    """What this person has asked for and where it got to."""
    emp = current_employee(request, db)
    rows = db.query(models.DBProfileChange).filter(
        models.DBProfileChange.employee_id == emp.id
    ).order_by(models.DBProfileChange.id.desc()).limit(20).all()
    return [{
        "id": r.id, "field": r.field, "status": r.status,
        # The proposed value is the employee's own, so they may see it whole.
        "new_value": r.new_value, "note": r.note or "",
        "created_at": r.created_at, "decided_at": r.decided_at or "",
    } for r in rows]


@app.get("/api/hr/profile-changes")
def hr_profile_changes(request: Request, status: str = "pending",
                       db: Session = Depends(get_db)):
    """The queue of bank-detail changes waiting on a decision."""
    client = get_client_user(request, db)
    q = db.query(models.DBProfileChange).filter(
        models.DBProfileChange.client_id == client.id)
    if status and status != "all":
        q = q.filter(models.DBProfileChange.status == status)
    rows = q.order_by(models.DBProfileChange.id.desc()).limit(200).all()

    emps = {e.id: e for e in db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id).all()}
    out = []
    for r in rows:
        emp = emps.get(r.employee_id)
        out.append({
            "id": r.id, "field": r.field,
            "old_value": r.old_value or "", "new_value": r.new_value,
            "status": r.status, "note": r.note or "",
            "created_at": r.created_at, "decided_at": r.decided_at or "",
            "employee": {
                "id": r.employee_id,
                "name": f"{emp.first_name} {emp.last_name}".strip() if emp else "",
                "email": emp.email if emp else "",
            },
        })
    return out


@app.post("/api/hr/profile-changes/{change_id}/decide")
def decide_profile_change(change_id: int, request: Request, body: dict = None,
                          db: Session = Depends(get_db)):
    """Approve writes the value across; reject leaves the record untouched.

    Either way the employee is told, because a change to where their wages land
    is not something they should have to come back and check on.
    """
    client = get_client_user(request, db)
    body = body or {}
    decision = (body.get("decision") or "").strip().lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve or reject")

    row = db.query(models.DBProfileChange).filter(
        models.DBProfileChange.id == change_id,
        models.DBProfileChange.client_id == client.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.status != "pending":
        raise HTTPException(status_code=409,
                            detail=f"This was already {row.status}.")

    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == row.employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    row.status = "approved" if decision == "approve" else "rejected"
    row.note = str(body.get("note") or "").strip()[:300]
    row.decided_by = client.email or "HR"
    row.decided_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if decision == "approve":
        # Only ever a field on the approval list - the id in the URL decides
        # which row, never which column.
        if row.field not in APPROVAL_FIELDS:
            raise HTTPException(status_code=400, detail="Unknown field")
        setattr(emp, row.field, row.new_value)

    label = row.field.replace("_", " ")
    notify_employee(
        db, emp,
        f"Your {label} change was {row.status}",
        row.note or (f"The {label} on your record has been updated."
                     if decision == "approve"
                     else f"HR did not apply the {label} change you asked for."),
        kind="success" if decision == "approve" else "warning",
        sent_by=client.email or "HR")

    log_audit(db, client.id, f"profile_change_{row.status}", "employee", emp.id,
              f"{emp.first_name} {emp.last_name}", row.field, request)
    db.commit()
    return {"status": row.status, "field": row.field}


EMPLOYEE_ASSISTANT_SYSTEM = (
    "You are the assistant inside an employee's own staff portal. "
    "You are speaking to that employee about their own record. "
    "Answer using ONLY the CONTEXT below, which is this one person's real data. "
    "Never invent numbers, dates or totals, and never speculate about anyone else - "
    "you have no information about colleagues' pay, leave or performance, and you "
    "must say so plainly if asked. "
    "An empty answer is still an answer: if the context says none or zero, say so "
    "directly rather than saying you lack the information. "
    "When something is missing from the context, name the tab where they can find "
    "it (Attendance, Leave, Payslips, Documents, Goals, Ask HR). "
    "For anything about why a figure was calculated a particular way, or anything "
    "contractual, tell them to raise it with HR through Ask HR - do not guess. "
    "Do not give legal, tax or financial advice. "
    "Be brief and concrete: two or three sentences, or a short list."
)


def build_employee_context(db: Session, emp) -> str:
    """One person's own facts, and nothing about anybody else.

    Deliberately not build_business_context: that one carries every salary in
    the company. Everything here is filtered to this employee's id.
    """
    lines = []
    name = f"{emp.first_name} {emp.last_name}".strip()
    lines.append("WHO YOU ARE SPEAKING TO")
    lines.append(f"Name: {name}")
    if emp.job_title:
        lines.append(f"Job title: {emp.job_title}")
    if emp.start_date:
        lines.append(f"Started: {emp.start_date}")
    lines.append(f"Employment status: {emp.status}")

    dept = db.query(models.DBDepartment).filter(
        models.DBDepartment.id == emp.department_id).first() if emp.department_id else None
    if dept:
        lines.append(f"Department: {dept.name}")
    manager = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == emp.reports_to).first() if emp.reports_to else None
    if manager:
        lines.append(f"Manager: {manager.first_name} {manager.last_name}".strip())

    # --- leave ---------------------------------------------------------------
    bal = leave_balance_for(db, emp)
    lines.append("")
    lines.append("YOUR LEAVE")
    lines.append(f"Annual: {bal['annual_remaining']} days left of {bal['annual_total']} "
                 f"({bal['annual_taken']} taken, {bal['annual_pending']} awaiting a decision)")
    lines.append(f"Sick: {bal['sick_remaining']} days left of {bal['sick_total']}")

    recent_leave = db.query(models.DBLeaveRequest).filter(
        models.DBLeaveRequest.employee_id == emp.id
    ).order_by(models.DBLeaveRequest.id.desc()).limit(5).all()
    if recent_leave:
        for lv in recent_leave:
            lines.append(f"- {lv.leave_type} {lv.start_date} to {lv.end_date}, "
                         f"{lv.days} days, {lv.status}")
    else:
        lines.append("- no leave requests on record")

    # --- pay -----------------------------------------------------------------
    payslips = db.query(models.DBPayslip).filter(
        models.DBPayslip.employee_id == emp.id
    ).order_by(models.DBPayslip.id.desc()).limit(4).all()
    cur = ""
    client = db.query(models.DBClient).filter(
        models.DBClient.id == emp.client_id).first()
    cur = base_currency(client) if client else "GBP"
    lines.append("")
    lines.append("YOUR PAY")
    if payslips:
        for ps in payslips:
            lines.append(
                f"- {ps.number} for {ps.period_start} to {ps.period_end}: "
                f"gross {cur} {ps.gross_pay:.2f}, tax {cur} {ps.tax_amount:.2f}, "
                f"deductions {cur} {ps.total_deductions:.2f}, "
                f"net {cur} {ps.net_pay:.2f} ({ps.status})")
    else:
        lines.append("- no payslips issued yet")

    # --- attendance this month ----------------------------------------------
    month = datetime.now().strftime("%Y-%m")
    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.employee_id == emp.id,
        models.DBAttendance.date.like(f"{month}%"),
    ).all()
    hours = round(sum(a.total_hours or 0 for a in att), 2)
    lines.append("")
    lines.append("YOUR ATTENDANCE THIS MONTH")
    lines.append(f"Days recorded: {len(att)}; hours logged: {hours}")
    today = datetime.now().strftime("%Y-%m-%d")
    todays = next((a for a in att if a.date == today), None)
    lines.append(f"Today: clocked in at {todays.clock_in}" if todays and todays.clock_in
                 else "Today: not clocked in yet")

    # --- documents -----------------------------------------------------------
    reqs = db.query(models.DBDocumentRequest).filter(
        models.DBDocumentRequest.employee_id == emp.id).all()
    outstanding = [r for r in reqs if r.status in ("pending", "rejected")]
    lines.append("")
    lines.append("YOUR DOCUMENTS")
    if outstanding:
        for r in outstanding:
            due = f", due {r.due_date}" if r.due_date else ""
            lines.append(f"- still to send: {r.name} ({r.status}{due})")
    else:
        lines.append("- nothing outstanding")

    # --- goals ---------------------------------------------------------------
    goals = db.query(models.DBEmployeeGoal).filter(
        models.DBEmployeeGoal.employee_id == emp.id).all()
    lines.append("")
    lines.append("YOUR GOALS")
    if goals:
        for g in goals:
            lines.append(f"- {g.title}: {g.current_value} of {g.target_value} "
                         f"{g.unit or ''} ({g.status})".replace("  ", " "))
    else:
        lines.append("- none set")

    # --- open questions with HR ----------------------------------------------
    open_threads = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.employee_id == emp.id,
        models.DBStaffRequest.status == "open").all()
    lines.append("")
    lines.append("YOUR OPEN QUESTIONS WITH HR")
    lines.extend([f"- {t.subject} ({t.category})" for t in open_threads] or ["- none"])

    return "\n".join(lines)


@app.post("/api/employee/assistant")
def employee_assistant(request: Request, body: dict = None,
                       db: Session = Depends(get_db)):
    """Answer a question about this person's own record.

    Billed to the employer's wallet like every other AI action - the employee
    has no wallet of their own, and the company is who the platform bills.
    """
    emp = current_employee(request, db)
    body = body or {}
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Ask a question")
    if len(question) > 500:
        raise HTTPException(status_code=400,
                            detail="Please keep the question under 500 characters")

    ensure_can_afford(db, emp.client_id, "ai_assistant")

    answer = llm_chat([
        {"role": "system", "content": EMPLOYEE_ASSISTANT_SYSTEM},
        {"role": "user", "content":
            f"CONTEXT:\n{build_employee_context(db, emp)}\n\nQUESTION: {question}"},
    ], temperature=0.2, max_tokens=400)

    if not answer:
        return {"answer": llm_error_message(), "available": False,
                "reason": llm.llm_last_error()}

    charge_after_success(db, emp.client_id, "ai_assistant", 1,
                         f"{emp.first_name}: {question[:40]}")
    return {"answer": answer, "available": True}


# --- Attendance corrections ------------------------------------------------
# Forgetting to clock out is the ordinary case. The nightly job closes those
# and records no hours, on purpose - it cannot know the shift length. This is
# how the person who worked the day says what it actually was.


def _valid_time(value):
    """HH:MM or HH:MM:SS, normalised to HH:MM:SS. None if it is neither."""
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    return None


def correction_to_dict(c, emp=None):
    return {
        "id": c.id, "attendance_id": c.attendance_id,
        "employee_id": c.employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "",
        "old_clock_in": c.old_clock_in, "old_clock_out": c.old_clock_out,
        "requested_clock_in": c.requested_clock_in,
        "requested_clock_out": c.requested_clock_out,
        "reason": c.reason, "status": c.status, "note": c.note,
        "created_at": c.created_at, "decided_at": c.decided_at,
        "decided_by": c.decided_by,
    }


@app.get("/api/employee/attendance/corrections")
def employee_list_corrections(request: Request, db: Session = Depends(get_db)):
    emp = current_employee(request, db)
    rows = db.query(models.DBAttendanceCorrection).filter(
        models.DBAttendanceCorrection.employee_id == emp.id,
    ).order_by(models.DBAttendanceCorrection.id.desc()).limit(100).all()
    return [correction_to_dict(c, emp) for c in rows]


@app.post("/api/employee/attendance/corrections")
def employee_raise_correction(request: Request, body: dict = None,
                              db: Session = Depends(get_db)):
    """Ask for a day to be corrected. Nothing is applied here."""
    emp = current_employee(request, db)
    body = body or {}

    att = db.query(models.DBAttendance).filter(
        models.DBAttendance.id == int(body.get("attendance_id") or 0),
        # Scoped to the person asking: an employee may only correct their own
        # attendance, never a colleague's.
        models.DBAttendance.employee_id == emp.id,
    ).first()
    if not att:
        raise HTTPException(status_code=404, detail="That day is not on your record")

    reason = str(body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400,
                            detail="Say what happened, so HR can decide")

    cin = _valid_time(body.get("clock_in"))
    cout = _valid_time(body.get("clock_out"))
    if cin is None or cout is None:
        raise HTTPException(status_code=400, detail="Times must look like 09:00")
    if not cin and not cout:
        raise HTTPException(status_code=400, detail="Give a start or a finish time")
    if cin and cout and cout <= cin:
        raise HTTPException(status_code=400,
                            detail="The finish time must be after the start time")

    # One open request per day. Otherwise a second one silently overwrites what
    # HR is part-way through deciding on.
    if db.query(models.DBAttendanceCorrection).filter(
            models.DBAttendanceCorrection.attendance_id == att.id,
            models.DBAttendanceCorrection.status == "pending").first():
        raise HTTPException(status_code=409,
                            detail="You already have a request waiting on this day")

    row = models.DBAttendanceCorrection(
        client_id=att.client_id, employee_id=emp.id, attendance_id=att.id,
        old_clock_in=att.clock_in or "", old_clock_out=att.clock_out or "",
        requested_clock_in=cin, requested_clock_out=cout, reason=reason[:500],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return correction_to_dict(row, emp)


@app.get("/api/hr/attendance/corrections")
def hr_list_corrections(request: Request, status: str = "pending",
                        db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    q = db.query(models.DBAttendanceCorrection).filter(
        models.DBAttendanceCorrection.client_id == client.id)
    if status and status != "all":
        q = q.filter(models.DBAttendanceCorrection.status == status)
    rows = q.order_by(models.DBAttendanceCorrection.id.desc()).limit(200).all()

    emp_ids = {r.employee_id for r in rows}
    emps = {}
    if emp_ids:
        emps = {e.id: e for e in db.query(models.DBEmployee).filter(
            models.DBEmployee.id.in_(emp_ids)).all()}
    return [correction_to_dict(c, emps.get(c.employee_id)) for c in rows]


@app.post("/api/hr/attendance/corrections/{correction_id}/decide")
def hr_decide_correction(correction_id: int, request: Request, body: dict = None,
                         db: Session = Depends(get_db)):
    """Approve writes the times across and recomputes the hours; reject leaves
    the attendance row exactly as it was."""
    client = get_client_user(request, db)
    body = body or {}
    decision = (body.get("decision") or "").strip().lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve or reject")

    row = db.query(models.DBAttendanceCorrection).filter(
        models.DBAttendanceCorrection.id == correction_id,
        models.DBAttendanceCorrection.client_id == client.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"This was already {row.status}.")

    row.status = "approved" if decision == "approve" else "rejected"
    row.note = str(body.get("note") or "").strip()[:300]
    row.decided_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row.decided_by = client.company_name or client.email or "HR"

    if decision == "approve":
        att = db.query(models.DBAttendance).filter(
            models.DBAttendance.id == row.attendance_id).first()
        if not att:
            raise HTTPException(status_code=404, detail="That day is no longer on record")
        if row.requested_clock_in:
            att.clock_in = row.requested_clock_in
        if row.requested_clock_out:
            att.clock_out = row.requested_clock_out
        # Recomputed from whatever the row now holds, so the hours always match
        # the times shown beside them.
        if att.clock_in and att.clock_out:
            try:
                cin = datetime.strptime(att.clock_in, "%H:%M:%S")
                cout = datetime.strptime(att.clock_out, "%H:%M:%S")
                att.total_hours = max(0.0, round((cout - cin).total_seconds() / 3600, 2))
                att.status = "completed"
            except ValueError:
                att.total_hours = 0.0
        log_audit(db, client.id, "attendance_corrected", "attendance", att.id,
                  att.date, f"{att.clock_in} to {att.clock_out}", request)

    db.commit()
    return correction_to_dict(row)


@app.get("/api/employee/assistant/suggestions")
def employee_assistant_suggestions(request: Request, db: Session = Depends(get_db)):
    """Openers drawn from what is actually true for this person, so the first
    question is one the assistant can definitely answer."""
    emp = current_employee(request, db)
    out = []

    bal = leave_balance_for(db, emp)
    if bal["annual_pending"]:
        out.append("What leave have I asked for that has not been decided?")
    out.append("How much annual leave do I have left?")

    if db.query(models.DBDocumentRequest).filter(
            models.DBDocumentRequest.employee_id == emp.id,
            models.DBDocumentRequest.status.in_(("pending", "rejected"))).count():
        out.append("What documents do I still need to send in?")

    if db.query(models.DBPayslip).filter(
            models.DBPayslip.employee_id == emp.id).count():
        out.append("What was my last payslip?")

    if db.query(models.DBEmployeeGoal).filter(
            models.DBEmployeeGoal.employee_id == emp.id).count():
        out.append("How am I doing against my goals?")

    out.append("How many hours have I logged this month?")
    return {"suggestions": out[:5]}


# --- the employee's side -----------------------------------------------------

@app.post("/api/employee/requests")
def raise_staff_request(request: Request, body: dict = None,
                        db: Session = Depends(get_db)):
    """Ask HR something, about anything."""
    emp = current_employee(request, db)
    body = body or {}

    subject = (body.get("subject") or "").strip()
    message = (body.get("message") or "").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Give your request a subject")
    if not message:
        raise HTTPException(status_code=400, detail="Say what you need")

    category = (body.get("category") or "question").strip().lower()
    if category not in REQUEST_CATEGORIES:
        category = "other"

    about = body.get("about_document_id")
    if about:
        # Only a document of their own, so a guessed id cannot attach a thread
        # to somebody else's paperwork.
        owns = db.query(models.DBDocumentRequest).filter(
            models.DBDocumentRequest.id == about,
            models.DBDocumentRequest.employee_id == emp.id).first()
        if not owns:
            about = None

    req = models.DBStaffRequest(
        client_id=emp.client_id, employee_id=emp.id, subject=subject[:200],
        category=category, status="open", about_document_id=about)
    db.add(req)
    db.flush()
    add_staff_message(db, req, "employee",
                      f"{emp.first_name or ''} {emp.last_name or ''}".strip(), message)
    db.commit()
    db.refresh(req)
    return staff_request_to_dict(req, employee=emp, with_messages=True)


@app.get("/api/employee/requests")
def list_my_requests(request: Request, db: Session = Depends(get_db)):
    emp = current_employee(request, db)
    rows = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.employee_id == emp.id
    ).order_by(models.DBStaffRequest.updated_at.desc()).limit(100).all()
    return {"requests": [staff_request_to_dict(r) for r in rows],
            "categories": list(REQUEST_CATEGORIES)}


@app.get("/api/employee/requests/{req_id}")
def read_my_request(req_id: int, request: Request, db: Session = Depends(get_db)):
    emp = current_employee(request, db)
    req = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.id == req_id,
        models.DBStaffRequest.employee_id == emp.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return staff_request_to_dict(req, employee=emp, with_messages=True)


@app.post("/api/employee/requests/{req_id}/reply")
def reply_as_employee(req_id: int, request: Request, body: dict = None,
                      db: Session = Depends(get_db)):
    emp = current_employee(request, db)
    req = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.id == req_id,
        models.DBStaffRequest.employee_id == emp.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status == "closed":
        raise HTTPException(status_code=409,
                            detail="This request is closed. Raise a new one.")

    add_staff_message(db, req, "employee",
                      f"{emp.first_name or ''} {emp.last_name or ''}".strip(),
                      (body or {}).get("message", ""))
    # Their reply reopens it, or an answered thread would sit closed-looking
    # while somebody is still waiting.
    req.status = "open"
    db.commit()
    db.refresh(req)
    return staff_request_to_dict(req, employee=emp, with_messages=True)


# --- HR's side ---------------------------------------------------------------

@app.get("/api/hr/requests")
def list_staff_requests(request: Request, status: str = "", db: Session = Depends(get_db)):
    """The queue. Open first, because that is what needs doing."""
    client = get_client_user(request, db)
    q = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.client_id == client.id)
    if status and status in REQUEST_STATUSES:
        q = q.filter(models.DBStaffRequest.status == status)
    rows = q.order_by(models.DBStaffRequest.updated_at.desc()).limit(200).all()

    people = {e.id: e for e in db.query(models.DBEmployee).filter(
        models.DBEmployee.client_id == client.id).all()}
    out = [staff_request_to_dict(r, employee=people.get(r.employee_id)) for r in rows]
    return {
        "requests": out,
        "open_count": sum(1 for r in rows if r.status == "open"),
        "categories": list(REQUEST_CATEGORIES),
    }


@app.get("/api/hr/requests/{req_id}")
def read_staff_request(req_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    req = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.id == req_id,
        models.DBStaffRequest.client_id == client.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == req.employee_id).first()
    return staff_request_to_dict(req, employee=emp, with_messages=True)


@app.post("/api/hr/requests/{req_id}/reply")
def reply_as_hr(req_id: int, request: Request, body: dict = None,
                db: Session = Depends(get_db)):
    """Answering marks the thread answered and tells the employee, so a reply
    is not something they have to go and look for."""
    client = get_client_user(request, db)
    req = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.id == req_id,
        models.DBStaffRequest.client_id == client.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    sender = client.company_name or client.contact_name or "HR"
    add_staff_message(db, req, "hr", sender, (body or {}).get("message", ""))
    if (body or {}).get("close"):
        req.status = "closed"
        req.closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        req.status = "answered"

    emp = db.query(models.DBEmployee).filter(
        models.DBEmployee.id == req.employee_id).first()
    if emp:
        notify_employee(db, emp, f"Reply: {req.subject}",
                        (body or {}).get("message", "")[:300],
                        kind="info", link="/employee-dashboard.html",
                        sent_by=sender)
    db.commit()
    db.refresh(req)
    return staff_request_to_dict(req, employee=emp, with_messages=True)


@app.post("/api/hr/requests/{req_id}/close")
def close_staff_request(req_id: int, request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    req = db.query(models.DBStaffRequest).filter(
        models.DBStaffRequest.id == req_id,
        models.DBStaffRequest.client_id == client.id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = "closed"
    req.closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    req.updated_at = req.closed_at
    db.commit()
    db.refresh(req)
    return staff_request_to_dict(req, with_messages=False)




# ============================================================================
# THE INVOICE THE CUSTOMER SEES
#
# Until now an invoice left as a PDF attached to an email. If that mail was
# missed the customer had nothing, and there was no page to put a pay button
# on. This is that page: a public URL carrying one invoice.
#
# The URL is the invoice's tracking id, a uuid4 that already existed for open
# tracking. Nothing here takes an invoice number or a customer name, so a
# guessed address gets nothing, and no session is involved at all - the person
# looking at it does not have an account and never will.
# ============================================================================

def public_invoice_payload(db: Session, inv, client):
    """Exactly what the customer is entitled to see, and nothing else.

    Built field by field rather than reusing the internal serialiser, because
    that one grows over time and would eventually leak something - the tenant
    id, an internal status, another customer's name on a shared field.
    """
    sub, tax, total = compute_invoice_totals(inv.line_items, inv.tax_type)
    currency = (inv.currency or client.currency or "GBP").upper()
    theme = default_theme_for(db, client.id)
    today = datetime.now().date()

    return {
        "number": inv.number,
        "title": (theme.approved_invoice_title if theme else "") or "TAX INVOICE",
        "status": inv.status,
        "issue_date": inv.issue_date,
        "due_date": inv.due_date,
        "reference": inv.ref or "",
        "days_overdue": invoice_overdue_days(inv, today),
        "currency": currency,
        "currency_symbol": currency_symbol(currency),
        "subtotal": money(sub),
        "tax": money(tax),
        "total": money(total),
        "paid": money(inv.paid or 0),
        "amount_due": money(inv.due or 0),
        "is_settled": inv.status == "Paid" or (inv.due or 0) <= 0,
        "line_items": [
            {"description": li.description or "", "qty": li.qty,
             "price": money(li.price), "amount": money((li.qty or 0) * (li.price or 0))}
            for li in (inv.line_items or [])
        ],
        "from": {
            "company": client.company_name or "",
            "address": client.address or "",
            "email": client.email or "",
            "phone": client.phone_number or "",
        },
        "to": {"name": inv.to_contact or ""},
        "bank_details": inv.bank_details or "",
        "payment_terms": (theme.payment_terms if theme else "") or "",
        "footer_note": (theme.footer_note if theme else "") or "",
        "brand_color": (theme.brand_color if theme else "") or "#4f46e5",
        # Whether a Pay button can be shown, and the public half of the
        # key it needs. The secret never leaves the server.
        # Either the business's own keys or the platform's, depending on how
        # the operator has set collection up. The customer sees no difference.
        "payment": ({
            "provider": "razorpay", "key_id": _pay_key,
        } if (_pay_key := collecting_keys(db, client.id)[0]) and
             not (inv.status == "Paid" or (inv.due or 0) <= 0) else None),
        "logo": (theme.logo_data if theme else "") or client.logo_url or "",
    }


@app.get("/api/public/invoices/{tracking_id}")
def public_invoice(tracking_id: str, request: Request, db: Session = Depends(get_db)):
    """One invoice, for the person it was sent to. No session, no account."""
    inv = db.query(models.DBInvoice).filter(
        models.DBInvoice.tracking_id == tracking_id).first()
    # A draft has not been issued to anybody, and a void one has been withdrawn.
    # Neither should be readable from a link that may have been forwarded.
    if not inv or inv.status in ("Draft", "Void"):
        raise HTTPException(status_code=404, detail="That invoice is not available")

    client = db.query(models.DBClient).filter(
        models.DBClient.id == inv.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="That invoice is not available")

    # Opening the page counts the same as opening the email did.
    inv.open_count = (inv.open_count or 0) + 1
    inv.last_opened = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()

    return public_invoice_payload(db, inv, client)




# ============================================================================
# A BUSINESS'S OWN PAYMENT KEYS
#
# Two separate things, kept apart on purpose:
#   - the platform's keys, in the environment, which take wallet top-ups.
#     That is money paid to us.
#   - these, which belong to the tenant and take invoice payments. That is
#     money paid to them, into their account.
#
# Mixing them would route a customer's payment to the wrong business.
# ============================================================================

CLIENT_PROVIDERS = ("razorpay", "stripe", "paypal")

PROVIDER_LABELS = {
    "razorpay": "Razorpay (UPI, cards, netbanking)",
    "stripe": "Stripe (cards)",
    "paypal": "PayPal",
}


def mask_secret(value: str) -> str:
    """Enough to recognise which key is saved, never enough to use it."""
    v = value or ""
    if not v:
        return ""
    return ("*" * max(0, len(v) - 4)) + v[-4:] if len(v) > 4 else "****"


def client_gateway_to_dict(g):
    return {
        "provider": g.provider,
        "label": PROVIDER_LABELS.get(g.provider, g.provider.title()),
        "public_key": g.public_key or "",
        # Never the real thing. This endpoint is read by a browser.
        "secret_key": mask_secret(g.secret_key),
        "has_secret": bool(g.secret_key),
        "webhook_secret": mask_secret(g.webhook_secret),
        "is_active": bool(g.is_active),
        "is_live": bool(g.is_live),
        "updated_at": g.updated_at or "",
    }


def active_client_gateway(db: Session, client_id: int):
    """The one a customer will be offered. Razorpay first because it is the
    only one wired end to end."""
    rows = db.query(models.DBClientGateway).filter(
        models.DBClientGateway.client_id == client_id,
        models.DBClientGateway.is_active == True,      # noqa: E712
    ).all()
    by_provider = {r.provider: r for r in rows if r.public_key and r.secret_key}
    for provider in CLIENT_PROVIDERS:
        if provider in by_provider:
            return by_provider[provider]
    return None


@app.get("/api/payment-gateways")
def list_client_gateways(request: Request, db: Session = Depends(get_db)):
    """What this business has set up to collect with."""
    client = get_client_user(request, db)
    rows = db.query(models.DBClientGateway).filter(
        models.DBClientGateway.client_id == client.id).all()
    saved = {r.provider: client_gateway_to_dict(r) for r in rows}
    return {
        "gateways": [
            saved.get(p, {
                "provider": p, "label": PROVIDER_LABELS[p], "public_key": "",
                "secret_key": "", "has_secret": False, "webhook_secret": "",
                "is_active": False, "is_live": False, "updated_at": "",
            })
            for p in CLIENT_PROVIDERS
        ],
        # Said plainly so nobody wires their own keys expecting wallet credit.
        "note": "These collect money from your customers into your own account. "
                "Topping up your aniprotech wallet is separate and always goes "
                "through us.",
    }


@app.put("/api/payment-gateways/{provider}")
def save_client_gateway(provider: str, request: Request, body: dict = None,
                        db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    provider = (provider or "").strip().lower()
    if provider not in CLIENT_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown payment provider")

    body = body or {}
    row = db.query(models.DBClientGateway).filter(
        models.DBClientGateway.client_id == client.id,
        models.DBClientGateway.provider == provider).first()
    if not row:
        row = models.DBClientGateway(client_id=client.id, provider=provider)
        db.add(row)

    if "public_key" in body:
        row.public_key = (body.get("public_key") or "").strip()[:200]
    # An empty secret means "leave the saved one alone", because the browser
    # only ever received a masked version and would otherwise send it back and
    # overwrite the real key with asterisks.
    secret = (body.get("secret_key") or "").strip()
    if secret and not secret.startswith("*"):
        row.secret_key = secret[:300]
    hook = (body.get("webhook_secret") or "").strip()
    if hook and not hook.startswith("*"):
        row.webhook_secret = hook[:300]

    if "is_active" in body:
        row.is_active = bool(body["is_active"])
    if "is_live" in body:
        row.is_live = bool(body["is_live"])
    row.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if row.is_active and not (row.public_key and row.secret_key):
        raise HTTPException(
            status_code=400,
            detail="Both keys are needed before this can take payments")

    log_audit(db, client.id, "payment_gateway_saved", "gateway", None,
              provider, "live" if row.is_live else "test", request)
    db.commit()
    db.refresh(row)
    return client_gateway_to_dict(row)


@app.delete("/api/payment-gateways/{provider}")
def remove_client_gateway(provider: str, request: Request,
                          db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    row = db.query(models.DBClientGateway).filter(
        models.DBClientGateway.client_id == client.id,
        models.DBClientGateway.provider == (provider or "").lower()).first()
    if not row:
        raise HTTPException(status_code=404, detail="Nothing saved for that provider")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Paying an invoice
# ---------------------------------------------------------------------------

def record_invoice_payment(db: Session, inv, amount: float, method: str,
                           reference: str, note: str = ""):
    """Put a receipt in the ledger and move the invoice's running totals.

    Returns False if this reference has already been recorded, so a webhook
    arriving twice - or a customer refreshing the confirmation - cannot pay the
    same invoice twice.
    """
    if reference:
        already = db.query(models.DBPayment).filter(
            models.DBPayment.invoice_id == inv.id,
            models.DBPayment.reference == reference).first()
        if already:
            return False

    amount = money(amount)
    db.add(models.DBPayment(
        client_id=inv.client_id, invoice_id=inv.id, amount=amount,
        paid_on=datetime.now().strftime("%Y-%m-%d"), method=method,
        reference=reference[:120], note=note[:200]))

    inv.paid = money((inv.paid or 0) + amount)
    sub, tax, total = compute_invoice_totals(inv.line_items, inv.tax_type)
    inv.due = money(max(0.0, total - inv.paid))
    if inv.due <= 0:
        inv.status = "Paid"
    return True


def payable_invoice(db: Session, tracking_id: str):
    """The invoice behind a payment link, if it can still be paid."""
    inv = db.query(models.DBInvoice).filter(
        models.DBInvoice.tracking_id == tracking_id).first()
    if not inv or inv.status in ("Draft", "Void"):
        raise HTTPException(status_code=404, detail="That invoice is not available")
    return inv


@app.post("/api/public/invoices/{tracking_id}/pay/razorpay/order")
def start_invoice_payment(tracking_id: str, request: Request,
                          db: Session = Depends(get_db)):
    """Open a Razorpay order against the business's own account."""
    inv = payable_invoice(db, tracking_id)
    if inv.status == "Paid" or (inv.due or 0) <= 0:
        raise HTTPException(status_code=409, detail="This invoice is already paid")

    key_id, key_secret, mode = collecting_keys(db, inv.client_id)
    if not (key_id and key_secret):
        raise HTTPException(status_code=503,
                            detail="Online payment is not set up for this invoice")

    currency = (inv.currency or "INR").upper()
    amount_minor = int(round(money(inv.due or 0) * 100))
    if amount_minor <= 0:
        raise HTTPException(status_code=409, detail="Nothing left to pay")

    try:
        resp = httpx.post(
            "https://api.razorpay.com/v1/orders",
            auth=(key_id, key_secret),
            json={"amount": amount_minor, "currency": currency,
                  "receipt": inv.number[:40],
                  "notes": {"invoice": inv.number}},
            timeout=20.0)
    except Exception:
        logger.exception("Razorpay unreachable for invoice %s", inv.number)
        raise HTTPException(
            status_code=502,
            detail="Could not reach the payment provider. Please try again shortly.")

    if resp.status_code >= 400:
        # The customer is not the one who can fix a misconfigured account, but
        # they should not be told a blank "something went wrong" either - and
        # the business needs the reason in the log to act on.
        logger.error("Razorpay order failed for invoice %s: %s",
                     inv.number, resp.text[:400])
        raise HTTPException(status_code=502,
                            detail=razorpay_complaint(resp, currency))
    order = resp.json()

    return {
        "order_id": order.get("id"),
        "key_id": key_id,                 # public half only
        "amount": amount_minor,
        "currency": currency,
        "invoice_number": inv.number,
        "description": f"Invoice {inv.number}",
    }


@app.post("/api/public/invoices/{tracking_id}/pay/razorpay/verify")
def confirm_invoice_payment(tracking_id: str, request: Request,
                            body: dict = None, db: Session = Depends(get_db)):
    """Mark it paid, but only against a signature we can verify ourselves.

    The browser tells us a payment happened. That claim is worth nothing on its
    own - anyone can post to this. Razorpay signs order_id|payment_id with the
    secret only the two of us hold, so recomputing it here is what makes the
    claim true.
    """
    body = body or {}
    inv = payable_invoice(db, tracking_id)

    key_id, key_secret, mode = collecting_keys(db, inv.client_id)
    if not key_secret:
        raise HTTPException(status_code=503, detail="Online payment is not set up")

    order_id = (body.get("razorpay_order_id") or "").strip()
    payment_id = (body.get("razorpay_payment_id") or "").strip()
    signature = (body.get("razorpay_signature") or "").strip()
    if not (order_id and payment_id and signature):
        raise HTTPException(status_code=400, detail="Incomplete payment details")

    expected = hmac.new(
        key_secret.encode(), f"{order_id}|{payment_id}".encode(),
        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("Rejected an unverified payment claim for %s", inv.number)
        raise HTTPException(status_code=400, detail="That payment could not be verified")

    amount = money(inv.due or 0)
    recorded = record_invoice_payment(
        db, inv, amount, "razorpay", payment_id,
        note="Paid online by the customer")

    # Taken into the platform's account, so the customer has paid and the
    # business has not. Recorded once, alongside the receipt.
    if recorded and mode == "platform":
        record_settlement(db, inv, int(round(amount * 100)),
                          (inv.currency or "INR"), payment_id)
    db.commit()

    return {
        "paid": True,
        "already_recorded": not recorded,
        "invoice_number": inv.number,
        "status": inv.status,
    }




# ============================================================================
# WHERE INVOICE MONEY LANDS
#
# Two arrangements, one switch, held by the operator:
#
#   direct     - each business uses its own Razorpay keys and the money goes
#                straight to them. Nothing is owed to anybody.
#   platform   - every business collects through the platform's own Razorpay
#                account. The customer has paid and the tenant has not been
#                paid, so each collection writes a settlement that stays owed
#                until it is paid out. Holding other people's money is a
#                commitment, not a shortcut, and this is the record of it.
# ============================================================================

COLLECTION_MODES = ("direct", "platform")
COLLECTION_SETTING = "INVOICE_COLLECTION_MODE"


def collection_mode(db: Session) -> str:
    """How invoice payments are routed right now. Platform-wide, not per tenant,
    because a customer paying an invoice cannot be asked which arrangement
    their supplier is on."""
    row = db.query(models.DBSettings).filter(
        models.DBSettings.key == COLLECTION_SETTING,
        models.DBSettings.client_id == None,        # noqa: E711
    ).first()
    value = (row.value if row else "") or "direct"
    return value if value in COLLECTION_MODES else "direct"


def collecting_keys(db: Session, client_id: int):
    """(key_id, key_secret, mode) for taking a payment on this invoice.

    In platform mode the tenant's own keys are ignored entirely - otherwise a
    business that had set up its own would quietly keep collecting directly
    while the operator believed everything came through one account.
    """
    mode = collection_mode(db)
    if mode == "platform":
        cfg = gateway_config()["razorpay"]
        return cfg["key_id"], cfg["key_secret"], "platform"

    gw = db.query(models.DBClientGateway).filter(
        models.DBClientGateway.client_id == client_id,
        models.DBClientGateway.provider == "razorpay",
        models.DBClientGateway.is_active == True,      # noqa: E712
    ).first()
    if gw:
        return gw.public_key, gw.secret_key, "direct"
    return "", "", "direct"


def record_settlement(db: Session, inv, amount_minor: int, currency: str,
                      payment_id: str):
    """Money taken into the platform account belongs to the tenant."""
    db.add(models.DBSettlement(
        client_id=inv.client_id, invoice_id=inv.id,
        amount_minor=amount_minor, currency=(currency or "INR").upper(),
        status="owed", gateway="razorpay",
        gateway_payment_id=payment_id[:120]))


@app.get("/api/superadmin/collection-mode")
def read_collection_mode(request: Request, db: Session = Depends(get_db)):
    require_superadmin(request)
    mode = collection_mode(db)
    cfg = gateway_config()["razorpay"]
    owed = db.query(models.DBSettlement).filter(
        models.DBSettlement.status == "owed").all()

    by_currency = {}
    for s in owed:
        by_currency[s.currency] = by_currency.get(s.currency, 0) + (s.amount_minor or 0)

    return {
        "mode": mode,
        "modes": list(COLLECTION_MODES),
        "platform_keys_ready": bool(cfg["key_id"] and cfg["key_secret"]),
        "platform_key_env": ["RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"],
        "owed_to_tenants": [
            {"currency": c, "amount": to_major(v, c)} for c, v in sorted(by_currency.items())
        ],
        "owed_count": len(owed),
        "note": ("In platform mode every customer payment lands in the platform's "
                 "Razorpay account, so each one is money owed to the business that "
                 "raised the invoice until it is paid out."),
    }


@app.put("/api/superadmin/collection-mode")
def set_collection_mode(request: Request, body: dict = None,
                        db: Session = Depends(get_db)):
    require_superadmin(request)
    mode = ((body or {}).get("mode") or "").strip().lower()
    if mode not in COLLECTION_MODES:
        raise HTTPException(status_code=400,
                            detail="Mode must be direct or platform")

    if mode == "platform":
        cfg = gateway_config()["razorpay"]
        if not (cfg["key_id"] and cfg["key_secret"]):
            raise HTTPException(
                status_code=400,
                detail="Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET before "
                       "collecting into the platform account")

    row = db.query(models.DBSettings).filter(
        models.DBSettings.key == COLLECTION_SETTING,
        models.DBSettings.client_id == None,        # noqa: E711
    ).first()
    if row:
        row.value = mode
    else:
        db.add(models.DBSettings(key=COLLECTION_SETTING, value=mode, client_id=None))
    db.commit()
    return {"mode": mode}


@app.get("/api/superadmin/settlements")
def list_settlements(request: Request, status: str = "owed",
                     db: Session = Depends(get_db)):
    """What is owed to whom, so it can actually be paid out."""
    require_superadmin(request)
    q = db.query(models.DBSettlement)
    if status in ("owed", "paid_out"):
        q = q.filter(models.DBSettlement.status == status)
    rows = q.order_by(models.DBSettlement.id.desc()).limit(500).all()

    clients = {c.id: c for c in db.query(models.DBClient).all()}
    invoices = {i.id: i for i in db.query(models.DBInvoice).filter(
        models.DBInvoice.id.in_([r.invoice_id for r in rows] or [0])).all()}

    return {
        "settlements": [{
            "id": r.id,
            "client_id": r.client_id,
            "business": (clients.get(r.client_id).company_name
                         if clients.get(r.client_id) else "") or "",
            "invoice_number": (invoices.get(r.invoice_id).number
                               if invoices.get(r.invoice_id) else ""),
            "amount": to_major(r.amount_minor, r.currency),
            "currency": r.currency,
            "status": r.status,
            "collected_at": r.collected_at,
            "paid_out_at": r.paid_out_at or "",
            "payout_reference": r.payout_reference or "",
            "gateway_payment_id": r.gateway_payment_id or "",
        } for r in rows],
    }


@app.post("/api/superadmin/settlements/{settlement_id}/paid-out")
def mark_settlement_paid(settlement_id: int, request: Request,
                         body: dict = None, db: Session = Depends(get_db)):
    """Record that this money has reached the business it belongs to."""
    require_superadmin(request)
    row = db.query(models.DBSettlement).filter(
        models.DBSettlement.id == settlement_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if row.status == "paid_out":
        raise HTTPException(status_code=409, detail="Already marked paid out")

    reference = ((body or {}).get("reference") or "").strip()
    if not reference:
        raise HTTPException(
            status_code=400,
            detail="Give the payout reference - this is the proof it was sent")

    row.status = "paid_out"
    row.paid_out_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row.payout_reference = reference[:120]
    log_audit(db, row.client_id, "settlement_paid_out", "settlement", row.id,
              reference, f"{to_major(row.amount_minor, row.currency)} {row.currency}",
              request, user_type="superadmin", user_name="superadmin")
    db.commit()
    return {"id": row.id, "status": row.status, "paid_out_at": row.paid_out_at}




# ============================================================================
# CHARGING WITHOUT THE PAYER PRESENT
#
# Two payers, one mechanism:
#   a customer authorises their invoices to be paid automatically
#   a business authorises its own wallet to top itself up when it runs low
#
# Everything here is arranged so the only untestable part is the single HTTP
# call to the gateway. What decides whether to charge, how much, and whether
# it has already happened is all ordinary code with tests behind it.
# ============================================================================

MANDATE_STATUSES = ("active", "cancelled", "failed")


def mandate_for_customer(db: Session, client_id: int, contact: str):
    """The standing permission covering this customer, if they gave one."""
    if not contact:
        return None
    return db.query(models.DBPaymentMandate).filter(
        models.DBPaymentMandate.client_id == client_id,
        models.DBPaymentMandate.payer_type == "customer",
        models.DBPaymentMandate.status == "active",
        models.DBPaymentMandate.payer_ref.ilike(contact.strip()),
    ).first()


def mandate_for_tenant(db: Session, client_id: int):
    """A business's permission to have its own wallet topped up."""
    return db.query(models.DBPaymentMandate).filter(
        models.DBPaymentMandate.client_id == client_id,
        models.DBPaymentMandate.payer_type == "tenant",
        models.DBPaymentMandate.status == "active",
    ).first()


def mandate_allows(mandate, amount_minor: int) -> bool:
    """A ceiling is the difference between "you may charge me" and "you may
    charge me anything". Zero means no ceiling was set."""
    if not mandate or mandate.status != "active":
        return False
    if mandate.max_amount_minor and amount_minor > mandate.max_amount_minor:
        return False
    return amount_minor > 0


def invoice_charge_key(inv) -> str:
    """One key per invoice per outstanding amount.

    Including the amount means a part-paid invoice can be charged for the
    remainder later, while charging the same balance twice is refused by the
    unique index rather than by remembering to check.
    """
    return f"invoice:{inv.id}:{int(round(money(inv.due or 0) * 100))}"


def topup_charge_key(wallet, on_date) -> str:
    """One automatic top-up per wallet per day, so a wallet that stays below
    its threshold is not charged every time the job runs."""
    return f"topup:{wallet.client_id}:{on_date}"


def already_attempted(db: Session, key: str):
    return db.query(models.DBAutoCharge).filter(
        models.DBAutoCharge.idempotency_key == key).first()


def charge_mandate(mandate, amount_minor: int, currency: str, description: str,
                   key_id: str, key_secret: str):
    """Ask the gateway to take money against a saved token.

    The one part of this that cannot be tested without a live account and a
    real mandate. Kept to a single call with everything decided by the time it
    is reached, so a failure here is a gateway problem and never a logic one.

    Returns (payment_id, error). Exactly one of them is set.
    """
    try:
        resp = httpx.post(
            "https://api.razorpay.com/v1/payments/createRecurringPayment",
            auth=(key_id, key_secret),
            json={
                "email": "", "contact": "",
                "amount": amount_minor,
                "currency": (currency or "INR").upper(),
                "order_id": None,
                "customer_id": mandate.customer_id,
                "token": mandate.token_id,
                "recurring": "1",
                "description": description[:120],
            },
            timeout=30.0)
        if resp.status_code in (200, 201):
            return (resp.json().get("razorpay_payment_id")
                    or resp.json().get("id") or ""), None
        return None, f"{resp.status_code}: {(resp.text or '')[:160]}"
    except Exception as exc:      # noqa: BLE001
        return None, str(exc)[:160]


def run_auto_charge(db: Session, mandate, amount_minor: int, currency: str,
                    purpose: str, key: str, description: str,
                    invoice=None, key_id="", key_secret=""):
    """Attempt one charge, recording it whatever happens.

    The row is written and committed before the gateway is called, so a crash
    partway leaves evidence rather than a silent gap.
    """
    if already_attempted(db, key):
        return None, "already_attempted"
    if not mandate_allows(mandate, amount_minor):
        return None, "not_permitted"
    if not (key_id and key_secret):
        return None, "no_gateway_keys"

    attempt = models.DBAutoCharge(
        client_id=mandate.client_id, mandate_id=mandate.id, purpose=purpose,
        invoice_id=invoice.id if invoice is not None else None,
        amount_minor=amount_minor, currency=(currency or "INR").upper(),
        idempotency_key=key, status="pending")
    db.add(attempt)
    db.commit()

    payment_id, error = charge_mandate(
        mandate, amount_minor, currency, description, key_id, key_secret)

    if error:
        attempt.status = "failed"
        attempt.failure_reason = error
        # A rejected token will keep being rejected, so stop using it rather
        # than failing against the same mandate every night.
        if "token" in error.lower() or "mandate" in error.lower():
            mandate.status = "failed"
            mandate.failure_reason = error[:200]
        db.commit()
        return None, error

    attempt.status = "succeeded"
    attempt.gateway_payment_id = payment_id or ""
    attempt.settled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mandate.last_used_at = attempt.settled_at
    db.commit()
    return attempt, None


# --- what is due to be charged ------------------------------------------------

def invoices_due_for_autopay(db: Session, on_date=None):
    """Issued, still owed, due today or already past it, and covered by a
    mandate. A draft has not been agreed and a future invoice is not yet owed.
    """
    on_date = on_date or datetime.now().date()
    out = []
    rows = db.query(models.DBInvoice).filter(
        models.DBInvoice.status.in_(list(OPEN_INVOICE_STATUSES))).all()
    for inv in rows:
        if (inv.due or 0) <= 0:
            continue
        due = _parse_date(inv.due_date)
        if not due or due > on_date:
            continue
        mandate = mandate_for_customer(db, inv.client_id, inv.to_contact or "")
        if not mandate:
            continue
        amount_minor = int(round(money(inv.due or 0) * 100))
        if not mandate_allows(mandate, amount_minor):
            continue
        if already_attempted(db, invoice_charge_key(inv)):
            continue
        out.append((inv, mandate, amount_minor))
    return out


def wallets_due_for_topup(db: Session, on_date=None):
    """Below the line the business set, with permission to fix it."""
    on_date = on_date or datetime.now().date()
    out = []
    rows = db.query(models.DBWallet).filter(
        models.DBWallet.auto_topup_enabled == True,      # noqa: E712
    ).all()
    for wallet in rows:
        if wallet.is_suspended:
            continue
        if (wallet.balance_minor or 0) > (wallet.auto_topup_threshold_minor or 0):
            continue
        amount = wallet.auto_topup_amount_minor or 0
        if amount <= 0:
            continue
        mandate = mandate_for_tenant(db, wallet.client_id)
        if not mandate_allows(mandate, amount):
            continue
        if already_attempted(db, topup_charge_key(wallet, on_date.isoformat())):
            continue
        out.append((wallet, mandate, amount))
    return out




@scheduled_job("invoice_autopay")
def job_invoice_autopay(db, now):
    """Collect invoices whose customer agreed to be charged.

    Runs after the overdue reminders so an invoice about to be paid
    automatically is not chased on the same morning.
    """
    charged, failed = 0, 0
    for inv, mandate, amount_minor in invoices_due_for_autopay(db, now.date()):
        key_id, key_secret, mode = collecting_keys(db, inv.client_id)
        attempt, error = run_auto_charge(
            db, mandate, amount_minor, inv.currency or mandate.currency,
            "invoice", invoice_charge_key(inv),
            f"Invoice {inv.number}", invoice=inv,
            key_id=key_id, key_secret=key_secret)
        if error:
            failed += 1
            continue

        recorded = record_invoice_payment(
            db, inv, money(amount_minor / 100.0), "razorpay",
            attempt.gateway_payment_id, note="Paid automatically")
        if recorded and mode == "platform":
            record_settlement(db, inv, amount_minor,
                              inv.currency or "INR", attempt.gateway_payment_id)
        charged += 1
    db.commit()
    return {"charged": charged, "failed": failed}


@scheduled_job("wallet_auto_topup")
def job_wallet_auto_topup(db, now):
    """Top up a wallet that has fallen below the line its owner set."""
    topped, failed = 0, 0
    cfg = gateway_config()["razorpay"]
    for wallet, mandate, amount_minor in wallets_due_for_topup(db, now.date()):
        attempt, error = run_auto_charge(
            db, mandate, amount_minor, wallet.currency, "wallet_topup",
            topup_charge_key(wallet, now.date().isoformat()),
            "Wallet top-up",
            key_id=cfg["key_id"], key_secret=cfg["key_secret"])
        if error:
            failed += 1
            continue
        credit_wallet(db, wallet.client_id, amount_minor,
                      "Automatic top-up",
                      reference=attempt.gateway_payment_id,
                      performed_by="autopay", action_key="topup")
        topped += 1
    db.commit()
    return {"topped_up": topped, "failed": failed}


# --- setting it up ------------------------------------------------------------

def mandate_to_dict(m):
    return {
        "id": m.id, "payer_type": m.payer_type, "payer_ref": m.payer_ref or "",
        "method": m.method or "", "masked": m.masked or "",
        "status": m.status, "currency": m.currency,
        "max_amount": to_major(m.max_amount_minor, m.currency) if m.max_amount_minor else None,
        "created_at": m.created_at, "last_used_at": m.last_used_at or "",
        "failure_reason": m.failure_reason or "",
    }


@app.post("/api/public/invoices/{tracking_id}/autopay")
def authorise_invoice_autopay(tracking_id: str, request: Request,
                              body: dict = None, db: Session = Depends(get_db)):
    """A customer agreeing that future invoices may be charged.

    Only reachable with a token the gateway issued for a payment that has just
    been verified, so agreeing to this is something the payer did at the
    checkout rather than something anyone can post.
    """
    body = body or {}
    inv = payable_invoice(db, tracking_id)

    token_id = (body.get("token_id") or "").strip()
    customer_id = (body.get("customer_id") or "").strip()
    payment_id = (body.get("razorpay_payment_id") or "").strip()
    signature = (body.get("razorpay_signature") or "").strip()
    order_id = (body.get("razorpay_order_id") or "").strip()
    if not (token_id and customer_id and payment_id and signature and order_id):
        raise HTTPException(status_code=400, detail="Incomplete authorisation")

    key_id, key_secret, mode = collecting_keys(db, inv.client_id)
    if not key_secret:
        raise HTTPException(status_code=503, detail="Payment is not set up")

    expected = hmac.new(key_secret.encode(),
                        f"{order_id}|{payment_id}".encode(),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.warning("Rejected an unverified autopay authorisation for %s", inv.number)
        raise HTTPException(status_code=400,
                            detail="That authorisation could not be verified")

    ceiling = body.get("max_amount")
    max_minor = int(round(float(ceiling) * 100)) if ceiling else 0

    existing = mandate_for_customer(db, inv.client_id, inv.to_contact or "")
    if existing:
        existing.status = "cancelled"
        existing.cancelled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    mandate = models.DBPaymentMandate(
        client_id=inv.client_id, payer_type="customer",
        payer_ref=(inv.to_contact or "").strip(),
        token_id=token_id, customer_id=customer_id,
        method=(body.get("method") or "")[:20],
        masked=(body.get("masked") or "")[:40],
        currency=(inv.currency or "INR").upper(),
        max_amount_minor=max_minor,
        created_from_invoice_id=inv.id)
    db.add(mandate)
    db.commit()
    db.refresh(mandate)
    return mandate_to_dict(mandate)


@app.get("/api/autopay/mandates")
def list_mandates(request: Request, db: Session = Depends(get_db)):
    """Who has agreed to be charged, and the business's own arrangement."""
    client = get_client_user(request, db)
    rows = db.query(models.DBPaymentMandate).filter(
        models.DBPaymentMandate.client_id == client.id
    ).order_by(models.DBPaymentMandate.id.desc()).limit(200).all()
    return {
        "customers": [mandate_to_dict(m) for m in rows if m.payer_type == "customer"],
        "own": next((mandate_to_dict(m) for m in rows
                     if m.payer_type == "tenant" and m.status == "active"), None),
    }


@app.delete("/api/autopay/mandates/{mandate_id}")
def cancel_mandate(mandate_id: int, request: Request,
                   db: Session = Depends(get_db)):
    """Stopping is immediate and needs no reason."""
    client = get_client_user(request, db)
    m = db.query(models.DBPaymentMandate).filter(
        models.DBPaymentMandate.id == mandate_id,
        models.DBPaymentMandate.client_id == client.id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    m.status = "cancelled"
    m.cancelled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    return {"id": m.id, "status": m.status}


@app.get("/api/wallet/auto-topup")
def read_auto_topup(request: Request, db: Session = Depends(get_db)):
    client = get_client_user(request, db)
    wallet = get_wallet(db, client.id)
    mandate = mandate_for_tenant(db, client.id)
    return {
        "enabled": bool(wallet.auto_topup_enabled),
        "threshold": to_major(wallet.auto_topup_threshold_minor or 0, wallet.currency),
        "amount": to_major(wallet.auto_topup_amount_minor or 0, wallet.currency),
        "currency": wallet.currency,
        "balance": to_major(wallet.balance_minor, wallet.currency),
        "has_mandate": mandate is not None,
        "mandate": mandate_to_dict(mandate) if mandate else None,
    }


@app.put("/api/wallet/auto-topup")
def set_auto_topup(request: Request, body: dict = None,
                   db: Session = Depends(get_db)):
    """Turning it on needs a threshold, an amount, and permission to charge -
    otherwise it is a setting that quietly does nothing."""
    client = get_client_user(request, db)
    body = body or {}
    wallet = get_wallet(db, client.id)

    enabled = bool(body.get("enabled"))
    if "threshold" in body:
        wallet.auto_topup_threshold_minor = to_minor(
            abs(float(body.get("threshold") or 0)), wallet.currency)
    if "amount" in body:
        wallet.auto_topup_amount_minor = to_minor(
            abs(float(body.get("amount") or 0)), wallet.currency)

    if enabled:
        if (wallet.auto_topup_amount_minor or 0) <= 0:
            raise HTTPException(status_code=400,
                                detail="Set how much to top up by")
        if not mandate_for_tenant(db, client.id):
            raise HTTPException(
                status_code=400,
                detail="Authorise a payment method before turning this on")
    wallet.auto_topup_enabled = enabled
    wallet.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    return read_auto_topup(request, db)


# Serve frontend
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at {frontend_path}")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, reload=False)
