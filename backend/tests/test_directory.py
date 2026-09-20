"""Department and employee data integrity, plus super admin visibility.

These fields feed payroll and the employee login, so a bad value here shows up
later as wrong pay or an account nobody can sign into.
"""
import pytest

from conftest import make_employee


# --- departments -----------------------------------------------------------

@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_department_name_cannot_be_blank(tenant, name):
    res = tenant.post("/api/departments", json={"name": name})
    assert res.status_code == 400
    assert "name is required" in res.json()["detail"]


def test_department_name_is_trimmed(tenant):
    dept = tenant.post("/api/departments", json={"name": "  Engineering  "}).json()
    assert dept["name"] == "Engineering"


def test_duplicate_department_is_case_insensitive(tenant):
    assert tenant.post("/api/departments", json={"name": "Engineering"}).status_code == 200
    res = tenant.post("/api/departments", json={"name": "engineering"})
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


def test_rename_cannot_duplicate_another_department(tenant):
    tenant.post("/api/departments", json={"name": "Engineering"})
    finance = tenant.post("/api/departments", json={"name": "Finance"}).json()
    # Create checked for duplicates; update did not, so a rename produced two
    # departments with the same name.
    res = tenant.put(f"/api/departments/{finance['id']}", json={"name": "Engineering"})
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


def test_department_can_be_renamed_to_its_own_name(tenant):
    dept = tenant.post("/api/departments", json={"name": "Engineering"}).json()
    res = tenant.put(f"/api/departments/{dept['id']}",
                     json={"name": "Engineering", "description": "Builds product"})
    assert res.status_code == 200
    assert res.json()["description"] == "Builds product"


def test_same_department_name_allowed_across_tenants(client, tenant):
    tenant.post("/api/departments", json={"name": "Engineering"})
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": "dept2@example.com", "password": "Passw0rdTest"})
    client.post("/api/client/login", json={"email": "dept2@example.com", "password": "Passw0rdTest"})
    assert client.post("/api/departments", json={"name": "Engineering"}).status_code == 200


# --- employees -------------------------------------------------------------

@pytest.mark.parametrize("field,label", [("first_name", "First name"), ("last_name", "Last name")])
def test_employee_names_are_required(tenant, field, label):
    payload = {"first_name": "A", "last_name": "B", "email": "blank@example.com"}
    payload[field] = "   "
    res = tenant.post("/api/employees", json=payload)
    assert res.status_code == 400
    assert label in res.json()["detail"]


def test_employee_email_must_be_valid(tenant):
    res = tenant.post("/api/employees", json={
        "first_name": "A", "last_name": "B", "email": "not-an-email",
    })
    assert res.status_code == 400
    assert "not a valid email" in res.json()["detail"]


def test_employee_email_is_normalised_and_deduped_case_insensitively(tenant):
    emp = make_employee(tenant, email="Person@Example.com")
    assert emp["email"] == "person@example.com"
    # Two rows differing only by case made the employee login ambiguous,
    # because it matches on email and takes the first row.
    res = tenant.post("/api/employees", json={
        "first_name": "X", "last_name": "Y", "email": "PERSON@example.com",
    })
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


@pytest.mark.parametrize("field,label", [
    ("salary", "Salary"), ("hourly_rate", "Hourly rate"),
    ("deductions", "Deductions"), ("allowances", "Allowances"), ("bonus", "Bonus"),
])
def test_employee_money_cannot_be_negative(tenant, field, label):
    payload = {"first_name": "A", "last_name": "B", "email": f"{field}@example.com", field: -1}
    res = tenant.post("/api/employees", json=payload)
    assert res.status_code == 400
    assert label in res.json()["detail"]


@pytest.mark.parametrize("rate", [-1, 101, 500])
def test_tax_rate_must_be_a_percentage(tenant, rate):
    """A 500% rate produced a payslip with a large negative net, i.e. one
    saying the employee owes the company money."""
    res = tenant.post("/api/employees", json={
        "first_name": "A", "last_name": "B", "email": f"tax{rate}@example.com", "tax_rate": rate,
    })
    assert res.status_code == 400
    assert "between 0 and 100" in res.json()["detail"]


def test_employee_code_must_be_unique(tenant):
    make_employee(tenant, employee_id="EMP-9999")
    res = tenant.post("/api/employees", json={
        "first_name": "X", "last_name": "Y", "email": "dupcode@example.com",
        "employee_id": "EMP-9999",
    })
    assert res.status_code == 400
    assert "already in use" in res.json()["detail"]


