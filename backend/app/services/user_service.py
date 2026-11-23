"""User administration with segregation-of-duties checks on role assignment."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RoleCode
from app.core.errors import ConflictError, NotFoundError, SegregationOfDutiesError, ValidationFailedError
from app.core.security import hash_password
from app.models import Partner, Role, User, UserRole

# Role combinations that would let one person both create and approve spend.
CONFLICTING_ROLES = [
    {RoleCode.PARTNER, RoleCode.PROJECT_MANAGER},
    {RoleCode.PARTNER, RoleCode.FINANCE_OFFICER},
    {RoleCode.PARTNER, RoleCode.FINANCE_LEAD},
    {RoleCode.PROJECT_MANAGER, RoleCode.FINANCE_OFFICER},
]


def validate_role_set(roles: set[RoleCode], partner_id: int | None) -> None:
    for combo in CONFLICTING_ROLES:
        if combo.issubset(roles):
            raise SegregationOfDutiesError(
                f"Role combination {sorted(r.value for r in combo)} violates segregation of duties."
            )
    if RoleCode.PARTNER in roles and partner_id is None:
        raise ValidationFailedError("Partner users must be linked to a partner organisation.")
    if RoleCode.PARTNER not in roles and partner_id is not None:
        raise ValidationFailedError("Only partner users can be linked to a partner organisation.")


def _roles(db: Session, codes: set[RoleCode]) -> list[Role]:
    roles = db.scalars(select(Role).where(Role.code.in_(codes))).all()
    if len(roles) != len(codes):
        raise ValidationFailedError("Unknown role code.")
    return list(roles)


def create_user(db: Session, *, email: str, full_name: str, password: str, roles: set[RoleCode],
                partner_id: int | None, actor: User | None) -> User:
    validate_role_set(roles, partner_id)
    if partner_id is not None and db.get(Partner, partner_id) is None:
        raise NotFoundError("Partner not found.")
    if db.scalars(select(User).where(User.email == email.lower())).first():
        raise ConflictError("A user with this email already exists.")
    user = User(email=email.lower(), full_name=full_name, password_hash=hash_password(password), partner_id=partner_id)
    db.add(user)
    db.flush()
    for role in _roles(db, roles):
        db.add(UserRole(user_id=user.id, role_id=role.id, granted_by_id=actor.id if actor else None))
    db.flush()
    db.refresh(user)
    return user


def set_roles(db: Session, user: User, roles: set[RoleCode], actor: User) -> User:
    if user.id == actor.id:
        raise SegregationOfDutiesError("Administrators cannot change their own roles.")
    validate_role_set(roles, user.partner_id)
    current = {ur.role.code: ur for ur in user.user_roles}
    for code, ur in current.items():
        if code not in roles:
            db.delete(ur)
    for role in _roles(db, roles - set(current)):
        db.add(UserRole(user_id=user.id, role_id=role.id, granted_by_id=actor.id))
    db.flush()
    db.refresh(user)
    return user
