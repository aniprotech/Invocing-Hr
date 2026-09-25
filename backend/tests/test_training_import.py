"""Reading certificates and training reports from the care platforms.

Certificates are made here as real PDFs, laid out the way these platforms
lay theirs out, so what is tested is what happens to an actual file - not
to text typed into a test.
"""
import csv
import io
from datetime import date, datetime

import pytest

import training_import as T


STAFF = [
    {"id": 1, "first_name": "Ann", "last_name": "Lee", "email": "ann.lee@care.test", "employee_id": "EMP-0001"},
    {"id": 2, "first_name": "Joann", "last_name": "Lee", "email": "joann@care.test", "employee_id": "EMP-0002"},
    {"id": 3, "first_name": "Mary Ann", "last_name": "Lee", "email": "maryann@care.test", "employee_id": "EMP-0003"},
    {"id": 4, "first_name": "John", "last_name": "Smith", "email": "john1@care.test", "employee_id": "EMP-0004"},
    {"id": 5, "first_name": "John", "last_name": "Smith", "email": "john2@care.test", "employee_id": "EMP-0005"},
    {"id": 6, "first_name": "Priya", "last_name": "O'Brien", "email": "priya@care.test", "employee_id": "EMP-0006"},
]


def staff():
    return T.Staff([dict(p) for p in STAFF])


def pdf(lines):
    """A one-page certificate, with these lines on it."""
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
    return buf.getvalue()


FLORENCE = ["Florence Academy", "Certificate of Completion", "This is to certify that", "Priya O'Brien",
            "has successfully completed", "Moving and Handling", "Completed on 14/09/2026",
            "Valid until 14/09/2027", "Certificate No: FA-123456"]


# --- the platforms --------------------------------------------------------------
def test_every_platform_named_in_the_list_is_there():
    names = {p["name"] for p in T.PARTNERS}
    for expected in ("Flourish - Click Learning", "CareTutor", "My Learning Cloud", "EduCare",
                     "Children's Homes Training Hub", "Caredemy", "Florence Academy", "Custoris Academy",
                     "NHS e-Learning for Healthcare", "Skills for Care"):
        assert expected in names


def test_what_each_platform_offers_is_stated_not_assumed():
    by = T.PARTNERS_BY_KEY
    assert by["mylearningcloud"]["api"] == "available" and by["caretutor"]["api"] == "available"
    assert by["flourish"]["api"] == "planned"
    assert by["florence"]["api"] == "none published" and "Excel" in by["florence"]["export"]
    assert by["custoris"]["site"] == "" and "check them" in by["custoris"]["api_note"]


def test_a_certificate_names_its_platform():
    assert T.partner_in("Florence Academy certificate")["key"] == "florence"
    assert T.partner_in("elearning for healthcare")["key"] == "elfh"
    assert T.partner_in("Click Learning by Flourish")["key"] == "flourish"


def test_florence_the_person_is_not_florence_the_academy():
    assert T.partner_in("Certificate awarded to Florence Nightingale") is None


def test_a_file_name_is_enough_to_say_whose_export_it_is():
    assert T.partner_in_filename("florence-export.xlsx")["key"] == "florence"
    assert T.partner_in_filename("MyLearningCloud_Matrix.xlsx")["key"] == "mylearningcloud"
    assert T.partner_in_filename("training.csv") is None


def test_a_skills_for_care_logo_does_not_hide_who_issued_it():
    """CareTutor prints the Skills for Care logo on its certificates."""
    assert T.partner_in("CareTutor ... endorsed by Skills for Care")["key"] == "caretutor"
    assert T.partner_in("Skills for Care endorsed")["key"] == "skillsforcare"


# --- dates ---------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("14/09/2026", date(2026, 9, 14)),
    ("14.09.26", date(2026, 9, 14)),
    ("14-09-2026", date(2026, 9, 14)),
    ("2026-09-14", date(2026, 9, 14)),
    ("14 September 2026", date(2026, 9, 14)),
    ("14th of September, 2026", date(2026, 9, 14)),
    ("Sep 14, 2026", date(2026, 9, 14)),
    ("03/04/2026", date(2026, 4, 3)),        # day first, as the UK writes it
    ("14/09/2026 00:00", date(2026, 9, 14)),
])
def test_dates_are_read_the_uk_way(text, expected):
    assert T.parse_date(text) == expected


def test_a_date_that_does_not_exist_is_not_invented():
    assert T.parse_date("31/02/2026") is None
    assert T.parse_date("not a date") is None


