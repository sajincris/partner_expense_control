from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_roles
from app.core.enums import RoleCode
from app.core.errors import NotFoundError, SegregationOfDutiesError
from app.models import Role, User, UserRole
from app.schemas.identity import RoleOut, UserCreate, UserOut, UserRolesUpdate, UserUpdate, user_out
from app.services import user_service
from app.utils.pagination import Page, PageParams, apply_sort, paginate

router = APIRouter(tags=["Users & Roles"])
admin = require_roles(RoleCode.FINANCE_LEAD)
admin_or_auditor = require_roles(RoleCode.FINANCE_LEAD, RoleCode.AUDITOR)


@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db), _: User = Depends(admin_or_auditor)):
    return db.scalars(select(Role).order_by(Role.id)).all()


@router.get("/users", response_model=Page[UserOut])
def list_users(
    params: PageParams = Depends(),
    q: str | None = Query(None, description="Search email or name"),
    role: RoleCode | None = None,
    partner_id: int | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(admin_or_auditor),
):
    stmt = select(User).where(User.is_deleted.is_(False))
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    if role:
        stmt = stmt.join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id).where(Role.code == role)
    if partner_id:
        stmt = stmt.where(User.partner_id == partner_id)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    stmt = apply_sort(stmt, params.sort, {"email": User.email, "full_name": User.full_name, "created_at": User.created_at}, User.email)
    return paginate(db, stmt, params, user_out)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: User = Depends(admin)):
    user = user_service.create_user(db, email=body.email, full_name=body.full_name, password=body.password,
                                    roles=set(body.roles), partner_id=body.partner_id, actor=actor)
    db.commit()
    return user_out(user)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(admin_or_auditor)):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        raise NotFoundError("User not found.")
    return user_out(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(admin)):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        raise NotFoundError("User not found.")
    changes = body.model_dump(exclude_unset=True)
    if user.id == actor.id and changes.get("is_active") is False:
        raise SegregationOfDutiesError("You cannot deactivate your own account.")
    if "partner_id" in changes:
        user_service.validate_role_set(user.role_codes, changes["partner_id"])
    for k, v in changes.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.put("/users/{user_id}/roles", response_model=UserOut)
def set_user_roles(user_id: int, body: UserRolesUpdate, db: Session = Depends(get_db), actor: User = Depends(admin)):
    user = db.get(User, user_id)
    if not user or user.is_deleted:
        raise NotFoundError("User not found.")
    user = user_service.set_roles(db, user, set(body.roles), actor)
    db.commit()
    return user_out(user)
