from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BudgetVersionStatus
from app.models.base import Base, Money, TimestampMixin, pg_enum


class BudgetPlan(Base, TimestampMixin):
    """Approved plan header: one per partner x project x fiscal year.

    Amounts live on versioned lines. A plan is never edited in place once a
    version is ACTIVE: changes create a new version (reforecast trail).
    """

    __tablename__ = "budget_plans"
    __audited__ = True
    __table_args__ = (UniqueConstraint("partner_id", "project_id", "fiscal_year", name="uq_budget_plan_scope"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    versions: Mapped[list["BudgetPlanVersion"]] = relationship(
        back_populates="plan", order_by="BudgetPlanVersion.version_no", cascade="all, delete-orphan"
    )
    partner: Mapped["Partner"] = relationship()  # noqa: F821
    project: Mapped["Project"] = relationship()  # noqa: F821

    @property
    def active_version(self) -> "BudgetPlanVersion | None":
        return next((v for v in self.versions if v.status == BudgetVersionStatus.ACTIVE), None)


class BudgetPlanVersion(Base, TimestampMixin):
    __tablename__ = "budget_plan_versions"
    __audited__ = True
    __table_args__ = (
        UniqueConstraint("budget_plan_id", "version_no", name="uq_budget_version_no"),
        # At most one ACTIVE version per plan (partial unique index).
        Index(
            "uq_budget_one_active_version",
            "budget_plan_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    budget_plan_id: Mapped[int] = mapped_column(ForeignKey("budget_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[BudgetVersionStatus] = mapped_column(
        pg_enum(BudgetVersionStatus, "budget_version_status"), default=BudgetVersionStatus.DRAFT, nullable=False
    )
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    plan: Mapped[BudgetPlan] = relationship(back_populates="versions")
    lines: Mapped[list["BudgetPlanLine"]] = relationship(back_populates="version", cascade="all, delete-orphan", lazy="selectin")


class BudgetPlanLine(Base, TimestampMixin):
    __tablename__ = "budget_plan_lines"
    __audited__ = True
    __table_args__ = (
        UniqueConstraint("version_id", "period", "cost_category_id", "gl_account_id", name="uq_budget_line_key"),
        CheckConstraint("period BETWEEN 1 AND 12", name="ck_budget_line_period"),
        CheckConstraint("planned_amount >= 0", name="ck_budget_line_non_negative"),
        Index("ix_budget_line_lookup", "version_id", "cost_category_id", "gl_account_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("budget_plan_versions.id", ondelete="CASCADE"), nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_category_id: Mapped[int] = mapped_column(ForeignKey("cost_categories.id"), nullable=False)
    gl_account_id: Mapped[int] = mapped_column(ForeignKey("gl_accounts.id"), nullable=False)
    planned_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))

    version: Mapped[BudgetPlanVersion] = relationship(back_populates="lines")
    cost_category: Mapped["CostCategory"] = relationship(lazy="joined")  # noqa: F821
    gl_account: Mapped["GLAccount"] = relationship(lazy="joined")  # noqa: F821
