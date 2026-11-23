from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PeriodStatus
from app.models.base import Base, Rate, SoftDeleteMixin, TimestampMixin, pg_enum


class Currency(Base, TimestampMixin):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)  # ISO 4217
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    minor_units: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class ExchangeRate(Base, TimestampMixin):
    __tablename__ = "exchange_rates"
    __audited__ = True
    __table_args__ = (
        UniqueConstraint("from_currency", "to_currency", "rate_date", name="uq_fx_pair_date"),
        CheckConstraint("rate > 0", name="ck_fx_rate_positive"),
        CheckConstraint("from_currency <> to_currency", name="ck_fx_distinct_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    to_currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    rate: Mapped[object] = mapped_column(Rate, nullable=False)
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(100))


class Partner(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "partners"
    __audited__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    registration_number: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(String(2))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class Project(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "projects"
    __audited__ = True
    __table_args__ = (CheckConstraint("end_date >= start_date", name="ck_project_dates"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    donor: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    project_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    project_manager: Mapped["User | None"] = relationship(foreign_keys=[project_manager_id])  # noqa: F821
    partner_links: Mapped[list["ProjectPartner"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectPartner(Base, TimestampMixin):
    """Contractual link: a partner implements (part of) a project under an agreement."""

    __tablename__ = "project_partners"
    __audited__ = True
    __table_args__ = (UniqueConstraint("project_id", "partner_id", name="uq_project_partner"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True)
    agreement_reference: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    project: Mapped[Project] = relationship(back_populates="partner_links")
    partner: Mapped[Partner] = relationship()


class CostCategory(Base, TimestampMixin):
    __tablename__ = "cost_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class GLAccount(Base, TimestampMixin):
    __tablename__ = "gl_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    cost_category_id: Mapped[int | None] = mapped_column(ForeignKey("cost_categories.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class ReportingPeriod(Base, TimestampMixin):
    __tablename__ = "reporting_periods"
    __audited__ = True
    __table_args__ = (
        UniqueConstraint("fiscal_year", "period", name="uq_reporting_period"),
        CheckConstraint("period BETWEEN 1 AND 12", name="ck_reporting_period_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    submission_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PeriodStatus] = mapped_column(pg_enum(PeriodStatus, "period_status"), default=PeriodStatus.OPEN, nullable=False)
