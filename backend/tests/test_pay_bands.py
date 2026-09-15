"""What the company pays for a level, and where everybody sits.

A band per level, per year: the least, the middle, the most. Against it
each person has a compa-ratio and a position - below, within, above - and
the pay review is everybody on one page with that, when their pay last
moved, and their latest rating, and a way to change several salaries with
one effective date. Pay on the profile is per period, so it is
annualised by how often it is paid before it meets the band. Staff see
their own band only if the business switches that on.
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
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": EMP_PASSWORD})
    assert res.status_code == 200, res.text


def band(tenant, level, lo, hi, mid=None, **over):
    payload = {"min": lo, "max": hi}
    if mid is not None:
        payload["mid"] = mid
    payload.update(over)
    res = tenant.put(f"/api/pay-bands/{level}", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def row_for(tenant, emp_id):
    return next(r for r in tenant.get("/api/pay-review").json()["people"] if r["employee_id"] == emp_id)


# --- bands -----------------------------------------------------------------------

def test_a_band_is_set_per_level_with_the_middle_worked_out(tenant):
    b = band(tenant, "L3", 30000, 50000)
    assert b["level"] == "L3" and b["mid"] == 40000.0 and b["currency"]
    b = band(tenant, "l3", 32000, 52000, mid=44000)
    assert b["mid"] == 44000.0
    levels = {l["level"]: l for l in tenant.get("/api/pay-bands").json()["levels"]}
    assert len(levels) == 8 and levels["L3"]["band"]["max"] == 52000.0 and levels["L1"]["band"] is None


def test_nonsense_bands_are_refused(tenant):
    assert tenant.put("/api/pay-bands/L9", json={"min": 1, "max": 2}).status_code == 404
    assert tenant.put("/api/pay-bands/L2", json={"min": 50000, "max": 30000}).status_code == 400
    assert tenant.put("/api/pay-bands/L2", json={"min": 30000, "max": 50000, "mid": 60000}).status_code == 400
    assert tenant.put("/api/pay-bands/L2", json={"min": "lots", "max": 50000}).status_code == 400
    assert tenant.put("/api/pay-bands/L2", json={"max": 50000}).status_code == 400
    assert tenant.delete("/api/pay-bands/L2").status_code == 404
    band(tenant, "L2", 1, 2)
    assert tenant.delete("/api/pay-bands/L2").status_code == 200


# --- where people sit --------------------------------------------------------------

def test_pay_is_annualised_by_how_often_it_is_paid(tenant):
    band(tenant, "L3", 30000, 50000)
    monthly = person(tenant, level="L3", salary=3000.0, pay_frequency="monthly")
    weekly = person(tenant, level="L3", salary=1000.0, pay_frequency="weekly")
    hourly = person(tenant, level="L3", salary=0.0, hourly_rate=20.0)
    assert row_for(tenant, monthly["id"])["annual"] == 36000.0
    assert row_for(tenant, weekly["id"])["annual"] == 52000.0
    assert row_for(tenant, hourly["id"])["annual"] == 38400.0        # 160 hours a month


def test_compa_ratio_and_position(tenant):
    band(tenant, "L3", 30000, 50000)      # mid 40000
    low = person(tenant, first_name="Low", level="L3", salary=2000.0)       # 24000
    fair = person(tenant, first_name="Fair", level="L3", salary=3500.0)     # 42000
    high = person(tenant, first_name="High", level="L3", salary=5000.0)     # 60000
    none = person(tenant, first_name="None", level="L5", salary=4000.0)     # no band
    r = row_for(tenant, low["id"])
    assert r["position"] == "below" and r["compa_ratio"] == 0.6 and r["pct_through_band"] == -30
    r = row_for(tenant, fair["id"])
    assert r["position"] == "within" and r["compa_ratio"] == 1.05 and r["pct_through_band"] == 60
    assert row_for(tenant, high["id"])["position"] == "above"
    assert row_for(tenant, none["id"])["position"] == "no_band" and row_for(tenant, none["id"])["compa_ratio"] is None
    out = tenant.get("/api/pay-review").json()
    assert [p["name"].split()[0] for p in out["people"]][:2] == ["Low", "High"]    # the ones to look at first
    assert out["totals"]["below_band"] == 1 and out["totals"]["above_band"] == 1 and out["totals"]["no_band"] == 1
    assert out["totals"]["annual_payroll"] == 24000 + 42000 + 60000 + 48000
    levels = {l["level"]: l for l in tenant.get("/api/pay-bands").json()["levels"]}
    assert levels["L3"]["headcount"] == 3 and levels["L3"]["below"] == 1 and levels["L3"]["above"] == 1


def test_the_review_shows_when_pay_last_moved_and_the_latest_rating(tenant):
    emp = person(tenant, level="L3", salary=3000.0, start_date="2024-01-01")
    r = row_for(tenant, emp["id"])
    assert r["last_pay_change"] == "" and r["months_since_change"] >= 12
    tenant.put(f"/api/employees/{emp['id']}", json={"salary": 3200, "effective_on": "2026-06-01"})
    assert row_for(tenant, emp["id"])["last_pay_change"] == "2026-06-01"
    c = tenant.post("/api/review-cycles", json={"name": "H1"}).json()
    tenant.post(f"/api/review-cycles/{c['id']}/open")
    rid = next(x for x in tenant.get(f"/api/review-cycles/{c['id']}").json()["reviews"] if x["employee_id"] == emp["id"])["id"]
    tenant.post(f"/api/reviews/{rid}/manager", json={"answers": [{"rating": 4}] * 6, "rating": 4, "summary": "Good"})
    out = tenant.get("/api/pay-review").json()
    assert out["rating_cycle"] == "H1"
    assert row_for(tenant, emp["id"])["rating"] == 4


def test_leavers_are_not_in_the_review(tenant):
    gone = person(tenant, level="L3", salary=3000.0)
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "terminated"})
    assert not any(p["employee_id"] == gone["id"] for p in tenant.get("/api/pay-review").json()["people"])


# --- applying changes --------------------------------------------------------------------

def test_several_salaries_change_on_one_date_and_everybody_is_told(tenant):
    a = person(tenant, first_name="Ann", level="L3", salary=3000.0)
    b = person(tenant, first_name="Bob", level="L3", salary=3000.0)
    res = tenant.post("/api/pay-review", json={"effective_on": "2026-10-01", "note": "Annual review", "changes": [
        {"employee_id": a["id"], "salary": 3300},
        {"employee_id": b["id"], "salary": 3000},          # unchanged: skipped
    ]})
    assert res.status_code == 200, res.text
    assert res.json()["applied"] == 1 and res.json()["changes"][0]["was"] == 3000.0
    assert tenant.get(f"/api/employees/{a['id']}").json()["salary"] == 3300.0
    hist = tenant.get(f"/api/employees/{a['id']}/history").json()["history"]
    assert hist[0]["kind"] == "pay_change" and hist[0]["effective_on"] == "2026-10-01" and hist[0]["note"] == "Annual review"
    assert [h["kind"] for h in tenant.get(f"/api/employees/{b['id']}/history").json()["history"]] == ["joined"]
    as_staff(tenant, a)
    titles = [n["title"] for n in tenant.get("/api/employee/notifications").json()["notifications"]]
    assert "Your pay is changing" in titles


def test_a_bad_change_stops_the_whole_batch(tenant):
    a = person(tenant, level="L3", salary=3000.0)
    res = tenant.post("/api/pay-review", json={"changes": [{"employee_id": a["id"], "salary": -5}]})
    assert res.status_code == 400
    res = tenant.post("/api/pay-review", json={"changes": [{"employee_id": a["id"], "salary": 3300}, {"employee_id": 999999, "salary": 1}]})
    assert res.status_code == 404
    assert tenant.get(f"/api/employees/{a['id']}").json()["salary"] == 3000.0, "nothing applied when one is refused"
    assert tenant.post("/api/pay-review", json={"changes": []}).status_code == 400


# --- what staff see -----------------------------------------------------------------------------

def test_staff_see_their_band_only_when_the_business_says_so(tenant, account):
    band(tenant, "L3", 30000, 50000)
    emp = person(tenant, level="L3", salary=3500.0)
    as_staff(tenant, emp)
    assert tenant.get("/api/employee/pay-band").json() == {"visible": False}
    tenant.post("/api/employee/auth/logout")
    tenant.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert tenant.put("/api/pay-bands-visibility", json={"visible": True}).json()["visible_to_staff"] is True
    assert tenant.get("/api/pay-bands").json()["visible_to_staff"] is True
    as_staff(tenant, emp)
    mine = tenant.get("/api/employee/pay-band").json()
    assert mine["visible"] and mine["band"]["min"] == 30000.0 and mine["position"] == "within" and mine["pct_through_band"] == 60
    # Never anybody else's.
    assert "employee_id" not in mine


def test_another_business_has_its_own_bands(tenant, account):
    band(tenant, "L3", 30000, 50000)
    person(tenant, level="L3", salary=3000.0)         # somebody to leak, if it leaked
    other = f"other-{account['email']}"
    tenant.post("/api/client/logout")
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    levels = {l["level"]: l for l in tenant.get("/api/pay-bands").json()["levels"]}
    assert levels["L3"]["band"] is None
    assert tenant.get("/api/pay-review").json()["people"] == []


def test_analytics_carries_the_pay_block(tenant):
    band(tenant, "L3", 30000, 50000)
    person(tenant, level="L3", salary=2000.0)
    a = tenant.get("/api/hr/analytics").json()["pay"]
    assert a["below_band"] == 1 and a["annual_payroll"] == 24000.0 and a["average_compa_ratio"] == 0.6
