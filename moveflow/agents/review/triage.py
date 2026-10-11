from datetime import date

from moveflow.domain.enums import RequestStatus
from moveflow.domain.models import MoveRequest

# Lower number = shown first in the admin queue.
_STATUS_ORDER = {
    RequestStatus.SUBMITTED: 0,
    RequestStatus.UNDER_REVIEW: 0,
    RequestStatus.NEEDS_INFO: 1,
    RequestStatus.APPROVED: 2,
}


def prioritise(requests: list[MoveRequest], today: date) -> list[MoveRequest]:
    """Orders the queue: requests waiting on the admin first, soonest move date first."""

    def sort_key(request: MoveRequest) -> tuple[int, int]:
        days_to_move = (request.move_date - today).days if request.move_date else 999
        return _STATUS_ORDER.get(request.status, 3), days_to_move

    return sorted(requests, key=sort_key)
