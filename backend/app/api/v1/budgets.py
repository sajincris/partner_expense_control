from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import INTERNAL_READERS, get_current_user, require_roles
from app.core.enums import RoleCode
from app.core.errors import NotFoundError
from app.models import BudgetPlan, BudgetPlanVersion, Project, User
from app.schemas.budget import (
    BudgetImportResult,
    BudgetPlanCreate,
    BudgetPlanOut,
    BudgetVersionCreate,
    BudgetVersionDetail,
    BudgetVersionOut,
    line_out,
    plan_out,
)
from app.services import budget_service
from app.utils.pagination import Page, PageParams, apply_sort, paginate

router = APIRouter(prefix="/budget-plans", tags=["Budget plans"])
planners = require_roles(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD)
approver = require_roles(RoleCode.FINANCE_LEAD)


@router.get("", response_model=Page[BudgetPlanOut])
def list_plans(params: PageParams = Depends(), fiscal_year: int | None = None, partner_id: int | None = None,
               project_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(BudgetPlan)
    if user.has_role(RoleCode.PARTNER) and not user.has_role(*INTERNAL_READERS):
        partner_id = user.partner_id
    elif user.has_role(RoleCode.PROJECT_MANAGER) and not user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        stmt = stmt.join(Project).where(Project.project_manager_id == user.id)
    if fiscal_year:
        stmt = stmt.where(BudgetPlan.fiscal_year == fiscal_year)
    if partner_id:
        stmt = stmt.where(BudgetPlan.partner_id == partner_id)
    if project_id:
        stmt = stmt.where(BudgetPlan.project_id == project_id)
    stmt = apply_sort(stmt, params.sort, {"fiscal_year": BudgetPlan.fiscal_year, "created_at": BudgetPlan.created_at}, BudgetPlan.id)
    return paginate(db, stmt, params, plan_out)


@router.post("", response_model=BudgetPlanOut, status_code=201,
             summary="Create a plan with its first (DRAFT) version")
def create_plan(body: BudgetPlanCreate, db: Session = Depends(get_db), actor: User = Depends(planners)):
    plan = budget_service.create_plan(db, body, actor)
    db.commit()
    return plan_out(plan)


@router.post("/import", response_model=BudgetImportResult, summary="Upload plan lines from CSV (creates DRAFT versions)")
async def import_plans(file: UploadFile = File(...), change_reason: str = Form(..., min_length=5),
                       db: Session = Depends(get_db), actor: User = Depends(planners)):
    result = budget_service.import_csv(db, await file.read(), change_reason, actor)
    db.commit()
    return result


@router.get("/{plan_id}", response_model=BudgetPlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return plan_out(_visible_plan(db, plan_id, user))


@router.get("/{plan_id}/versions/{version_id}", response_model=BudgetVersionDetail)
def get_version(plan_id: int, version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _visible_plan(db, plan_id, user)
    version = db.get(BudgetPlanVersion, version_id)
    if not version or version.budget_plan_id != plan_id:
        raise NotFoundError("Budget version not found.")
    base = BudgetVersionOut.model_validate(version).model_dump()
    return BudgetVersionDetail(**base, lines=[line_out(ln) for ln in sorted(version.lines, key=lambda x: (x.period, x.cost_category_id, x.gl_account_id))])


@router.post("/{plan_id}/versions", response_model=BudgetVersionOut, status_code=201,
             summary="Create a new DRAFT version (reforecast). Reason is mandatory.")
def create_version(plan_id: int, body: BudgetVersionCreate, db: Session = Depends(get_db), actor: User = Depends(planners)):
    version = budget_service.create_version(db, plan_id, body, actor)
    db.commit()
    return version


@router.post("/{plan_id}/versions/{version_id}/activate", response_model=BudgetVersionOut,
             summary="Activate a DRAFT version (maker-checker: Finance Lead, not the creator)")
def activate_version(plan_id: int, version_id: int, db: Session = Depends(get_db), actor: User = Depends(approver)):
    version = budget_service.activate_version(db, plan_id, version_id, actor)
    db.commit()
    return version


def _visible_plan(db: Session, plan_id: int, user: User) -> BudgetPlan:
    plan = db.get(BudgetPlan, plan_id)
    if plan is None:
        raise NotFoundError("Budget plan not found.")
    if user.has_role(RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR):
        return plan
    if user.has_role(RoleCode.PROJECT_MANAGER) and plan.project.project_manager_id == user.id:
        return plan
    if user.has_role(RoleCode.PARTNER) and plan.partner_id == user.partner_id:
        return plan
    raise NotFoundError("Budget plan not found.")
