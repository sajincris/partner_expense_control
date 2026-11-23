"""Read models for dashboards and management reports.

All figures are scoped to what the caller may see: partners see their own
organisation, project managers their own projects, finance and auditors all.
"""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.enums import BOOKED_STATUSES, BudgetVersionStatus, ExceptionStatus, ExceptionType, ReportStatus, RoleCode
from app.models import (
    BudgetPlan,
    BudgetPlanLine,
    BudgetPlanVersion,
    CostCategory,
    ExpenseLine,
    ExpenseReport,
    GLAccount,
    Partner,
    Project,
    User,
    VarianceReview,
)
from app.models.base import utcnow
from app.services.variance_engine import q2, variance_pct

PENDING = (ReportStatus.PENDING_PM_REVIEW, ReportStatus.PENDING_FINANCE_REVIEW)
D0 = Decimal("0.00")


def _d(value) -> Decimal:
    """DB aggregates may come back as float on SQLite; go through str to stay exact."""
    return Decimal(str(value or 0))


def _project_ids_for_pm(db: Session, user: User) -> list[int] | None:
    if user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        return None
    if user.has_role(RoleCode.PROJECT_MANAGER):
        return list(db.scalars(select(Project.id).where(Project.project_manager_id == user.id)).all())
    return None


def _report_filters(db: Session, user: User, fiscal_year: int | None, partner_id: int | None = None, project_id: int | None = None) -> list:
    f = []
    if fiscal_year:
        f.append(ExpenseReport.fiscal_year == fiscal_year)
    if user.has_role(RoleCode.PARTNER) and not user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        f.append(ExpenseReport.partner_id == (user.partner_id or -1))
    pm_projects = _project_ids_for_pm(db, user)
    if pm_projects is not None and not user.has_role(RoleCode.PARTNER):
        f.append(ExpenseReport.project_id.in_(pm_projects or [-1]))
    if partner_id:
        f.append(ExpenseReport.partner_id == partner_id)
    if project_id:
        f.append(ExpenseReport.project_id == project_id)
    return f


def _plan_filters(db: Session, user: User, fiscal_year: int | None, partner_id: int | None = None, project_id: int | None = None) -> list:
    f = [BudgetPlanVersion.status == BudgetVersionStatus.ACTIVE]
    if fiscal_year:
        f.append(BudgetPlan.fiscal_year == fiscal_year)
    if user.has_role(RoleCode.PARTNER) and not user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        f.append(BudgetPlan.partner_id == (user.partner_id or -1))
    pm_projects = _project_ids_for_pm(db, user)
    if pm_projects is not None and not user.has_role(RoleCode.PARTNER):
        f.append(BudgetPlan.project_id.in_(pm_projects or [-1]))
    if partner_id:
        f.append(BudgetPlan.partner_id == partner_id)
    if project_id:
        f.append(BudgetPlan.project_id == project_id)
    return f


def _planned_stmt(*group_cols):
    return (
        select(*group_cols, func.coalesce(func.sum(BudgetPlanLine.planned_amount), 0))
        .select_from(BudgetPlanLine)
        .join(BudgetPlanVersion, BudgetPlanVersion.id == BudgetPlanLine.version_id)
        .join(BudgetPlan, BudgetPlan.id == BudgetPlanVersion.budget_plan_id)
    )


def _actual_stmt(*group_cols):
    return (
        select(*group_cols, func.coalesce(func.sum(ExpenseLine.amount), 0))
        .select_from(ExpenseLine)
        .join(ExpenseReport, ExpenseReport.id == ExpenseLine.report_id)
        .where(ExpenseLine.is_deleted.is_(False))
    )


def summary(db: Session, user: User, fiscal_year: int) -> dict:
    rf = _report_filters(db, user, fiscal_year)
    counts = dict(db.execute(select(ExpenseReport.status, func.count()).where(*rf).group_by(ExpenseReport.status)).all())
    planned = db.execute(_planned_stmt().where(*_plan_filters(db, user, fiscal_year))).scalar() or 0
    booked = db.execute(_actual_stmt().where(*rf, ExpenseReport.status.in_(BOOKED_STATUSES))).scalar() or 0
    pending_amt = db.execute(_actual_stmt().where(*rf, ExpenseReport.status.in_(PENDING))).scalar() or 0
    overdue = db.scalar(select(func.count()).select_from(ExpenseReport).where(
        *rf, ExpenseReport.status.in_(PENDING), ExpenseReport.review_due_at < utcnow())) or 0
    open_exc = db.scalar(select(func.count()).select_from(VarianceReview).join(ExpenseReport).where(
        *rf, VarianceReview.status == ExceptionStatus.OPEN)) or 0
    planned, booked = q2(_d(planned)), q2(_d(booked))
    over_budget = [p for p in by_project(db, user, fiscal_year) if p["over_budget"]]
    return {
        "fiscal_year": fiscal_year,
        "planned_total": planned,
        "actual_booked": booked,
        "actual_pending_review": q2(_d(pending_amt)),
        "variance": booked - planned,
        "utilization_pct": q2(booked / planned * 100) if planned else None,
        "remaining_budget": planned - booked,
        "status_counts": {s.value: counts.get(s, 0) for s in ReportStatus},
        "pending_pm_review": counts.get(ReportStatus.PENDING_PM_REVIEW, 0),
        "pending_finance_review": counts.get(ReportStatus.PENDING_FINANCE_REVIEW, 0),
        "overdue_reviews": overdue,
        "open_exceptions": open_exc,
        "over_budget_projects": len(over_budget),
    }


