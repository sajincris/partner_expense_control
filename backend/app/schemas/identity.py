from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import RoleCode
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class RoleOut(ORMModel):
    id: int
    code: RoleCode
    name: str
    description: str | None = None


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    partner_id: int | None = None
    partner_name: str | None = None
    roles: list[RoleCode] = []
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    partner_id: int | None = None
    roles: list[RoleCode] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v.lower().strip()


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    is_active: bool | None = None
    partner_id: int | None = None


class UserRolesUpdate(BaseModel):
    roles: list[RoleCode] = Field(min_length=1)


def user_out(user) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        partner_id=user.partner_id,
        partner_name=user.partner.name if user.partner else None,
        roles=sorted(user.role_codes, key=lambda r: r.value),
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


TokenResponse.model_rebuild()
