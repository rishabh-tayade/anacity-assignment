import pytest

from moveflow.domain.enums import RequestStatus as S
from moveflow.domain.state_machine import InvalidTransitionError, can_transition, ensure_transition, is_final


def test_normal_review_path_is_allowed():
    path = [S.DRAFT, S.SUBMITTED, S.UNDER_REVIEW, S.NEEDS_INFO, S.UNDER_REVIEW, S.APPROVED, S.COMPLETED]
    for current, target in zip(path, path[1:]):
        assert can_transition(current, target)


def test_agent_can_approve_straight_from_submitted():
    assert can_transition(S.SUBMITTED, S.APPROVED)


@pytest.mark.parametrize("current,target", [
    (S.DRAFT, S.APPROVED),
    (S.REJECTED, S.UNDER_REVIEW),
    (S.COMPLETED, S.CANCELLED),
    (S.NEEDS_INFO, S.APPROVED),
])
def test_invalid_transitions_raise(current, target):
    with pytest.raises(InvalidTransitionError):
        ensure_transition(current, target)


def test_final_states():
    assert {status for status in S if is_final(status)} == {S.REJECTED, S.COMPLETED, S.CANCELLED}
