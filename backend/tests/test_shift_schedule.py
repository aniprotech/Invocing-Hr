"""The hours HR sets, and everything measured against them.

Attendance recorded when people arrived and left, and totalled the difference.
Nothing said what a day was supposed to be, so nothing could say whether one
was short, complete or over - "7.2 hours" is a fact, not an answer.

HR now sets the production hours a day is measured against, alongside the
start and end times that were already there. One function does the judging,
because the alternative is each screen doing its own arithmetic: the gauge in
the employee portal and the register their manager reads have to produce the
same number or somebody is going to dispute a figure the product states two
ways.

These cover the judging, and the refusals that keep a schedule usable - a day
of zero hours has no ratio, and a half day longer than a full one marks every
complete shift as half.
"""
from datetime import datetime

import pytest

import main


class Row:
    """An attendance row, without needing the database for arithmetic."""

    def __init__(self, **kw):
        self.date = kw.get("date", "2026-03-02")
        self.clock_in = kw.get("clock_in", "")
        self.clock_out = kw.get("clock_out", "")
        self.total_hours = kw.get("total_hours", 0.0)
        self.break_minutes = kw.get("break_minutes", 0.0)
        self.break_start = kw.get("break_start", "")
        self.is_on_break = kw.get("is_on_break", False)


class Rules:
    def __init__(self, **kw):
        for k, v in main.SHIFT_DEFAULTS.items():
            setattr(self, k, kw.get(k, v))
        for k, v in kw.items():
            setattr(self, k, v)


NOON = datetime(2026, 3, 2, 12, 0, 0)


# --- what HR sets is what gets measured ------------------------------------
def test_the_target_is_the_hours_hr_asked_for():
    p = main.shift_progress(Rules(standard_hours=7.5), Row(), NOON)
    assert p["target_hours"] == 7.5


def test_a_finished_day_is_measured_against_it():
    done = Row(clock_in="09:00:00", clock_out="17:00:00", total_hours=8.0)
    assert main.shift_progress(Rules(standard_hours=8), done, NOON)["state"] == "complete"
    assert main.shift_progress(Rules(standard_hours=9), done, NOON)["state"] == "short"


def test_changing_the_target_changes_the_verdict():
    """The point of letting HR decide: the same day reads differently under a
    different schedule, and nothing in the code has to change for it to."""
    day = Row(clock_in="09:00:00", clock_out="15:00:00", total_hours=6.0)
    assert main.shift_progress(Rules(standard_hours=6), day, NOON)["state"] == "complete"
    assert main.shift_progress(Rules(standard_hours=8), day, NOON)["state"] == "short"
    assert main.shift_progress(Rules(standard_hours=8, half_day_hours=7),
                               day, NOON)["state"] == "half_day"


# --- the gauge --------------------------------------------------------------
def test_a_day_not_started_reads_as_nothing_worked():
    p = main.shift_progress(Rules(), Row(), NOON)
    assert p["worked_hours"] == 0
    assert p["fraction"] == 0
    assert p["state"] == "not_started"
    assert p["remaining_hours"] == 8.0


def test_time_in_progress_is_counted_from_the_clock_in():
    p = main.shift_progress(Rules(standard_hours=8),
                            Row(clock_in="09:00:00"), NOON)
    assert p["worked_hours"] == 3.0
    assert p["remaining_hours"] == 5.0
    assert p["percent"] == 38
    assert p["state"] == "working"


def test_the_needle_never_sweeps_past_the_end_of_the_dial():
    """A twelve-hour day on an eight-hour target is 150%, and a gauge drawn
    from that points at the wall."""
    long_day = Row(clock_in="00:00:00", clock_out="12:00:00", total_hours=12.0)
    p = main.shift_progress(Rules(standard_hours=8), long_day, NOON)
    assert p["fraction"] == 1.0
    assert p["percent"] == 100
    # The part that did not fit is still reported, just not on the needle.
    assert p["overtime_hours"] == 4.0
    assert p["state"] == "complete"


