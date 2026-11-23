import pytest

from app.core.enums import ReportStatus as S
from app.core.enums import RoleCode as R
from app.core.enums import WorkflowAction as A
from app.core.errors import InvalidTransitionError, PermissionDeniedError
from app.workflows.state_machine import (
    TRANSITIONS,
    authorize_transition,
    available_actions,
    get_transition,
    mermaid_diagram,
)


def test_every_status_is_reachable_or_initial():
    targets = {t.to_status for t in TRANSITIONS} | {S.DRAFT}
    assert targets == set(S)


def test_terminal_statuses_have_no_outgoing_transitions():
    for terminal in (S.AUTO_ACCEPTED, S.APPROVED, S.REJECTED, S.CANCELLED):
        assert not [t for t in TRANSITIONS if t.from_status == terminal]


def test_partner_cannot_approve():
    with pytest.raises(PermissionDeniedError):
        authorize_transition(S.PENDING_PM_REVIEW, A.APPROVE, {R.PARTNER})
    with pytest.raises(PermissionDeniedError):
        authorize_transition(S.PENDING_FINANCE_REVIEW, A.APPROVE, {R.PARTNER})


def test_pm_cannot_give_final_financial_approval():
    with pytest.raises(PermissionDeniedError):
        authorize_transition(S.PENDING_FINANCE_REVIEW, A.APPROVE, {R.PROJECT_MANAGER})


def test_pm_approval_goes_to_finance_not_to_approved():
    assert get_transition(S.PENDING_PM_REVIEW, A.APPROVE).to_status == S.PENDING_FINANCE_REVIEW


def test_only_finance_reaches_approved():
    into_approved = [t for t in TRANSITIONS if t.to_status == S.APPROVED]
    assert len(into_approved) == 1 and into_approved[0].allowed_roles == frozenset({R.FINANCE_OFFICER})


def test_admin_has_no_workflow_power():
    assert available_actions(S.PENDING_PM_REVIEW, {R.FINANCE_LEAD, R.AUDITOR}) == []


def test_reviewer_decisions_require_comment():
    for t in TRANSITIONS:
        if t.from_status in (S.PENDING_PM_REVIEW, S.PENDING_FINANCE_REVIEW):
            assert t.comment_required


def test_invalid_transition_lists_allowed_actions():
    with pytest.raises(InvalidTransitionError) as exc:
        get_transition(S.APPROVED, A.REJECT)
    assert exc.value.details["allowed_actions"] == []


def test_system_only_transitions():
    authorize_transition(S.SUBMITTED, A.AUTO_ACCEPT, set(), is_system=True)
    with pytest.raises(PermissionDeniedError):
        authorize_transition(S.SUBMITTED, A.AUTO_ACCEPT, {R.FINANCE_OFFICER})


def test_mermaid_diagram_contains_all_transitions():
    diagram = mermaid_diagram()
    assert diagram.count("-->") == len(TRANSITIONS) + 5
