"""Decides what the intake agent should do next.

This is plain code on purpose. Given the same session it always picks the same
step, which makes the conversation predictable and easy to test. The LLM helps
understand the resident; it doesn't decide the flow.
"""

from __future__ import annotations

import dataclasses
from enum import StrEnum

from moveflow.agents.intake.conversation import Ambiguity, Choice, IntakeSession
from moveflow.config.schema import CommunityConfig, DocumentRequirement, FieldSpec
from moveflow.domain.enums import Severity
from moveflow.policies.base import CheckResult
from moveflow.services.compliance_service import ComplianceService, warnings
from moveflow.services.slot_service import SCHEDULING_FIELDS, SlotFinder

DOCUMENTS_RULE = "required_documents"


class StepKind(StrEnum):
    ASK_REQUEST_TYPE = "ask_request_type"
    CLARIFY = "clarify"
    FIX_ISSUES = "fix_issues"
    ASK_FIELD = "ask_field"
    ASK_DOCUMENTS = "ask_documents"
    CONFIRM = "confirm"
    SUBMIT = "submit"


@dataclasses.dataclass
class Step:
    kind: StepKind
    field: FieldSpec | None = None
    ambiguity: Ambiguity | None = None
    issues: list[CheckResult] = dataclasses.field(default_factory=list)
    # Numbered options shown to the resident; replying with a number picks one.
    choices: list[Choice] = dataclasses.field(default_factory=list)
    missing_documents: list[DocumentRequirement] = dataclasses.field(default_factory=list)
    documents_optional: bool = False
    warnings: list[CheckResult] = dataclasses.field(default_factory=list)
    checks: list[CheckResult] = dataclasses.field(default_factory=list)


class IntakePlanner:
    def __init__(self, compliance: ComplianceService, slot_finder: SlotFinder):
        self._compliance = compliance
        self._slot_finder = slot_finder

    def next_step(self, session: IntakeSession, config: CommunityConfig, confirmed: bool = False) -> Step:
        if session.pending_ambiguities:
            ambiguity = session.pending_ambiguities[0]
            return Step(StepKind.CLARIFY, ambiguity=ambiguity, choices=ambiguity.choices)
        if session.request_type is None:
            return Step(StepKind.ASK_REQUEST_TYPE)

        draft = session.to_draft()
        checks = self._compliance.check(draft)

        # Problems with what the resident already told us come first, so we don't
        # collect five more answers for a date that can never work.
        issues = [check for check in checks if check.is_blocking and check.rule != DOCUMENTS_RULE]
        if issues:
            choices = []
            if any(SCHEDULING_FIELDS & set(issue.fields) for issue in issues):
                choices = [
                    Choice(
                        label=option.describe(),
                        values={"move_date": option.move_date.isoformat(), "time_slot": option.slot_id},
                    )
                    for option in self._slot_finder.alternatives(draft)
                ]
            return Step(StepKind.FIX_ISSUES, issues=issues, choices=choices, checks=checks)

        next_field = self._next_unanswered_field(session, config)
        if next_field:
            choices = []
            if next_field.kind == "slot":
                choices = [Choice(label=slot.label, values={next_field.key: slot.id}) for slot in config.time_slots]
            return Step(StepKind.ASK_FIELD, field=next_field, choices=choices, checks=checks)

        documents_check = next((check for check in checks if check.rule == DOCUMENTS_RULE), None)
        missing_docs = [
            doc
            for doc in config.documents_for(draft.request_type, draft.occupancy)
            if doc.doc_type not in draft.uploaded_doc_types
        ]
        documents_optional = documents_check is None or documents_check.severity is Severity.WARNING
        if missing_docs and not (documents_optional and session.documents_deferred):
            return Step(
                StepKind.ASK_DOCUMENTS,
                missing_documents=missing_docs,
                documents_optional=documents_optional,
                checks=checks,
            )

        if confirmed:
            return Step(StepKind.SUBMIT, checks=checks)
        return Step(StepKind.CONFIRM, warnings=warnings(checks), checks=checks)

    @staticmethod
    def _next_unanswered_field(session: IntakeSession, config: CommunityConfig) -> FieldSpec | None:
        # Optional fields are asked once; a skipped answer is stored as None.
        return next(
            (spec for spec in config.fields_for(session.request_type) if spec.key not in session.answers),
            None,
        )
