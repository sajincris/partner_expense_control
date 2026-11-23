from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import JSON, DateTime, Enum, Numeric, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Monetary amounts: 18 digits, 2 decimals. Rates: 18 digits, 8 decimals.
Money = Numeric(18, 2, asdecimal=True)
Rate = Numeric(18, 8, asdecimal=True)
Percent = Numeric(9, 4, asdecimal=True)
JsonType = JSON().with_variant(JSONB(), "postgresql")

ZERO = Decimal("0.00")


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalise DB datetimes (SQLite returns naive values) to aware UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def pg_enum(enum_cls: type[PyEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e], validate_strings=True)


class Base(DeclarativeBase):
    # When True, every INSERT/UPDATE/DELETE through the ORM is written to audit_logs
    # with old and new values (see app.services.audit_listener).
    __audited__: bool = False


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_id: Mapped[int | None] = mapped_column()
