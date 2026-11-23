"""Audit trail.

Two complementary mechanisms:

1. ``after_flush`` listener: every INSERT / UPDATE / DELETE of a model marked
   ``__audited__ = True`` is written to ``audit_logs`` with field-level old and
   new values, automatically. Nobody - including administrators - can change an
   audited record through the application without leaving a trace.
2. ``record_event``: explicit business events (SUBMIT, APPROVE, LOGIN, EXPORT,
   ...) with a human-readable comment.

The acting user is attached to the session with ``set_audit_context``.
"""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import event, insert, inspect
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.system import AuditLog

EXCLUDED_FIELDS = {"password_hash", "updated_at", "created_at"}


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return str(value)


def set_audit_context(session: Session, *, user=None, request_id: str | None = None, ip: str | None = None) -> None:
    if user is not None:
        session.info["actor"] = {
            "id": user.id,
            "email": user.email,
            "roles": ",".join(sorted(r.value for r in user.role_codes)),
        }
    if request_id:
        session.info["request_id"] = request_id
    if ip:
        session.info["ip"] = ip


def _actor_fields(session: Session) -> dict[str, Any]:
    actor = session.info.get("actor") or {}
    return {
        "actor_id": actor.get("id"),
        "actor_email": actor.get("email", "system"),
        "actor_roles": actor.get("roles"),
        "request_id": session.info.get("request_id"),
        "ip_address": session.info.get("ip"),
    }


def _entity_id(obj: Any) -> str:
    ident = inspect(obj).identity
    if ident:
        return ":".join(str(i) for i in ident)
    pk = inspect(obj).mapper.primary_key
    return ":".join(str(getattr(obj, c.key, "")) for c in pk)


def _snapshot(obj: Any) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    return {
        attr.key: to_jsonable(getattr(obj, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in EXCLUDED_FIELDS
    }


def _diff(obj: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    state = inspect(obj)
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        if attr.key in EXCLUDED_FIELDS:
            continue
        hist = state.attrs[attr.key].history
        if hist.has_changes():
            old[attr.key] = to_jsonable(hist.deleted[0]) if hist.deleted else None
            new[attr.key] = to_jsonable(hist.added[0]) if hist.added else None
    return old, new


@event.listens_for(Session, "after_flush")
def _audit_after_flush(session: Session, flush_context) -> None:  # pragma: no cover - exercised in integration tests
    if session.info.get("audit_disabled"):
        return
    rows: list[dict[str, Any]] = []
    base = _actor_fields(session)
    now = utcnow()

    for obj in session.new:
        if getattr(obj, "__audited__", False):
            rows.append({**base, "entity_type": obj.__tablename__, "entity_id": _entity_id(obj), "action": "CREATE",
                         "old_values": None, "new_values": _snapshot(obj), "created_at": now})
    for obj in session.dirty:
        if getattr(obj, "__audited__", False) and session.is_modified(obj, include_collections=False):
            old, new = _diff(obj)
            if not new:
                continue
            action = "SOFT_DELETE" if new.get("is_deleted") is True else "UPDATE"
            if "status" in new and action == "UPDATE":
                action = "STATUS_CHANGE"
            rows.append({**base, "entity_type": obj.__tablename__, "entity_id": _entity_id(obj), "action": action,
                         "old_values": old, "new_values": new, "created_at": now})
    for obj in session.deleted:
        if getattr(obj, "__audited__", False):
            rows.append({**base, "entity_type": obj.__tablename__, "entity_id": _entity_id(obj), "action": "DELETE",
                         "old_values": _snapshot(obj), "new_values": None, "created_at": now})
    if rows:
        session.connection().execute(insert(AuditLog.__table__), rows)


def record_event(
    session: Session,
    *,
    entity_type: str,
    entity_id: Any,
    action: str,
    comment: str | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        comment=comment,
        old_values=to_jsonable(old_values) if old_values else None,
        new_values=to_jsonable(new_values) if new_values else None,
        created_at=utcnow(),
        **_actor_fields(session),
    )
    session.add(log)
    return log