def plan_vs_actual_by_period(db: Session, user: User, fiscal_year: int, partner_id: int | None = None, project_id: int | None = None) -> list[dict]:
    pf = _plan_filters(db, user, fiscal_year, partner_id, project_id)
    rf = _report_filters(db, user, fiscal_year, partner_id, project_id)
    planned = dict(db.execute(_planned_stmt(BudgetPlanLine.period).where(*pf).group_by(BudgetPlanLine.period)).all())
    booked = dict(db.execute(_actual_stmt(ExpenseReport.period).where(*rf, ExpenseReport.status.in_(BOOKED_STATUSES)).group_by(ExpenseReport.period)).all())
    pending = dict(db.execute(_actual_stmt(ExpenseReport.period).where(*rf, ExpenseReport.status.in_(PENDING)).group_by(ExpenseReport.period)).all())
    out, cum_p, cum_a = [], D0, D0
    for period in range(1, 13):
        p, a = q2(_d(planned.get(period, 0))), q2(_d(booked.get(period, 0)))
        cum_p += p
        cum_a += a
        out.append({
            "period": period, "planned": p, "actual": a, "pending": q2(_d(pending.get(period, 0))),
            "variance": a - p, "variance_pct": variance_pct(p, a) if a else None,
            "ytd_planned": cum_p, "ytd_actual": cum_a, "ytd_variance": cum_a - cum_p,
        })
    return out


def _totals_by(db: Session, user: User, fiscal_year: int, plan_col, report_col) -> tuple[dict, dict, dict]:
    pf = _plan_filters(db, user, fiscal_year)
    rf = _report_filters(db, user, fiscal_year)
    planned = dict(db.execute(_planned_stmt(plan_col).where(*pf).group_by(plan_col)).all())
    booked = dict(db.execute(_actual_stmt(report_col).where(*rf, ExpenseReport.status.in_(BOOKED_STATUSES)).group_by(report_col)).all())
    pending = dict(db.execute(_actual_stmt(report_col).where(*rf, ExpenseReport.status.in_(PENDING)).group_by(report_col)).all())
    return planned, booked, pending


def _rows(entities, planned, booked, pending, label) -> list[dict]:
    rows = []
    for e in entities:
        p, a = q2(_d(planned.get(e.id, 0))), q2(_d(booked.get(e.id, 0)))
        if not p and not a and not pending.get(e.id):
            continue
        rows.append({
            "id": e.id, "code": e.code, "name": e.name, **label(e), "planned": p, "actual": a,
            "pending": q2(_d(pending.get(e.id, 0))), "variance": a - p,
            "utilization_pct": q2(a / p * 100) if p else None, "remaining_budget": p - a, "over_budget": a > p,
        })
    return rows


def by_project(db: Session, user: User, fiscal_year: int) -> list[dict]:
    planned, booked, pending = _totals_by(db, user, fiscal_year, BudgetPlan.project_id, ExpenseReport.project_id)
    projects = db.scalars(select(Project).where(Project.is_deleted.is_(False)).order_by(Project.code)).all()
    return _rows(projects, planned, booked, pending, lambda p: {"donor": p.donor})


def by_partner(db: Session, user: User, fiscal_year: int) -> list[dict]:
    planned, booked, pending = _totals_by(db, user, fiscal_year, BudgetPlan.partner_id, ExpenseReport.partner_id)
    partners = db.scalars(select(Partner).where(Partner.is_deleted.is_(False)).order_by(Partner.code)).all()
    return _rows(partners, planned, booked, pending, lambda p: {"country": p.country})


