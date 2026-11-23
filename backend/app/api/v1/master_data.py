"""Partners, projects, reference data (cost categories, GL accounts, currencies)."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ALL_ROLES, INTERNAL_READERS, get_current_user, require_roles
from app.core.enums import RoleCode
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import CostCategory, Currency, GLAccount, Partner, Project, ProjectPartner, User
from app.models.base import utcnow
from app.schemas.master_data import (
    CostCategoryOut,
    CurrencyOut,
    GLAccountOut,
    PartnerCreate,
    PartnerOut,
    PartnerUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectPartnerCreate,
    ProjectUpdate,
    project_out,
)
from app.utils.pagination import Page, PageParams, apply_sort, paginate

router = APIRouter(tags=["Master data"])
admin = require_roles(RoleCode.FINANCE_LEAD)
internal = require_roles(*INTERNAL_READERS)
anyone = require_roles(*ALL_ROLES)


# ------------------------------------------------------------------ reference data
@router.get("/master/cost-categories", response_model=list[CostCategoryOut])
def cost_categories(db: Session = Depends(get_db), _: User = Depends(anyone)):
    return db.scalars(select(CostCategory).where(CostCategory.is_active.is_(True)).order_by(CostCategory.code)).all()


@router.get("/master/gl-accounts", response_model=list[GLAccountOut])
def gl_accounts(cost_category_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(anyone)):
    stmt = select(GLAccount).where(GLAccount.is_active.is_(True)).order_by(GLAccount.account_number)
    if cost_category_id:
        stmt = stmt.where(GLAccount.cost_category_id == cost_category_id)
    return db.scalars(stmt).all()


@router.get("/master/currencies", response_model=list[CurrencyOut])
def currencies(db: Session = Depends(get_db), _: User = Depends(anyone)):
    return db.scalars(select(Currency).where(Currency.is_active.is_(True)).order_by(Currency.code)).all()


# ------------------------------------------------------------------ partners
@router.get("/partners", response_model=Page[PartnerOut])
def list_partners(params: PageParams = Depends(), q: str | None = None, is_active: bool | None = None,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Partner).where(Partner.is_deleted.is_(False))
    if user.has_role(RoleCode.PARTNER) and not user.has_role(*INTERNAL_READERS):
        stmt = stmt.where(Partner.id == user.partner_id)
    if q:
        stmt = stmt.where(or_(Partner.name.ilike(f"%{q}%"), Partner.code.ilike(f"%{q}%")))
    if is_active is not None:
        stmt = stmt.where(Partner.is_active.is_(is_active))
    stmt = apply_sort(stmt, params.sort, {"code": Partner.code, "name": Partner.name}, Partner.code)
    return paginate(db, stmt, params, PartnerOut.model_validate)


@router.post("/partners", response_model=PartnerOut, status_code=201)
def create_partner(body: PartnerCreate, db: Session = Depends(get_db), _: User = Depends(admin)):
    if db.scalars(select(Partner).where(Partner.code == body.code)).first():
        raise ConflictError("Partner code already exists.")
    partner = Partner(**body.model_dump())
    db.add(partner)
    db.commit()
    return partner


@router.get("/partners/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    partner = db.get(Partner, partner_id)
    if not partner or partner.is_deleted or (user.has_role(RoleCode.PARTNER) and user.partner_id != partner_id):
        raise NotFoundError("Partner not found.")
    return partner


@router.patch("/partners/{partner_id}", response_model=PartnerOut)
def update_partner(partner_id: int, body: PartnerUpdate, db: Session = Depends(get_db), _: User = Depends(admin)):
    partner = db.get(Partner, partner_id)
    if not partner or partner.is_deleted:
        raise NotFoundError("Partner not found.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(partner, k, v)
    db.commit()
    return partner


@router.delete("/partners/{partner_id}", status_code=204)
def delete_partner(partner_id: int, db: Session = Depends(get_db), actor: User = Depends(admin)):
    """Soft delete: financial history must remain traceable."""
    partner = db.get(Partner, partner_id)
    if not partner or partner.is_deleted:
        raise NotFoundError("Partner not found.")
    partner.is_deleted, partner.is_active, partner.deleted_at, partner.deleted_by_id = True, False, utcnow(), actor.id
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ projects
@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(params: PageParams = Depends(), q: str | None = None, partner_id: int | None = None,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Project).where(Project.is_deleted.is_(False))
    if user.has_role(RoleCode.PARTNER) and not user.has_role(*INTERNAL_READERS):
        partner_id = user.partner_id
    if partner_id:
        stmt = stmt.join(ProjectPartner).where(ProjectPartner.partner_id == partner_id)
    if q:
        stmt = stmt.where(or_(Project.name.ilike(f"%{q}%"), Project.code.ilike(f"%{q}%")))
    stmt = apply_sort(stmt, params.sort, {"code": Project.code, "name": Project.name, "start_date": Project.start_date}, Project.code)
    return paginate(db, stmt, params, project_out)


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), _: User = Depends(admin)):
    if db.scalars(select(Project).where(Project.code == body.code)).first():
        raise ConflictError("Project code already exists.")
    _check_pm(db, body.project_manager_id)
    project = Project(**body.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_out(project)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), _: User = Depends(internal)):
    project = db.get(Project, project_id)
    if not project or project.is_deleted:
        raise NotFoundError("Project not found.")
    return project_out(project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db), _: User = Depends(admin)):
    project = db.get(Project, project_id)
    if not project or project.is_deleted:
        raise NotFoundError("Project not found.")
    changes = body.model_dump(exclude_unset=True)
    if "project_manager_id" in changes:
        _check_pm(db, changes["project_manager_id"])
    for k, v in changes.items():
        setattr(project, k, v)
    db.commit()
    db.refresh(project)
    return project_out(project)


@router.post("/projects/{project_id}/partners", response_model=ProjectOut, status_code=201)
def link_partner(project_id: int, body: ProjectPartnerCreate, db: Session = Depends(get_db), _: User = Depends(admin)):
    project = db.get(Project, project_id)
    if not project or not db.get(Partner, body.partner_id):
        raise NotFoundError("Project or partner not found.")
    if any(link.partner_id == body.partner_id for link in project.partner_links):
        raise ConflictError("Partner already linked to this project.")
    db.add(ProjectPartner(project_id=project_id, **body.model_dump()))
    db.commit()
    db.refresh(project)
    return project_out(project)


def _check_pm(db: Session, user_id: int | None) -> None:
    if user_id is None:
        return
    pm = db.get(User, user_id)
    if not pm or not pm.has_role(RoleCode.PROJECT_MANAGER):
        raise ValidationFailedError("project_manager_id must reference a user with the PROJECT_MANAGER role.")

