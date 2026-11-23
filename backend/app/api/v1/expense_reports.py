from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.enums import ReportStatus, RoleCode
from app.core.errors import NotFoundError
from app.models import ApprovalAction, CostCategory, ExpenseAttachment, ExpenseReport, GLAccount, Project, User
from app.models.base import as_utc, utcnow
from app.schemas.expense import (
    ApprovalActionOut,
    AttachmentOut,
    CancelRequest,
    ExpenseLineIn,
    ExpenseLineOut,
    ExpenseLineUpdate,
    ExpenseReportCreate,
    ExpenseReportDetail,
    ExpenseReportSummary,
    FindingOut,
    SubmitRequest,
    VarianceResultOut,
    VarianceReviewOut,
    VarianceRowOut,
)
from app.services import report_service
from app.services.dashboard_service import open_exception_stats
from app.services.storage import get_storage
from app.services.variance_service import evaluate
from app.utils.pagination import Page, PageParams, apply_sort, paginate
from app.workflows import report_workflow as wf
from app.workflows.state_machine import available_actions

router = APIRouter(prefix="/expense-reports", tags=["Expense reports"])
partner_only = require_roles(RoleCode.PARTNER)


# ------------------------------------------------------------------ serializers
def summary_out(r: ExpenseReport, stats: dict | None = None) -> ExpenseReportSummary:
    s = (stats or {}).get(r.id, {})
    return ExpenseReportSummary(
        id=r.id, report_number=r.report_number, partner_id=r.partner_id, partner_name=r.partner.name,
        project_id=r.project_id, project_code=r.project.code, project_name=r.project.name, fiscal_year=r.fiscal_year,
        period=r.period, currency=r.currency, status=r.status, total_amount=r.total_amount,
        requires_review=r.requires_review, open_exceptions=s.get("count", 0), submitted_at=r.submitted_at,
        review_due_at=r.review_due_at, is_overdue=bool(r.review_due_at and as_utc(r.review_due_at) < utcnow()),
        created_at=r.created_at,
    )


def line_out(ln) -> ExpenseLineOut:
    return ExpenseLineOut(
        id=ln.id, line_no=ln.line_no, expense_date=ln.expense_date, cost_category_id=ln.cost_category_id,
        cost_category_name=ln.cost_category.name, gl_account_id=ln.gl_account_id,
        gl_account_number=ln.gl_account.account_number, description=ln.description, amount=ln.amount,
        currency=ln.currency, invoice_reference=ln.invoice_reference, matched_plan_line_id=ln.matched_plan_line_id,
        attachments=[AttachmentOut.model_validate(a) for a in ln.attachments],
    )


def detail_out(db: Session, r: ExpenseReport, user: User) -> ExpenseReportDetail:
    db.refresh(r)
    stats = open_exception_stats(db, [r.id])
    actions = db.scalars(
        select(ApprovalAction).where(ApprovalAction.report_id == r.id).order_by(ApprovalAction.created_at, ApprovalAction.id)
    ).all()
    base = summary_out(r, stats).model_dump()
    return ExpenseReportDetail(
        **base,
        partner_comment=r.partner_comment, submission_count=r.submission_count, submitted_by_id=r.submitted_by_id,
        pm_approved_by_id=r.pm_approved_by_id, pm_approved_at=r.pm_approved_at,
        finance_approved_by_id=r.finance_approved_by_id, finance_approved_at=r.finance_approved_at,
        lines=[line_out(ln) for ln in r.lines],
        exceptions=[VarianceReviewOut.model_validate(e) for e in sorted(r.exceptions, key=lambda e: (-e.submission_no, e.id))],
        actions=[ApprovalActionOut(**ApprovalActionOut.model_validate(a).model_dump(exclude={"actor_name"}),
                                   actor_name=a.actor.full_name if a.actor else "System") for a in actions],
        available_actions=available_actions(r.status, user.role_codes),
    )


# ------------------------------------------------------------------ queries
@router.get("", response_model=Page[ExpenseReportSummary])
def list_reports(
    params: PageParams = Depends(),
    status: list[ReportStatus] | None = Query(None),
    fiscal_year: int | None = None,
    period: int | None = Query(None, ge=1, le=12),
    partner_id: int | None = None,
    project_id: int | None = None,
    overdue: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ExpenseReport).join(Project, Project.id == ExpenseReport.project_id)
    if not user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        if user.has_role(RoleCode.PROJECT_MANAGER):
            stmt = stmt.where(Project.project_manager_id == user.id)
        else:
            stmt = stmt.where(ExpenseReport.partner_id == (user.partner_id or -1))
    if status:
        stmt = stmt.where(ExpenseReport.status.in_(status))
    if fiscal_year:
        stmt = stmt.where(ExpenseReport.fiscal_year == fiscal_year)
    if period:
        stmt = stmt.where(ExpenseReport.period == period)
    if partner_id:
        stmt = stmt.where(ExpenseReport.partner_id == partner_id)
    if project_id:
        stmt = stmt.where(ExpenseReport.project_id == project_id)
    if overdue:
        stmt = stmt.where(ExpenseReport.review_due_at < utcnow())
    stmt = apply_sort(stmt, params.sort, {
        "created_at": ExpenseReport.created_at, "submitted_at": ExpenseReport.submitted_at, "period": ExpenseReport.period,
        "total_amount": ExpenseReport.total_amount, "status": ExpenseReport.status, "review_due_at": ExpenseReport.review_due_at,
    }, ExpenseReport.created_at.desc())
    page = paginate(db, stmt, params)
    stats = open_exception_stats(db, [r.id for r in page["items"]])
    page["items"] = [summary_out(r, stats) for r in page["items"]]
    return page


