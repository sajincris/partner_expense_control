from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ReportStatus,
    ReviewDecision,
    ReviewStage,
    WorkflowAction,
)
from app.schemas.common import CurrencyCode, FiscalYear, ORMModel, Period, PositiveMoney


class ExpenseReportCreate(BaseModel):
    project_id: int
    fiscal_year: FiscalYear
    period: Period
    currency: CurrencyCode = "USD"
    partner_id: int | None = Field(default=None, description="Ignored for partner users (taken from the token)")
    partner_comment: str | None = Field(default=None, max_length=4000)


class ExpenseLineIn(BaseModel):
    expense_date: date
    cost_category_id: int
    gl_account_id: int
    description: str = Field(min_length=3, max_length=500)
    amount: PositiveMoney
    currency: CurrencyCode = "USD"
    invoice_reference: str = Field(min_length=1, max_length=100)


class ExpenseLineUpdate(BaseModel):
    expense_date: date | None = None
    cost_category_id: int | None = None
    gl_account_id: int | None = None
    description: str | None = Field(default=None, min_length=3, max_length=500)
    amount: PositiveMoney | None = None
    invoice_reference: str | None = Field(default=None, min_length=1, max_length=100)


class AttachmentOut(ORMModel):
    id: int
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by_id: int
    created_at: datetime


class ExpenseLineOut(ORMModel):
    id: int
    line_no: int
    expense_date: date
    cost_category_id: int
    cost_category_name: str
    gl_account_id: int
    gl_account_number: str
    description: str
    amount: Decimal
    currency: str
    invoice_reference: str
    matched_plan_line_id: int | None
    attachments: list[AttachmentOut] = []


class VarianceReviewOut(ORMModel):
    id: int
    submission_no: int
    expense_line_id: int | None
    exception_type: ExceptionType
    severity: ExceptionSeverity
    status: ExceptionStatus
    cost_category_id: int | None
    gl_account_id: int | None
    planned_amount: Decimal | None
    actual_amount: Decimal | None
    variance_amount: Decimal | None
    variance_pct: Decimal | None
    tolerance_rule_id: int | None
    message: str
    pm_justification: str | None
    finance_note: str | None
    created_at: datetime


class ApprovalActionOut(ORMModel):
    id: int
    stage: ReviewStage
    action: WorkflowAction
    from_status: ReportStatus
    to_status: ReportStatus
    comment: str | None
    checklist: dict | None
    actor_id: int | None
    actor_name: str | None = None
    created_at: datetime


class ExpenseReportSummary(ORMModel):
    id: int
    report_number: str
    partner_id: int
    partner_name: str
    project_id: int
    project_code: str
    project_name: str
    fiscal_year: int
    period: int
    currency: str
    status: ReportStatus
    total_amount: Decimal
    requires_review: bool
    open_exceptions: int = 0
    submitted_at: datetime | None
    review_due_at: datetime | None
    is_overdue: bool = False
    created_at: datetime


class ExpenseReportDetail(ExpenseReportSummary):
    partner_comment: str | None
    submission_count: int
    submitted_by_id: int | None
    pm_approved_by_id: int | None
    pm_approved_at: datetime | None
    finance_approved_by_id: int | None
    finance_approved_at: datetime | None
    lines: list[ExpenseLineOut]
    exceptions: list[VarianceReviewOut]
    actions: list[ApprovalActionOut]
    available_actions: list[str]


class SubmitRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=4000, description="Mandatory when resubmitting after clarification")


class CancelRequest(BaseModel):
    comment: str = Field(min_length=5, max_length=4000)


class FinanceChecklist(BaseModel):
    budget_available: bool
    accounting_treatment_ok: bool
    documents_ok: bool


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    comment: str = Field(min_length=5, max_length=4000, description="Mandatory justification for every decision")
    checklist: FinanceChecklist | None = Field(default=None, description="Required for Finance APPROVE")


class VarianceRowOut(BaseModel):
    cost_category_id: int
    cost_category_name: str | None = None
    gl_account_id: int
    gl_account_number: str | None = None
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
    rule_name: str | None
    reason: str


class FindingOut(BaseModel):
    exception_type: ExceptionType
    severity: ExceptionSeverity
    message: str
    line_id: int | None


class VarianceResultOut(BaseModel):
    report_id: int
    rows: list[VarianceRowOut]
    findings: list[FindingOut]
    totals: dict
    auto_accept: bool


class QueueItem(ExpenseReportSummary):
    stage: str
    highest_severity: ExceptionSeverity | None = None
    exception_types: list[ExceptionType] = []
    max_variance_pct: Decimal | None = None
