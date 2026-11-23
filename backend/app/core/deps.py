from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.enums import RoleCode
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.models import User
from app.services.audit import set_audit_context

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise AuthenticationError("Missing bearer token.")
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise AuthenticationError("Invalid or expired token.") from None
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.is_deleted:
        raise AuthenticationError("User is inactive or no longer exists.")
    set_audit_context(
        db,
        user=user,
        request_id=getattr(request.state, "request_id", None),
        ip=request.client.host if request.client else None,
    )
    return user


def require_roles(*roles: RoleCode) -> Callable[[User], User]:
    """Endpoint guard: the caller must hold at least one of ``roles``."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if not user.has_role(*roles):
            raise PermissionDeniedError(
                "You do not have permission to perform this action.",
                details={"required_any_of": [r.value for r in roles]},
            )
        return user

    return _guard


# Convenience role groups
INTERNAL_READERS = (RoleCode.PROJECT_MANAGER, RoleCode.FINANCE_OFFICER, RoleCode.FINANCE_LEAD, RoleCode.AUDITOR)
ALL_ROLES = (RoleCode.PARTNER, *INTERNAL_READERS)
