"""One app, three front doors.

invoice.aniprotech.com, hr.aniprotech.com and employee.aniprotech.com are the
same deployment. The first label of the host names the face: what the root
serves, which product the app shows, where a page that belongs to another
face sends you. The API is the same on every host. Until PRODUCT_HOSTS names
the hosts, every host serves everything, as it always did.
"""
import pathlib
import re

import pytest
from starlette.middleware.sessions import SessionMiddleware

import main
from conftest import make_employee

HOSTS = "invoicing=invoice.aniprotech.com, hr=https://hr.aniprotech.com/, employee=employee.aniprotech.com, junk"


@pytest.fixture
def split(monkeypatch):
    monkeypatch.setenv("PRODUCT_HOSTS", HOSTS)
    monkeypatch.setenv("APP_BASE_URL", "https://www.aniprotech.com")


@pytest.fixture
def one_address(monkeypatch):
    monkeypatch.delenv("PRODUCT_HOSTS", raising=False)
    monkeypatch.setenv("APP_BASE_URL", "https://www.aniprotech.com")


def on(host):
    return {"host": host}


# --- naming the face -----------------------------------------------------------
def test_the_first_label_of_the_host_names_the_face():
    assert main.product_for_host("invoice.aniprotech.com") == "invoicing"
    assert main.product_for_host("Invoicing.aniprotech.com") == "invoicing"
    assert main.product_for_host("hr.aniprotech.com:8000") == "hr"
    assert main.product_for_host("employee.localhost:8000") == "employee"
    assert main.product_for_host("staff.aniprotech.com") == "employee"
    for site in ("www.aniprotech.com", "aniprotech.com", "localhost:8000", "testserver", "", None):
        assert main.product_for_host(site) == "", site


def test_product_hosts_are_read_from_the_environment(split, monkeypatch):
    assert main.product_hosts() == {"invoicing": "invoice.aniprotech.com", "hr": "hr.aniprotech.com",
                                    "employee": "employee.aniprotech.com"}
    assert main.hosts_are_split()
    assert main.product_base_url("hr") == "https://hr.aniprotech.com"
    monkeypatch.delenv("PRODUCT_HOSTS")
    assert main.product_hosts() == {} and not main.hosts_are_split()
    assert main.product_base_url("hr") == ""


def test_a_link_goes_to_the_host_its_page_lives_on(split):
    assert main.page_url("/app.html#/leave") == "https://hr.aniprotech.com/app.html#/leave"
    assert main.page_url("/app.html#/people/12") == "https://hr.aniprotech.com/app.html#/people/12"
    assert main.page_url("/app.html#/hr") == "https://hr.aniprotech.com/app.html#/hr"
    assert main.page_url("/app.html#/invoices/INV-1") == "https://invoice.aniprotech.com/app.html#/invoices/INV-1"
    assert main.page_url("/app.html#/settings") == "https://invoice.aniprotech.com/app.html#/settings"
    assert main.page_url("/app.html") == "https://invoice.aniprotech.com/app.html"
    assert main.page_url("/login.html?next=%2Fapp.html") == "https://invoice.aniprotech.com/login.html?next=%2Fapp.html"
    assert main.page_url("/invoice.html?id=abc") == "https://invoice.aniprotech.com/invoice.html?id=abc"
    assert main.page_url("/quote.html?id=abc") == "https://invoice.aniprotech.com/quote.html?id=abc"
    assert main.page_url("/employee-login.html") == "https://employee.aniprotech.com/employee-login.html"
    assert main.page_url("/reset-password.html?token=x&portal=employee") == "https://employee.aniprotech.com/reset-password.html?token=x&portal=employee"
    assert main.page_url("/reset-password.html?token=x&portal=team") == "https://invoice.aniprotech.com/reset-password.html?token=x&portal=team"
    assert main.page_url("/superadmin.html") == "https://www.aniprotech.com/superadmin.html"
    assert main.page_url("/privacy") == "https://www.aniprotech.com/privacy"