def top_variances(db: Session, user: User, fiscal_year: int, limit: int = 10) -> list[dict]:
    rf = _report_filters(db, user, fiscal_year)
    stmt = (
        select(VarianceReview, ExpenseReport, CostCategory.name, GLAccount.account_number)
        .join(ExpenseReport, ExpenseReport.id == VarianceReview.report_id)
        .outerjoin(CostCategory, CostCategory.id == VarianceReview.cost_category_id)
        .outerjoin(GLAccount, GLAccount.id == VarianceReview.gl_account_id)
        .where(*rf, VarianceReview.exception_type == ExceptionType.VARIANCE_OVER_TOLERANCE,
               VarianceReview.status != ExceptionStatus.SUPERSEDED)
        .order_by(func.abs(VarianceReview.variance_amount).desc())
        .limit(limit)
    )
    return [
        {
            "exception_id": v.id, "report_id": r.id, "report_number": r.report_number, "partner_name": r.partner.name,
            "project_code": r.project.code, "period": r.period, "cost_category": cat, "gl_account": gl,
            "planned": v.planned_amount, "actual": v.actual_amount, "variance": v.variance_amount,
            "variance_pct": v.variance_pct, "severity": v.severity.value, "exception_status": v.status.value,
            "report_status": r.status.value,
        }
        for v, r, cat, gl in db.execute(stmt).all()
    ]


def monthly_variance_report(db: Session, user: User, fiscal_year: int, period: int) -> list[dict]:
    """Plan vs actual per partner/project/category/GL for one period (booked + pending shown separately)."""
    pf = _plan_filters(db, user, fiscal_year)
    rf = _report_filters(db, user, fiscal_year)
    key_cols_p = (BudgetPlan.partner_id, BudgetPlan.project_id, BudgetPlanLine.cost_category_id, BudgetPlanLine.gl_account_id)
    key_cols_a = (ExpenseReport.partner_id, ExpenseReport.project_id, ExpenseLine.cost_category_id, ExpenseLine.gl_account_id)
    planned = {tuple(r[:4]): r[4] for r in db.execute(_planned_stmt(*key_cols_p).where(*pf, BudgetPlanLine.period == period).group_by(*key_cols_p)).all()}
    booked = {tuple(r[:4]): r[4] for r in db.execute(_actual_stmt(*key_cols_a).where(*rf, ExpenseReport.period == period, ExpenseReport.status.in_(BOOKED_STATUSES)).group_by(*key_cols_a)).all()}
    pending = {tuple(r[:4]): r[4] for r in db.execute(_actual_stmt(*key_cols_a).where(*rf, ExpenseReport.period == period, ExpenseReport.status.in_(PENDING)).group_by(*key_cols_a)).all()}
    statuses = {(r.partner_id, r.project_id): r.status.value for r in db.scalars(select(ExpenseReport).where(*rf, ExpenseReport.period == period, ExpenseReport.status != ReportStatus.CANCELLED)).all()}

    partners = {p.id: p for p in db.scalars(select(Partner)).all()}
    projects = {p.id: p for p in db.scalars(select(Project)).all()}
    cats = {c.id: c for c in db.scalars(select(CostCategory)).all()}
    gls = {g.id: g for g in db.scalars(select(GLAccount)).all()}
    rows = []
    for key in sorted(set(planned) | set(booked) | set(pending)):
        pa, pr, cat, gl = key
        p, a = q2(_d(planned.get(key, 0))), q2(_d(booked.get(key, 0)))
        rows.append({
            "fiscal_year": fiscal_year, "period": period, "partner": partners[pa].name, "project": projects[pr].code,
            "cost_category": cats[cat].name, "gl_account": gls[gl].account_number, "planned": p, "actual_booked": a,
            "actual_pending": q2(_d(pending.get(key, 0))), "variance": a - p,
            "variance_pct": variance_pct(p, a) if a or p else None,
            "report_status": statuses.get((pa, pr), "NOT_SUBMITTED"),
        })
    return rows


def queue_filters(stage: str | None, overdue: bool | None) -> list:
    f = []
    if stage == "PM":
        f.append(ExpenseReport.status == ReportStatus.PENDING_PM_REVIEW)
    elif stage == "FINANCE":
        f.append(ExpenseReport.status == ReportStatus.PENDING_FINANCE_REVIEW)
    else:
        f.append(ExpenseReport.status.in_(PENDING))
    if overdue:
        f.append(and_(ExpenseReport.review_due_at.is_not(None), ExpenseReport.review_due_at < utcnow()))
    return f


def open_exception_stats(db: Session, report_ids: list[int]) -> dict[int, dict]:
    if not report_ids:
        return {}
    rows = db.scalars(select(VarianceReview).where(VarianceReview.report_id.in_(report_ids), VarianceReview.status == ExceptionStatus.OPEN)).all()
    stats: dict[int, dict] = defaultdict(lambda: {"count": 0, "types": set(), "severity": None, "max_pct": None})
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    for v in rows:
        s = stats[v.report_id]
        s["count"] += 1
        s["types"].add(v.exception_type)
        if s["severity"] is None or order[v.severity.value] > order[s["severity"].value]:
            s["severity"] = v.severity
        if v.variance_pct is not None and (s["max_pct"] is None or abs(v.variance_pct) > abs(s["max_pct"])):
            s["max_pct"] = v.variance_pct
    return stats
