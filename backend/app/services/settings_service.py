from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import MissingDocumentPolicy
from app.models import SystemSetting

DEFAULT_SETTINGS: dict[str, tuple[Any, str]] = {
    "missing_document_policy": (
        MissingDocumentPolicy.REQUIRE_REVIEW.value,
        "BLOCK = refuse submission when a line has no document; REQUIRE_REVIEW = create an exception and route to PM.",
    ),
    "pm_review_sla_days": (3, "Working days the Project Manager has before a review becomes overdue."),
    "finance_review_sla_days": (3, "Days Finance has before a validation becomes overdue."),
    "require_open_period": (True, "Reports can only be submitted for OPEN reporting periods."),
    "budget_maker_checker": (True, "A budget version must be activated by a different user than its creator."),
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(SystemSetting, key)
    if row is not None:
        value = row.value
        return value.get("value") if isinstance(value, dict) and "value" in value else value
    return DEFAULT_SETTINGS[key][0]


def ensure_defaults(db: Session) -> None:
    for key, (value, description) in DEFAULT_SETTINGS.items():
        if db.get(SystemSetting, key) is None:
            db.add(SystemSetting(key=key, value={"value": value}, description=description))
