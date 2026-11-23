from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.errors import AuthenticationError
from app.core.security import create_access_token, verify_password
from app.models import User
from app.models.base import utcnow
from app.schemas.identity import LoginRequest, TokenResponse, UserOut, user_out
from app.services.audit import record_event, set_audit_context

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _login(db: Session, email: str, password: str) -> TokenResponse:
    user = db.scalars(select(User).where(User.email == email.lower().strip())).first()
    if not user or user.is_deleted or not user.is_active or not verify_password(password, user.password_hash):
        db.info["audit_disabled"] = True  # a failed login must not leave a dirty session
        record_event(db, entity_type="users", entity_id=user.id if user else "unknown", action="LOGIN_FAILED",
                     new_values={"email": email.lower().strip()})
        db.commit()
        raise AuthenticationError("Invalid email or password.")
    set_audit_context(db, user=user)
    user.last_login_at = utcnow()
    db.info["audit_disabled"] = True  # last_login_at is not a business change; LOGIN event below
    db.flush()
    db.info["audit_disabled"] = False
    record_event(db, entity_type="users", entity_id=user.id, action="LOGIN")
    db.commit()
    token = create_access_token(user.id, [r.value for r in user.role_codes], {"partner_id": user.partner_id})
    return TokenResponse(access_token=token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, user=user_out(user))


@router.post("/login", response_model=TokenResponse, summary="Login (JSON or OAuth2 form)")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenResponse:
    """OAuth2 password flow (used by Swagger's *Authorize* button). `username` = email."""
    return _login(db, form.username, form.password)


@router.post("/token", response_model=TokenResponse, summary="Login with a JSON body")
def login_json(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return _login(db, body.email, body.password)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return user_out(user)
