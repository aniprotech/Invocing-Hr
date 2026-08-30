"""Giving an account a password of its own.

Sign-in was Google only. An account had no password, no way to make one, and
so no way in at all if the Google account was ever lost - the business would
be locked out of its own invoices.

The rules that matter here are the ones that stop this becoming a way in for
somebody else: changing a password you already have needs the current one,
and a colleague changes their own password rather than the owner's.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import main
import models


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


# --- the common case: a Google account gaining a password -------------------
def test_an_account_with_no_password_can_create_one(tenant):
    """The tenant fixture registers with a password, so clear it first to get
    the state a Google-only account is actually in."""
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        db.query(models.DBClient).filter(models.DBClient.id == cid).update(
            {"password_hash": ""})
        db.commit()

    assert tenant.get("/api/client/password-status").json()["has_password"] is False

    res = tenant.post("/api/client/set-password", json={"new_password": "Str0ngPass1"})
    assert res.status_code == 200, res.text
    assert res.json()["has_password"] is True
    assert tenant.get("/api/client/password-status").json()["has_password"] is True


def test_and_can_then_sign_in_with_it(tenant):
    """The whole point - a way in that does not depend on Google."""
    me = tenant.get("/api/client/me").json()
    with main.SessionLocal() as db:
        db.query(models.DBClient).filter(models.DBClient.id == me["id"]).update(
            {"password_hash": ""})
        db.commit()
    tenant.post("/api/client/set-password", json={"new_password": "Str0ngPass1"})

    with TestClient(main.app) as fresh:
        res = fresh.post("/api/client/login",
                         json={"email": me["email"], "password": "Str0ngPass1"})
        assert res.status_code == 200, res.text
        assert fresh.get("/api/client/me").json()["id"] == me["id"]


# --- changing one you already have ------------------------------------------
def test_changing_a_password_needs_the_current_one(tenant):
    """Without this a session somebody else has got hold of becomes a
    permanent takeover: they set a password and keep the account."""
    res = tenant.post("/api/client/set-password", json={"new_password": "Different1"})
    assert res.status_code == 400
    assert "current password" in res.json()["detail"].lower()


def test_a_wrong_current_password_is_refused(tenant):
    res = tenant.post("/api/client/set-password", json={
        "current_password": "NotTheOne1", "new_password": "Different1"})
    assert res.status_code == 401


def test_the_right_current_password_lets_it_through(tenant):
    res = tenant.post("/api/client/set-password", json={
        "current_password": "Passw0rdTest", "new_password": "Different1"})
    assert res.status_code == 200, res.text

    me = tenant.get("/api/client/me").json()
    with TestClient(main.app) as fresh:
        assert fresh.post("/api/client/login", json={
            "email": me["email"], "password": "Different1"}).status_code == 200
        assert fresh.post("/api/client/login", json={
            "email": me["email"], "password": "Passw0rdTest"}).status_code == 401


def test_setting_the_same_password_again_is_called_out(tenant):
    """A save that changed nothing but says "done" is worse than a refusal."""
    res = tenant.post("/api/client/set-password", json={
        "current_password": "Passw0rdTest", "new_password": "Passw0rdTest"})
    assert res.status_code == 400
    assert "already" in res.json()["detail"].lower()


# --- the new password has to be a real one ----------------------------------
@pytest.mark.parametrize("weak", ["", "short1A", "alllowercase1", "NODIGITSHERE"])
def test_a_weak_password_is_refused(tenant, weak):
    res = tenant.post("/api/client/set-password", json={
        "current_password": "Passw0rdTest", "new_password": weak})
    assert res.status_code == 400, res.text


def test_a_refused_change_leaves_the_old_password_working(tenant):
    me = tenant.get("/api/client/me").json()
    tenant.post("/api/client/set-password", json={
        "current_password": "Passw0rdTest", "new_password": "weak"})
    with TestClient(main.app) as fresh:
        assert fresh.post("/api/client/login", json={
            "email": me["email"], "password": "Passw0rdTest"}).status_code == 200


# --- who it actually changes ------------------------------------------------
def test_a_colleague_changes_their_own_password_not_the_owner_s(tenant):
    """member_id is on the session so these two cannot be confused. Changing
    the owner's credentials is changing what the whole tenancy hangs off."""
    cid = tenant.get("/api/client/me").json()["id"]
    member_email = f"colleague-{uuid.uuid4().hex[:8]}@example.com"
    with main.SessionLocal() as db:
        member = models.DBTeamMember(
            client_id=cid, email=member_email, name="Colleague",
            password_hash=main.hash_password("MemberPass1"),
            role="admin", is_active=True)
        db.add(member)
        db.commit()

    with TestClient(main.app) as colleague:
        assert colleague.post("/api/client/login", json={
            "email": member_email, "password": "MemberPass1"}).status_code == 200

        assert colleague.post("/api/client/set-password", json={
            "current_password": "MemberPass1",
            "new_password": "MemberNew1"}).status_code == 200

    with main.SessionLocal() as db:
        owner = db.query(models.DBClient).filter(models.DBClient.id == cid).first()
        member = db.query(models.DBTeamMember).filter(
            models.DBTeamMember.email == member_email).first()
        assert main.verify_password("MemberNew1", member.password_hash), \
            "the colleague's own password did not change"
        assert main.verify_password("Passw0rdTest", owner.password_hash), \
            "the owner's password was changed by a colleague"


def test_the_status_endpoint_reports_the_colleague_not_the_owner(tenant):
    cid = tenant.get("/api/client/me").json()["id"]
    member_email = f"colleague-{uuid.uuid4().hex[:8]}@example.com"
    with main.SessionLocal() as db:
        db.add(models.DBTeamMember(
            client_id=cid, email=member_email, name="Colleague",
            password_hash=main.hash_password("MemberPass1"),
            role="admin", is_active=True))
        db.commit()

    with TestClient(main.app) as colleague:
        colleague.post("/api/client/login", json={
            "email": member_email, "password": "MemberPass1"})
        status = colleague.get("/api/client/password-status").json()
        assert status["email"] == member_email
        assert status["is_owner"] is False


# --- signed out ---------------------------------------------------------------
def test_a_stranger_cannot_set_a_password(client):
    res = client.post("/api/client/set-password", json={"new_password": "Str0ngPass1"})
    assert res.status_code in (401, 403)


def test_a_stranger_cannot_read_the_password_status(client):
    assert client.get("/api/client/password-status").status_code in (401, 403)
