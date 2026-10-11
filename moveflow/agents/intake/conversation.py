"""State the intake agent keeps between turns of a conversation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from moveflow.domain.enums import RequestType
from moveflow.domain.models import MoveRequest, UploadedDocument


class Intent(StrEnum):
    PROVIDE_INFO = "provide_info"
    ASK_QUESTION = "ask_question"
    CONFIRM = "confirm"
    CHANGE = "change"
    SKIP = "skip"
    CHECK_STATUS = "check_status"
    CANCEL = "cancel"


class Choice(BaseModel):
    """An option the agent offered, e.g. an alternative slot. Picking it fills in `values`."""

    label: str
    values: dict[str, Any]


class Ambiguity(BaseModel):
    field: str
    question: str
    choices: list[Choice] = Field(default_factory=list)


class Extraction(BaseModel):
    """What the agent understood from one resident message."""

    intent: Intent = Intent.PROVIDE_INFO
    request_type: RequestType | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    question: str = ""
    source: str = "rules"


class ChatTurn(BaseModel):
    role: Literal["resident", "agent"]
    text: str


class IntakeSession(BaseModel):
    community_id: str
    # What the platform already knows about the logged-in resident (name, phone).
    profile: dict[str, str] = Field(default_factory=dict)
    request_type: RequestType | None = None
    answers: dict[str, Any] = Field(default_factory=dict)
    documents: list[UploadedDocument] = Field(default_factory=list)
    turns: list[ChatTurn] = Field(default_factory=list)

    # What the agent last asked for; used to interpret short replies like "2" or "no".
    pending_field: str | None = None
    # Things the resident said that could mean more than one thing, asked about one at a time.
    pending_ambiguities: list[Ambiguity] = Field(default_factory=list)
    offered_choices: list[Choice] = Field(default_factory=list)
    awaiting_confirmation: bool = False
    awaiting_documents: bool = False
    documents_deferred: bool = False

    submitted_request_id: str | None = None

    @classmethod
    def start(cls, community_id: str, profile: dict[str, str]) -> IntakeSession:
        """Begin a conversation, pre-filling what the platform already knows about the resident."""
        answers = {key: value for key, value in profile.items() if value}
        return cls(community_id=community_id, profile=profile, answers=answers)

    def reset(self) -> None:
        """Clears the draft but keeps the chat history."""
        fresh = IntakeSession.start(self.community_id, self.profile)
        for name in IntakeSession.model_fields:
            if name != "turns":
                setattr(self, name, getattr(fresh, name))

    def apply(self, extraction: Extraction) -> dict[str, Any]:
        """Merges an extraction into the session. Returns only the values that changed."""
        if extraction.request_type and extraction.request_type != self.request_type:
            self.request_type = extraction.request_type

        changed = {key: value for key, value in extraction.values.items() if self.answers.get(key, ...) != value}
        self.answers.update(extraction.values)

        new_fields = {ambiguity.field for ambiguity in extraction.ambiguities}
        self.pending_ambiguities = [
            ambiguity
            for ambiguity in self.pending_ambiguities
            if ambiguity.field not in extraction.values and ambiguity.field not in new_fields
        ] + list(extraction.ambiguities)
        return changed

    def skip_pending(self) -> bool:
        """Handles "skip" / "none" / "later". Returns False if there was nothing to skip."""
        if self.awaiting_documents:
            self.documents_deferred = True
            return True
        if self.pending_field:
            self.answers[self.pending_field] = None
            return True
        return False

    def add_document(self, document: UploadedDocument) -> None:
        self.documents = [doc for doc in self.documents if doc.doc_type != document.doc_type]
        self.documents.append(document)

    def add_turn(self, role: Literal["resident", "agent"], text: str) -> None:
        self.turns.append(ChatTurn(role=role, text=text))

    def to_draft(self) -> MoveRequest:
        if self.request_type is None:
            raise ValueError("Request type is not known yet")
        return MoveRequest(
            community_id=self.community_id,
            request_type=self.request_type,
            answers=dict(self.answers),
            documents=list(self.documents),
        )
