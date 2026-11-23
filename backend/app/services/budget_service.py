"""Budget plans and versioning (reforecast trail with maker-checker)."""
import csv
import io
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import BudgetVersionStatus
from app.core.errors import ConflictError, NotFoundError, SegregationOfDutiesError, ValidationFailedError
from app.models import (
    BudgetPlan,
    BudgetPlanLine,
    BudgetPlanVersion,
    CostCategory,
    GLAccount,
    Partner,
    Project,
    ProjectPartner,
    User,
)
from app.models.base import utcnow
from app.schemas.budget import BudgetLineIn, BudgetPlanCreate, BudgetVersionCreate
from app.services.audit import record_event
from app.services.settings_service import get_setting


def _validate_lines(db: Session, lines: list[BudgetLineIn]) -> None:
    cat_ids = {ln.cost_category_id for ln in lines}
    gl_ids = {ln.gl_account_id for ln in lines}
    found_cats = set(db.scalars(select(CostCategory.id).where(CostCategory.id.in_(cat_ids))).all())
    found_gls = set(db.scalars(select(GLAccount.id).where(GLAccount.id.in_(gl_ids))).all())
    missing = {"cost_category_ids": sorted(cat_ids - found_cats), "gl_account_ids": sorted(gl_ids - found_gls)}
    if missing["cost_category_ids"] or missing["gl_account_ids"]:
        raise ValidationFailedError("Unknown cost categories or GL accounts.", details=missing)


def _add_version(db: Session, plan: BudgetPlan, data: BudgetVersionCreate, actor: User) -> BudgetPlanVersion:
    _validate_lines(db, data.lines)
    next_no = (db.scalar(select(func.max(BudgetPlanVersion.version_no)).where(BudgetPlanVersion.budget_plan_id == plan.id)) or 0) + 1
    version = BudgetPlanVersion(
        budget_plan_id=plan.id, version_no=next_no, status=BudgetVersionStatus.DRAFT, change_reason=data.change_reason,
        total_amount=sum((ln.planned_amount for ln in data.lines), Decimal("0.00")), created_by_id=actor.id,
    )
    db.add(version)
    db.flush()
    for ln in data.lines:
        db.add(BudgetPlanLine(version_id=version.id, **ln.model_dump()))
    db.flush()
    return version


def create_plan(db: Session, data: BudgetPlanCreate, actor: User) -> BudgetPlan:
    if not db.get(Partner, data.partner_id) or not db.get(Project, data.project_id):
        raise NotFoundError("Partner or project not found.")
    link = db.scalars(select(ProjectPartner).where(ProjectPartner.project_id == data.project_id, ProjectPartner.partner_id == data.partner_id)).first()
    if link is None:
        raise ValidationFailedError("The partner is not linked to this project.")
    exists = db.scalars(select(BudgetPlan).where(
        BudgetPlan.partner_id == data.partner_id, BudgetPlan.project_id == data.project_id, BudgetPlan.fiscal_year == data.fiscal_year
    )).first()
    if exists:
        raise ConflictError("A plan already exists for this partner, project and fiscal year; create a new version instead.",
                            details={"budget_plan_id": exists.id})
    plan = BudgetPlan(partner_id=data.partner_id, project_id=data.project_id, fiscal_year=data.fiscal_year,
                      currency=data.currency, name=data.name, created_by_id=actor.id)
    db.add(plan)
    db.flush()
    _add_version(db, plan, data.initial_version, actor)
    db.refresh(plan)
    return plan


def create_version(db: Session, plan_id: int, data: BudgetVersionCreate, actor: User) -> BudgetPlanVersion:
    plan = db.get(BudgetPlan, plan_id)
    if plan is None:
        raise NotFoundError("Budget plan not found.")
    return _add_version(db, plan, data, actor)