@router.post("", response_model=ExpenseReportDetail, status_code=201)
def create_report(body: ExpenseReportCreate, db: Session = Depends(get_db), user: User = Depends(partner_only)):
    report = report_service.create_report(db, body, user)
    db.commit()
    return detail_out(db, report, user)


@router.get("/{report_id}", response_model=ExpenseReportDetail)
def get_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return detail_out(db, wf.get_report_for(db, report_id, user), user)


@router.get("/{report_id}/variance", response_model=VarianceResultOut,
            summary="Plan vs actual calculation (live preview for drafts, recomputed for submitted reports)")
def variance(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = wf.get_report_for(db, report_id, user)
    on = report.submitted_at.date() if report.submitted_at else date.today()
    result, _ = evaluate(db, report, on_date=on)
    cats = {c.id: c.name for c in db.scalars(select(CostCategory)).all()}
    gls = {g.id: g.account_number for g in db.scalars(select(GLAccount)).all()}
    return VarianceResultOut(
        report_id=report.id,
        rows=[VarianceRowOut(
            cost_category_id=r.key.cost_category_id, cost_category_name=cats.get(r.key.cost_category_id),
            gl_account_id=r.key.gl_account_id, gl_account_number=gls.get(r.key.gl_account_id),
            planned=r.planned, actual=r.actual, variance=r.variance, variance_pct=r.variance_pct,
            ytd_planned=r.ytd_planned, ytd_actual=r.ytd_actual, ytd_variance=r.ytd_variance,
            annual_planned=r.annual_planned, remaining_budget=r.remaining_budget, has_plan_line=r.has_plan_line,
            within_tolerance=r.within_tolerance, rule_name=r.rule_name, reason=r.reason,
        ) for r in result.rows],
        findings=[FindingOut(exception_type=f.exception_type, severity=f.severity, message=f.message, line_id=f.line_id) for f in result.findings],
        totals=result.as_dict(),
        auto_accept=result.auto_accept,
    )


# ------------------------------------------------------------------ lines (partner, editable statuses only)
@router.post("/{report_id}/lines", response_model=ExpenseLineOut, status_code=201)
def add_line(report_id: int, body: ExpenseLineIn, db: Session = Depends(get_db), user: User = Depends(partner_only)):
    report = wf.get_report_for(db, report_id, user)
    line = report_service.add_line(db, report, body, user)
    db.commit()
    db.refresh(line)
    return line_out(line)


@router.patch("/{report_id}/lines/{line_id}", response_model=ExpenseLineOut)
def update_line(report_id: int, line_id: int, body: ExpenseLineUpdate, db: Session = Depends(get_db), user: User = Depends(partner_only)):
    report = wf.get_report_for(db, report_id, user)
    line = report_service.update_line(db, report, line_id, body, user)
    db.commit()
    db.refresh(line)
    return line_out(line)


@router.delete("/{report_id}/lines/{line_id}", status_code=204)
def delete_line(report_id: int, line_id: int, db: Session = Depends(get_db), user: User = Depends(partner_only)):
    report = wf.get_report_for(db, report_id, user)
    report_service.delete_line(db, report, line_id, user)
    db.commit()


@router.post("/{report_id}/attachments", response_model=AttachmentOut, status_code=201,
             summary="Upload a supporting document (PDF, image, CSV, XLSX)")
async def upload(report_id: int, file: UploadFile = File(...), line_id: int | None = Form(None),
                 db: Session = Depends(get_db), user: User = Depends(partner_only)):
    report = wf.get_report_for(db, report_id, user)
    att = report_service.upload_attachment(db, report, line_id, data=await file.read(), filename=file.filename or "document",
                                           content_type=file.content_type or "application/octet-stream", actor=user)
    db.commit()
    return att


@router.get("/{report_id}/attachments/{attachment_id}/download")
def download(report_id: int, attachment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wf.get_report_for(db, report_id, user)
    att = db.get(ExpenseAttachment, attachment_id)
    if not att or att.report_id != report_id or att.is_deleted:
        raise NotFoundError("Attachment not found.")
    return StreamingResponse(get_storage().open(att.storage_key), media_type=att.content_type,
                             headers={"Content-Disposition": f'attachment; filename="{att.original_filename}"'})


# ------------------------------------------------------------------ partner workflow actions
@router.post("/{report_id}/submit", response_model=ExpenseReportDetail,
             summary="Submit (or resubmit after clarification). Runs validation and the variance engine.")
def submit(report_id: int, body: SubmitRequest | None = None, db: Session = Depends(get_db), user: User = Depends(partner_only)):
    report = wf.get_report_for(db, report_id, user)
    wf.submit_report(db, report, user, comment=body.comment if body else None)
    db.commit()
    return detail_out(db, report, user)


@router.post("/{report_id}/cancel", response_model=ExpenseReportDetail)
def cancel(report_id: int, body: CancelRequest, db: Session = Depends(get_db), user: User = Depends(partner_only)):
    report = wf.get_report_for(db, report_id, user)
    wf.cancel_report(db, report, user, body.comment)
    db.commit()
    return detail_out(db, report, user)
