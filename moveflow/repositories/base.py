from collections.abc import Collection
from typing import Protocol

from moveflow.domain.enums import RequestStatus
from moveflow.domain.models import MoveRequest


class RequestRepository(Protocol):
    def save(self, request: MoveRequest) -> None: ...

    def get(self, request_id: str) -> MoveRequest | None: ...

    def list(
        self,
        community_id: str | None = None,
        statuses: Collection[RequestStatus] | None = None,
    ) -> list[MoveRequest]: ...

    def list_for_resident(self, community_id: str, phone: str) -> list[MoveRequest]: ...


class RequestNotFoundError(LookupError):
    pass
