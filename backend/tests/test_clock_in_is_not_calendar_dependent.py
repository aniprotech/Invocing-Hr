"""Signing in starts a shift only on a working day.

That rule is deliberate - somebody opening the portal on a Sunday to check a
document is not at work - but four tests had been asserting the opposite by
accident, because they ran on weekdays and never on a Saturday. This pins both
halves of the rule against a fixed day rather than against today.
"""
from datetime import date

import pytest

import main
from conftest import make_employee, work_every_day


@pytest.fixture(autouse=True)
def _reset_limiter():
    main.rate_limiter._hits.clear()
    yield


class Settings:
    """Only the two attributes the rule reads."""

    def __init__(self, working_days="1,2,3,4,5", auto_clock_in=True):
        self.working_days = working_days
        self.auto_clock_in = auto_clock_in


MONDAY = date(2026, 8, 17)
SATURDAY = date(2026, 8, 15)
SUNDAY = date(2026, 8, 16)


# --- the rule itself, against fixed dates ------------------------------------

def test_a_weekday_starts_a_shift():
    assert main.should_auto_clock_in(Settings(), MONDAY) is True


@pytest.mark.parametrize("day", [SATURDAY, SUNDAY])
def test_the_weekend_does_not(day):
    assert main.should_auto_clock_in(Settings(), day) is False


def test_a_tenant_can_choose_to_work_weekends():
    weekends_too = Settings(working_days="1,2,3,4,5,6,7")
    assert main.should_auto_clock_in(weekends_too, SATURDAY) is True
    assert main.should_auto_clock_in(weekends_too, SUNDAY) is True


def test_a_tenant_can_turn_the_whole_thing_off():
    """Some businesses do not want signing in to count as attendance at all."""
    off = Settings(auto_clock_in=False)
    assert main.should_auto_clock_in(off, MONDAY) is False


def test_a_saturday_only_business():
    assert main.should_auto_clock_in(Settings(working_days="6"), SATURDAY) is True
    assert main.should_auto_clock_in(Settings(working_days="6"), MONDAY) is False


# --- and through the API, so the wiring is covered too ------------------------

def test_signing_in_on_a_working_day_clocks_you_in(client, tenant):
    work_every_day(tenant)
    emp = make_employee(tenant, password="EmpPass123")
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": "EmpPass123"})
    assert res.status_code == 200, res.text
    assert res.json()["clock_in"], "a working day must start the shift"


def test_signing_in_on_a_non_working_day_does_not(client, tenant):
    """The setting is emptied of every day, so no date can be a working day -
    the assertion then holds whatever day the suite runs on."""
    tenant.put("/api/attendance/settings", json={"auto_clock_in": False})
    emp = make_employee(tenant, password="EmpPass123")
    res = client.post("/api/employee/auth/login",
                      json={"email": emp["email"], "password": "EmpPass123"})
    assert res.status_code == 200, res.text
    assert not res.json()["clock_in"]


def test_they_can_still_clock_in_by_hand(client, tenant):
    """The point of the rule: coming in on a day off is allowed, it just is not
    automatic."""
    tenant.put("/api/attendance/settings", json={"auto_clock_in": False})
    emp = make_employee(tenant, password="EmpPass123")
    client.post("/api/employee/auth/login",
                json={"email": emp["email"], "password": "EmpPass123"})

    res = client.post("/api/employee/attendance/clock-in", json={})
    assert res.status_code == 200, res.text
