"""Expense report creation and line maintenance (partner side)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ReportStatus, RoleCode
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models import (
    CostCategory,
    ExpenseAttachment,
    ExpenseLine,
    ExpenseReport,
    GLAccount,
    Project,
    ProjectPartner,
    User,
)
from app.models.base import utcnow
from app.schemas.expense import ExpenseLineIn, ExpenseLineUpdate, ExpenseReportCreate
from app.services.audit import record_event
from app.services.storage import get_storage, validate_upload
from app.workflows.report_workflow import assert_editable, assert_partner_owner


def _next_report_number(db: Session, fiscal_year: int) -> str:
    count = db.scalar(select(func.count(ExpenseReport.id)).where(ExpenseReport.fiscal_year == fiscal_year)) or 0
    return f"ER-{fiscal_year}-{count + 1:05d}"


def create_report(db: Session, data: ExpenseReportCreate, actor: User) -> ExpenseReport:
    if not actor.has_role(RoleCode.PARTNER) or actor.partner_id is None:
        raise PermissionDeniedError("Only partner users can create expense reports.")
    partner_id = actor.partner_id
    project = db.get(Project, data.project_id)
    if project is None or project.is_deleted:
        raise NotFoundError("Project not found.")
    link = db.scalars(select(ProjectPartner).where(
        ProjectPartner.project_id == project.id, ProjectPartner.partner_id == partner_id, ProjectPartner.is_active.is_(True)
    )).first()
    if link is None:
        raise PermissionDeniedError("Your organisation is not an implementing partner of this project.")
    existing = db.scalars(select(ExpenseReport).where(
        ExpenseReport.partner_id == partner_id, ExpenseReport.project_id == project.id,
        ExpenseReport.fiscal_year == data.fiscal_year, ExpenseReport.period == data.period,
        ExpenseReport.status.not_in([ReportStatus.CANCELLED, ReportStatus.REJECTED]),
    )).first()
    if existing:
        raise ConflictError("A report already exists for this project and period.", details={"report_id": existing.id})
    report = ExpenseReport(
        report_number=_next_report_number(db, data.fiscal_year), partner_id=partner_id, project_id=project.id,
        fiscal_year=data.fiscal_year, period=data.period, currency=data.currency, status=ReportStatus.DRAFT,
        partner_comment=data.partner_comment, created_by_id=actor.id,
    )
    db.add(report)
    db.flush()
    return report


def _validate_line_refs(db: Session, cost_category_id: int | None, gl_account_id: int | None) -> None:
    if cost_category_id is not None and db.get(CostCategory, cost_category_id) is None:
        raise ValidationFailedError("Unknown cost category.")
    if gl_account_id is not None:
        gl = db.get(GLAccount, gl_account_id)
        if gl is None:
            raise ValidationFailedError("Unknown GL account.")
        if cost_category_id is not None and gl.cost_category_id not in (None, cost_category_id):
            raise ValidationFailedError(f"GL account {gl.account_number} is not mapped to the selected cost category.")


def add_line(db: Session, report: ExpenseReport, data: ExpenseLineIn, actor: User) -> ExpenseLine:
    assert_partner_owner(actor, report)
    assert_editable(report)
    _validate_line_refs(db, data.cost_category_id, data.gl_account_id)
    next_no = (db.scalar(select(func.max(ExpenseLine.line_no)).where(ExpenseLine.report_id == report.id)) or 0) + 1
    line = ExpenseLine(report_id=report.id, line_no=next_no, **data.model_dump())
    db.add(line)
    db.flush()
    _recalc_total(db, report)
    return line


def get_line(db: Session, report: ExpenseReport, line_id: int) -> ExpenseLine:
    line = db.get(ExpenseLine, line_id)
    if line is None or line.report_id != report.id or line.is_deleted:
        raise NotFoundError("Expense line not found.")
    return line


def update_line(db: Session, report: ExpenseReport, line_id: int, data: ExpenseLineUpdate, actor: User) -> ExpenseLine:
    assert_partner_owner(actor, report)
    assert_editable(report)
    line = get_line(db, report, line_id)
    changes = data.model_dump(exclude_unset=True)
    _validate_line_refs(db, changes.get("cost_category_id", line.cost_category_id), changes.get("gl_account_id", line.gl_account_id))
    for k, v in changes.items():
        setattr(line, k, v)  # old/new values captured by the audit listener
    db.flush()
    _recalc_total(db, report)
    return line


def delete_line(db: Session, report: ExpenseReport, line_id: int, actor: User) -> None:
    assert_partner_owner(actor, report)
    assert_editable(report)
    line = get_line(db, report, line_id)
    line.is_deleted = True
    line.deleted_at = utcnow()
    line.deleted_by_id = actor.id
    db.flush()
    db.expire(report, ["lines"])
    _recalc_total(db, report)


def _recalc_total(db: Session, report: ExpenseReport) -> None:
    total = db.scalar(select(func.coalesce(func.sum(ExpenseLine.amount), 0)).where(
        ExpenseLine.report_id == report.id, ExpenseLine.is_deleted.is_(False)))
    report.total_amount = total
    db.flush()
    db.expire(report, ["lines"])


def upload_attachment(db: Session, report: ExpenseReport, line_id: int | None, *, data: bytes, filename: str,
                      content_type: str, actor: User) -> ExpenseAttachment:
    assert_partner_owner(actor, report)
    assert_editable(report)
    if line_id is not None:
        get_line(db, report, line_id)
    digest = validate_upload(data, content_type)
    key = get_storage().save(data, filename=filename, content_type=content_type)
    att = ExpenseAttachment(report_id=report.id, expense_line_id=line_id, original_filename=filename[:255], storage_key=key,
                            content_type=content_type, size_bytes=len(data), sha256=digest, uploaded_by_id=actor.id)
    db.add(att)
    db.flush()
    record_event(db, entity_type="expense_attachments", entity_id=att.id, action="UPLOAD",
                 new_values={"report_id": report.id, "line_id": line_id, "file": filename, "sha256": digest})
    if line_id is not None:
        db.expire(get_line(db, report, line_id), ["attachments"])
    return att