def test_excel_cells_and_serial_numbers():
    assert T.parse_date(datetime(2026, 9, 14, 10, 0)) == date(2026, 9, 14)
    assert T.parse_date(46279) == date(2026, 9, 14)       # Excel's day number
    assert T.parse_date(12) is None                        # a count, not a date


# --- who it belongs to ------------------------------------------------------------
def test_staff_are_found_by_email_number_or_name():
    s = staff()
    assert s.find(email="ANN.LEE@care.test")["id"] == 1
    assert s.find(code="emp-0002")["id"] == 2
    assert s.find(name="ann lee")["id"] == 1
    assert s.find(name="Lee, Ann")["id"] == 1, "surname first, as reports often write it"
    assert s.find(first="Priya", last="O'Brien")["id"] == 6


def test_two_people_with_one_name_are_never_guessed_between():
    assert staff().find(name="John Smith") is None
    assert staff().find(name="John Smith", email="john2@care.test")["id"] == 5


def test_a_name_inside_a_longer_name_is_not_a_match():
    s = staff()
    assert s.in_text("This certifies that Joann Lee has completed")["id"] == 2
    assert s.in_text("This certifies that Mary Ann Lee has completed")["id"] == 3
    assert s.in_text("Ann Lee has completed")["id"] == 1


def test_a_certificate_naming_two_people_is_nobodys():
    assert staff().in_text("Ann Lee and Priya O'Brien attended") is None


# --- certificates --------------------------------------------------------------------
def test_a_florence_certificate_is_read_whole():
    got = T.read_certificate(T.pdf_text(pdf(FLORENCE)), staff())
    assert got["employee_id"] == 6 and got["employee_name"] == "Priya O'Brien"
    assert got["name"] == "Moving and Handling"
    assert got["issuer"] == "Florence Academy" and got["partner"] == "florence"
    assert (got["issued_on"], got["expires_on"]) == ("2026-09-14", "2027-09-14")
    assert got["reference"] == "FA-123456"
    assert got["missing"] == [] and got["readable"]


def test_an_elfh_certificate_with_the_course_on_the_same_line():
    lines = ["elearning for healthcare", "Certificate of completion", "Ann Lee",
             "has completed Safeguarding Adults Level 2 on 3 March 2026"]
    got = T.read_certificate(T.pdf_text(pdf(lines)), staff())
    assert (got["employee_id"], got["name"], got["issued_on"], got["expires_on"]) == \
        (1, "Safeguarding Adults Level 2", "2026-03-03", "")
    assert got["partner"] == "elfh"


def test_a_course_the_business_already_runs_is_named_its_way():
    lines = ["EduCare", "Ann Lee", "Awarded for completing", "Infection Prevention & Control (IPC)",
             "Date: 01/08/2026", "Renewal due: 01/08/2027"]
    got = T.read_certificate(T.pdf_text(pdf(lines)), staff(), course_titles=["Infection Prevention & Control"])
    assert got["name"] == "Infection Prevention & Control"
    assert (got["issued_on"], got["expires_on"]) == ("2026-08-01", "2027-08-01")


def test_an_expiry_printed_before_the_completion_is_still_the_expiry():
    """EduCare-style: "Expiry Date" above "Date Completed". Both labels say
    date; only the word expiry tells them apart."""
    lines = ["EduCare", "Ann Lee", "has completed", "Safeguarding Children",
             "Expiry Date: 01/01/2027", "Date Completed: 01/01/2026"]
    got = T.read_certificate(T.pdf_text(pdf(lines)), staff())
    assert (got["issued_on"], got["expires_on"]) == ("2026-01-01", "2027-01-01")


def test_two_bare_dates_are_the_completion_then_the_expiry():
    lines = ["CareTutor", "Joann Lee", "has completed", "Fire Safety", "12/01/2026", "12/01/2027"]
    got = T.read_certificate(T.pdf_text(pdf(lines)), staff())
    assert (got["issued_on"], got["expires_on"]) == ("2026-01-12", "2027-01-12")


def test_what_could_not_be_read_is_named():
    got = T.read_certificate(T.pdf_text(pdf(["Some Training Ltd", "Well done!"])), staff())
    assert got["employee_id"] is None
    assert got["missing"] == ["who it belongs to", "the course", "the date it was completed"]


def test_a_scanned_picture_has_no_words_and_says_so():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(50, 50, 200, 200, fill=1)      # a picture, no text
    c.save()
    got = T.read_certificate(T.pdf_text(buf.getvalue()), staff())
    assert got["readable"] is False


