from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ReportStatus,
    ReviewStage,
    WorkflowAction,
)
from app.models.base import Base, JsonType, Money, Percent, TimestampMixin, pg_enum


class VarianceReview(Base, TimestampMixin):
    """A variance exception raised by the control engine for a report.

    One row per finding (variance breach, missing plan line, duplicate invoice,
    missing document, annual budget overrun). The full calculation snapshot is
    stored so the decision can be re-explained later even if the plan changes.
    """

    __tablename__ = "variance_reviews"
    __audited__ = True
    __table_args__ = (
        Index("ix_variance_review_report", "report_id"),
        Index("ix_variance_review_status_type", "status", "exception_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False)
    submission_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expense_line_id: Mapped[int | None] = mapped_column(ForeignKey("expense_lines.id"))
    exception_type: Mapped[ExceptionType] = mapped_column(pg_enum(ExceptionType, "exception_type"), nullable=False)
    severity: Mapped[ExceptionSeverity] = mapped_column(pg_enum(ExceptionSeverity, "exception_severity"), nullable=False)
    status: Mapped[ExceptionStatus] = mapped_column(
        pg_enum(ExceptionStatus, "exception_status"), default=ExceptionStatus.OPEN, nullable=False
    )
    cost_category_id: Mapped[int | None] = mapped_column(ForeignKey("cost_categories.id"))
    gl_account_id: Mapped[int | None] = mapped_column(ForeignKey("gl_accounts.id"))
    planned_amount: Mapped[Decimal | None] = mapped_column(Money)
    actual_amount: Mapped[Decimal | None] = mapped_column(Money)
    variance_amount: Mapped[Decimal | None] = mapped_column(Money)
    variance_pct: Mapped[Decimal | None] = mapped_column(Percent)
    tolerance_rule_id: Mapped[int | None] = mapped_column(ForeignKey("tolerance_rules.id"))
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    calculation_snapshot: Mapped[dict | None] = mapped_column(JsonType)
    pm_justification: Mapped[str | None] = mapped_column(Text)
    finance_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    report: Mapped["ExpenseReport"] = relationship(back_populates="exceptions")  # noqa: F821


class ApprovalAction(Base):
    """Immutable workflow journal: every status transition with actor and comment."""

    __tablename__ = "approval_actions"
    __table_args__ = (Index("ix_approval_action_report", "report_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[ReviewStage] = mapped_column(pg_enum(ReviewStage, "review_stage"), nullable=False)
    action: Mapped[WorkflowAction] = mapped_column(pg_enum(WorkflowAction, "workflow_action"), nullable=False)
    from_status: Mapped[ReportStatus] = mapped_column(pg_enum(ReportStatus, "report_status"), nullable=False)
    to_status: Mapped[ReportStatus] = mapped_column(pg_enum(ReportStatus, "report_status"), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    checklist: Mapped[dict | None] = mapped_column(JsonType)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # NULL = system
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    actor: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821