def activate_version(db: Session, plan_id: int, version_id: int, actor: User) -> BudgetPlanVersion:
    version = db.get(BudgetPlanVersion, version_id)
    if version is None or version.budget_plan_id != plan_id:
        raise NotFoundError("Budget version not found.")
    if version.status != BudgetVersionStatus.DRAFT:
        raise ValidationFailedError(f"Only DRAFT versions can be activated (current: {version.status.value}).")
    if get_setting(db, "budget_maker_checker") and version.created_by_id == actor.id:
        raise SegregationOfDutiesError("Maker-checker: a budget version must be activated by a different user than its creator.")
    current = db.scalars(select(BudgetPlanVersion).where(
        BudgetPlanVersion.budget_plan_id == plan_id, BudgetPlanVersion.status == BudgetVersionStatus.ACTIVE
    )).first()
    if current:
        current.status = BudgetVersionStatus.SUPERSEDED
        db.flush()  # free the partial unique index before activating the new one
    version.status = BudgetVersionStatus.ACTIVE
    version.approved_by_id = actor.id
    version.approved_at = utcnow()
    record_event(db, entity_type="budget_plan_versions", entity_id=version.id, action="ACTIVATE",
                 comment=version.change_reason,
                 old_values={"active_version": current.version_no if current else None, "total": str(current.total_amount) if current else None},
                 new_values={"active_version": version.version_no, "total": str(version.total_amount)})
    db.flush()
    return version


REQUIRED_COLUMNS = {"partner_code", "project_code", "fiscal_year", "period", "cost_category_code", "gl_account", "planned_amount"}


def import_csv(db: Session, content: bytes, change_reason: str, actor: User) -> dict:
    """Import plan lines from CSV. Creates one DRAFT version per partner/project/year.

    Columns: partner_code, project_code, fiscal_year, period, cost_category_code,
    gl_account, planned_amount[, currency]
    """
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset({f.strip() for f in reader.fieldnames}):
        raise ValidationFailedError("Invalid CSV header.", details={"required": sorted(REQUIRED_COLUMNS)})

    partners = {p.code: p for p in db.scalars(select(Partner)).all()}
    projects = {p.code: p for p in db.scalars(select(Project)).all()}
    cats = {c.code: c for c in db.scalars(select(CostCategory)).all()}
    gls = {g.account_number: g for g in db.scalars(select(GLAccount)).all()}

    groups: dict[tuple, list[BudgetLineIn]] = defaultdict(list)
    currencies: dict[tuple, str] = {}
    errors: list[str] = []
    for i, row in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        try:
            partner = partners[row["partner_code"]]
            project = projects[row["project_code"]]
            cat = cats[row["cost_category_code"]]
            gl = gls[row["gl_account"]]
            amount = Decimal(row["planned_amount"]).quantize(Decimal("0.01"))
            period = int(row["period"])
            fy = int(row["fiscal_year"])
            if amount < 0 or not 1 <= period <= 12:
                raise ValueError("amount must be >= 0 and period 1..12")
        except KeyError as e:
            errors.append(f"Row {i}: unknown code {e}")
            continue
        except (ValueError, InvalidOperation) as e:
            errors.append(f"Row {i}: {e}")
            continue
        key = (partner.id, project.id, fy)
        groups[key].append(BudgetLineIn(period=period, cost_category_id=cat.id, gl_account_id=gl.id, planned_amount=amount))
        currencies[key] = row.get("currency") or project.currency
    if errors:
        raise ValidationFailedError("CSV contains invalid rows; nothing was imported.", details={"errors": errors[:50]})

    plans_created = versions_created = lines = 0
    for (partner_id, project_id, fy), plan_lines in groups.items():
        version_data = BudgetVersionCreate(change_reason=change_reason, lines=plan_lines)
        plan = db.scalars(select(BudgetPlan).where(BudgetPlan.partner_id == partner_id, BudgetPlan.project_id == project_id, BudgetPlan.fiscal_year == fy)).first()
        if plan is None:
            project = db.get(Project, project_id)
            plan = create_plan(db, BudgetPlanCreate(
                partner_id=partner_id, project_id=project_id, fiscal_year=fy, currency=currencies[(partner_id, project_id, fy)],
                name=f"{project.code} FY{fy} plan", initial_version=version_data), actor)
            plans_created += 1
        else:
            _add_version(db, plan, version_data, actor)
        versions_created += 1
        lines += len(plan_lines)
    record_event(db, entity_type="budget_plans", entity_id="import", action="IMPORT", comment=change_reason,
                 new_values={"plans_created": plans_created, "versions_created": versions_created, "lines": lines})
    return {"plans_created": plans_created, "versions_created": versions_created, "lines_imported": lines, "errors": []}
