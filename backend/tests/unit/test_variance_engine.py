"""Unit tests for the pure variance engine (no DB / framework needed)."""
from datetime import date
from decimal import Decimal as D

from app.core.enums import ExceptionType, VarianceDirection
from app.services.variance_engine import (
    ActualLine,
    LineKey,
    Rule,
    check_tolerance,
    evaluate_report,
    resolve_rule,
    variance_pct,
)

K1 = LineKey(1, 6100)
K2 = LineKey(2, 6200)
GLOBAL = Rule(id=1, name="Global 5% / 500", max_variance_pct=D("5"), max_variance_abs=D("500"))
TODAY = date(2026, 3, 31)


def plan_for(*items):
    return {(p, k): D(a) for p, k, a in items}


def run(actuals, plan=None, prior=None, rules=(GLOBAL,), dups=None, period=3):
    return evaluate_report(
        partner_id=10, project_id=20, period=period, on_date=TODAY,
        plan=plan if plan is not None else plan_for((1, K1, "10000"), (2, K1, "10000"), (3, K1, "10000"), (3, K2, "2000")),
        actual_lines=actuals, prior_booked=prior or {}, rules=rules, external_duplicate_invoices=dups,
    )


def line(key, amount, inv, doc=True, line_id=None):
    return ActualLine(line_id=line_id, key=key, amount=D(amount), invoice_reference=inv, has_document=doc)


# ---------------------------------------------------------------- calculations
def test_variance_pct_basic_and_rounding():
    assert variance_pct(D("10000"), D("10450")) == D("4.50")
    assert variance_pct(D("3"), D("4")) == D("33.33")
    assert variance_pct(D("0"), D("0")) == D("0")
    assert variance_pct(D("0"), D("10")) is None


def test_calculation_totals_ytd_and_remaining_budget():
    prior = {(1, K1): D("9800"), (2, K1): D("10100")}
    res = run([line(K1, "10200.00", "INV-1"), line(K2, "2000", "INV-2")], prior=prior)
    row = next(r for r in res.rows if r.key == K1)
    assert row.planned == D("10000.00")
    assert row.actual == D("10200.00")
    assert row.variance == D("200.00")
    assert row.variance_pct == D("2.00")
    assert row.ytd_planned == D("30000.00")
    assert row.ytd_actual == D("30100.00")
    assert row.ytd_variance == D("100.00")
    assert row.annual_planned == D("30000.00")
    assert row.remaining_budget == D("-100.00")
    assert res.total_planned == D("12000.00")
    assert res.total_actual == D("12200.00")


def test_decimal_precision_no_float_drift():
    res = run([line(K1, "0.10", "A"), line(K1, "0.20", "B"), line(K2, "2000", "C")],
              plan=plan_for((3, K1, "0.30"), (3, K2, "2000")))
    row = next(r for r in res.rows if r.key == K1)
    assert row.actual == D("0.30") and row.variance == D("0.00")


# ---------------------------------------------------------------- tolerance
def test_auto_accept_within_tolerance():
    res = run([line(K1, "10400", "INV-1"), line(K2, "2000", "INV-2")])
    assert res.auto_accept
    assert all(r.within_tolerance for r in res.rows)


def test_pct_breach_creates_exception():
    res = run([line(K1, "10000", "INV-1"), line(K2, "2200", "INV-2")])  # +10% but only 200 abs
    assert not res.auto_accept
    f = res.findings[0]
    assert f.exception_type == ExceptionType.VARIANCE_OVER_TOLERANCE
    assert f.variance_pct == D("10.00")


def test_abs_breach_creates_exception_even_if_pct_small():
    plan = plan_for((3, K1, "100000"), (4, K1, "100000"))
    res = run([line(K1, "101000", "INV-1")], plan=plan)  # +1% but 1000 abs
    assert [f.exception_type for f in res.findings] == [ExceptionType.VARIANCE_OVER_TOLERANCE]


def test_boundary_exactly_at_limit_is_within():
    plan = plan_for((3, K1, "10000"), (4, K1, "10000"))
    res = run([line(K1, "10500", "INV-1")], plan=plan)  # exactly 5% and 500
    assert res.auto_accept


def test_underspend_not_flagged_with_overspend_only_rule():
    res = run([line(K1, "5000", "INV-1"), line(K2, "2000", "INV-2")])
    assert res.auto_accept


def test_underspend_flagged_with_both_direction_rule():
    both = Rule(id=2, name="Strict", max_variance_pct=D("5"), max_variance_abs=D("500"), direction=VarianceDirection.BOTH)
    res = run([line(K1, "5000", "INV-1"), line(K2, "2000", "INV-2")], rules=(both,))
    assert not res.auto_accept


def test_no_rule_is_fail_safe():
    ok, reason = check_tolerance(D("100"), D("100.01"), None)
    assert not ok and "fail-safe" in reason


def test_spend_against_zero_period_plan_is_exception():
    plan = plan_for((1, K1, "1000"), (3, K2, "100"))
    res = run([line(K1, "50", "INV-1"), line(K2, "100", "INV-2")], plan=plan)
    assert [f.exception_type for f in res.findings] == [ExceptionType.VARIANCE_OVER_TOLERANCE]


# ---------------------------------------------------------------- other controls
def test_missing_plan_line_exception():
    unknown = LineKey(9, 6900)
    res = run([line(K1, "10000", "INV-1"), line(K2, "2000", "INV-2"), line(unknown, "300", "INV-3", line_id=77)])
    types = [f.exception_type for f in res.findings]
    assert types == [ExceptionType.NO_PLAN_LINE]
    assert res.findings[0].line_id == 77


def test_duplicate_invoice_within_report_and_external():
    res = run([line(K1, "5000", "INV-1"), line(K1, "5000", "inv-1 "), line(K2, "2000", "OLD-9")], dups={"OLD-9"})
    dups = [f for f in res.findings if f.exception_type == ExceptionType.DUPLICATE_INVOICE]
    assert len(dups) == 2


def test_missing_document_exception():
    res = run([line(K1, "10000", "INV-1", doc=False), line(K2, "2000", "INV-2")])
    assert [f.exception_type for f in res.findings] == [ExceptionType.MISSING_DOCUMENT]


def test_over_annual_budget_flag():
    plan = plan_for((1, K1, "1000"), (2, K1, "1000"), (3, K1, "1000"))
    prior = {(1, K1): D("1040"), (2, K1): D("1040")}
    res = run([line(K1, "1040", "INV-3")], plan=plan, prior=prior)
    assert res.project_over_budget
    assert ExceptionType.OVER_ANNUAL_BUDGET in [f.exception_type for f in res.findings]


# ---------------------------------------------------------------- rule resolution
def test_most_specific_rule_wins_and_dates_respected():
    project_rule = Rule(id=2, name="Project", max_variance_pct=D("10"), max_variance_abs=D("1000"), project_id=20)
    partner_rule = Rule(id=3, name="Partner", max_variance_pct=D("2"), max_variance_abs=D("100"), partner_id=10)
    expired = Rule(id=4, name="Old", max_variance_pct=D("50"), max_variance_abs=D("9999"), project_id=20,
                   cost_category_id=1, effective_to=date(2025, 12, 31))
    r = resolve_rule([GLOBAL, partner_rule, project_rule, expired], partner_id=10, project_id=20, cost_category_id=1, on_date=TODAY)
    assert r.id == 2
    r2 = resolve_rule([GLOBAL, partner_rule], partner_id=11, project_id=20, cost_category_id=1, on_date=TODAY)
    assert r2.id == 1
