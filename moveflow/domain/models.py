from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from moveflow.domain.enums import Actor, OccupancyType, RequestStatus, RequestType


def _new_request_id() -> str:
    return "MV-" + uuid.uuid4().hex[:6].upper()


class UploadedDocument(BaseModel):
    doc_type: str
    file_name: str
    uploaded_at: datetime = Field(default_factory=datetime.now)


class TimelineEvent(BaseModel):
    at: datetime = Field(default_factory=datetime.now)
    actor: Actor
    action: str
    note: str = ""


class Message(BaseModel):
    """A message exchanged between the admin desk and the resident on a request."""

    at: datetime = Field(default_factory=datetime.now)
    sender: Actor
    text: str


class MoveRequest(BaseModel):
    """A move-in or move-out request.

    Everything the resident tells us lives in `answers`, keyed by the field keys
    defined in the community config. That keeps the model the same for every
    community; the typed properties below expose the handful of core fields that
    the policies and the UI rely on.
    """

    id: str = Field(default_factory=_new_request_id)
    community_id: str
    request_type: RequestType
    status: RequestStatus = RequestStatus.DRAFT
    answers: dict[str, Any] = Field(default_factory=dict)
    documents: list[UploadedDocument] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @property
    def resident_name(self) -> str:
        return self.answers.get("resident_name") or ""

    @property
    def phone(self) -> str:
        return self.answers.get("phone") or ""

    @property
    def unit(self) -> str | None:
        return self.answers.get("unit")

    @property
    def occupancy(self) -> OccupancyType | None:
        value = self.answers.get("occupancy")
        return OccupancyType(value) if value else None

    @property
    def move_date(self) -> date | None:
        value = self.answers.get("move_date")
        return date.fromisoformat(value) if value else None

    @property
    def time_slot(self) -> str | None:
        return self.answers.get("time_slot")

    @property
    def uploaded_doc_types(self) -> set[str]:
        return {doc.doc_type for doc in self.documents}

    def record(self, actor: Actor, action: str, note: str = "") -> None:
        self.timeline.append(TimelineEvent(actor=actor, action=action, note=note))
        self.updated_at = datetime.now()

    def add_message(self, sender: Actor, text: str) -> None:
        self.messages.append(Message(sender=sender, text=text))
        self.updated_at = datetime.now()