def test_a_file_that_is_not_a_pdf_reads_as_nothing_rather_than_breaking():
    assert T.pdf_text(b"this is not a pdf") == ""


# --- training reports ---------------------------------------------------------------
def csv_bytes(rows):
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def xlsx_bytes(rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_a_report_with_one_row_per_course():
    data = csv_bytes([
        ["Learner", "Email", "Course", "Completion Date", "Expiry Date", "Status"],
        ["Ann Lee", "ann.lee@care.test", "Fire Safety", "14/09/2026", "14/09/2027", "Completed"],
        ["Joann Lee", "joann@care.test", "Moving and Handling", "", "", "In progress"],
        ["Zara Stone", "zara@elsewhere.test", "Fire Safety", "01/09/2026", "", "Passed"],
        ["Priya O'Brien", "priya@care.test", "Fire Safety", "10/09/2026", "", "Failed"],
    ])
    got = T.read_training_report("caretutor-report.csv", data, staff())
    assert got["shape"] == "one row per course"
    assert len(got["rows"]) == 1
    row = got["rows"][0]
    assert (row["employee_id"], row["name"], row["issued_on"], row["expires_on"]) == (1, "Fire Safety", "2026-09-14", "2027-09-14")
    assert got["skipped"] == 2, "the course still in progress, and the one failed on a date"
    assert all(r["employee_id"] != 6 for r in got["rows"]), "a failed attempt is not a completion"
    assert got["unmatched"] == [{"name": "Zara Stone", "courses": 1}]
    assert got["partner"] == "caretutor"


def test_a_training_matrix_one_column_per_course():
    data = xlsx_bytes([
        ["Staff Name", "Department", "Moving and Handling", "Fire Safety", "Home care", "Compliance %"],
        ["Ann Lee", "Care", datetime(2026, 3, 1), "Not started", datetime(2026, 5, 2), 67],
        ["Lee, Joann", "Night", datetime(2026, 4, 1), datetime(2026, 4, 2), None, 100],
    ])
    got = T.read_training_report("florence-export.xlsx", data, staff())
    assert got["shape"] == "training matrix" and got["partner"] == "florence"
    pairs = {(r["employee_id"], r["name"], r["issued_on"]) for r in got["rows"]}
    assert pairs == {(1, "Moving and Handling", "2026-03-01"), (1, "Home care", "2026-05-02"),
                     (2, "Moving and Handling", "2026-04-01"), (2, "Fire Safety", "2026-04-02")}
    assert got["skipped"] == 1, "'Not started' is not a completion"


def test_a_course_date_column_is_not_taken_for_the_course():
    data = csv_bytes([
        ["Email", "Course Completion Date", "Course"],
        ["ann.lee@care.test", "2026-09-01", "Food Hygiene"],
    ])
    rows = T.read_training_report("r.csv", data, staff())["rows"]
    assert rows and rows[0]["name"] == "Food Hygiene" and rows[0]["issued_on"] == "2026-09-01"


def test_first_and_last_name_columns():
    data = csv_bytes([["First Name", "Surname", "Module", "Date Completed"],
                      ["Priya", "O'Brien", "Dysphagia", "02/02/2026"]])
    rows = T.read_training_report("r.csv", data, staff())["rows"]
    assert rows[0]["employee_id"] == 6


def test_the_business_spelling_of_a_course_is_kept():
    data = csv_bytes([["Name", "Course", "Completed"], ["Ann Lee", "fire  SAFETY", "01/01/2026"]])
    rows = T.read_training_report("r.csv", data, staff(), course_titles=["Fire Safety"])["rows"]
    assert rows[0]["name"] == "Fire Safety"


def test_a_semicolon_csv_from_excel_in_another_locale():
    data = "Name;Course;Completed\nAnn Lee;First Aid;05/05/2026\n".encode("utf-8")
    rows = T.read_training_report("r.csv", data, staff())["rows"]
    assert rows and rows[0]["name"] == "First Aid"


def test_a_report_with_no_person_column_says_why():
    with pytest.raises(ValueError, match="who each row is about"):
        T.read_training_report("r.csv", csv_bytes([["Course", "Date"], ["Fire", "01/01/2026"]]), staff())


def test_the_old_excel_format_is_asked_for_again():
    with pytest.raises(ValueError, match="xlsx or .csv"):
        T.read_training_report("old.xls", b"\xd0\xcf\x11\xe0", staff())
