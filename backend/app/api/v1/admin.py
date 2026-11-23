"""Audit trail, system configuration, reporting periods, notifications."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.enums import RoleCode
from app.core.errors import ConflictError, NotFoundError
from app.models import AuditLog, Notification, ReportingPeriod, SystemSetting, ToleranceRule, User
from app.models.base import utcnow
from app.schemas.master_data import ReportingPeriodIn, ReportingPeriodOut
from app.schemas.system import (
    AuditLogOut,
    NotificationOut,
    SettingOut,
    SettingUpdate,
    ToleranceRuleIn,
    ToleranceRuleOut,
    ToleranceRuleUpdate,
)
from app.services.audit import record_event
from app.services.settings_service import DEFAULT_SETTINGS
from app.utils.pagination import Page, PageParams, apply_sort, paginate

router = APIRouter()
admin = require_roles(RoleCode.FINANCE_LEAD)
config_readers = require_roles(RoleCode.FINANCE_LEAD, RoleCode.FINANCE_OFFICER, RoleCode.AUDITOR)
audit_readers = require_roles(RoleCode.FINANCE_LEAD, RoleCode.FINANCE_OFFICER, RoleCode.AUDITOR, RoleCode.PROJECT_MANAGER)


# ------------------------------------------------------------------ audit trail (read-only for everyone)
@router.get("/audit-logs", response_model=Page[AuditLogOut], tags=["Audit trail"])
def audit_logs(
    params: PageParams = Depends(),
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    actor_id: int | None = None,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(audit_readers),
):
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    stmt = apply_sort(stmt, params.sort, {"created_at": AuditLog.created_at, "entity_type": AuditLog.entity_type}, AuditLog.id.desc())
    return paginate(db, stmt, params, AuditLogOut.model_validate)


# ------------------------------------------------------------------ tolerance rules
@router.get("/config/tolerance-rules", response_model=list[ToleranceRuleOut], tags=["Configuration"])
def list_rules(include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(config_readers)):
    stmt = select(ToleranceRule).order_by(ToleranceRule.priority, ToleranceRule.id)
    if not include_inactive:
        stmt = stmt.where(ToleranceRule.is_active.is_(True))
    return db.scalars(stmt).all()


@router.post("/config/tolerance-rules", response_model=ToleranceRuleOut, status_code=201, tags=["Configuration"])
def create_rule(body: ToleranceRuleIn, db: Session = Depends(get_db), _: User = Depends(admin)):
    rule = ToleranceRule(**body.model_dump())
    db.add(rule)
    db.commit()
    return rule


@router.patch("/config/tolerance-rules/{rule_id}", response_model=ToleranceRuleOut, tags=["Configuration"],
              summary="Change a rule. A change reason is mandatory and stored in the audit trail.")
def update_rule(rule_id: int, body: ToleranceRuleUpdate, db: Session = Depends(get_db), _: User = Depends(admin)):
    rule = db.get(ToleranceRule, rule_id)
    if not rule:
        raise NotFoundError("Tolerance rule not found.")
    changes = body.model_dump(exclude_unset=True, exclude={"change_reason"})
    for k, v in changes.items():
        setattr(rule, k, v)
    record_event(db, entity_type="tolerance_rules", entity_id=rule.id, action="CONFIG_CHANGE", comment=body.change_reason,
                 new_values=changes)
    db.commit()
    db.refresh(rule)
    return rule


# ------------------------------------------------------------------ system settings
@router.get("/config/settings", response_model=list[SettingOut], tags=["Configuration"])
def list_settings(db: Session = Depends(get_db), _: User = Depends(config_readers)):
    rows = {s.key: s for s in db.scalars(select(SystemSetting)).all()}
    return [
        SettingOut(key=k, value=(rows[k].value.get("value") if k in rows else v), description=(rows[k].description if k in rows else d))
        for k, (v, d) in DEFAULT_SETTINGS.items()
    ]


@router.put("/config/settings/{key}", response_model=SettingOut, tags=["Configuration"])
def update_setting(key: str, body: SettingUpdate, db: Session = Depends(get_db), _: User = Depends(admin)):
    if key not in DEFAULT_SETTINGS:
        raise NotFoundError("Unknown setting.")
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value={"value": body.value}, description=DEFAULT_SETTINGS[key][1])
        db.add(row)
    else:
        row.value = {"value": body.value}
    record_event(db, entity_type="system_settings", entity_id=key, action="CONFIG_CHANGE", comment=body.change_reason,
                 new_values={"value": body.value})
    db.commit()
    return SettingOut(key=key, value=body.value, description=row.description)


# ------------------------------------------------------------------ reporting periods
@router.get("/config/reporting-periods", response_model=list[ReportingPeriodOut], tags=["Configuration"])
def list_periods(fiscal_year: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(ReportingPeriod).order_by(ReportingPeriod.fiscal_year, ReportingPeriod.period)
    if fiscal_year:
        stmt = stmt.where(ReportingPeriod.fiscal_year == fiscal_year)
    return db.scalars(stmt).all()


@router.post("/config/reporting-periods", response_model=ReportingPeriodOut, status_code=201, tags=["Configuration"])
def create_period(body: ReportingPeriodIn, db: Session = Depends(get_db), _: User = Depends(admin)):
    if db.scalars(select(ReportingPeriod).where(ReportingPeriod.fiscal_year == body.fiscal_year, ReportingPeriod.period == body.period)).first():
        raise ConflictError("Reporting period already exists.")
    period = ReportingPeriod(**body.model_dump())
    db.add(period)
    db.commit()
    return period


@router.patch("/config/reporting-periods/{period_id}", response_model=ReportingPeriodOut, tags=["Configuration"],
              summary="Open/close a period or move its deadline")
def update_period(period_id: int, body: ReportingPeriodIn, db: Session = Depends(get_db), _: User = Depends(admin)):
    period = db.get(ReportingPeriod, period_id)
    if not period:
        raise NotFoundError("Reporting period not found.")
    for k in ("status", "submission_deadline", "start_date", "end_date"):
        setattr(period, k, getattr(body, k))
    db.commit()
    return period


# ------------------------------------------------------------------ notifications
@router.get("/notifications", response_model=list[NotificationOut], tags=["Notifications"])
def my_notifications(unread_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(100)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    return db.scalars(stmt).all()


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut, tags=["Notifications"])
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise NotFoundError("Notification not found.")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return n
