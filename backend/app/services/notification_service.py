"""In-app notifications. Email/Slack delivery is a roadmap item: add a sender
behind ``notify`` without changing callers."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RoleCode
from app.models import Notification, Role, User, UserRole


def notify(db: Session, user_ids: set[int], *, type: str, title: str, message: str, entity_type: str, entity_id: int) -> None:
    for uid in user_ids:
        db.add(Notification(user_id=uid, type=type, title=title, message=message, entity_type=entity_type, entity_id=entity_id))


def users_with_role(db: Session, role: RoleCode) -> set[int]:
    stmt = (
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(Role.code == role, User.is_active.is_(True), User.is_deleted.is_(False))
    )
    return set(db.scalars(stmt).all())


def partner_users(db: Session, partner_id: int) -> set[int]:
    return set(db.scalars(select(User.id).where(User.partner_id == partner_id, User.is_active.is_(True))).all())
