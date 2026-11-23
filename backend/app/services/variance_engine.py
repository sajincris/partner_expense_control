"""Plan-vs-actual variance engine.

Pure Python (Decimal only): no database, no framework. The service layer loads
plan lines, actuals and rules, calls :func:`evaluate_report`, and persists the
result. This keeps the financial logic deterministic and fully unit-testable.

Comparison grain: (cost category, GL account) for the report's period.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import ExceptionSeverity, ExceptionType, VarianceDirection

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, order=True)
class LineKey:
    cost_category_id: int
    gl_account_id: int


@dataclass(frozen=True)
class Rule:
    id: int
    name: str
    max_variance_pct: Decimal
    max_variance_abs: Decimal
    abs_currency: str = "USD"
    direction: VarianceDirection = VarianceDirection.OVERSPEND_ONLY
    partner_id: int | None = None
    project_id: int | None = None
    cost_category_id: int | None = None
    priority: int = 100
    effective_from: date = date(2000, 1, 1)
    effective_to: date | None = None
    is_active: bool = True

    @property
    def specificity(self) -> int:
        # Project-level scope outranks partner-level, which outranks category-level.
        return (4 if self.project_id else 0) + (2 if self.partner_id else 0) + (1 if self.cost_category_id else 0)


@dataclass(frozen=True)
class ActualLine:
    line_id: int | None
    key: LineKey
    amount: Decimal
    invoice_reference: str
    has_document: bool = True


@dataclass
class VarianceRow:
    key: LineKey
    planned: Decimal
    actual: Decimal
    variance: Decimal
    variance_pct: Decimal | None
    ytd_planned: Decimal
    ytd_actual: Decimal
    ytd_variance: Decimal
    annual_planned: Decimal
    remaining_budget: Decimal
    has_plan_line: bool
    within_tolerance: bool
    rule_id: int | None
    rule_name: str | None
    reason: str


@dataclass
class Finding:
    exception_type: ExceptionType
    severity: ExceptionSeverity
    message: str
    key: LineKey | None = None
    line_id: int | None = None
    planned: Decimal | None = None
    actual: Decimal | None = None
    variance: Decimal | None = None
    variance_pct: Decimal | None = None
    rule_id: int | None = None
    snapshot: dict = field(default_factory=dict)


@dataclass
class EvaluationResult:
    rows: list[VarianceRow]
    findings: list[Finding]
    total_planned: Decimal
    total_actual: Decimal
    total_variance: Decimal
    total_variance_pct: Decimal | None
    ytd_planned: Decimal
    ytd_actual: Decimal
    ytd_variance: Decimal
    annual_planned: Decimal
    remaining_budget: Decimal
    project_over_budget: bool

    @property
    def auto_accept(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {
            "total_planned": str(self.total_planned),
            "total_actual": str(self.total_actual),
            "total_variance": str(self.total_variance),
            "total_variance_pct": None if self.total_variance_pct is None else str(self.total_variance_pct),
            "ytd_planned": str(self.ytd_planned),
            "ytd_actual": str(self.ytd_actual),
            "ytd_variance": str(self.ytd_variance),
            "annual_planned": str(self.annual_planned),
            "remaining_budget": str(self.remaining_budget),
            "project_over_budget": self.project_over_budget,
            "auto_accept": self.auto_accept,
        }


# --------------------------------------------------------------------------- rules
def resolve_rule(
    rules: Iterable[Rule],
    *,
    partner_id: int,
    project_id: int,
    cost_category_id: int,
    on_date: date,
) -> Rule | None:
    """Return the most specific active rule matching the scope, or None."""

    def matches(r: Rule) -> bool:
        if not r.is_active or r.effective_from > on_date or (r.effective_to and r.effective_to < on_date):
            return False
        return (
            (r.partner_id is None or r.partner_id == partner_id)
            and (r.project_id is None or r.project_id == project_id)
            and (r.cost_category_id is None or r.cost_category_id == cost_category_id)
        )

    candidates = sorted((r for r in rules if matches(r)), key=lambda r: (-r.specificity, r.priority, r.id))
    return candidates[0] if candidates else None


def variance_pct(planned: Decimal, actual: Decimal) -> Decimal | None:
    """Variance % relative to plan. None when plan is zero (undefined)."""
    if planned == ZERO:
        return None if actual != ZERO else ZERO
    return q2((actual - planned) / planned * HUNDRED)


def check_tolerance(
    planned: Decimal, actual: Decimal, rule: Rule | None, fx_to_rule_ccy: Decimal = Decimal("1")
) -> tuple[bool, str]:
    """Return (within_tolerance, reason)."""
    if rule is None:
        return False, "No active tolerance rule applies - manual review required (fail-safe)."
    variance = actual - planned
    if rule.direction == VarianceDirection.OVERSPEND_ONLY and variance <= ZERO:
        return True, "Within plan (under-spend is not subject to approval under this rule)."
    tested_abs = abs(variance) * fx_to_rule_ccy
    pct = variance_pct(planned, actual)
    if pct is None:
        return False, "Spending against a zero plan for this period - percentage undefined."
    tested_pct = abs(pct)
    pct_ok = tested_pct <= rule.max_variance_pct
    abs_ok = q2(tested_abs) <= rule.max_variance_abs
    if pct_ok and abs_ok:
        return True, (
            f"Within tolerance: {tested_pct}% <= {rule.max_variance_pct}% and "
            f"{q2(tested_abs)} <= {rule.max_variance_abs} {rule.abs_currency}."
        )
    parts = []
    if not pct_ok:
        parts.append(f"{tested_pct}% > {rule.max_variance_pct}%")
    if not abs_ok:
        parts.append(f"{q2(tested_abs)} > {rule.max_variance_abs} {rule.abs_currency}")
    return False, "Outside tolerance: " + " and ".join(parts) + "."


# --------------------------------------------------------------------------- engine
def evaluate_report(
    *,
    partner_id: int,
    project_id: int,
    period: int,
    on_date: date,
    plan: Mapping[tuple[int, LineKey], Decimal],
    actual_lines: Iterable[ActualLine],
    prior_booked: Mapping[tuple[int, LineKey], Decimal],
    rules: Iterable[Rule],
    fx_to_rule_ccy: Decimal = Decimal("1"),
    external_duplicate_invoices: set[str] | None = None,
) -> EvaluationResult:
    """Evaluate a report against the active plan.

    plan: (period, key) -> planned amount for the fiscal year (active version).
    prior_booked: (period, key) -> actuals already AUTO_ACCEPTED/APPROVED in
      other reports of the same partner/project/fiscal year.
    external_duplicate_invoices: invoice references already used by other live
      reports of the same partner/project.
    """
    rules = list(rules)
    actual_lines = list(actual_lines)
    external_duplicate_invoices = {r.strip().upper() for r in (external_duplicate_invoices or set())}

    planned_keys_fy = {k for (_, k) in plan.keys()}
    actual_by_key: dict[LineKey, Decimal] = defaultdict(lambda: ZERO)
    for line in actual_lines:
        actual_by_key[line.key] += line.amount

    period_plan_keys = {k for (p, k), amt in plan.items() if p == period}
    keys = sorted(period_plan_keys | set(actual_by_key.keys()))

    rows: list[VarianceRow] = []
    findings: list[Finding] = []

    for key in keys:
        planned = q2(plan.get((period, key), ZERO))
        actual = q2(actual_by_key.get(key, ZERO))
        variance = actual - planned
        pct = variance_pct(planned, actual)
        annual = q2(sum((amt for (p, k), amt in plan.items() if k == key), ZERO))
        ytd_planned = q2(sum((amt for (p, k), amt in plan.items() if k == key and p <= period), ZERO))
        ytd_actual = q2(sum((amt for (p, k), amt in prior_booked.items() if k == key and p <= period), ZERO) + actual)
        has_plan = key in planned_keys_fy
        rule = resolve_rule(rules, partner_id=partner_id, project_id=project_id, cost_category_id=key.cost_category_id, on_date=on_date)

        if not has_plan:
            within, reason = False, "No approved plan line exists for this cost category / GL account in the fiscal year."
        else:
            within, reason = check_tolerance(planned, actual, rule, fx_to_rule_ccy)

        rows.append(
            VarianceRow(
                key=key, planned=planned, actual=actual, variance=variance, variance_pct=pct,
                ytd_planned=ytd_planned, ytd_actual=ytd_actual, ytd_variance=ytd_actual - ytd_planned,
                annual_planned=annual, remaining_budget=annual - q2(sum((amt for (p, k), amt in prior_booked.items() if k == key), ZERO)) - actual,
                has_plan_line=has_plan, within_tolerance=within,
                rule_id=rule.id if rule else None, rule_name=rule.name if rule else None, reason=reason,
            )
        )

        snapshot = {
            "period": period, "cost_category_id": key.cost_category_id, "gl_account_id": key.gl_account_id,
            "planned": str(planned), "actual": str(actual), "variance": str(variance),
            "variance_pct": None if pct is None else str(pct), "ytd_planned": str(ytd_planned),
            "ytd_actual": str(ytd_actual), "annual_planned": str(annual),
            "rule": None if rule is None else {
                "id": rule.id, "name": rule.name, "max_variance_pct": str(rule.max_variance_pct),
                "max_variance_abs": str(rule.max_variance_abs), "currency": rule.abs_currency,
                "direction": rule.direction.value,
            },
            "reason": reason,
        }

        if not has_plan:
            for line in (ln for ln in actual_lines if ln.key == key):
                findings.append(Finding(
                    exception_type=ExceptionType.NO_PLAN_LINE, severity=ExceptionSeverity.HIGH,
                    message=f"Expense line has no matching approved plan line (category {key.cost_category_id}, GL {key.gl_account_id}).",
                    key=key, line_id=line.line_id, planned=ZERO, actual=q2(line.amount), variance=q2(line.amount),
                    snapshot=snapshot,
                ))
        elif not within:
            severe = (
                rule is None
                or pct is None
                or abs(pct) > rule.max_variance_pct * 2
                or abs(variance) * fx_to_rule_ccy > rule.max_variance_abs * 2
            )
            findings.append(Finding(
                exception_type=ExceptionType.VARIANCE_OVER_TOLERANCE,
                severity=ExceptionSeverity.HIGH if severe else ExceptionSeverity.MEDIUM,
                message=reason, key=key, planned=planned, actual=actual, variance=variance, variance_pct=pct,
                rule_id=rule.id if rule else None, snapshot=snapshot,
            ))

    # Duplicate invoices: inside the report and against other live reports.
    seen: dict[str, int | None] = {}
    for line in actual_lines:
        ref = line.invoice_reference.strip().upper()
        if ref in seen or ref in external_duplicate_invoices:
            where = "earlier in this report" if ref in seen else "in another report for the same partner/project"
            findings.append(Finding(
                exception_type=ExceptionType.DUPLICATE_INVOICE, severity=ExceptionSeverity.HIGH,
                message=f"Invoice reference '{line.invoice_reference}' was already submitted {where}.",
                key=line.key, line_id=line.line_id, actual=q2(line.amount),
                snapshot={"invoice_reference": line.invoice_reference},
            ))
        seen.setdefault(ref, line.line_id)

    for line in actual_lines:
        if not line.has_document:
            findings.append(Finding(
                exception_type=ExceptionType.MISSING_DOCUMENT, severity=ExceptionSeverity.MEDIUM,
                message=f"No supporting document attached to invoice '{line.invoice_reference}'.",
                key=line.key, line_id=line.line_id, actual=q2(line.amount),
                snapshot={"invoice_reference": line.invoice_reference},
            ))

    total_planned = q2(sum((r.planned for r in rows), ZERO))
    total_actual = q2(sum((r.actual for r in rows), ZERO))
    ytd_planned = q2(sum((amt for (p, _), amt in plan.items() if p <= period), ZERO))
    ytd_actual = q2(sum((amt for (p, _), amt in prior_booked.items() if p <= period), ZERO) + total_actual)
    annual_planned = q2(sum(plan.values(), ZERO))
    all_booked = q2(sum(prior_booked.values(), ZERO))
    cumulative_actual = all_booked + total_actual
    over_budget = cumulative_actual > annual_planned

    if over_budget:
        findings.append(Finding(
            exception_type=ExceptionType.OVER_ANNUAL_BUDGET, severity=ExceptionSeverity.HIGH,
            message=f"Cumulative actuals {cumulative_actual} would exceed the approved annual plan {annual_planned}.",
            planned=annual_planned, actual=cumulative_actual, variance=cumulative_actual - annual_planned,
            snapshot={"annual_planned": str(annual_planned), "cumulative_actual": str(cumulative_actual)},
        ))

    return EvaluationResult(
        rows=rows, findings=findings,
        total_planned=total_planned, total_actual=total_actual,
        total_variance=total_actual - total_planned, total_variance_pct=variance_pct(total_planned, total_actual),
        ytd_planned=ytd_planned, ytd_actual=ytd_actual, ytd_variance=ytd_actual - ytd_planned,
        annual_planned=annual_planned, remaining_budget=annual_planned - cumulative_actual,
        project_over_budget=over_budget,
    )
