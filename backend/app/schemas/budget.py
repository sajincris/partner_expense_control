from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.core.enums import BudgetVersionStatus
from app.schemas.common import CurrencyCode, FiscalYear, NonNegativeMoney, ORMModel, Period


class BudgetLineIn(BaseModel):
    period: Period
    cost_category_id: int
    gl_account_id: int
    planned_amount: NonNegativeMoney
    notes: str | None = Field(default=None, max_length=500)


class BudgetVersionCreate(BaseModel):
    change_reason: str = Field(min_length=5, max_length=2000)
    lines: list[BudgetLineIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_keys(self):
        keys = [(ln.period, ln.cost_category_id, ln.gl_account_id) for ln in self.lines]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate (period, cost_category_id, gl_account_id) lines in the version")
        return self


class BudgetPlanCreate(BaseModel):
    partner_id: int
    project_id: int
    fiscal_year: FiscalYear
    currency: CurrencyCode = "USD"
    name: str = Field(min_length=3, max_length=200)
    initial_version: BudgetVersionCreate


class BudgetLineOut(ORMModel):
    id: int
    period: int
    cost_category_id: int
    cost_category_name: str
    gl_account_id: int
    gl_account_number: str
    planned_amount: Decimal
    notes: str | None = None


class BudgetVersionOut(ORMModel):
    id: int
    version_no: int
    status: BudgetVersionStatus
    change_reason: str
    total_amount: Decimal
    created_by_id: int | None
    approved_by_id: int | None
    approved_at: datetime | None
    created_at: datetime


class BudgetVersionDetail(BudgetVersionOut):
    lines: list[BudgetLineOut]


class BudgetPlanOut(ORMModel):
    id: int
    partner_id: int
    partner_name: str
    project_id: int
    project_code: str
    project_name: str
    fiscal_year: int
    currency: str
    name: str
    active_version_no: int | None
    active_total: Decimal | None
    versions: list[BudgetVersionOut] = []


class BudgetImportResult(BaseModel):
    plans_created: int
    versions_created: int
    lines_imported: int
    errors: list[str] = []


def line_out(ln) -> BudgetLineOut:
    return BudgetLineOut(
        id=ln.id, period=ln.period, cost_category_id=ln.cost_category_id, cost_category_name=ln.cost_category.name,
        gl_account_id=ln.gl_account_id, gl_account_number=ln.gl_account.account_number,
        planned_amount=ln.planned_amount, notes=ln.notes,
    )


def plan_out(plan) -> BudgetPlanOut:
    active = plan.active_version
    return BudgetPlanOut(
        id=plan.id, partner_id=plan.partner_id, partner_name=plan.partner.name, project_id=plan.project_id,
        project_code=plan.project.code, project_name=plan.project.name, fiscal_year=plan.fiscal_year,
        currency=plan.currency, name=plan.name,
        active_version_no=active.version_no if active else None,
        active_total=active.total_amount if active else None,
        versions=[BudgetVersionOut.model_validate(v) for v in plan.versions],
    )
