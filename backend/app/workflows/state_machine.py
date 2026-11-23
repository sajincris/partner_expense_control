"""Expense report status machine.

Single source of truth for which transitions exist, who may trigger them and
whether a comment is mandatory. Framework-free; enforced by
app.workflows.report_workflow and documented in docs/business-rules.md.
"""
from dataclasses import dataclass

from app.core.enums import ReportStatus as S
from app.core.enums import ReviewStage, RoleCode
from app.core.enums import WorkflowAction as A
from app.core.errors import InvalidTransitionError, PermissionDeniedError

SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class Transition:
    from_status: S
    action: A
    to_status: S
    stage: ReviewStage
    allowed_roles: frozenset  # RoleCode values, or {"SYSTEM"}
    comment_required: bool = False


TRANSITIONS: tuple[Transition, ...] = (
    # Partner
    Transition(S.DRAFT, A.SUBMIT, S.SUBMITTED, ReviewStage.PARTNER, frozenset({RoleCode.PARTNER})),
    Transition(S.DRAFT, A.CANCEL, S.CANCELLED, ReviewStage.PARTNER, frozenset({RoleCode.PARTNER})),
    Transition(S.RETURNED_FOR_CLARIFICATION, A.RESUBMIT, S.SUBMITTED, ReviewStage.PARTNER, frozenset({RoleCode.PARTNER}), comment_required=True),
    Transition(S.RETURNED_FOR_CLARIFICATION, A.CANCEL, S.CANCELLED, ReviewStage.PARTNER, frozenset({RoleCode.PARTNER}), comment_required=True),
    # System (control engine)
    Transition(S.SUBMITTED, A.AUTO_ACCEPT, S.AUTO_ACCEPTED, ReviewStage.SYSTEM, frozenset({SYSTEM})),
    Transition(S.SUBMITTED, A.ROUTE_TO_PM, S.PENDING_PM_REVIEW, ReviewStage.SYSTEM, frozenset({SYSTEM})),
    # Project Manager
    Transition(S.PENDING_PM_REVIEW, A.APPROVE, S.PENDING_FINANCE_REVIEW, ReviewStage.PM, frozenset({RoleCode.PROJECT_MANAGER}), comment_required=True),
    Transition(S.PENDING_PM_REVIEW, A.REJECT, S.REJECTED, ReviewStage.PM, frozenset({RoleCode.PROJECT_MANAGER}), comment_required=True),
    Transition(S.PENDING_PM_REVIEW, A.RETURN, S.RETURNED_FOR_CLARIFICATION, ReviewStage.PM, frozenset({RoleCode.PROJECT_MANAGER}), comment_required=True),
    # Finance (final approver for exceptions)
    Transition(S.PENDING_FINANCE_REVIEW, A.APPROVE, S.APPROVED, ReviewStage.FINANCE, frozenset({RoleCode.FINANCE_OFFICER}), comment_required=True),
    Transition(S.PENDING_FINANCE_REVIEW, A.REJECT, S.REJECTED, ReviewStage.FINANCE, frozenset({RoleCode.FINANCE_OFFICER}), comment_required=True),
    Transition(S.PENDING_FINANCE_REVIEW, A.RETURN, S.RETURNED_FOR_CLARIFICATION, ReviewStage.FINANCE, frozenset({RoleCode.FINANCE_OFFICER}), comment_required=True),
)

_INDEX = {(t.from_status, t.action): t for t in TRANSITIONS}


def get_transition(from_status: S, action: A) -> Transition:
    try:
        return _INDEX[(S(from_status), A(action))]
    except KeyError:
        raise InvalidTransitionError(
            f"Action {A(action).value} is not allowed when the report is {S(from_status).value}.",
            details={"from_status": S(from_status).value, "action": A(action).value,
                     "allowed_actions": [t.action.value for t in TRANSITIONS if t.from_status == S(from_status)]},
        ) from None


def authorize_transition(from_status: S, action: A, actor_roles: set, *, is_system: bool = False) -> Transition:
    t = get_transition(from_status, action)
    if is_system:
        if SYSTEM not in t.allowed_roles:
            raise PermissionDeniedError("The system cannot perform this transition.")
        return t
    if SYSTEM in t.allowed_roles or not t.allowed_roles.intersection(actor_roles):
        raise PermissionDeniedError(
            f"Your role is not allowed to {t.action.value} a report in status {t.from_status.value}.",
            details={"required_roles": sorted(r.value if hasattr(r, "value") else r for r in t.allowed_roles)},
        )
    return t


def available_actions(status: S, actor_roles: set) -> list[str]:
    return [t.action.value for t in TRANSITIONS if t.from_status == status and t.allowed_roles.intersection(actor_roles)]


def mermaid_diagram() -> str:
    """Generate the state diagram used in the docs (keeps docs in sync with code)."""
    lines = ["stateDiagram-v2", "    [*] --> DRAFT"]
    for t in TRANSITIONS:
        lines.append(f"    {t.from_status.value} --> {t.to_status.value}: {t.action.value} ({t.stage.value})")
    for terminal in (S.AUTO_ACCEPTED, S.APPROVED, S.REJECTED, S.CANCELLED):
        lines.append(f"    {terminal.value} --> [*]")
    return "\n".join(lines)
