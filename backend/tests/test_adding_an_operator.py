"""Adding a second platform operator.

Found the hard way. A second address was put in SUPERADMIN_EMAILS, and from
that moment the application would not start - not once, on every deploy, with
nothing visible but a health check timing out for five minutes and the release
being rejected. The site stayed up only because the platform kept serving the
previous container.

Two separate faults, and both had to be fixed:

  - Every operator was created with the username "superadmin". The column is
    unique, so the first one worked and the second raised IntegrityError.
    Adding an operator was not something this could do.
  - ensure_super_admin() ran outside the guard that startup puts around
    everything else it does, so that IntegrityError propagated out of the
    lifespan and killed the process. The schema updates and the pricing seed
    both already refuse to be fatal; this was the one step that did not.

The second is the more serious of the two. Any failure in here, for any
reason, took the whole platform's ability to deploy with it.
"""
import pytest

import database
import main
import models


@pytest.fixture
def no_operators():
    """Operators are seeded once for the session, so a test that counts them
    has to start from a known state and put back what it found."""
    with main.SessionLocal() as db:
        kept = [(a.username, a.password_hash, a.email) for a in
                db.query(models.DBSuperAdmin).all()]
        db.query(models.DBSuperAdmin).delete()
        db.commit()
    yield
    with main.SessionLocal() as db:
        db.query(models.DBSuperAdmin).delete()
        for username, pwd, email in kept:
            db.add(models.DBSuperAdmin(username=username, password_hash=pwd, email=email))
        db.commit()


def operators():
    with main.SessionLocal() as db:
        return [(a.username, a.email) for a in
                db.query(models.DBSuperAdmin).order_by(models.DBSuperAdmin.id).all()]


def with_emails(monkeypatch, value):
    monkeypatch.setenv("SUPERADMIN_EMAILS", value)
    main.ensure_super_admin()


# --- the fault that stopped the deploys -------------------------------------------

def test_a_second_operator_can_be_added(client, no_operators, monkeypatch):
    """What was actually being asked for. Before this it raised
    IntegrityError on the duplicate username."""
    with_emails(monkeypatch, "first@example.com,second@example.com")
    assert sorted(e for _, e in operators()) == ["first@example.com", "second@example.com"], \
        operators()


def test_and_a_third(client, no_operators, monkeypatch):
    with_emails(monkeypatch, "a@example.com,b@example.com,c@example.com")
    assert len(operators()) == 3, operators()


def test_they_do_not_share_a_username(client, no_operators, monkeypatch):
    """The unique constraint that was being violated."""
    with_emails(monkeypatch, "one@example.com,two@example.com,three@example.com")
    names = [u for u, _ in operators()]
    assert len(set(names)) == len(names), names


def test_the_first_one_keeps_the_name_people_sign_in_with(client, no_operators, monkeypatch):
    """Somebody may be typing "superadmin" rather than their address, and a
    rename would lock them out of the one account that can reach everything."""
    with_emails(monkeypatch, "first@example.com,second@example.com")
    assert operators()[0][0] == "superadmin", operators()


def test_an_operator_added_later_gets_a_name_from_their_address(client, no_operators, monkeypatch):
    with_emails(monkeypatch, "first@example.com,priya@example.com")
    assert dict((e, u) for u, e in operators())["priya@example.com"] == "priya", operators()


def test_two_addresses_with_the_same_name_still_differ(client, no_operators, monkeypatch):
    """info@ at two domains is the obvious way to collide a second time."""
    with_emails(monkeypatch, "first@example.com,info@a.com,info@b.com")
    names = [u for u, _ in operators()]
    assert len(set(names)) == 3, names


def test_running_it_again_adds_nobody(client, no_operators, monkeypatch):
    """It runs on every boot."""
    with_emails(monkeypatch, "first@example.com,second@example.com")
    main.ensure_super_admin()
    main.ensure_super_admin()
    assert len(operators()) == 2, operators()


