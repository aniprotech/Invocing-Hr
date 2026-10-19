"""Every part of the app that belongs to one product is refused to a business
that has not got that product - not just hidden from its menu.

These areas were reachable by URL from either plan: pension, expense claims,
surveys and the rest of HR from an invoicing-only account, and credit notes,
chasing and dunning from an HR-only one.
"""
import pytest

import main
import models

HR_ONLY = ["/api/absence", "/api/assets", "/api/certifications", "/api/check-ins/coverage", "/api/courses", "/api/expenses",
           "/api/feed", "/api/kudos", "/api/pay-bands", "/api/pay-review", "/api/pension/scheme", "/api/people/export.csv", "/api/policies",
           "/api/probations", "/api/review-cycles", "/api/reviews/1", "/api/skills", "/api/surveys", "/api/talent-grid",
           "/api/training/partners", "/api/workflows", "/api/workflow-tasks", "DELETE /api/employment-changes/1", "/api/job-board/settings",
           "/api/payroll/settings", "/api/payslips", "/api/hmrc/rti"]
INVOICING_ONLY = ["/api/credit-notes", "/api/chasing", "/api/dunning", "/api/autopay/mandates", "/api/invoice-list",
                  "/api/next-invoice-number", "/api/next-quote-number", "/api/next-bill-number", "/api/sales/pipeline",
                  "/api/suppliers", "/api/ledger/sales", "/api/bills", "/api/invoices", "/api/inventory"]
SHARED = ["/api/settings", "/api/contacts", "/api/accounts", "/api/bank/lines", "/api/client/me", "/api/wallet",
          "/api/tax-rates", "/api/search?q=a", "/api/dashboard-summary", "/api/reports/profit-loss"]


@pytest.fixture(autouse=True)
def _reset():
    main.rate_limiter._hits.clear()
    yield


def call(tenant, entry):
    method, _, path = entry.partition(" ") if " " in entry else ("GET", "", entry)
    return getattr(tenant, method.lower())(path)


def bare(entry):
    return entry.split(" ")[-1].split("?")[0]


def set_plan(tenant, modules):
    cid = tenant.get("/api/client/me").json()["id"]
    with main.SessionLocal() as db:
        db.query(models.DBClient).filter(models.DBClient.id == cid).update({"modules": modules})
        db.commit()


@pytest.mark.parametrize("path", HR_ONLY)
def test_an_hr_area_belongs_to_the_hr_plan(path):
    assert main.module_for_path(bare(path)) == "hr", path


@pytest.mark.parametrize("path", INVOICING_ONLY)
def test_an_invoicing_area_belongs_to_the_invoicing_plan(path):
    assert main.module_for_path(bare(path)) == "invoicing", path


@pytest.mark.parametrize("path", SHARED)
def test_what_both_plans_use_belongs_to_neither(path):
    assert main.module_for_path(bare(path)) is None, path


def test_an_invoicing_only_business_is_refused_hr_areas(tenant):
    set_plan(tenant, "invoicing")
    for path in HR_ONLY:
        assert call(tenant, path).status_code == 403, path


def test_an_hr_only_business_is_refused_invoicing_areas(tenant):
    set_plan(tenant, "hr")
    for path in INVOICING_ONLY:
        assert call(tenant, path).status_code == 403, path


@pytest.mark.parametrize("plan", ["hr", "invoicing"])
def test_the_shared_parts_answer_on_either_plan(tenant, plan):
    set_plan(tenant, plan)
    for path in SHARED:
        assert call(tenant, path).status_code != 403, (plan, path)


def test_a_business_with_both_reaches_both(tenant):
    for path in HR_ONLY + INVOICING_ONLY:
        assert call(tenant, path).status_code != 403, path
