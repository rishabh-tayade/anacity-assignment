from enum import StrEnum


class RequestType(StrEnum):
    MOVE_IN = "move_in"
    MOVE_OUT = "move_out"

    @property
    def label(self) -> str:
        return self.value.replace("_", "-").capitalize()


class OccupancyType(StrEnum):
    OWNER = "owner"
    TENANT = "tenant"


class RequestStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    NEEDS_INFO = "needs_info"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").capitalize()


class Actor(StrEnum):
    RESIDENT = "resident"
    ADMIN = "admin"
    AGENT = "agent"
    SYSTEM = "system"


class Severity(StrEnum):
    """How a failed policy check affects the request.

    BLOCKER: the resident has to fix it before the request can be submitted.
    WARNING: the request can go through, but an admin should look at it.
    """

    BLOCKER = "blocker"
    WARNING = "warning"
