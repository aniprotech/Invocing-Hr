"""A shift clocked into and never out of.

Nothing closed these, so a forgotten clock-out stayed open for ever. In
production there were rows weeks old still offering a "Clock Out" button,
still reading "present", and counting as zero hours in payroll despite the
person having worked the day.

The nightly job closes them and marks them needs_review. It deliberately does
not invent a finish time: the length of that shift is not knowable, and a
guessed number in payroll is worse than a visible gap, because it is wrong
and it looks right.
"""
from datetime import datetime, timedelta

import pytest

import database
import main
import models
from conftest import make_employee


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


def _client_id(tenant):
    return tenant.get("/api/client/me").json()["id"]


def _add_shift(tenant, day, clock_in="09:00:00", clock_out="", status="present"):
    """Put a raw attendance row in, the way a real clock-in would have."""
    emp = make_employee(tenant)
    with database.SessionLocal() as db:
        att = models.DBAttendance(
            client_id=_client_id(tenant), employee_id=emp["id"], date=day,
            clock_in=clock_in, clock_out=clock_out, status=status,
            check_type="office", location_label="Head office",
        )
        db.add(att)
        db.commit()
        return att.id


def _get(att_id):
    with database.SessionLocal() as db:
        return db.query(models.DBAttendance).filter(
            models.DBAttendance.id == att_id).first()


NOW = datetime(2026, 8, 24, 20, 0, 0)
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
LONG_AGO = (NOW - timedelta(days=18)).strftime("%Y-%m-%d")
TODAY = NOW.strftime("%Y-%m-%d")


def test_an_old_open_shift_is_closed_and_flagged(tenant):
    att_id = _add_shift(tenant, LONG_AGO)
    main.job_close_abandoned_shifts(database.SessionLocal(), NOW)

    row = _get(att_id)
    assert row.status == "needs_review"
    assert "no clock-out" in (row.notes or "").lower()


def test_it_does_not_invent_hours(tenant):
    """The whole point. Payroll must not be handed a number nobody recorded."""
    att_id = _add_shift(tenant, LONG_AGO, clock_in="09:00:00")
    main.job_close_abandoned_shifts(database.SessionLocal(), NOW)

    row = _get(att_id)
    assert row.total_hours == 0.0, "a shift length was guessed"
    assert not row.clock_out, "a finish time was invented"


def test_todays_open_shift_is_left_alone(tenant):
    """Somebody still at work is not somebody who forgot."""
    att_id = _add_shift(tenant, TODAY)
    main.job_close_abandoned_shifts(database.SessionLocal(), NOW)

    assert _get(att_id).status == "present"


def test_a_finished_shift_is_untouched(tenant):
    att_id = _add_shift(tenant, LONG_AGO, clock_out="17:00:00", status="completed")
    main.job_close_abandoned_shifts(database.SessionLocal(), NOW)

    row = _get(att_id)
    assert row.status == "completed"
    assert row.clock_out == "17:00:00"


def test_running_it_twice_does_not_stack_notes(tenant):
    """The scheduler claims a period, but the job must be safe on its own."""
    att_id = _add_shift(tenant, LONG_AGO)
    main.job_close_abandoned_shifts(database.SessionLocal(), NOW)
    first = _get(att_id).notes
    main.job_close_abandoned_shifts(database.SessionLocal(), NOW)

    assert _get(att_id).notes == first


def test_it_is_registered_with_the_scheduler():
    """A job nothing ever calls fixes nothing."""
    assert "close_abandoned_shifts" in [name for name, _, _ in main.SCHEDULED_JOBS]


# --- what the history table is sent ----------------------------------------

def test_the_history_sends_type_and_location(tenant):
    """Both columns have been in the table all along and were never sent, so
    every row read "-" for everyone, for ever."""
    _add_shift(tenant, LONG_AGO, clock_out="17:00:00", status="completed")

    rows = tenant.get("/api/attendance").json()
    assert rows, "no attendance came back"
    assert rows[0]["check_type"] == "office"
    assert rows[0]["location_label"] == "Head office"