def test_the_variable_naming_only_the_new_address_still_works(client, no_operators, monkeypatch):
    """Production's exact shape. The operator already in the database was
    seeded from the old default, and the variable was then set to one new
    address rather than to both - so the row that is there is not named in
    the variable at all, and the address in the variable has no row.

    Nothing is removed: an operator account is not something a deploy should
    be able to delete by leaving a name out of an environment variable."""
    with_emails(monkeypatch, "hello@keyroutes.co")
    assert operators() == [("superadmin", "hello@keyroutes.co")]

    with_emails(monkeypatch, "info@aniprotech.com")
    assert sorted(operators()) == [("info", "info@aniprotech.com"),
                                   ("superadmin", "hello@keyroutes.co")], operators()


def test_an_address_added_to_an_existing_install_joins_the_ones_there(client, no_operators, monkeypatch):
    """The exact sequence that broke: one operator already in the database,
    a second address added to the variable, restart."""
    with_emails(monkeypatch, "first@example.com")
    assert len(operators()) == 1

    with_emails(monkeypatch, "first@example.com,info@aniprotech.com")
    assert sorted(e for _, e in operators()) == \
        ["first@example.com", "info@aniprotech.com"], operators()


# --- and it must never take the application down again ---------------------------------

@pytest.fixture
def a_failing_setup(monkeypatch):
    """Make the step fail, and put the shared error list back afterwards.

    The list is module state that /api/health reports, so a test that leaves
    an entry in it changes what a later test in the same run sees - which is
    exactly what happened when these two cleaned up by hand."""
    def explode():
        raise RuntimeError("the database said no")

    monkeypatch.setattr(main, "_ensure_super_admin", explode)
    before = list(database.MIGRATION_ERRORS)
    yield
    database.MIGRATION_ERRORS[:] = before


def test_startup_survives_this_failing_for_any_reason(client, a_failing_setup):
    """The fault above is fixed, but this is why it was able to do so much
    damage. Anything raising in here used to propagate out of the lifespan and
    stop the process, so a bad row meant the platform could not deploy at all
    - and the only symptom was a health check timing out."""
    main.ensure_super_admin()          # must not raise


def test_and_says_what_went_wrong_where_an_operator_will_see_it(client, a_failing_setup):
    """Swallowing it silently would trade one invisible failure for another.
    The same list the schema updates report through."""
    before = len(database.MIGRATION_ERRORS)
    main.ensure_super_admin()
    assert len(database.MIGRATION_ERRORS) == before + 1, database.MIGRATION_ERRORS
    assert "the database said no" in database.MIGRATION_ERRORS[-1]


def test_the_lifespan_calls_the_guarded_one(client):
    """The guard is worth nothing if startup reaches past it."""
    import inspect
    body = inspect.getsource(main.lifespan)
    assert "ensure_super_admin()" in body
    assert "_ensure_super_admin()" not in body, \
        "startup calls the unguarded version, so a failure still stops the boot"


# --- signing in with the new account ------------------------------------------------------

def test_a_later_operator_signs_in_with_their_address(client, no_operators, monkeypatch):
    """They are named from their email rather than "superadmin", so the
    address has to work - it is the only thing they were told."""
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "TestSuper123")
    with_emails(monkeypatch, "first@example.com,priya@example.com")

    res = client.post("/api/superadmin/login",
                      json={"identifier": "priya@example.com", "password": "TestSuper123"})
    assert res.status_code == 200, res.text
    assert res.json()["email"] == "priya@example.com"


def test_and_with_the_username_they_were_given(client, no_operators, monkeypatch):
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "TestSuper123")
    with_emails(monkeypatch, "first@example.com,priya@example.com")

    res = client.post("/api/superadmin/login",
                      json={"identifier": "priya", "password": "TestSuper123"})
    assert res.status_code == 200, res.text


# --- the name allocator on its own ------------------------------------------------------------

@pytest.mark.parametrize("taken,email,expected", [
    (set(), "anything@example.com", "superadmin"),
    ({"superadmin"}, "priya@example.com", "priya"),
    ({"superadmin", "priya"}, "priya@other.com", "priya2"),
    ({"superadmin", "priya", "priya2"}, "priya@third.com", "priya3"),
    # Dots, dashes and underscores survive; the +tag an address may carry does not.
    ({"superadmin"}, "a.b-c_d+tag@example.com", "a.b-c_dtag"),
    ({"superadmin"}, "", "operator"),
    ({"superadmin"}, "!!!@example.com", "operator"),
])
def test_the_name_it_picks(taken, email, expected):
    assert main.a_free_operator_username(set(taken), email) == expected
