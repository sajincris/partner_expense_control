from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

MoneyIn = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
CurrencyCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")]
Period = Annotated[int, Field(ge=1, le=12)]
FiscalYear = Annotated[int, Field(ge=2000, le=2100)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = {}


class ErrorResponse(BaseModel):
    error: ErrorBody


class Message(BaseModel):
    message: str
