"""Job boards: the XML feed a board pulls on its own, and structured data
on the careers page that Google for Jobs reads on its own - the two ways
in without needing a board's own approval first.
"""
import re

import pytest

import main
from conftest import make_employee


@pytest.fixture(autouse=True)
def _clear_limits():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def dept(tenant):
    return tenant.post("/api/departments", json={"name": "Care"}).json()


def an_open_job(tenant, **kw):
    fields = dict(title="Support Worker", location="Leeds", work_mode="onsite",
                 employment_type="full_time", status="open",
                 description="Help people at home.", requirements="A driving licence.",
                 salary_min=24000, salary_max=27000, salary_currency="GBP")
    fields.update(kw)
    res = tenant.post("/api/recruitment/jobs", json=fields)
    assert res.status_code == 200, res.text
    return res.json()


def client_id_of(tenant):
    row = tenant.get("/api/client/me").json()
    return row["id"]


def feed_xml(tenant, cid=None):
    cid = cid or client_id_of(tenant)
    res = tenant.get(f"/api/public/jobs/{cid}/feed.xml")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("application/xml")
    return res.text


# --- the feed --------------------------------------------------------------------
def test_the_feed_is_well_formed_xml_with_the_indeed_wrapper(tenant):
    an_open_job(tenant)
    xml = feed_xml(tenant)
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<source>" in xml and "</source>" in xml
    import xml.etree.ElementTree as ET
    ET.fromstring(xml)  # raises if not well-formed


def test_an_open_job_is_in_the_feed_with_the_fields_indeed_asks_for(tenant):
    job = an_open_job(tenant)
    xml = feed_xml(tenant)
    assert f"<title>{job['title']}</title>" in xml
    assert f"<referencenumber>{job['reference']}</referencenumber>" in xml
    assert f"<requisitionid>{job['reference']}</requisitionid>" in xml
    assert "<city>Leeds</city>" in xml
    assert "<jobtype>Full-time</jobtype>" in xml
    assert "Help people at home." in xml and "A driving licence." in xml
    assert "24000 - 27000 GBP" in xml


def test_a_draft_job_is_not_in_the_feed(tenant):
    an_open_job(tenant, title="Still drafting", status="draft")
    assert "Still drafting" not in feed_xml(tenant)


def test_a_closed_job_is_not_in_the_feed(tenant):
    job = an_open_job(tenant, title="Filled role")
    res = tenant.put(f"/api/recruitment/jobs/{job['id']}", json={"title": "Filled role", "status": "closed"})
    assert res.status_code == 200, res.text
    assert "Filled role" not in feed_xml(tenant)


def test_a_job_past_its_closing_date_drops_out_on_its_own(tenant):
    an_open_job(tenant, title="Expired role", closing_date="2020-01-01")
    assert "Expired role" not in feed_xml(tenant)


def test_a_remote_job_says_so(tenant):
    an_open_job(tenant, work_mode="remote")
    assert "<remotetype>Fully remote</remotetype>" in feed_xml(tenant)


def test_hidden_salary_is_not_in_the_feed(tenant):
    an_open_job(tenant, show_salary=False)
    assert "<salary>" not in feed_xml(tenant)


def test_special_characters_do_not_break_the_xml(tenant):
    an_open_job(tenant, title="R&D Lead <Senior>")
    xml = feed_xml(tenant)
    import xml.etree.ElementTree as ET
    ET.fromstring(xml)  # would raise on a bare & or <
    assert "&amp;" in xml


def test_a_department_becomes_a_category(tenant, dept):
    an_open_job(tenant, department_id=dept["id"])
    assert "<category>Care</category>" in feed_xml(tenant)


def test_an_unknown_company_reference_is_404(tenant):
    assert tenant.get("/api/public/jobs/999999/feed.xml").status_code == 404


def test_a_business_with_no_open_roles_still_gets_valid_empty_xml(tenant):
    xml = feed_xml(tenant)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    assert root.tag == "source" and len(root) == 0


def test_another_business_never_sees_these_jobs_in_its_own_feed(tenant, client, account):
    an_open_job(tenant, title="Tenant One Role")
    other = f"other-{account['email']}"
    client.post("/api/client/logout")
    client.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    client.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    other_id = client.get("/api/client/me").json()["id"]
    assert "Tenant One Role" not in feed_xml(client, other_id)


def test_the_feed_needs_no_session_at_all(tenant, client):
    """A board fetching it on a schedule is never signed in."""
    cid = client_id_of(tenant)
    tenant.post("/api/client/logout") if False else None  # tenant stays signed in for other assertions
    an_open_job(tenant)
    res = client.get(f"/api/public/jobs/{cid}/feed.xml")  # client: a fresh, signed-out session
    assert res.status_code == 200 and res.text.strip().startswith("<?xml")


# --- what the Recruitment screen is told -----------------------------------------------
def test_the_settings_route_gives_the_feed_url_and_every_board(tenant):
    an_open_job(tenant)
    res = tenant.get("/api/job-board/settings")
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["feed_url"].endswith("/feed.xml") and "jobs" not in got["feed_url"].split("/")[-2]
    assert got["open_jobs"] == 1
    keys = {b["key"] for b in got["boards"]}
    assert {"indeed", "google", "ziprecruiter", "adzuna", "linkedin"} <= keys


def test_indeed_is_honest_about_needing_a_partner_agreement_for_its_own_api(tenant):
    indeed = next(b for b in tenant.get("/api/job-board/settings").json()["boards"] if b["key"] == "indeed")
    assert indeed["method"] == "feed"
    note = indeed["note"].lower()
    assert "approve this product as a partner" in note
    assert "not something switched on from here" in note


def test_google_for_jobs_needs_nothing_added(tenant):
    google = next(b for b in tenant.get("/api/job-board/settings").json()["boards"] if b["key"] == "google")
    assert google["method"] == "automatic" and google["add_url"] == ""


def test_linkedin_is_honest_about_being_manual(tenant):
    li = next(b for b in tenant.get("/api/job-board/settings").json()["boards"] if b["key"] == "linkedin")
    assert li["method"] == "manual"


def test_job_board_settings_needs_a_session(client):
    client.post("/api/client/logout")
    assert client.get("/api/job-board/settings").status_code == 401


# --- the public careers page carries what google for jobs needs -------------------------
def test_the_public_job_board_carries_a_posted_date(tenant):
    an_open_job(tenant)
    listing = tenant.get(f"/api/public/jobs/{client_id_of(tenant)}").json()["jobs"][0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", listing["posted_on"])
