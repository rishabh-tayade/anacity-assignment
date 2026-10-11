from collections.abc import Iterable
from datetime import date

from moveflow.domain.models import MoveRequest
from moveflow.domain.state_machine import ACTIVE_STATUSES


def count_bookings(
    requests: Iterable[MoveRequest],
    move_date: date,
    slot_id: str,
    exclude_request_id: str | None = None,
) -> int:
    """How many active requests already hold this date and slot."""
    return sum(
        1
        for request in requests
        if request.id != exclude_request_id
        and request.status in ACTIVE_STATUSES
        and request.move_date == move_date
        and request.time_slot == slot_id
    )
