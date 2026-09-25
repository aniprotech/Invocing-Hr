"""Training partners, through the app: which platforms a business uses,
PDF certificates, reading what came in, and filing what the business checked.

What is read is proven in test_training_import.py. These tests are about
the joins: the business's own staff and courses are what is matched
against, nothing is saved until import, the same certificate is not filed
twice, an assigned course is closed by its certificate, and none of it
crosses a business.
"""
import base64
import csv
import io

import pytest

import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def pdf_url(lines):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    y = 520
    for line in lines:
        c.setFont("Helvetica", 16)
        c.drawCentredString(420, y, line)
        y -= 34
    c.save()
    return "data:application/pdf;base64," + base64.b64encode(buf.getvalue()).decode()


PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
       "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def csv_url(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return "data:text/csv;base64," + base64.b64encode(buf.getvalue().encode()).decode()


def person(tenant, first, last, **kw):
    return make_employee(tenant, first_name=first, last_name=last,
                         email=kw.pop("email", f"{first.lower()}.{last.lower()}@care.test"), **kw)


def certs(tenant):
    return tenant.get("/api/certifications").json()["certifications"]


# --- which platforms ---------------------------------------------------------------
def test_the_platforms_are_listed_with_what_each_offers(tenant):
    got = tenant.get("/api/training/partners").json()
    keys = [p["key"] for p in got["partners"]]
    assert "florence" in keys and "mylearningcloud" in keys and len(keys) == 10
    mlc = next(p for p in got["partners"] if p["key"] == "mylearningcloud")
    assert mlc["api"] == "available" and mlc["site"].startswith("https://") and "match" not in mlc
    assert got["chosen"] == []


def test_a_business_says_which_it_uses(tenant):
    res = tenant.put("/api/training/partners", json={"chosen": ["florence", "caretutor"]})
    assert res.status_code == 200, res.text
    assert res.json()["chosen"] == ["caretutor", "florence"], "kept in the list's own order"
    assert tenant.get("/api/training/partners").json()["chosen"] == ["caretutor", "florence"]


def test_a_platform_it_does_not_know_is_refused(tenant):
    res = tenant.put("/api/training/partners", json={"chosen": ["florence", "moodle"]})
    assert res.status_code == 400 and "moodle" in res.json()["detail"]


# --- a certificate may be a PDF ------------------------------------------------------
def test_a_pdf_certificate_is_kept_and_served_as_a_pdf(tenant):
    emp = person(tenant, "Ann", "Lee")
    res = tenant.post(f"/api/employees/{emp['id']}/certifications",
                      json={"name": "Fire Safety", "document_data": pdf_url(["Fire Safety"])})
    assert res.status_code == 200, res.text
    doc = tenant.get(f"/api/certifications/{res.json()['id']}/document")
    assert doc.status_code == 200 and doc.headers["content-type"] == "application/pdf"
    assert doc.content.startswith(b"%PDF-")


def test_something_calling_itself_a_pdf_that_is_not_is_refused(tenant):
    emp = person(tenant, "Ann", "Lee")
    fake = "data:application/pdf;base64," + base64.b64encode(b"<script>alert(1)</script>").decode()
    res = tenant.post(f"/api/employees/{emp['id']}/certifications", json={"name": "X", "document_data": fake})
    assert res.status_code == 400 and "not one" in res.json()["detail"]


def test_a_picture_of_a_certificate_is_still_fine(tenant):
    emp = person(tenant, "Ann", "Lee")
    res = tenant.post(f"/api/employees/{emp['id']}/certifications", json={"name": "X", "document_data": PNG})
    assert res.status_code == 200, res.text


# --- reading certificates -----------------------------------------------------------
FLORENCE = ["Florence Academy", "Certificate of Completion", "This is to certify that", "Ann Lee",
            "has successfully completed", "Moving and Handling", "Completed on 14/09/2026",
            "Valid until 14/09/2027", "Certificate No: FA-123456"]


