from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RoleCode
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, pg_enum


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[RoleCode] = mapped_column(pg_enum(RoleCode, "role_code"), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    __audited__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    # Partner users are bound to exactly one partner organisation (data scoping).
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id", ondelete="RESTRICT"), index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user_roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin", foreign_keys="UserRole.user_id"
    )
    partner: Mapped["Partner | None"] = relationship(lazy="joined")  # noqa: F821

    @property
    def role_codes(self) -> set[RoleCode]:
        return {ur.role.code for ur in self.user_roles}

    def has_role(self, *codes: RoleCode) -> bool:
        return bool(self.role_codes.intersection(codes))


class UserRole(Base, TimestampMixin):
    __tablename__ = "user_roles"
    __audited__ = True
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    granted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    user: Mapped[User] = relationship(back_populates="user_roles", foreign_keys=[user_id])
    role: Mapped[Role] = relationship(lazy="joined")
