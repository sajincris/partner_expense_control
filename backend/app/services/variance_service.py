"""Bridges the database and the pure variance engine."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import BOOKED_STATUSES, INVOICE_HOLDING_STATUSES, BudgetVersionStatus
from app.core.errors import ValidationFailedError
from app.models import (
    BudgetPlan,
    BudgetPlanLine,
    BudgetPlanVersion,
    ExchangeRate,
    ExpenseLine,
    ExpenseReport,
    ToleranceRule,
)
from app.services.variance_engine import ActualLine, EvaluationResult, LineKey, Rule, evaluate_report


def active_version(db: Session, partner_id: int, project_id: int, fiscal_year: int) -> BudgetPlanVersion | None:
    stmt = (
        select(BudgetPlanVersion)
        .join(BudgetPlan, BudgetPlan.id == BudgetPlanVersion.budget_plan_id)
        .where(
            BudgetPlan.partner_id == partner_id,
            BudgetPlan.project_id == project_id,
            BudgetPlan.fiscal_year == fiscal_year,
            BudgetPlanVersion.status == BudgetVersionStatus.ACTIVE,
        )
    )
    return db.scalars(stmt).first()


def load_plan(db: Session, version: BudgetPlanVersion) -> tuple[dict, dict]:
    """Return ((period, key) -> amount, (period, key) -> plan_line_id)."""
    lines = db.scalars(select(BudgetPlanLine).where(BudgetPlanLine.version_id == version.id)).all()
    plan = {(ln.period, LineKey(ln.cost_category_id, ln.gl_account_id)): ln.planned_amount for ln in lines}
    ids = {(ln.period, LineKey(ln.cost_category_id, ln.gl_account_id)): ln.id for ln in lines}
    return plan, ids


def load_prior_booked(db: Session, report: ExpenseReport) -> dict:
    stmt = (
        select(ExpenseReport.period, ExpenseLine.cost_category_id, ExpenseLine.gl_account_id, func.sum(ExpenseLine.amount))
        .join(ExpenseLine, ExpenseLine.report_id == ExpenseReport.id)
        .where(
            ExpenseReport.partner_id == report.partner_id,
            ExpenseReport.project_id == report.project_id,
            ExpenseReport.fiscal_year == report.fiscal_year,
            ExpenseReport.id != report.id,
            ExpenseReport.status.in_(BOOKED_STATUSES),
            ExpenseLine.is_deleted.is_(False),
        )
        .group_by(ExpenseReport.period, ExpenseLine.cost_category_id, ExpenseLine.gl_account_id)
    )
    out: dict = defaultdict(lambda: Decimal("0"))
    for period, cat, gl, total in db.execute(stmt).all():
        out[(period, LineKey(cat, gl))] += Decimal(str(total))
    return dict(out)


def load_external_duplicates(db: Session, report: ExpenseReport, refs: set[str]) -> set[str]:
    if not refs:
        return set()
    stmt = (
        select(func.upper(func.trim(ExpenseLine.invoice_reference)))
        .join(ExpenseReport, ExpenseReport.id == ExpenseLine.report_id)
        .where(
            ExpenseReport.partner_id == report.partner_id,
            ExpenseReport.project_id == report.project_id,
            ExpenseReport.id != report.id,
            ExpenseReport.status.in_(INVOICE_HOLDING_STATUSES),
            ExpenseLine.is_deleted.is_(False),
            func.upper(func.trim(ExpenseLine.invoice_reference)).in_(refs),
        )
    )
    return set(db.scalars(stmt).all())


def load_rules(db: Session) -> list[Rule]:
    rows = db.scalars(select(ToleranceRule).where(ToleranceRule.is_active.is_(True))).all()
    return [
        Rule(
            id=r.id, name=r.name, max_variance_pct=r.max_variance_pct, max_variance_abs=r.max_variance_abs,
            abs_currency=r.abs_currency, direction=r.direction, partner_id=r.partner_id, project_id=r.project_id,
            cost_category_id=r.cost_category_id, priority=r.priority, effective_from=r.effective_from,
            effective_to=r.effective_to, is_active=r.is_active,
        )
        for r in rows
    ]


def fx_rate(db: Session, from_ccy: str, to_ccy: str, on: date) -> Decimal:
    if from_ccy == to_ccy:
        return Decimal("1")
    rate = db.scalars(
        select(ExchangeRate.rate)
        .where(ExchangeRate.from_currency == from_ccy, ExchangeRate.to_currency == to_ccy, ExchangeRate.rate_date <= on)
        .order_by(ExchangeRate.rate_date.desc())
    ).first()
    if rate is None:
        raise ValidationFailedError(f"No exchange rate {from_ccy}->{to_ccy} on or before {on}.")
    return Decimal(rate)


def evaluate(db: Session, report: ExpenseReport, *, on_date: date | None = None) -> tuple[EvaluationResult, dict]:
    version = active_version(db, report.partner_id, report.project_id, report.fiscal_year)
    if version is None:
        raise ValidationFailedError(
            "No ACTIVE budget plan version exists for this partner, project and fiscal year.",
            code="NO_ACTIVE_PLAN",
        )
    plan, plan_ids = load_plan(db, version)
    lines = [ln for ln in report.lines if not ln.is_deleted]
    actuals = [
        ActualLine(
            line_id=ln.id, key=LineKey(ln.cost_category_id, ln.gl_account_id), amount=ln.amount,
            invoice_reference=ln.invoice_reference, has_document=bool(ln.attachments),
        )
        for ln in lines
    ]
    refs = {ln.invoice_reference.strip().upper() for ln in lines}
    on = on_date or date.today()
    result = evaluate_report(
        partner_id=report.partner_id, project_id=report.project_id, period=report.period, on_date=on,
        plan=plan, actual_lines=actuals, prior_booked=load_prior_booked(db, report), rules=load_rules(db),
        fx_to_rule_ccy=fx_rate(db, report.currency, settings.BASE_CURRENCY, on),
        external_duplicate_invoices=load_external_duplicates(db, report, refs),
    )
    return result, {"version": version, "plan_ids": plan_ids}