def test_overtime_while_still_working_says_so():
    p = main.shift_progress(Rules(standard_hours=2),
                            Row(clock_in="09:00:00"), NOON)
    assert p["state"] == "overtime"
    assert p["overtime_hours"] == 1.0


# --- breaks -----------------------------------------------------------------
def test_an_unpaid_break_does_not_count_toward_the_target():
    p = main.shift_progress(Rules(paid_breaks=False),
                            Row(clock_in="09:00:00", break_minutes=60), NOON)
    assert p["worked_hours"] == 2.0


def test_a_paid_break_does():
    p = main.shift_progress(Rules(paid_breaks=True),
                            Row(clock_in="09:00:00", break_minutes=60), NOON)
    assert p["worked_hours"] == 3.0


def test_a_break_still_running_is_deducted_as_it_happens():
    """Otherwise the gauge keeps climbing through lunch."""
    on_lunch = Row(clock_in="09:00:00", is_on_break=True, break_start="11:30:00")
    p = main.shift_progress(Rules(paid_breaks=False), on_lunch, NOON)
    assert p["worked_hours"] == 2.5
    assert p["state"] == "on_break"


# --- late and early ---------------------------------------------------------
def test_arriving_within_the_grace_period_is_not_late():
    """The grace is there to be used; counting it as lateness makes it a lie."""
    p = main.shift_progress(Rules(work_start="09:00", grace_minutes=15),
                            Row(clock_in="09:14:00"), NOON)
    assert p["late_minutes"] == 0


def test_arriving_after_it_is():
    p = main.shift_progress(Rules(work_start="09:00", grace_minutes=15),
                            Row(clock_in="09:40:00"), NOON)
    assert p["late_minutes"] == 25


def test_arriving_early_is_not_negative_lateness():
    p = main.shift_progress(Rules(work_start="09:00"),
                            Row(clock_in="08:30:00"), NOON)
    assert p["late_minutes"] == 0


def test_leaving_before_the_end_time_is_recorded():
    day = Row(clock_in="09:00:00", clock_out="16:00:00", total_hours=7.0)
    p = main.shift_progress(Rules(work_end="17:30"), day, NOON)
    assert p["left_early_minutes"] == 90


def test_staying_late_is_not_negative_early_leaving():
    day = Row(clock_in="09:00:00", clock_out="19:00:00", total_hours=10.0)
    assert main.shift_progress(Rules(work_end="17:30"), day, NOON)["left_early_minutes"] == 0


# --- a schedule that is always usable ---------------------------------------
def test_a_tenant_who_has_never_opened_the_settings_still_has_a_schedule():
    """There is no row at all until somebody saves one."""
    p = main.shift_progress(None, Row(clock_in="09:00:00"), NOON)
    assert p["target_hours"] == 8.0
    assert p["expected_in"] == "09:00"


def test_a_row_saved_before_these_columns_existed_reads_as_the_defaults():
    stale = Rules(standard_hours=None, half_day_hours=None, paid_breaks=None)
    r = main.shift_rules(stale)
    assert r["standard_hours"] == 8.0
    assert r["half_day_hours"] == 4.0


def test_a_day_of_no_hours_cannot_divide_by_zero():
    """Every ratio on the gauge is against this number."""
    r = main.shift_rules(Rules(standard_hours=0))
    assert r["standard_hours"] > 0
    p = main.shift_progress(Rules(standard_hours=0), Row(clock_in="09:00:00"), NOON)
    assert p["fraction"] <= 1.0


def test_a_half_day_longer_than_a_full_one_is_brought_back():
    """It would otherwise mark every complete shift as half."""
    r = main.shift_rules(Rules(standard_hours=8, half_day_hours=9))
    assert r["half_day_hours"] < r["standard_hours"]


def test_a_nonsense_clock_in_does_not_take_the_gauge_down():
    p = main.shift_progress(Rules(), Row(clock_in="not a time"), NOON)
    assert p["worked_hours"] == 0


