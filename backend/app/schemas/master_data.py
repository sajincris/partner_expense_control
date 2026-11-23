from datetime import date

from pydantic import BaseModel, Field, model_validator

from app.core.enums import PeriodStatus
from app.schemas.common import CurrencyCode, FiscalYear, ORMModel, Period


class PartnerBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    registration_number: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    contact_email: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class PartnerCreate(PartnerBase):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9\-]+$")


class PartnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    registration_number: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)
    contact_email: str | None = None
    is_active: bool | None = None


class PartnerOut(ORMModel, PartnerBase):
    id: int
    code: str


class ProjectBase(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    donor: str | None = Field(default=None, max_length=200)
    start_date: date
    end_date: date
    currency: CurrencyCode = "USD"
    project_manager_id: int | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class ProjectCreate(ProjectBase):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Z0-9\-]+$")


class ProjectUpdate(BaseModel):
    name: str | None = None
    donor: str | None = None
    end_date: date | None = None
    project_manager_id: int | None = None
    is_active: bool | None = None


class ProjectPartnerOut(ORMModel):
    id: int
    partner_id: int
    partner_name: str
    agreement_reference: str | None = None
    is_active: bool


class ProjectOut(ORMModel):
    id: int
    code: str
    name: str
    donor: str | None
    start_date: date
    end_date: date
    currency: str
    project_manager_id: int | None
    project_manager_name: str | None = None
    is_active: bool
    partners: list[ProjectPartnerOut] = []


class ProjectPartnerCreate(BaseModel):
    partner_id: int
    agreement_reference: str | None = Field(default=None, max_length=100)
    start_date: date | None = None
    end_date: date | None = None


class CostCategoryOut(ORMModel):
    id: int
    code: str
    name: str


class GLAccountOut(ORMModel):
    id: int
    account_number: str
    name: str
    cost_category_id: int | None


class CurrencyOut(ORMModel):
    code: str
    name: str
    minor_units: int


class ReportingPeriodIn(BaseModel):
    fiscal_year: FiscalYear
    period: Period
    start_date: date
    end_date: date
    submission_deadline: date
    status: PeriodStatus = PeriodStatus.OPEN


class ReportingPeriodOut(ORMModel, ReportingPeriodIn):
    id: int


def project_out(p) -> ProjectOut:
    return ProjectOut(
        id=p.id, code=p.code, name=p.name, donor=p.donor, start_date=p.start_date, end_date=p.end_date,
        currency=p.currency, project_manager_id=p.project_manager_id,
        project_manager_name=p.project_manager.full_name if p.project_manager else None, is_active=p.is_active,
        partners=[
            ProjectPartnerOut(id=link.id, partner_id=link.partner_id, partner_name=link.partner.name,
                              agreement_reference=link.agreement_reference, is_active=link.is_active)
            for link in p.partner_links
        ],
    )

