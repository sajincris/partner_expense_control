from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.enums import RoleCode
from app.models import ExpenseReport, Project, User
from app.schemas.expense import ExpenseReportDetail, QueueItem, ReviewRequest
from app.services.dashboard_service import open_exception_stats, queue_filters
from app.utils.pagination import Page, PageParams, apply_sort, paginate
from app.workflows import report_workflow as wf

from .expense_reports import detail_out, summary_out

router = APIRouter(tags=["Variance reviews"])
reviewers = require_roles(RoleCode.PROJECT_MANAGER, RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR)
pm_only = require_roles(RoleCode.PROJECT_MANAGER)
finance_only = require_roles(RoleCode.FINANCE_OFFICER)


@router.get("/reviews/queue", response_model=Page[QueueItem], summary="Variance exception queue")
def queue(
    params: PageParams = Depends(),
    stage: Literal["PM", "FINANCE"] | None = None,
    overdue: bool | None = None,
    project_id: int | None = None,
    partner_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(reviewers),
):
    stmt = select(ExpenseReport).join(Project, Project.id == ExpenseReport.project_id).where(*queue_filters(stage, overdue))
    if user.has_role(RoleCode.PROJECT_MANAGER) and not user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        stmt = stmt.where(Project.project_manager_id == user.id)
    if project_id:
        stmt = stmt.where(ExpenseReport.project_id == project_id)
    if partner_id:
        stmt = stmt.where(ExpenseReport.partner_id == partner_id)
    stmt = apply_sort(stmt, params.sort, {"review_due_at": ExpenseReport.review_due_at, "submitted_at": ExpenseReport.submitted_at,
                                          "total_amount": ExpenseReport.total_amount}, ExpenseReport.review_due_at.asc())
    page = paginate(db, stmt, params)
    stats = open_exception_stats(db, [r.id for r in page["items"]])
    items = []
    for r in page["items"]:
        s = stats.get(r.id, {})
        items.append(QueueItem(
            **summary_out(r, stats).model_dump(),
            stage="PM" if r.status.value == "PENDING_PM_REVIEW" else "FINANCE",
            highest_severity=s.get("severity"), exception_types=sorted(s.get("types", set()), key=lambda t: t.value),
            max_variance_pct=s.get("max_pct"),
        ))
    page["items"] = items
    return page


@router.post("/expense-reports/{report_id}/pm-review", response_model=ExpenseReportDetail,
             summary="Project Manager decision: APPROVE (-> Finance), REJECT or RETURN. Comment mandatory.")
def pm_review(report_id: int, body: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(pm_only)):
    report = wf.get_report_for(db, report_id, user)
    wf.pm_review(db, report, user, body.decision, body.comment)
    db.commit()
    return detail_out(db, report, user)


@router.post("/expense-reports/{report_id}/finance-review", response_model=ExpenseReportDetail,
             summary="Finance decision (final approver). APPROVE requires the checklist and a prior PM approval.")
def finance_review(report_id: int, body: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(finance_only)):
    report = wf.get_report_for(db, report_id, user)
    wf.finance_review(db, report, user, body.decision, body.comment,
                      checklist=body.checklist.model_dump() if body.checklist else None)
    db.commit()
    return detail_out(db, report, user)
