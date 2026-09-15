"""Recognition: one person thanking another in front of everybody.

A shout-out names a person still here, says what they did, and may carry
one of the business's own values. The person is told; a webhook that
wants it hears; the giver can take it back and HR can take it down, but
nobody else can touch it. The analytics say which values are being lived
and who has never been thanked. None of it crosses a business.
"""
import os

os.environ["WEBHOOKS_ASYNC"] = "0"

import pytest

import main
import models
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


def as_hr(client, account):
    main.rate_limiter._hits.clear()
    client.post("/api/employee/auth/logout")
    res = client.post("/api/client/login", json={"email": account["email"], "password": account["password"]})
    assert res.status_code == 200, res.text


def test_a_shout_out_reaches_the_person_and_the_feed(tenant, account):
    ann = person(tenant, first_name="Ann", last_name="Lee")
    bo = person(tenant, first_name="Bo", last_name="Ray")
    as_staff(tenant, ann)
    before = tenant.get("/api/employee/kudos").json()
    assert before["received"] == 0 and before["given"] == 0 and before["values"] == []
    assert [p["name"] for p in before["people"]] == ["Bo Ray"], "the picker is everyone but me"
    res = tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "Stayed late to ship the fix."})
    assert res.status_code == 200, res.text
    given = res.json()
    assert given["from"] == "Ann Lee" and given["to"] == "Bo Ray" and given["mine"] is True and given["value"] == ""
    after = tenant.get("/api/employee/kudos").json()
    assert after["given"] == 1 and after["recent"][0]["id"] == given["id"]

    as_staff(tenant, bo)
    mine = tenant.get("/api/employee/kudos").json()
    assert mine["received"] == 1 and mine["recent"][0]["mine"] is False
    notes = tenant.get("/api/employee/notifications").json()
    titles = [n["title"] for n in (notes if isinstance(notes, list) else notes.get("notifications", []))]
    assert "Ann Lee gave you a shout-out" in titles, titles


def test_what_a_shout_out_must_be(tenant, account):
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    gone = person(tenant, first_name="Gone")
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "left"})
    as_staff(tenant, ann)
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "  "}).status_code == 400
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": ann["id"], "message": "me"}).status_code == 400
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": gone["id"], "message": "bye"}).status_code == 404
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": "x", "message": "bye"}).status_code == 404
    long = "x" * 900
    res = tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": long})
    assert res.status_code == 200 and len(res.json()["message"]) == main.KUDOS_MESSAGE_MAX


def test_values_are_the_business_s_own_words(tenant, account):
    res = tenant.put("/api/kudos/values", json={"values": "Ownership, kindness,, Craft\nOwnership , " + "y" * 80})
    assert res.status_code == 200
    assert res.json()["values"] == ["Ownership", "kindness", "Craft", "y" * 40], "trimmed, deduplicated case-blind, capped"
    assert tenant.get("/api/kudos/values").json()["values"][0] == "Ownership"
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    as_staff(tenant, ann)
    assert tenant.get("/api/employee/kudos").json()["values"][:2] == ["Ownership", "kindness"]
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x", "value": "Speed"}).status_code == 400
    ok = tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x", "value": "KINDNESS"})
    assert ok.status_code == 200 and ok.json()["value"] == "kindness", "spelled the business's way"
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x", "value": ""}).status_code == 200


def test_no_values_means_any_word_or_none(tenant, account):
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    as_staff(tenant, ann)
    ok = tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x", "value": "Whatever"})
    assert ok.status_code == 200 and ok.json()["value"] == "Whatever"


def test_ten_a_day_is_plenty(tenant, account):
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    as_staff(tenant, ann)
    for i in range(main.KUDOS_PER_DAY):
        assert tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": f"thanks {i}"}).status_code == 200
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "one more"}).status_code == 429


def test_the_giver_can_withdraw_and_nobody_else_can(tenant, account):
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    cy = person(tenant, first_name="Cy")
    as_staff(tenant, ann)
    k = tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x"}).json()
    as_staff(tenant, cy)
    assert tenant.delete(f"/api/employee/kudos/{k['id']}").status_code == 404
    as_staff(tenant, bo)
    assert tenant.delete(f"/api/employee/kudos/{k['id']}").status_code == 404, "not even the person it is about"
    as_staff(tenant, ann)
    assert tenant.delete(f"/api/employee/kudos/{k['id']}").status_code == 200
    assert tenant.get("/api/employee/kudos").json()["recent"] == []


def test_hr_sees_all_of_it_and_can_take_one_down(tenant, account):
    ann = person(tenant, first_name="Ann", last_name="Lee")
    bo = person(tenant, first_name="Bo", last_name="Ray")
    as_staff(tenant, ann)
    k = tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "Something unkind"}).json()
    tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "Something kind"})
    as_hr(tenant, account)
    listed = tenant.get("/api/kudos").json()
    assert [x["message"] for x in listed["kudos"]] == ["Something kind", "Something unkind"]
    assert listed["summary"]["this_month"] == 2
    prof = tenant.get(f"/api/employees/{bo['id']}/kudos").json()
    assert prof["received_count"] == 2 and prof["given_count"] == 0 and prof["received"][0]["from"] == "Ann Lee"
    assert tenant.delete(f"/api/kudos/{k['id']}").status_code == 200
    assert tenant.delete(f"/api/kudos/{k['id']}").status_code == 404
    assert [x["message"] for x in tenant.get("/api/kudos").json()["kudos"]] == ["Something kind"]
    logs = tenant.get("/api/audit-logs").json()
    hit = next(l for l in logs if l["action"] == "kudos_removed")
    assert hit["entity_name"] == "Ann Lee to Bo Ray" and hit["details"] == "Something unkind"


