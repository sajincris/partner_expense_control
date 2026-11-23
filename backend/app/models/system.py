from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import VarianceDirection
from app.models.base import Base, JsonType, Money, Percent, TimestampMixin, pg_enum, utcnow


class ToleranceRule(Base, TimestampMixin):
    """Configurable variance tolerance.

    Scope columns left NULL mean "any". The most specific active rule wins
    (see app.services.variance_engine.resolve_rule).
    A line is WITHIN tolerance when |variance %| <= max_variance_pct AND
    |variance| <= max_variance_abs (both limits must hold).
    """

    __tablename__ = "tolerance_rules"
    __audited__ = True
    __table_args__ = (
        CheckConstraint("max_variance_pct >= 0", name="ck_rule_pct_non_negative"),
        CheckConstraint("max_variance_abs >= 0", name="ck_rule_abs_non_negative"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_rule_dates"),
        Index("ix_rule_scope", "project_id", "partner_id", "cost_category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    cost_category_id: Mapped[int | None] = mapped_column(ForeignKey("cost_categories.id"))
    max_variance_pct: Mapped[Decimal] = mapped_column(Percent, nullable=False)
    max_variance_abs: Mapped[Decimal] = mapped_column(Money, nullable=False)
    abs_currency: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    direction: Mapped[VarianceDirection] = mapped_column(
        pg_enum(VarianceDirection, "variance_direction"), default=VarianceDirection.BOTH, nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)


class SystemSetting(Base, TimestampMixin):
    """Key/value configuration (SLA days, missing-document policy, ...)."""

    __tablename__ = "system_settings"
    __audited__ = True

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JsonType, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))


class AuditLog(Base):
    """Append-only audit trail. UPDATE/DELETE are blocked by a DB trigger in PostgreSQL."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_actor", "actor_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    old_values: Mapped[dict | None] = mapped_column(JsonType)
    new_values: Mapped[dict | None] = mapped_column(JsonType)
    comment: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_email: Mapped[str | None] = mapped_column(String(255))
    actor_roles: Mapped[str | None] = mapped_column(String(200))
    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notification_user_unread", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
