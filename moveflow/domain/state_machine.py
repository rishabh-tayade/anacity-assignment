"""Allowed status changes for a move request.

Keeping this as a plain table makes the lifecycle easy to read and to change.
Every status change in the system goes through `ensure_transition`.
"""

from moveflow.domain.enums import RequestStatus as S

TRANSITIONS: dict[S, set[S]] = {
    S.DRAFT: {S.SUBMITTED, S.CANCELLED},
    S.SUBMITTED: {S.UNDER_REVIEW, S.APPROVED, S.CANCELLED},
    S.UNDER_REVIEW: {S.APPROVED, S.REJECTED, S.NEEDS_INFO, S.CANCELLED},
    S.NEEDS_INFO: {S.UNDER_REVIEW, S.REJECTED, S.CANCELLED},
    S.APPROVED: {S.COMPLETED, S.CANCELLED},
    S.REJECTED: set(),
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}

# Requests in these states hold a move slot and count as "in flight" for a unit.
ACTIVE_STATUSES = frozenset({S.SUBMITTED, S.UNDER_REVIEW, S.NEEDS_INFO, S.APPROVED})

# Requests in these states are waiting on the admin desk.
AWAITING_ADMIN = frozenset({S.SUBMITTED, S.UNDER_REVIEW})


class InvalidTransitionError(Exception):
    def __init__(self, current: S, target: S):
        super().__init__(f"Cannot move a request from '{current.label}' to '{target.label}'.")
        self.current = current
        self.target = target


def can_transition(current: S, target: S) -> bool:
    return target in TRANSITIONS[current]


def ensure_transition(current: S, target: S) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


def is_final(status: S) -> bool:
    return not TRANSITIONS[status]
