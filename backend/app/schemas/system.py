from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, model_validator

from app.core.enums import VarianceDirection
from app.schemas.common import CurrencyCode, NonNegativeMoney, ORMModel

Pct = Annotated[Decimal, Field(ge=0, le=1000, max_digits=9, decimal_places=4)]


class ToleranceRuleIn(BaseModel):
    name: str = Field(min_length=3, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    partner_id: int | None = None
    project_id: int | None = None
    cost_category_id: int | None = None
    max_variance_pct: Pct
    max_variance_abs: NonNegativeMoney
    abs_currency: CurrencyCode = "USD"
    direction: VarianceDirection = VarianceDirection.OVERSPEND_ONLY
    priority: int = Field(default=100, ge=1, le=10000)
    effective_from: date
    effective_to: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class ToleranceRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    max_variance_pct: Pct | None = None
    max_variance_abs: NonNegativeMoney | None = None
    direction: VarianceDirection | None = None
    priority: int | None = Field(default=None, ge=1, le=10000)
    effective_to: date | None = None
    is_active: bool | None = None
    change_reason: str = Field(min_length=5, max_length=1000)


class ToleranceRuleOut(ORMModel):
    id: int
    name: str
    description: str | None
    partner_id: int | None
    project_id: int | None
    cost_category_id: int | None
    max_variance_pct: Decimal
    max_variance_abs: Decimal
    abs_currency: str
    direction: VarianceDirection
    priority: int
    effective_from: date
    effective_to: date | None
    is_active: bool
    updated_at: datetime


class SettingOut(ORMModel):
    key: str
    value: Any
    description: str | None


class SettingUpdate(BaseModel):
    value: Any
    change_reason: str = Field(min_length=5, max_length=1000)


class AuditLogOut(ORMModel):
    id: int
    entity_type: str
    entity_id: str
    action: str
    old_values: dict | None
    new_values: dict | None
    comment: str | None
    actor_id: int | None
    actor_email: str | None
    actor_roles: str | None
    request_id: str | None
    ip_address: str | None
    created_at: datetime


class NotificationOut(ORMModel):
    id: int
    type: str
    title: str
    message: str
    entity_type: str | None
    entity_id: int | None
    read_at: datetime | None
    created_at: datetime