# --- through the API --------------------------------------------------------
def test_hr_can_set_the_production_hours(tenant):
    res = tenant.put("/api/attendance/settings", json={
        "standard_hours": 7.5, "half_day_hours": 3.5,
        "work_start": "08:30", "work_end": "17:00"})
    assert res.status_code == 200, res.text

    got = tenant.get("/api/attendance/settings").json()
    assert got["standard_hours"] == 7.5
    assert got["half_day_hours"] == 3.5
    assert got["work_start"] == "08:30"
    assert got["work_end"] == "17:00"


def test_a_tenant_who_has_saved_nothing_is_told_the_defaults(tenant):
    got = tenant.get("/api/attendance/settings").json()
    assert got["standard_hours"] == 8.0
    assert got["half_day_hours"] == 4.0


@pytest.mark.parametrize("hours", [0, -1, 25, "eight"])
def test_a_day_that_is_not_a_number_of_hours_is_refused(tenant, hours):
    res = tenant.put("/api/attendance/settings", json={"standard_hours": hours})
    assert res.status_code == 400, res.text


def test_a_half_day_longer_than_a_full_day_is_refused(tenant):
    res = tenant.put("/api/attendance/settings",
                     json={"standard_hours": 8, "half_day_hours": 9})
    assert res.status_code == 400, res.text
    # And the refusal left the old values alone.
    assert tenant.get("/api/attendance/settings").json()["standard_hours"] == 8.0


def test_a_refused_save_does_not_half_apply(tenant):
    """work_start comes before standard_hours in the body; if the refusal came
    after the write, the time would be saved and the hours would not."""
    tenant.put("/api/attendance/settings", json={"work_start": "09:00"})
    tenant.put("/api/attendance/settings",
               json={"work_start": "07:00", "standard_hours": 99})
    assert tenant.get("/api/attendance/settings").json()["work_start"] == "09:00"


def test_hr_and_the_employee_are_shown_the_same_judgement(tenant):
    """Two screens doing their own arithmetic is how somebody ends up
    disputing a figure the product states two different ways."""
    tenant.put("/api/attendance/settings", json={"standard_hours": 6})
    emp = tenant.post("/api/employees", json={
        "first_name": "Ada", "last_name": "Reid", "email": "ada@acme.test",
        "job_title": "Analyst", "status": "active"}).json()

    live = tenant.get("/api/attendance/live").json()
    row = next(r for r in live if r["id"] == emp["id"])
    assert "shift" in row, "the register does not say how the day is going"
    assert row["shift"]["target_hours"] == 6, \
        "the register is measuring against a different day than HR set"
    assert row["shift"]["expected_in"]


def test_saving_something_unrelated_on_a_fresh_tenant_works(tenant):
    """The first save a business ever makes, touching none of the hours.

    A settings row created in memory has None in every column until it is
    inserted, so validating the raw attributes made "half day >= full day"
    read as 0 >= 0 and refused it. Every tenant's first visit to the page.
    """
    res = tenant.put("/api/attendance/settings", json={"office_name": "Depot"})
    assert res.status_code == 200, res.text
    assert tenant.get("/api/attendance/settings").json()["office_name"] == "Depot"


def test_changing_only_the_full_day_keeps_the_half_day_valid(tenant):
    """Raising the full day alone must not trip the check on the old half."""
    tenant.put("/api/attendance/settings",
               json={"standard_hours": 8, "half_day_hours": 4})
    res = tenant.put("/api/attendance/settings", json={"standard_hours": 10})
    assert res.status_code == 200, res.text
    assert tenant.get("/api/attendance/settings").json()["standard_hours"] == 10


def test_lowering_the_full_day_under_the_half_day_is_still_refused(tenant):
    tenant.put("/api/attendance/settings",
               json={"standard_hours": 10, "half_day_hours": 6})
    res = tenant.put("/api/attendance/settings", json={"standard_hours": 5})
    assert res.status_code == 400, res.text
