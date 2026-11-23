from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-based page number"),
        size: int = Query(25, ge=1, le=200, description="Page size (max 200)"),
        sort: str | None = Query(None, description="Sort field, prefix with '-' for descending, e.g. -created_at"),
    ):
        self.page = page
        self.size = size
        self.sort = sort


def apply_sort(stmt: Select, sort: str | None, allowed: dict[str, Any], default: Any) -> Select:
    if not sort:
        return stmt.order_by(default)
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    if key not in allowed:
        raise ValidationFailedError(f"Cannot sort by '{key}'.", details={"allowed": sorted(allowed)})
    col = allowed[key]
    return stmt.order_by(col.desc() if desc else col.asc())


def paginate(db: Session, stmt: Select, params: PageParams, mapper=lambda x: x) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.offset((params.page - 1) * params.size).limit(params.size)).unique().all()
    return {
        "items": [mapper(r) for r in rows],
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": (total + params.size - 1) // params.size if total else 0,
    }
