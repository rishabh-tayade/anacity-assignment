from collections.abc import Collection

from moveflow.domain.enums import RequestStatus
from moveflow.domain.models import MoveRequest


class InMemoryRequestRepository:
    """Used by tests. Stores copies so callers can't mutate stored state by accident."""

    def __init__(self) -> None:
        self._requests: dict[str, MoveRequest] = {}

    def save(self, request: MoveRequest) -> None:
        self._requests[request.id] = request.model_copy(deep=True)

    def get(self, request_id: str) -> MoveRequest | None:
        request = self._requests.get(request_id)
        return request.model_copy(deep=True) if request else None

    def list(
        self,
        community_id: str | None = None,
        statuses: Collection[RequestStatus] | None = None,
    ) -> list[MoveRequest]:
        return [
            request.model_copy(deep=True)
            for request in self._requests.values()
            if (community_id is None or request.community_id == community_id)
            and (statuses is None or request.status in statuses)
        ]

    def list_for_resident(self, community_id: str, phone: str) -> list[MoveRequest]:
        return [request for request in self.list(community_id) if request.phone == phone]