def test_update_applies_the_same_validation(tenant):
    emp = make_employee(tenant)
    assert tenant.put(f"/api/employees/{emp['id']}", json={"tax_rate": 500}).status_code == 400
    assert tenant.put(f"/api/employees/{emp['id']}", json={"salary": -1}).status_code == 400
    assert tenant.put(f"/api/employees/{emp['id']}", json={"first_name": "  "}).status_code == 400
    assert tenant.put(f"/api/employees/{emp['id']}", json={"email": "bad"}).status_code == 400
    # A valid change still works.
    assert tenant.put(f"/api/employees/{emp['id']}", json={"salary": 1234}).status_code == 200


def test_update_email_to_another_employees_address_is_blocked(tenant):
    a = make_employee(tenant, email="a-person@example.com")
    make_employee(tenant, email="b-person@example.com")
    res = tenant.put(f"/api/employees/{a['id']}", json={"email": "b-person@example.com"})
    assert res.status_code == 400


def test_employee_keeps_its_own_email_on_update(tenant):
    emp = make_employee(tenant, email="keeper@example.com")
    res = tenant.put(f"/api/employees/{emp['id']}", json={"email": "keeper@example.com", "phone": "123"})
    assert res.status_code == 200


def test_validated_employee_produces_a_sane_payslip(tenant):
    emp = make_employee(tenant, salary=3000.0, tax_rate=20.0)
    ps = tenant.post("/api/payslips", json={
        "employee_id": emp["id"], "period_start": "2026-01-01",
        "period_end": "2026-01-31", "pay_date": "2026-02-01",
    }).json()
    assert ps["net_pay"] == 2400.00
    assert ps["net_pay"] > 0


# --- super admin -----------------------------------------------------------

@pytest.fixture
def superadmin(client):
    import main
    main.rate_limiter._hits.clear()
    res = client.post("/api/superadmin/login", json={
        "identifier": "hello@keyroutes.co", "password": "TestSuper123",
    })
    assert res.status_code == 200, res.text
    return client


def test_platform_stats_cover_every_module(superadmin):
    data = superadmin.get("/api/superadmin/platform-stats").json()
    for section in ("tenants", "invoicing", "hr", "recruitment"):
        assert section in data
    assert "employees" in data["hr"]
    assert "open_jobs" in data["recruitment"]


def test_platform_active_count_ignores_non_client_logins(client, superadmin):
    """The super admin's own login has a NULL client_id and used to be counted
    as an active tenant."""
    data = superadmin.get("/api/superadmin/platform-stats").json()
    assert data["tenants"]["active_last_30_days"] <= data["tenants"]["total"]


def test_client_overview_reports_usage_and_portals(client, account, superadmin):
    # The tenant from the `account` fixture already exists.
    clients = superadmin.get("/api/superadmin/clients").json()
    assert clients
    cid = clients[0]["id"]
    d = superadmin.get(f"/api/superadmin/clients/{cid}/overview").json()
    for section in ("invoicing", "hr", "recruitment", "portals"):
        assert section in d
    # Absolute now: once the hosts are split the employee portal is on its
    # own host, and the operator's link has to go there.
    assert d["portals"]["employee"].endswith("/employee-login.html")
    assert d["portals"]["hr"].endswith("/app.html#/hr")
    assert d["portals"]["job_board"] == f"/jobs.html?c={cid}"


def test_client_overview_names_the_doors_once_split(client, account, superadmin, monkeypatch):
    monkeypatch.setenv("PRODUCT_HOSTS", "invoicing=invoice.aniprotech.com,hr=hr.aniprotech.com,employee=employee.aniprotech.com")
    monkeypatch.setenv("APP_BASE_URL", "https://www.aniprotech.com")
    cid = superadmin.get("/api/superadmin/clients").json()[0]["id"]
    d = superadmin.get(f"/api/superadmin/clients/{cid}/overview").json()
    assert d["portals"]["employee"] == "https://employee.aniprotech.com/employee-login.html"
    assert d["portals"]["hr"] == "https://hr.aniprotech.com/app.html#/hr"
    assert d["portals"]["invoicing"] == "https://invoice.aniprotech.com/app.html"


def test_superadmin_endpoints_require_authorisation(client):
    client.post("/api/superadmin/logout")
    assert client.get("/api/superadmin/platform-stats").status_code == 401
    assert client.get("/api/superadmin/clients/1/overview").status_code == 401


def test_client_overview_404s_for_unknown_tenant(superadmin):
    assert superadmin.get("/api/superadmin/clients/999999/overview").status_code == 404
