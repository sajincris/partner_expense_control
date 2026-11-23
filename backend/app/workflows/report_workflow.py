"""Expense report workflow orchestration.

Every status change goes through ``_transition`` which:
  1. asks the state machine whether (status, action, role) is legal,
  2. applies segregation-of-duties guards,
  3. writes an immutable ApprovalAction + an explicit audit event,
  4. notifies the next actor.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    EDITABLE_STATUSES,
    ExceptionStatus,
    MissingDocumentPolicy,
    PeriodStatus,
    ReportStatus,
    ReviewDecision,
    RoleCode,
    WorkflowAction,
)
from app.core.errors import (
    InvalidTransitionError,
    NotFoundError,
    PermissionDeniedError,
    SegregationOfDutiesError,
    ValidationFailedError,
)
from app.models import (
    ApprovalAction,
    ExpenseReport,
    Project,
    ProjectPartner,
    ReportingPeriod,
    User,
    VarianceReview,
)
from app.models.base import utcnow
from app.services import notification_service as notif
from app.services.audit import record_event
from app.services.settings_service import get_setting
from app.services.variance_engine import LineKey
from app.services.variance_service import evaluate
from app.workflows.state_machine import authorize_transition

DECISION_TO_ACTION = {
    ReviewDecision.APPROVE: WorkflowAction.APPROVE,
    ReviewDecision.REJECT: WorkflowAction.REJECT,
    ReviewDecision.RETURN: WorkflowAction.RETURN,
}


# ---------------------------------------------------------------- visibility
def can_view(user: User, report: ExpenseReport) -> bool:
    if user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        return True
    if user.has_role(RoleCode.PROJECT_MANAGER) and report.project.project_manager_id == user.id:
        return True
    if user.has_role(RoleCode.PARTNER) and user.partner_id == report.partner_id:
        return True
    return False


def get_report_for(db: Session, report_id: int, user: User) -> ExpenseReport:
    report = db.get(ExpenseReport, report_id)
    if report is None or not can_view(user, report):
        # 404 (not 403) so partners cannot probe other partners' report ids.
        raise NotFoundError("Expense report not found.")
    return report


def assert_partner_owner(user: User, report: ExpenseReport) -> None:
    if not user.has_role(RoleCode.PARTNER) or user.partner_id != report.partner_id:
        raise PermissionDeniedError("Only users of the reporting partner can modify this report.")


def assert_editable(report: ExpenseReport) -> None:
    if report.status not in EDITABLE_STATUSES:
        raise ValidationFailedError(
            f"Report is {report.status.value}; lines can only be changed in DRAFT or RETURNED_FOR_CLARIFICATION.",
            code="REPORT_LOCKED",
        )


# ---------------------------------------------------------------- core transition
def _transition(
    db: Session,
    report: ExpenseReport,
    action: WorkflowAction,
    actor: User | None,
    *,
    comment: str | None = None,
    checklist: dict | None = None,
    now: datetime | None = None,
) -> ApprovalAction:
    roles = actor.role_codes if actor else set()
    t = authorize_transition(report.status, action, roles, is_system=actor is None)
    if t.comment_required and not (comment and comment.strip()):
        raise ValidationFailedError("A comment is mandatory for this action.", code="COMMENT_REQUIRED")
    from_status = report.status
    report.status = t.to_status
    entry = ApprovalAction(
        report_id=report.id, stage=t.stage, action=t.action, from_status=from_status, to_status=t.to_status,
        comment=comment, checklist=checklist, actor_id=actor.id if actor else None, created_at=now or utcnow(),
    )
    db.add(entry)
    record_event(
        db, entity_type="expense_reports", entity_id=report.id, action=t.action.value, comment=comment,
        old_values={"status": from_status.value}, new_values={"status": t.to_status.value, "stage": t.stage.value},
    )
    return entry


# ---------------------------------------------------------------- submission
def _validate_for_submission(db: Session, report: ExpenseReport) -> None:
    errors: list[str] = []
    lines = [ln for ln in report.lines if not ln.is_deleted]
    if not lines:
        errors.append("The report has no expense lines.")

    link = db.scalars(
        select(ProjectPartner).where(
            ProjectPartner.project_id == report.project_id, ProjectPartner.partner_id == report.partner_id,
            ProjectPartner.is_active.is_(True),
        )
    ).first()
    if link is None:
        errors.append("The partner is not an active implementing partner of this project.")

    if get_setting(db, "require_open_period"):
        rp = db.scalars(
            select(ReportingPeriod).where(ReportingPeriod.fiscal_year == report.fiscal_year, ReportingPeriod.period == report.period)
        ).first()
        if rp is None or rp.status != PeriodStatus.OPEN:
            errors.append(f"Reporting period {report.fiscal_year}-{report.period:02d} is not open for submission.")

    period_end = (date(report.fiscal_year + (report.period == 12), report.period % 12 + 1, 1) - timedelta(days=1))
    for ln in lines:
        if ln.currency != report.currency:
            errors.append(f"Line {ln.line_no}: currency {ln.currency} differs from report currency {report.currency}.")
        if ln.expense_date.year != report.fiscal_year or ln.expense_date > period_end:
            errors.append(f"Line {ln.line_no}: expense date {ln.expense_date} is outside fiscal year / after period end.")

    if get_setting(db, "missing_document_policy") == MissingDocumentPolicy.BLOCK.value:
        missing = [ln.line_no for ln in lines if not ln.attachments]
        if missing:
            errors.append(f"Supporting documents are mandatory; missing on lines {missing}.")

    if errors:
        raise ValidationFailedError("The report cannot be submitted.", details={"errors": errors}, code="SUBMISSION_INVALID")


def submit_report(db: Session, report: ExpenseReport, actor: User, comment: str | None = None, now: datetime | None = None) -> ExpenseReport:
    assert_partner_owner(actor, report)
    now = now or utcnow()
    action = WorkflowAction.RESUBMIT if report.status == ReportStatus.RETURNED_FOR_CLARIFICATION else WorkflowAction.SUBMIT
    _validate_for_submission(db, report)

    # Evaluate and match lines to plan BEFORE the status changes: once the report
    # leaves DRAFT/RETURNED its lines are locked (also enforced by a DB trigger).
    result, ctx = evaluate(db, report, on_date=now.date())
    for ln in report.lines:
        ln.matched_plan_line_id = ctx["plan_ids"].get((report.period, LineKey(ln.cost_category_id, ln.gl_account_id)))
    db.flush()

    _transition(db, report, action, actor, comment=comment, now=now)
    report.submission_count += 1
    report.submitted_by_id = actor.id
    report.submitted_at = now
    report.pm_approved_by_id = report.pm_approved_at = None
    report.finance_approved_by_id = report.finance_approved_at = None
    report.total_amount = sum((ln.amount for ln in report.lines if not ln.is_deleted), Decimal("0.00"))
    report.budget_plan_version_id = ctx["version"].id
    if comment:
        report.partner_comment = comment

    # Exceptions from an earlier submission are superseded by the new evaluation.
    for exc in report.exceptions:
        if exc.status == ExceptionStatus.OPEN:
            exc.status = ExceptionStatus.SUPERSEDED
            exc.resolved_at = now

    for f in result.findings:
        db.add(VarianceReview(
            report_id=report.id, submission_no=report.submission_count, expense_line_id=f.line_id,
            exception_type=f.exception_type, severity=f.severity, status=ExceptionStatus.OPEN,
            cost_category_id=f.key.cost_category_id if f.key else None, gl_account_id=f.key.gl_account_id if f.key else None,
            planned_amount=f.planned, actual_amount=f.actual, variance_amount=f.variance, variance_pct=f.variance_pct,
            tolerance_rule_id=f.rule_id, message=f.message, calculation_snapshot={**f.snapshot, "totals": result.as_dict()},
        ))

    if result.auto_accept:
        _transition(db, report, WorkflowAction.AUTO_ACCEPT, None,
                    comment="All lines within tolerance; no control exceptions.", now=now)
        report.requires_review = False
        report.closed_at = now
        report.review_due_at = None
        notif.notify(db, notif.partner_users(db, report.partner_id), type="REPORT_ACCEPTED",
                     title=f"{report.report_number} accepted", message="Your report was automatically accepted.",
                     entity_type="expense_reports", entity_id=report.id)
    else:
        _transition(db, report, WorkflowAction.ROUTE_TO_PM, None,
                    comment=f"{len(result.findings)} exception(s) raised; routed to Project Manager.", now=now)
        report.requires_review = True
        report.review_due_at = now + timedelta(days=int(get_setting(db, "pm_review_sla_days")))
        pm_id = report.project.project_manager_id
        if pm_id:
            notif.notify(db, {pm_id}, type="PM_REVIEW_REQUIRED", title=f"Review {report.report_number}",
                         message=f"{len(result.findings)} variance exception(s) require your business justification.",
                         entity_type="expense_reports", entity_id=report.id)
    db.flush()
    db.expire(report, ["exceptions"])
    return report


def cancel_report(db: Session, report: ExpenseReport, actor: User, comment: str) -> ExpenseReport:
    assert_partner_owner(actor, report)
    _transition(db, report, WorkflowAction.CANCEL, actor, comment=comment)
    report.closed_at = utcnow()
    db.flush()
    return report


# ---------------------------------------------------------------- reviews
def _expect_status(report: ExpenseReport, expected: ReportStatus, decision: ReviewDecision) -> None:
    if report.status != expected:
        raise InvalidTransitionError(
            f"Cannot {decision.value} at this stage: report is {report.status.value}, expected {expected.value}.",
            details={"status": report.status.value, "expected": expected.value},
        )


def _sod_common(report: ExpenseReport, actor: User) -> None:
    if actor.partner_id is not None or actor.has_role(RoleCode.PARTNER):
        raise SegregationOfDutiesError("Partner users cannot review expense reports.")
    if report.submitted_by_id == actor.id or report.created_by_id == actor.id:
        raise SegregationOfDutiesError("You cannot review a report you created or submitted.")


def pm_review(db: Session, report: ExpenseReport, actor: User, decision: ReviewDecision, comment: str, now: datetime | None = None) -> ExpenseReport:
    now = now or utcnow()
    _expect_status(report, ReportStatus.PENDING_PM_REVIEW, decision)
    _sod_common(report, actor)
    project: Project = report.project
    if project.project_manager_id != actor.id:
        raise PermissionDeniedError("Only the Project Manager assigned to this project can review it.")

    _transition(db, report, DECISION_TO_ACTION[decision], actor, comment=comment, now=now)
    open_exc = [e for e in report.exceptions if e.status == ExceptionStatus.OPEN]
    for e in open_exc:
        e.pm_justification = comment

    if decision == ReviewDecision.APPROVE:
        report.pm_approved_by_id = actor.id
        report.pm_approved_at = now
        report.review_due_at = now + timedelta(days=int(get_setting(db, "finance_review_sla_days")))
        notif.notify(db, notif.users_with_role(db, RoleCode.FINANCE_OFFICER) - {actor.id}, type="FINANCE_REVIEW_REQUIRED",
                     title=f"Validate {report.report_number}", message="PM approved; budget and accounting validation required.",
                     entity_type="expense_reports", entity_id=report.id)
    else:
        _close_or_return(db, report, decision, comment, now)
    db.flush()
    return report


def finance_review(
    db: Session, report: ExpenseReport, actor: User, decision: ReviewDecision, comment: str,
    checklist: dict | None = None, now: datetime | None = None,
) -> ExpenseReport:
    now = now or utcnow()
    _expect_status(report, ReportStatus.PENDING_FINANCE_REVIEW, decision)
    _sod_common(report, actor)
    if report.pm_approved_by_id == actor.id:
        raise SegregationOfDutiesError("Four-eyes principle: the PM approver cannot also give the Finance approval.")

    if decision == ReviewDecision.APPROVE:
        if report.pm_approved_by_id is None:
            raise ValidationFailedError("Final approval requires a recorded PM approval.", code="PM_APPROVAL_MISSING")
        if not checklist or not all(checklist.get(k) for k in ("budget_available", "accounting_treatment_ok", "documents_ok")):
            raise ValidationFailedError(
                "Finance approval requires budget availability, accounting treatment and documents to be confirmed.",
                code="FINANCE_CHECKLIST_INCOMPLETE",
            )

    _transition(db, report, DECISION_TO_ACTION[decision], actor, comment=comment, checklist=checklist, now=now)
    for e in report.exceptions:
        if e.status == ExceptionStatus.OPEN:
            e.finance_note = comment

    if decision == ReviewDecision.APPROVE:
        report.finance_approved_by_id = actor.id
        report.finance_approved_at = now
        report.closed_at = now
        report.review_due_at = None
        for e in report.exceptions:
            if e.status == ExceptionStatus.OPEN:
                e.status = ExceptionStatus.RESOLVED
                e.resolved_at = now
        notif.notify(db, notif.partner_users(db, report.partner_id), type="REPORT_APPROVED",
                     title=f"{report.report_number} approved", message="Your report was approved by Finance.",
                     entity_type="expense_reports", entity_id=report.id)
    else:
        _close_or_return(db, report, decision, comment, now)
    db.flush()
    return report


def _close_or_return(db: Session, report: ExpenseReport, decision: ReviewDecision, comment: str, now: datetime) -> None:
    if decision == ReviewDecision.REJECT:
        report.closed_at = now
        report.review_due_at = None
        for e in report.exceptions:
            if e.status == ExceptionStatus.OPEN:
                e.status = ExceptionStatus.REJECTED
                e.resolved_at = now
        title, ntype = f"{report.report_number} rejected", "REPORT_REJECTED"
    else:  # RETURN
        report.review_due_at = None
        title, ntype = f"{report.report_number} returned for clarification", "REPORT_RETURNED"
    notif.notify(db, notif.partner_users(db, report.partner_id), type=ntype, title=title, message=comment,
                 entity_type="expense_reports", entity_id=report.id)