def test_on_one_address_every_link_is_on_the_site(one_address):
    for path in ("/app.html#/leave", "/employee-login.html", "/invoice.html?id=abc", "/superadmin.html"):
        assert main.page_url(path) == "https://www.aniprotech.com" + path


def test_the_hr_routes_named_here_are_the_ones_the_nav_calls_hr():
    """HR_SLUGS decides which host an app link is built on; the nav decides
    what the app shows. They must agree, or a link lands on the wrong door."""
    page = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app.html").read_text(encoding="utf-8")
    nav = re.findall(r'href="#/([a-z-]+)"[^>]*data-portal="(invoicing|hr)"', page)
    assert nav, "no nav entries found"
    hr = {slug for slug, portal in nav if portal == "hr"}
    invoicing = {slug for slug, portal in nav if portal == "invoicing"}
    assert hr <= main.HR_SLUGS, sorted(hr - main.HR_SLUGS)
    assert not (invoicing & main.HR_SLUGS), sorted(invoicing & main.HR_SLUGS)


# --- the front door ----------------------------------------------------------------
def test_a_product_host_opens_on_its_sign_in_and_an_employee_host_on_the_portal(client, one_address):
    r = client.get("/", headers=on("hr.aniprotech.com"), follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login.html"
    r = client.get("/index.html", headers=on("invoice.aniprotech.com"), follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login.html"
    r = client.get("/", headers=on("employee.aniprotech.com"), follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/employee-login.html"
    # The site keeps its front page.
    r = client.get("/", headers=on("www.aniprotech.com"), follow_redirects=False)
    assert r.status_code == 200 and "<title>" in r.text


def test_somebody_already_in_opens_on_the_app(tenant, one_address):
    r = tenant.get("/", headers=on("invoice.aniprotech.com"), follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/app.html"


def test_a_member_of_staff_already_in_opens_on_their_dashboard(tenant, one_address):
    emp = make_employee(tenant, email="door@example.com", password="EmpPass123")
    tenant.post("/api/client/logout")
    main.rate_limiter._hits.clear()
    r = tenant.post("/api/employee/auth/login", json={"email": "door@example.com", "password": "EmpPass123"})
    assert r.status_code == 200, r.text
    r = tenant.get("/", headers=on("employee.aniprotech.com"), follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/employee-dashboard.html"


def test_until_the_hosts_are_named_every_host_serves_everything(client, one_address):
    for path, host in (("/employee-login.html", "hr.aniprotech.com"), ("/app.html", "www.aniprotech.com"),
                       ("/login.html", "employee.aniprotech.com"), ("/superadmin.html", "invoice.aniprotech.com")):
        r = client.get(path, headers=on(host), follow_redirects=False)
        assert r.status_code == 200, (path, host, r.status_code)


def test_once_named_a_page_on_the_wrong_host_is_sent_to_the_right_one(client, split):
    cases = [
        ("/employee-login.html?x=1", "hr.aniprotech.com", "https://employee.aniprotech.com/employee-login.html?x=1"),
        ("/employee-dashboard.html", "invoice.aniprotech.com", "https://employee.aniprotech.com/employee-dashboard.html"),
        ("/superadmin.html", "invoice.aniprotech.com", "https://www.aniprotech.com/superadmin.html"),
        ("/login.html", "employee.aniprotech.com", "https://hr.aniprotech.com/login.html"),
        ("/app.html", "employee.aniprotech.com", "https://hr.aniprotech.com/app.html"),
        ("/superadmin-login.html", "employee.aniprotech.com", "https://www.aniprotech.com/superadmin-login.html"),
        ("/app.html", "www.aniprotech.com", "https://invoice.aniprotech.com/app.html"),
        ("/login.html?next=%2Fapp.html", "www.aniprotech.com", "https://invoice.aniprotech.com/login.html?next=%2Fapp.html"),
        ("/hr.html", "www.aniprotech.com", "https://hr.aniprotech.com/hr.html"),
        ("/employee-login.html", "www.aniprotech.com", "https://employee.aniprotech.com/employee-login.html"),
        ("/onboard.html", "something-else.up.railway.app", "https://invoice.aniprotech.com/onboard.html"),
    ]
    for path, host, where in cases:
        r = client.get(path, headers=on(host), follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == where, (path, host, r.status_code, r.headers.get("location"))


def test_a_page_on_its_own_host_is_served_and_the_api_is_the_same_everywhere(client, split):
    for path, host in (("/app.html", "invoice.aniprotech.com"), ("/app.html", "hr.aniprotech.com"),
                       ("/login.html", "hr.aniprotech.com"), ("/employee-login.html", "employee.aniprotech.com"),
                       ("/superadmin.html", "www.aniprotech.com"), ("/invoice.html", "hr.aniprotech.com"),
                       ("/", "www.aniprotech.com")):
        r = client.get(path, headers=on(host), follow_redirects=False)
        assert r.status_code == 200, (path, host, r.status_code)
    for host in ("invoice.aniprotech.com", "hr.aniprotech.com", "employee.aniprotech.com", "www.aniprotech.com"):
        assert client.get("/api/health", headers=on(host)).status_code == 200
    r = client.post("/api/client/login", json={"email": "nobody@example.com", "password": "x"},
                    headers=on("employee.aniprotech.com"), follow_redirects=False)
    assert r.status_code != 302


# --- what the app and the front page are told ------------------------------------------
def test_the_app_is_told_which_face_it_wears_and_where_the_others_are(tenant, split):
    me = tenant.get("/api/client/me", headers=on("hr.aniprotech.com")).json()
    assert me["product"] == "hr"
    assert me["products"] == {"invoicing": "https://invoice.aniprotech.com", "hr": "https://hr.aniprotech.com",
                              "employee": "https://employee.aniprotech.com"}
    assert tenant.get("/api/client/me", headers=on("invoice.aniprotech.com")).json()["product"] == "invoicing"
    assert tenant.get("/api/client/me").json()["product"] == ""


def test_the_front_page_is_told_the_doors(client, split, monkeypatch):
    assert client.get("/api/platform/landing").json()["products"]["employee"] == "https://employee.aniprotech.com"
    monkeypatch.delenv("PRODUCT_HOSTS")
    assert client.get("/api/platform/landing").json()["products"] == {}


def test_the_session_cookie_can_sit_on_the_parent_domain():
    """COOKIE_DOMAIN is what lets one sign-in count on every host."""
    sess = [m for m in main.app.user_middleware if m.cls is SessionMiddleware]
    assert len(sess) == 1 and "domain" in sess[0].kwargs


# --- links in mail -----------------------------------------------------------------------
def test_mail_links_land_on_the_right_door(tenant, split):
    """The staff digest points at the employee host, the HR digest at the HR
    host, and a customer's invoice link at Invoicing."""
    emp = make_employee(tenant, email="digest@example.com")
    with main.SessionLocal() as db:
        row = db.get(main.models.DBEmployee, emp["id"])
        db.add(main.models.DBNotification(client_id=row.client_id, employee_id=row.id, title="A thing",
                                          created_at="2030-01-01 09:00:00"))
        db.commit()
        staff = main.employee_digest_for(db, row, "2029-12-31 00:00:00")
        hr = main.hr_digest_for(db, db.get(main.models.DBClient, row.client_id))
    assert staff and "https://employee.aniprotech.com/employee-login.html" in staff["text"]
    assert hr and "https://hr.aniprotech.com/app.html#/hr" in hr["text"]
    inv = main.models.DBInvoice(tracking_id="trk123")
    assert main.invoice_public_link(inv) == "https://invoice.aniprotech.com/invoice.html?id=trk123"


def test_the_installed_app_is_named_for_its_face(client):
    site = client.get("/manifest.webmanifest", headers=on("www.aniprotech.com")).json()
    hr = client.get("/manifest.webmanifest", headers=on("hr.aniprotech.com")).json()
    inv = client.get("/manifest.webmanifest", headers=on("invoice.aniprotech.com")).json()
    assert site["name"] == "Ani Protech" and hr["name"] == "aniprotech HR" and inv["name"] == "aniprotech Invoicing"
    assert hr["icons"] == site["icons"] and hr["start_url"] == site["start_url"]
