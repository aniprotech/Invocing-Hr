"""The password-reset email reaches the person, whatever the business did
with its own email.

The reset was sent as the business's mail, so it went through the business's
own Gmail or mail server when it had one. When that connection had lapsed -
which is when people get locked out and cannot reconnect it - the reset
failed, nothing recorded it, and the health check (which tests the
platform's connection) still said email was ready. Team members, who sign in
on the same page, were never sent a link at all.
"""
import re
import uuid

import pytest

import main
import models
from test_password_reset import _email_can_send  # noqa: F401 - the platform can send
from test_team import invite, set_their_password, sign_in_as


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


@pytest.fixture
def sent(monkeypatch):
    out = []

    def capture(to_email, subject, body, from_email, *a, **kw):
        out.append({"to": to_email, "body": body, "client_id": kw.get("client_id", "missing")})
        return True, "captured"
    monkeypatch.setattr(main, "send_email_background", capture)
    return out


def link(body):
    m = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    assert m, body
    return m.group(1)


def owner_id(email):
    with main.SessionLocal() as db:
        return db.query(models.DBClient).filter(models.DBClient.email == email).first().id


def test_an_owners_reset_is_platform_mail_even_when_the_business_has_its_own_gmail(tenant, account, sent):
    with main.SessionLocal() as db:
        db.add(models.DBClientEmailSettings(client_id=owner_id(account["email"]), transport="gmail",
                                            from_email="billing@business.example"))
        db.commit()
    tenant.post("/api/client/logout")
    assert tenant.post("/api/client/forgot-password", json={"email": account["email"]}).status_code == 200
    assert len(sent) == 1 and sent[0]["to"] == account["email"]
    assert sent[0]["client_id"] is None                 # the platform's connection, not the business's


def test_a_failed_reset_send_is_written_down_where_the_operator_looks(tenant, account, monkeypatch):
    monkeypatch.setattr(main, "_send_email_now", lambda *a, **k: (False, "Gmail refused it"))
    tenant.post("/api/client/logout")
    assert tenant.post("/api/client/forgot-password", json={"email": account["email"]}).status_code == 200
    with main.SessionLocal() as db:
        row = db.query(models.DBEmailDelivery).filter(models.DBEmailDelivery.client_id == None,   # noqa: E711
                                                     models.DBEmailDelivery.to_email == account["email"]).order_by(
            models.DBEmailDelivery.id.desc()).first()
    assert row is not None and row.status == "failed" and "Gmail refused it" in row.error
    assert row.reference == "Reset your aniprotech password"


def test_a_team_member_is_sent_a_link_that_works(client, tenant, sent):
    member, email = invite(tenant)
    set_their_password(member["id"])
    tenant.post("/api/client/logout")
    sent.clear()
    assert client.post("/api/client/forgot-password", json={"email": email.upper()}).status_code == 200
    assert len(sent) == 1 and sent[0]["to"] == email and sent[0]["client_id"] is None
    assert "(team member)" in sent[0]["body"]
    done = client.post("/api/client/reset-password", json={"token": link(sent[0]["body"]), "password": "NewPassw0rd9"})
    assert done.status_code == 200, done.text
    assert sign_in_as(client, email, "NewPassw0rd9").status_code == 200


def test_a_removed_team_member_is_sent_nothing(client, tenant, sent):
    member, email = invite(tenant)
    with main.SessionLocal() as db:
        db.query(models.DBTeamMember).filter(models.DBTeamMember.id == member["id"]).first().is_active = False
        db.commit()
    sent.clear()
    r = client.post("/api/client/forgot-password", json={"email": email})
    assert r.status_code == 200 and "on its way" in r.json()["message"] and sent == []


def test_an_owner_who_is_also_on_another_team_gets_a_link_for_each(client, tenant, account, sent):
    from fastapi.testclient import TestClient
    other_owner = f"other-{uuid.uuid4().hex[:8]}@example.com"
    with TestClient(main.app) as other:
        other.post("/api/client/register", json={"email": other_owner, "password": "Passw0rdTest", "company_name": "Other Co"})
        other.post("/api/client/login", json={"email": other_owner, "password": "Passw0rdTest"})
        mate, _ = invite(other, email=account["email"])
    sent.clear()
    client.post("/api/client/forgot-password", json={"email": account["email"]})
    assert len(sent) == 2 and {s["to"] for s in sent} == {account["email"]}
    assert any("Other Co (team member)" in s["body"] for s in sent)
    assert link(sent[0]["body"]) != link(sent[1]["body"])


def test_a_staff_reset_is_platform_mail_too(client, tenant, sent):
    from conftest import make_employee
    emp = make_employee(tenant, password="EmpPass123")
    sent.clear()
    assert client.post("/api/employee/forgot-password", json={"email": emp["email"]}).status_code == 200
    assert len(sent) == 1 and sent[0]["client_id"] is None
