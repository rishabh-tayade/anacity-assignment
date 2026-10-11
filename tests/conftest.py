from datetime import date

import pytest

from moveflow.agents.intake.conversation import IntakeSession
from moveflow.container import Container, build_container
from moveflow.domain.enums import RequestStatus, RequestType
from moveflow.domain.models import MoveRequest, UploadedDocument
from moveflow.repositories.memory_repository import InMemoryRequestRepository

# A Monday. Green Meadows needs 3 days notice, blocks Sundays and 20 Oct (Dussehra).
TODAY = date(2026, 10, 12)


@pytest.fixture
def container() -> Container:
    return build_container(InMemoryRequestRepository(), llm=None, today=lambda: TODAY)


@pytest.fixture
def green(container):
    return container.catalog.get("green-meadows")


@pytest.fixture
def skyline(container):
    return container.catalog.get("skyline-towers")


def make_request(
    community_id: str = "green-meadows",
    request_type: RequestType = RequestType.MOVE_IN,
    status: RequestStatus = RequestStatus.DRAFT,
    docs: tuple[str, ...] = (),
    **answers,
) -> MoveRequest:
    defaults = {
        "resident_name": "Test Resident",
        "phone": "9000000000",
        "unit": "B-1204",
        "occupancy": "owner",
        "move_date": "2026-10-16",
        "time_slot": "morning",
    }
    return MoveRequest(
        community_id=community_id,
        request_type=request_type,
        status=status,
        answers={**defaults, **answers},
        documents=[UploadedDocument(doc_type=doc, file_name=f"{doc}.pdf") for doc in docs],
    )


def new_session(community_id: str = "green-meadows", name: str = "Ananya Rao", phone: str = "9876543210"):
    return IntakeSession.start(community_id, {"resident_name": name, "phone": phone})