def test_certificates_are_read_against_the_business_own_staff(tenant):
    ann = person(tenant, "Ann", "Lee")
    res = tenant.post("/api/training/certificates/read", json={"files": [
        {"name": "ann-mh.pdf", "data": pdf_url(FLORENCE)}]})
    assert res.status_code == 200, res.text
    got = res.json()["certificates"][0]
    assert (got["employee_id"], got["name"], got["issuer"]) == (ann["id"], "Moving and Handling", "Florence Academy")
    assert (got["issued_on"], got["expires_on"], got["reference"]) == ("2026-09-14", "2027-09-14", "FA-123456")
    assert got["file_name"] == "ann-mh.pdf" and got["missing"] == []


def test_reading_saves_nothing(tenant):
    person(tenant, "Ann", "Lee")
    tenant.post("/api/training/certificates/read", json={"files": [{"name": "a.pdf", "data": pdf_url(FLORENCE)}]})
    assert certs(tenant) == []


def test_a_picture_is_accepted_but_said_to_be_unreadable(tenant):
    got = tenant.post("/api/training/certificates/read", json={"files": [{"name": "photo.png", "data": PNG}]}).json()
    c = got["certificates"][0]
    assert c["readable"] is False and "picture" in c["note"]


def test_a_file_that_is_not_a_certificate_is_named_not_fatal(tenant):
    bad = "data:text/plain;base64," + base64.b64encode(b"hello").decode()
    got = tenant.post("/api/training/certificates/read", json={"files": [
        {"name": "notes.txt", "data": bad}, {"name": "good.pdf", "data": pdf_url(FLORENCE)}]}).json()
    assert got["certificates"][0]["problem"] and got["certificates"][1]["name"] == "Moving and Handling"


def test_too_many_at_once_is_refused(tenant):
    files = [{"name": f"{i}.pdf", "data": pdf_url(["x"])} for i in range(26)]
    assert tenant.post("/api/training/certificates/read", json={"files": files}).status_code == 400


def test_a_leaver_is_not_matched(tenant):
    ann = person(tenant, "Ann", "Lee")
    tenant.put(f"/api/employees/{ann['id']}", json={"status": "terminated"})
    got = tenant.post("/api/training/certificates/read", json={"files": [{"name": "a.pdf", "data": pdf_url(FLORENCE)}]}).json()
    assert got["certificates"][0]["employee_id"] is None


# --- reading reports -------------------------------------------------------------------
def test_a_report_is_read_against_the_business_own_staff(tenant):
    ann = person(tenant, "Ann", "Lee")
    res = tenant.post("/api/training/report/read", json={"name": "caretutor.csv", "data": csv_url([
        ["Learner", "Email", "Course", "Completion Date", "Expiry Date"],
        ["Ann Lee", "ann.lee@care.test", "Fire Safety", "14/09/2026", "14/09/2027"],
        ["Zed Nobody", "zed@x.test", "Fire Safety", "01/09/2026", ""]])})
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["rows"][0]["employee_id"] == ann["id"] and got["rows"][0]["issuer"] == "CareTutor"
    assert got["unmatched"] == [{"name": "Zed Nobody", "courses": 1}]
    assert certs(tenant) == [], "reading saves nothing"


def test_a_report_that_cannot_be_read_says_why(tenant):
    res = tenant.post("/api/training/report/read", json={"name": "r.csv", "data": csv_url([["Course", "Date"], ["Fire", "1/1/2026"]])})
    assert res.status_code == 400 and "who each row is about" in res.json()["detail"]
    res = tenant.post("/api/training/report/read", json={"name": "r.xlsx", "data": "data:x;base64," + base64.b64encode(b"not excel").decode()})
    assert res.status_code == 400 and "spreadsheet" in res.json()["detail"]


# --- filing ---------------------------------------------------------------------------------
def item(emp, **kw):
    return dict({"employee_id": emp["id"], "name": "Moving and Handling", "issuer": "Florence Academy",
                 "issued_on": "2026-09-14", "expires_on": "2027-09-14", "reference": "FA-1"}, **kw)


