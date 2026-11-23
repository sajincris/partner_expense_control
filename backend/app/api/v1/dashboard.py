from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.enums import ReportStatus, RoleCode
from app.models import ExpenseReport, Project, User
from app.services import dashboard_service as ds
from app.services.audit import record_event, to_jsonable
from app.services.export_service import export_rows

router = APIRouter(tags=["Dashboard & reports"])
internal_readers = require_roles(RoleCode.PROJECT_MANAGER, RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR)


def money_json(data) -> JSONResponse:
    """Serialise money as exact decimal strings (never floats)."""
    return JSONResponse(to_jsonable(data))


def _fy(fiscal_year: int | None) -> int:
    return fiscal_year or date.today().year


@router.get("/dashboard/summary")
def summary(fiscal_year: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return money_json(ds.summary(db, user, _fy(fiscal_year)))


@router.get("/dashboard/plan-vs-actual")
def plan_vs_actual(fiscal_year: int | None = None, partner_id: int | None = None, project_id: int | None = None,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return money_json(ds.plan_vs_actual_by_period(db, user, _fy(fiscal_year), partner_id, project_id))


@router.get("/dashboard/projects")
def projects(fiscal_year: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return money_json(ds.by_project(db, user, _fy(fiscal_year)))


@router.get("/dashboard/partners")
def partners(fiscal_year: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return money_json(ds.by_partner(db, user, _fy(fiscal_year)))


@router.get("/dashboard/top-variances")
def top_variances(fiscal_year: int | None = None, limit: int = Query(10, ge=1, le=100),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return money_json(ds.top_variances(db, user, _fy(fiscal_year), limit))


# ------------------------------------------------------------------ reports & exports
@router.get("/reports/monthly-variance", summary="Monthly variance report (json | csv | xlsx)")
def monthly_variance(fiscal_year: int, period: int = Query(..., ge=1, le=12), format: str = Query("json", pattern="^(json|csv|xlsx)$"),
                     db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = ds.monthly_variance_report(db, user, fiscal_year, period)
    if format == "json":
        return money_json(rows)
    record_event(db, entity_type="reports", entity_id=f"monthly-variance-{fiscal_year}-{period:02d}", action="EXPORT",
                 new_values={"format": format, "rows": len(rows)})
    db.commit()
    return export_rows(rows, filename=f"monthly-variance-{fiscal_year}-{period:02d}", fmt=format, title="Monthly variance")


@router.get("/reports/expense-reports/export", summary="Expense report register export (csv | xlsx)")
def export_register(fiscal_year: int | None = None, status: list[ReportStatus] | None = Query(None),
                    format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(ExpenseReport).join(Project, Project.id == ExpenseReport.project_id).where(*ds._report_filters(db, user, fiscal_year))
    if status:
        stmt = stmt.where(ExpenseReport.status.in_(status))
    reports = db.scalars(stmt.order_by(ExpenseReport.fiscal_year, ExpenseReport.period, ExpenseReport.report_number)).all()
    rows = [{
        "report_number": r.report_number, "partner": r.partner.name, "project": r.project.code, "fiscal_year": r.fiscal_year,
        "period": r.period, "currency": r.currency, "total_amount": r.total_amount, "status": r.status.value,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "pm_approved_at": r.pm_approved_at.isoformat() if r.pm_approved_at else None,
        "finance_approved_at": r.finance_approved_at.isoformat() if r.finance_approved_at else None,
        "open_exceptions": sum(1 for e in r.exceptions if e.status.value == "OPEN"),
    } for r in reports]
    record_event(db, entity_type="reports", entity_id="expense-register", action="EXPORT", new_values={"format": format, "rows": len(rows)})
    db.commit()
    return export_rows(rows, filename=f"expense-register-{fiscal_year or 'all'}", fmt=format, title="Expense reports")


@router.get("/reports/top-variances/export")
def export_top_variances(fiscal_year: int | None = None, format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
                         db: Session = Depends(get_db), user: User = Depends(internal_readers)):
    rows = ds.top_variances(db, user, _fy(fiscal_year), limit=500)
    record_event(db, entity_type="reports", entity_id="top-variances", action="EXPORT", new_values={"format": format})
    db.commit()
    return export_rows(rows, filename="top-variances", fmt=format, title="Top variances")