def test_the_summary_says_who_is_thanked_and_who_never_is(tenant, account):
    tenant.put("/api/kudos/values", json={"values": "Craft, Care"})
    ann = person(tenant, first_name="Ann", last_name="Lee")
    bo = person(tenant, first_name="Bo", last_name="Ray")
    cy = person(tenant, first_name="Cy", last_name="Dee")
    gone = person(tenant, first_name="Gone", last_name="Away")
    tenant.put(f"/api/employees/{gone['id']}", json={"status": "left"})
    as_staff(tenant, ann)
    tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "a", "value": "Craft"})
    tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "b", "value": "Craft"})
    tenant.post("/api/employee/kudos", json={"to_employee_id": cy["id"], "message": "c", "value": "Care"})
    as_staff(tenant, bo)
    tenant.post("/api/employee/kudos", json={"to_employee_id": ann["id"], "message": "d"})
    as_hr(tenant, account)
    s = tenant.get("/api/hr/analytics").json()["recognition"]
    assert s["this_month"] == 4 and s["total_90d"] == 4
    assert s["people_recognised_pct"] == 100, "everybody still here has been thanked; the leaver does not count"
    assert s["never_recognised"] == []
    assert s["top_recognised"][0] == {"employee_id": bo["id"], "name": "Bo Ray", "count": 2}
    assert s["top_givers"][0] == {"employee_id": ann["id"], "name": "Ann Lee", "count": 3}
    assert s["by_value"] == [{"value": "Craft", "count": 2}, {"value": "Care", "count": 1}]
    assert s["values"] == ["Craft", "Care"]
    dee = person(tenant, first_name="Dee", last_name="New")
    s = tenant.get("/api/hr/analytics").json()["recognition"]
    assert s["people_recognised_pct"] == 75 and s["never_recognised"] == ["Dee New"]


def test_a_webhook_hears_it(tenant, account):
    tenant.post("/api/webhooks", json={"url": "https://a.example/hook", "events": ["kudos.given"]})
    assert "kudos.given" in tenant.get("/api/webhooks").json()["events"]
    ann = person(tenant, first_name="Ann", last_name="Lee")
    bo = person(tenant, first_name="Bo", last_name="Ray")
    as_staff(tenant, ann)
    tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x", "value": "Grit"})
    with main.SessionLocal() as db:
        d = db.query(models.DBWebhookDelivery).filter(models.DBWebhookDelivery.event == "kudos.given").first()
        assert d is not None
        assert '"Grit"' in d.payload and "Bo Ray" in d.payload


def test_nothing_crosses_a_business(tenant, account):
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    as_staff(tenant, ann)
    k = tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x"}).json()
    # The other business: its own values, its own people, none of ours.
    other = f"other-{account['email']}"
    tenant.post("/api/employee/auth/logout")
    main.rate_limiter._hits.clear()
    tenant.post("/api/client/register", json={"email": other, "password": "Passw0rdTest", "company_name": "Other Ltd"})
    tenant.post("/api/client/login", json={"email": other, "password": "Passw0rdTest"})
    theirs = person(tenant, first_name="Their", last_name="Person")
    assert tenant.get("/api/kudos").json()["kudos"] == []
    assert tenant.delete(f"/api/kudos/{k['id']}").status_code == 404
    assert tenant.get(f"/api/employees/{bo['id']}/kudos").status_code == 404
    tenant.put("/api/kudos/values", json={"values": "Theirs"})
    as_staff(tenant, ann)
    mine = tenant.get("/api/employee/kudos").json()
    assert mine["values"] == [] and all(p["id"] != theirs["id"] for p in mine["people"])
    assert tenant.post("/api/employee/kudos", json={"to_employee_id": theirs["id"], "message": "x"}).status_code == 404
    assert [x["id"] for x in mine["recent"]] == [k["id"]]


def test_leaving_takes_the_thanks_with_them(tenant, account):
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    as_staff(tenant, ann)
    tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x"})
    as_hr(tenant, account)
    assert tenant.delete(f"/api/employees/{bo['id']}").status_code == 200
    assert tenant.get("/api/kudos").json()["kudos"] == []


def test_the_operator_counts_it_as_adoption(tenant, account):
    ann = person(tenant, first_name="Ann")
    bo = person(tenant, first_name="Bo")
    as_staff(tenant, ann)
    tenant.post("/api/employee/kudos", json={"to_employee_id": bo["id"], "message": "x"})
    with main.SessionLocal() as db:
        cid = db.query(models.DBClient).filter(models.DBClient.email == account["email"]).first().id
    tenant.post("/api/employee/auth/logout")
    main.rate_limiter._hits.clear()
    res = tenant.post("/api/superadmin/login", json={"identifier": "hello@keyroutes.co", "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    rows = tenant.get("/api/superadmin/hr-adoption").json()
    mine = next(r for r in rows["businesses"] if r["client_id"] == cid)
    assert mine["features"]["kudos"] == 1 and "kudos" in rows["feature_keys"]
