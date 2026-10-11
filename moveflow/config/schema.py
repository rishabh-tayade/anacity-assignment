"""Shape of a community configuration file.

Everything that differs between communities is described here and loaded from
YAML: what we ask residents, which documents are needed, move slots, which
policy rules apply (and with what parameters), and how much the agent is allowed
to do on its own. Core code reads this; it never hard-codes a community.
"""

from __future__ import annotations

from datetime import time
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from moveflow.domain.enums import OccupancyType, RequestType, Severity

BOTH_TYPES = [RequestType.MOVE_IN, RequestType.MOVE_OUT]
BOTH_OCCUPANCIES = [OccupancyType.OWNER, OccupancyType.TENANT]

# Fields the core logic depends on. Every community must ask for these.
CORE_FIELDS = ("resident_name", "phone", "unit", "occupancy", "move_date", "time_slot")

FieldKind = Literal["text", "phone", "unit", "occupancy", "date", "slot", "number", "yes_no", "choice"]


class FieldSpec(BaseModel):
    key: str
    label: str
    question: str
    kind: FieldKind = "text"
    choices: list[str] = Field(default_factory=list)
    applies_to: list[RequestType] = Field(default_factory=lambda: list(BOTH_TYPES))
    required: bool = True
    # Profile fields are pre-filled from the logged-in resident's profile.
    from_profile: bool = False


class TimeSlot(BaseModel):
    id: str
    label: str
    start: time
    end: time
    capacity: int = 1
    aliases: list[str] = Field(default_factory=list)

    def contains(self, moment: time) -> bool:
        return self.start <= moment < self.end


class DocumentRequirement(BaseModel):
    doc_type: str
    label: str
    description: str = ""
    applies_to: list[RequestType] = Field(default_factory=lambda: list(BOTH_TYPES))
    occupancy: list[OccupancyType] = Field(default_factory=lambda: list(BOTH_OCCUPANCIES))


class RuleConfig(BaseModel):
    name: str
    severity: Severity = Severity.BLOCKER
    params: dict[str, Any] = Field(default_factory=dict)


class AutonomyConfig(BaseModel):
    """What the agent may decide without a human.

    Auto-approval only ever happens when every policy check passes; these
    settings narrow it further.
    """

    auto_approve: bool = False
    request_types: list[RequestType] = Field(default_factory=list)
    occupancy: list[OccupancyType] = Field(default_factory=list)


class Faq(BaseModel):
    question: str
    answer: str
    keywords: list[str] = Field(default_factory=list)


class CommunityConfig(BaseModel):
    id: str
    name: str
    city: str = ""
    admin_desk: str = "Facility desk"
    time_slots: list[TimeSlot]
    intake_fields: list[FieldSpec]
    documents: list[DocumentRequirement] = Field(default_factory=list)
    rules: list[RuleConfig] = Field(default_factory=list)
    autonomy: AutonomyConfig = Field(default_factory=AutonomyConfig)
    guidelines: dict[RequestType, list[str]] = Field(default_factory=dict)
    move_day_checklist: dict[RequestType, list[str]] = Field(default_factory=dict)
    faqs: list[Faq] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_core_fields(self) -> CommunityConfig:
        keys = {spec.key for spec in self.intake_fields}
        missing = [key for key in CORE_FIELDS if key not in keys]
        if missing:
            raise ValueError(f"Community '{self.id}' is missing core intake fields: {missing}")
        return self

    def fields_for(self, request_type: RequestType) -> list[FieldSpec]:
        return [spec for spec in self.intake_fields if request_type in spec.applies_to]

    def field(self, key: str) -> FieldSpec | None:
        return next((spec for spec in self.intake_fields if spec.key == key), None)

    def documents_for(
        self, request_type: RequestType, occupancy: OccupancyType | None
    ) -> list[DocumentRequirement]:
        if occupancy is None:
            return []
        return [
            doc
            for doc in self.documents
            if request_type in doc.applies_to and occupancy in doc.occupancy
        ]

    def slot(self, slot_id: str | None) -> TimeSlot | None:
        return next((slot for slot in self.time_slots if slot.id == slot_id), None)

    def slot_label(self, slot_id: str | None) -> str:
        slot = self.slot(slot_id)
        return slot.label if slot else (slot_id or "-")

    def document_label(self, doc_type: str) -> str:
        doc = next((d for d in self.documents if d.doc_type == doc_type), None)
        return doc.label if doc else doc_type.replace("_", " ").title()
