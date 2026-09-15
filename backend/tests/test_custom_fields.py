"""The three things about a person no product thought of.

A field is named once per business and typed - words, a number, a date, a
choice, yes or no - and appears on every profile. Values are checked
against the kind, go out in the CSV and the person's export, come back in
with the file, and are shown to the person only if the field says so.
"""
import pytest

import main
from conftest import make_employee

EMP_PASSWORD = "EmpPass123"


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def person(tenant, **kw):
    kw.setdefault("password", EMP_PASSWORD)
    return make_employee(tenant, **kw)


def as_staff(client, emp):
    main.rate_limiter._hits.clear()
    client.post("/api/client/logout")
    res = client.post("/api/employee/auth/login", json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def field(tenant, label, kind="text", **over):
    payload = {"label": label, "kind": kind}
    payload.update(over)
    res = tenant.post("/api/custom-fields", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def custom_of(tenant, emp_id):
    return {f["key"]: f["value"] for f in tenant.get(f"/api/employees/{emp_id}").json()["custom_fields"]}


def test_a_field_gets_a_key_from_its_label_and_keys_stay_unique(tenant):
    a = field(tenant, "Locker number")
    b = field(tenant, "Locker  Number!")
    assert a["key"] == "locker_number" and b["key"] == "locker_number_2"
    assert [f["key"] for f in tenant.get("/api/custom-fields").json()["fields"]] == ["locker_number", "locker_number_2"]


def test_kinds_are_checked_and_a_choice_needs_choices(tenant):
    assert tenant.post("/api/custom-fields", json={"label": "X", "kind": "colour"}).status_code == 400
    assert tenant.post("/api/custom-fields", json={"label": "Shirt", "kind": "choice", "choices": ["M"]}).status_code == 400
    f = field(tenant, "Shirt size", "choice", choices="S, M, L")
    assert f["choices"] == ["S", "M", "L"]
    assert tenant.post("/api/custom-fields", json={"label": " "}).status_code == 400


def test_values_are_checked_against_the_kind(tenant):
    field(tenant, "Locker", "number")
    field(tenant, "Licence expires", "date")
    field(tenant, "Shirt size", "choice", choices=["S", "M", "L"])
    field(tenant, "Drives", "bool")
    field(tenant, "Notes")
    emp = person(tenant)
    ok = tenant.put(f"/api/employees/{emp['id']}", json={"custom": {"locker": "12", "licence_expires": "2027-01-31",
                                                                     "shirt_size": "m", "drives": "Yes", "notes": "Left-handed"}})
    assert ok.status_code == 200, ok.text
    assert custom_of(tenant, emp["id"]) == {"locker": "12", "licence_expires": "2027-01-31", "shirt_size": "M",
                                            "drives": "yes", "notes": "Left-handed"}
    for bad in ({"locker": "twelve"}, {"licence_expires": "soon"}, {"shirt_size": "XXL"}, {"drives": "maybe"}):
        res = tenant.put(f"/api/employees/{emp['id']}", json={"custom": bad})
        assert res.status_code == 400, bad
    # Only the keys sent change; an unknown key is ignored.
    tenant.put(f"/api/employees/{emp['id']}", json={"custom": {"locker": "14", "nonsense": "x"}})
    got = custom_of(tenant, emp["id"])
    assert got["locker"] == "14" and got["notes"] == "Left-handed"


def test_a_required_field_cannot_be_blanked(tenant):
    field(tenant, "Clearance", required=True)
    emp = person(tenant)
    assert tenant.put(f"/api/employees/{emp['id']}", json={"custom": {"clearance": ""}}).status_code == 400
    assert tenant.put(f"/api/employees/{emp['id']}", json={"custom": {"clearance": "SC"}}).status_code == 200
    # A person can be edited without touching the field at all.
    assert tenant.put(f"/api/employees/{emp['id']}", json={"phone": "0123"}).status_code == 200


def test_a_field_can_be_set_on_the_hire_and_edited_but_not_retyped(tenant):
    f = field(tenant, "Locker", "number")
    res = tenant.post("/api/employees", json={"first_name": "Nia", "last_name": "New", "email": f"nia-{f['id']}@example.com",
                                              "custom": {"locker": "7"}})
    assert res.status_code == 200, res.text
    emp_id = res.json()["id"]
    assert custom_of(tenant, emp_id)["locker"] == "7"
    assert tenant.put(f"/api/custom-fields/{f['id']}", json={"kind": "text"}).status_code == 409
    assert tenant.put(f"/api/custom-fields/{f['id']}", json={"label": "Locker no.", "shown_to_staff": True}).json()["label"] == "Locker no."
    assert tenant.delete(f"/api/custom-fields/{f['id']}").status_code == 200
    assert custom_of(tenant, emp_id) == {}


def test_staff_see_only_what_is_shown_to_them(tenant):
    field(tenant, "Locker", shown_to_staff=True)
    field(tenant, "Clearance", shown_to_staff=False)
    emp = person(tenant)
    tenant.put(f"/api/employees/{emp['id']}", json={"custom": {"locker": "3", "clearance": "SC"}})
    as_staff(tenant, emp)
    mine = tenant.get("/api/employee/profile").json()["custom_fields"]
    assert [(f["label"], f["value"]) for f in mine] == [("Locker", "3")]
    assert "Clearance" not in tenant.get("/api/employee/profile").text
    # The person's own export has everything held about them.
    assert tenant.get("/api/employee/my-data").json()["profile"]["custom_fields"] == {"Locker": "3", "Clearance": "SC"}


def test_values_go_out_in_the_csv_and_come_back_in(tenant):
    field(tenant, "Locker", "number")
    emp = person(tenant, first_name="Ann", last_name="Lee")
    tenant.put(f"/api/employees/{emp['id']}", json={"custom": {"locker": "9"}})
    csv = tenant.get("/api/people/export.csv").text
    assert csv.splitlines()[0].endswith(",status,custom:locker")
    assert any(l.startswith("Ann,Lee,") and l.endswith(",9") for l in csv.splitlines())
    edited = csv.replace(",9", ",11")
    out = tenant.post("/api/people/import", json={"csv": edited}).json()
    assert out["summary"]["update"] >= 1
    assert custom_of(tenant, emp["id"])["locker"] == "11"


def test_another_business_has_its_own_fields(tenant, account):
    f = field(tenant, "Locker")
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert tenant.get("/api/custom-fields").json()["fields"] == []
    assert tenant.delete(f"/api/custom-fields/{f['id']}").status_code == 404
