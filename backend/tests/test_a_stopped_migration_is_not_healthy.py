"""A schema update that stopped early must not report as healthy.

ensure_columns applies 51 steps, each guarded so a partial failure cannot stop
the app booting. Every one of them appends to MIGRATION_ERRORS when it fails,
and /api/health reads that list - the whole apparatus exists because a
migration that silently did not run is indistinguishable from one that worked.

The outer handler did not append. It printed:

    except Exception as e:
        print(f"Column check skipped: {e}")

So anything raised between steps rather than inside one - a dropped
connection, a lock timeout, a CREATE TABLE outside a step's try - abandoned
every remaining migration and left the list empty. health_check then found
nothing wrong and answered "ok".

That is the worst arrangement available: columns missing, screens failing on
them, and the one instrument built to catch exactly this reporting green,
while the reason went to a log nobody reads.
"""
import pytest

import database
import main


@pytest.fixture
def errors_restored():
    before = list(database.MIGRATION_ERRORS)
    yield
    database.MIGRATION_ERRORS[:] = before


def abandon_the_migration(reason):
    """Make ensure_columns fail between steps and put everything back.

    Two things are in the way of doing this simply. ensure_columns returns
    immediately on SQLite, which the suite runs on, so the body never executes
    unless the URL says otherwise. And the connection it fails on is the same
    one /api/health uses, so the break has to be undone before anything else
    asks a question.
    """
    real_connect = database.engine.connect
    real_url = database.DATABASE_URL

    def die(*a, **k):
        raise RuntimeError(reason)

    database.DATABASE_URL = "postgresql://not-really"
    database.engine.connect = die
    try:
        database.ensure_columns()          # must not raise
    finally:
        database.engine.connect = real_connect
        database.DATABASE_URL = real_url


def test_a_failure_between_steps_is_recorded(errors_restored):
    """Not printed. The list is the only thing anybody reads."""
    database.MIGRATION_ERRORS.clear()

    abandon_the_migration("connection dropped mid-migration")

    assert database.MIGRATION_ERRORS,         "the whole schema update abandoned itself and recorded nothing"
    assert "connection dropped mid-migration" in database.MIGRATION_ERRORS[-1]


def test_and_health_stops_calling_itself_ok(client, errors_restored):
    """The consequence. This is what made it invisible."""
    database.MIGRATION_ERRORS.clear()
    assert client.get("/api/health").json()["status"] == "ok"

    abandon_the_migration("lock timeout")

    said = client.get("/api/health").json()
    assert said["status"] == "ok_with_warnings", said
    assert said["migration_warnings"] >= 1, said


def test_a_clean_run_still_says_nothing(client, errors_restored):
    """The list is only useful while it stays empty when things are fine."""
    database.MIGRATION_ERRORS.clear()
    database.ensure_columns()
    assert database.MIGRATION_ERRORS == [], database.MIGRATION_ERRORS


def test_the_messages_stay_off_the_public_endpoint(client, errors_restored):
    """They carry table and column names, and /api/health is public. A count
    is the most it may say."""
    database.MIGRATION_ERRORS.clear()
    database.MIGRATION_ERRORS.append("schema update stopped early: relation "
                                     "\"secret_table\" does not exist")

    body = client.get("/api/health").text
    assert "secret_table" not in body, body
    assert "1" in body