def test_what_was_checked_is_filed_as_a_verified_certification(tenant):
    ann = person(tenant, "Ann", "Lee")
    res = tenant.post("/api/training/import", json={"items": [item(ann, document_data=pdf_url(FLORENCE))]})
    assert res.status_code == 200, res.text
    assert res.json()["created"] == 1
    c = certs(tenant)[0]
    assert (c["employee_id"], c["name"], c["issuer"], c["expires_on"]) == (ann["id"], "Moving and Handling", "Florence Academy", "2027-09-14")
    assert c["added_by"] == "import" and c["verified"] and c["has_document"]


def test_the_same_certificate_is_not_filed_twice(tenant):
    ann = person(tenant, "Ann", "Lee")
    tenant.post("/api/training/import", json={"items": [item(ann)]})
    res = tenant.post("/api/training/import", json={"items": [item(ann, name="moving and handling")]}).json()
    assert res["created"] == 0 and "already has" in res["skipped"][0]["reason"]
    assert len(certs(tenant)) == 1


def test_a_renewal_is_a_new_certificate(tenant):
    ann = person(tenant, "Ann", "Lee")
    tenant.post("/api/training/import", json={"items": [item(ann)]})
    res = tenant.post("/api/training/import", json={"items": [item(ann, issued_on="2027-09-10", expires_on="2028-09-10")]}).json()
    assert res["created"] == 1


def test_one_bad_row_does_not_stop_the_rest(tenant):
    ann = person(tenant, "Ann", "Lee")
    res = tenant.post("/api/training/import", json={"items": [
        item(ann, issued_on="not a date"), {"employee_id": 999999, "name": "X"}, item(ann, name="")  ,
        item(ann, name="Fire Safety")]}).json()
    assert res["created"] == 1
    reasons = " | ".join(s["reason"] for s in res["skipped"])
    assert "not matched" in reasons and "no course" in reasons and len(res["skipped"]) == 3


def test_a_course_that_must_be_renewed_sets_the_expiry(tenant):
    ann = person(tenant, "Ann", "Lee")
    tenant.post("/api/courses", json={"title": "Moving and Handling", "renew_months": 12})
    tenant.post("/api/training/import", json={"items": [item(ann, expires_on="")]})
    assert certs(tenant)[0]["expires_on"] == "2027-09-14"


def test_a_certificate_closes_the_course_the_person_was_assigned(tenant):
    ann = person(tenant, "Ann", "Lee")
    course = tenant.post("/api/courses", json={"title": "Moving and Handling", "renew_months": 12}).json()
    cid = course.get("id") or course.get("course", {}).get("id")
    assert tenant.post(f"/api/courses/{cid}/assign", json={"employee_ids": [ann["id"]]}).status_code == 200
    res = tenant.post("/api/training/import", json={"items": [item(ann)]}).json()
    assert res["courses_completed"] == 1
    with main.SessionLocal() as db:
        a = db.query(models.DBCourseAssignment).filter(models.DBCourseAssignment.employee_id == ann["id"]).first()
        assert (a.status, a.completed_on, a.completed_by, a.expires_on) == ("done", "2026-09-14", "import", "2027-09-14")


def test_nothing_to_import_is_refused(tenant):
    assert tenant.post("/api/training/import", json={"items": []}).status_code == 400


# --- one business at a time ------------------------------------------------------------------
def test_another_business_cannot_file_onto_these_staff_or_see_their_platforms(tenant, client, account):
    ann = person(tenant, "Ann", "Lee")
    tenant.put("/api/training/partners", json={"chosen": ["florence"]})
    other = f"other-{account['email']}"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    assert client.get("/api/training/partners").json()["chosen"] == []
    res = client.post("/api/training/import", json={"items": [item(ann)]}).json()
    assert res["created"] == 0 and "not matched" in res["skipped"][0]["reason"]
    got = client.post("/api/training/certificates/read", json={"files": [{"name": "a.pdf", "data": pdf_url(FLORENCE)}]}).json()
    assert got["certificates"][0]["employee_id"] is None, "another business's staff are not read against"


def test_signed_out_it_answers_nothing(client):
    client.post("/api/client/logout")
    assert client.get("/api/training/partners").status_code == 401
    assert client.post("/api/training/import", json={"items": [{}]}).status_code == 401
