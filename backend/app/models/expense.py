from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ReportStatus
from app.models.base import Base, Money, SoftDeleteMixin, TimestampMixin, pg_enum


class ExpenseReport(Base, TimestampMixin):
    __tablename__ = "expense_reports"
    __audited__ = True
    __table_args__ = (
        CheckConstraint("period BETWEEN 1 AND 12", name="ck_report_period"),
        CheckConstraint("total_amount >= 0", name="ck_report_total_non_negative"),
        # Control: an APPROVED report carries both approvals, given by different people.
        CheckConstraint(
            "status <> 'APPROVED' OR (pm_approved_by_id IS NOT NULL AND finance_approved_by_id IS NOT NULL "
            "AND pm_approved_by_id <> finance_approved_by_id)",
            name="ck_report_approved_needs_two_approvers",
        ),
        # One live report per partner/project/period. Cancelled and rejected reports
        # do not block a corrected report for the same period.
        Index(
            "uq_report_live_per_period",
            "partner_id",
            "project_id",
            "fiscal_year",
            "period",
            unique=True,
            postgresql_where=text("status NOT IN ('CANCELLED', 'REJECTED')"),
            sqlite_where=text("status NOT IN ('CANCELLED', 'REJECTED')"),
        ),
        Index("ix_report_status", "status"),
        Index("ix_report_project_period", "project_id", "fiscal_year", "period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    budget_plan_version_id: Mapped[int | None] = mapped_column(ForeignKey("budget_plan_versions.id"))
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(pg_enum(ReportStatus, "report_status"), default=ReportStatus.DRAFT, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    partner_comment: Mapped[str | None] = mapped_column(Text)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    submission_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pm_approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    pm_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finance_approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    finance_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Active (non-deleted) lines. View-only: lines are written with an explicit report_id.
    lines: Mapped[list["ExpenseLine"]] = relationship(
        viewonly=True,
        order_by="ExpenseLine.line_no",
        primaryjoin="and_(ExpenseReport.id == ExpenseLine.report_id, ExpenseLine.is_deleted == False)",  # noqa: E712
        lazy="selectin",
    )
    partner: Mapped["Partner"] = relationship(lazy="joined")  # noqa: F821
    project: Mapped["Project"] = relationship(lazy="joined")  # noqa: F821
    exceptions: Mapped[list["VarianceReview"]] = relationship(back_populates="report", lazy="selectin")  # noqa: F821


class ExpenseLine(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "expense_lines"
    __audited__ = True
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_line_positive"),
        Index("ix_expense_line_invoice", "invoice_reference"),
        Index("ix_expense_line_report", "report_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    cost_category_id: Mapped[int] = mapped_column(ForeignKey("cost_categories.id"), nullable=False)
    gl_account_id: Mapped[int] = mapped_column(ForeignKey("gl_accounts.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    invoice_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    matched_plan_line_id: Mapped[int | None] = mapped_column(ForeignKey("budget_plan_lines.id"))

    report: Mapped[ExpenseReport] = relationship(foreign_keys=[report_id])
    cost_category: Mapped["CostCategory"] = relationship(lazy="joined")  # noqa: F821
    gl_account: Mapped["GLAccount"] = relationship(lazy="joined")  # noqa: F821
    attachments: Mapped[list["ExpenseAttachment"]] = relationship(
        viewonly=True,
        primaryjoin="and_(ExpenseLine.id == ExpenseAttachment.expense_line_id, ExpenseAttachment.is_deleted == False)",  # noqa: E712
        lazy="selectin",
    )


class ExpenseAttachment(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "expense_attachments"
    __audited__ = True
    __table_args__ = (CheckConstraint("size_bytes > 0", name="ck_attachment_size"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("expense_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    expense_line_id: Mapped[int | None] = mapped_column(ForeignKey("expense_lines.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    line: Mapped[ExpenseLine | None] = relationship(foreign_keys=[expense_line_id])
