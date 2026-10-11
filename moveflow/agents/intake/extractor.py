"""Understanding resident messages.

Two strategies share one interface:
- RuleBasedExtractor: regexes and keyword lists. Predictable, free, works offline.
- LLMExtractor: asks the model for structured output, then validates every value
  with the same parsers the rule-based path uses. Falls back to rules on any error.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Protocol

from moveflow.agents.intake import parsing
from moveflow.agents.intake.conversation import Ambiguity, Choice, Extraction, IntakeSession, Intent
from moveflow.agents.intake.field_parser import ONLY_WHEN_ASKED, FieldParser
from moveflow.agents.prompts import load_prompt
from moveflow.config.schema import CommunityConfig, FieldSpec
from moveflow.domain.enums import RequestType
from moveflow.llm.base import LLMClient, LLMError

logger = logging.getLogger(__name__)

_CANCEL = re.compile(r"\b(cancel|start over|restart|never ?mind|forget it)\b")
_STATUS = re.compile(r"\b(status|track)\b|\bupdate on my\b|\bwhere is my\b")
_QUESTION_START = re.compile(r"^(what|which|how|when|where|why|is there|are there|do i|does|do you)\b")


class FieldExtractor(Protocol):
    def extract(self, message: str, session: IntakeSession, config: CommunityConfig, today: date) -> Extraction: ...


class RuleBasedExtractor:
    def extract(self, message: str, session: IntakeSession, config: CommunityConfig, today: date) -> Extraction:
        text = parsing.normalise(message)

        if _CANCEL.search(text):
            return Extraction(intent=Intent.CANCEL)
        if _STATUS.search(text):
            return Extraction(intent=Intent.CHECK_STATUS)
        if "?" in message or _QUESTION_START.search(text):
            return Extraction(intent=Intent.ASK_QUESTION, question=message.strip())

        pending = config.field(session.pending_field) if session.pending_field else None
        if session.awaiting_confirmation:
            answer = parsing.parse_yes_no(text)
            if answer is True:
                return Extraction(intent=Intent.CONFIRM)
            if answer is False:
                return Extraction(intent=Intent.CHANGE)
        if parsing.is_skip(text) and not (pending and pending.kind == "yes_no"):
            return Extraction(intent=Intent.SKIP)

        request_type = parsing.detect_request_type(text)
        values, ambiguities = self._extract_fields(message, session, config, today, request_type)
        return Extraction(request_type=request_type, values=values, ambiguities=ambiguities)

    def _extract_fields(
        self,
        message: str,
        session: IntakeSession,
        config: CommunityConfig,
        today: date,
        request_type: RequestType | None,
    ) -> tuple[dict[str, Any], list[Ambiguity]]:
        parser = FieldParser(config, today)
        active_type = request_type or session.request_type
        specs = config.fields_for(active_type) if active_type else config.intake_fields
        # Free-text fields go last: they take the whole message only if nothing else matched.
        specs = sorted(specs, key=lambda spec: spec.kind == "text")

        values: dict[str, Any] = {}
        ambiguities: list[Ambiguity] = []
        for spec in specs:
            if spec.kind in ONLY_WHEN_ASKED and spec.key != session.pending_field:
                continue
            if spec.kind == "text" and (values or ambiguities or request_type):
                continue
            result = parser.parse(spec, message)
            if result.value is not None:
                values[spec.key] = result.value
            elif result.ambiguity:
                ambiguities.append(result.ambiguity)
        return values, ambiguities


EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": [intent.value for intent in Intent]},
        "request_type": {"type": "string", "enum": ["move_in", "move_out", "unknown"]},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                "required": ["key", "value"],
                "additionalProperties": False,
            },
        },
        "ambiguities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "question": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"label": {"type": "string"}, "value": {"type": "string"}},
                            "required": ["label", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["field", "question", "options"],
                "additionalProperties": False,
            },
        },
        "question": {"type": "string"},
    },
    "required": ["intent", "request_type", "fields", "ambiguities", "question"],
    "additionalProperties": False,
}


class LLMExtractor:
    def __init__(self, llm: LLMClient, fallback: FieldExtractor):
        self._llm = llm
        self._fallback = fallback

    def extract(self, message: str, session: IntakeSession, config: CommunityConfig, today: date) -> Extraction:
        try:
            raw = self._llm.generate_json(
                system=load_prompt("intake_extraction"),
                prompt=self._build_prompt(message, session, config, today),
                schema=EXTRACTION_SCHEMA,
            )
            return self._to_extraction(raw, config, today)
        except (LLMError, ValueError, KeyError) as error:
            logger.warning("LLM extraction failed, using rules instead: %s", error)
            return self._fallback.extract(message, session, config, today)

    def _build_prompt(self, message: str, session: IntakeSession, config: CommunityConfig, today: date) -> str:
        specs = config.fields_for(session.request_type) if session.request_type else config.intake_fields
        last_agent_message = next((t.text for t in reversed(session.turns) if t.role == "agent"), "")
        context = {
            "today": today.isoformat(),
            "today_weekday": today.strftime("%A"),
            "community": config.name,
            "request_type": session.request_type.value if session.request_type else "unknown",
            "fields": [_describe_field(spec) for spec in specs],
            "time_slots": [{"id": slot.id, "label": slot.label} for slot in config.time_slots],
            "known_answers": session.answers,
            "pending_field": session.pending_field,
            "awaiting_confirmation": session.awaiting_confirmation,
            "awaiting_documents": session.awaiting_documents,
            "offered_choices": [choice.model_dump() for choice in session.offered_choices],
            "last_agent_message": last_agent_message,
        }
        return f"Context:\n{json.dumps(context, indent=2, default=str)}\n\nResident message:\n{message}"

    def _to_extraction(self, raw: dict[str, Any], config: CommunityConfig, today: date) -> Extraction:
        parser = FieldParser(config, today)

        values: dict[str, Any] = {}
        for item in raw["fields"]:
            spec = config.field(item["key"])
            if spec is None:
                continue
            parsed = parser.parse(spec, item["value"])
            if parsed.value is not None:
                values[spec.key] = parsed.value

        ambiguities = []
        for item in raw["ambiguities"]:
            spec = config.field(item["field"])
            if spec is None:
                continue
            ambiguities.append(Ambiguity(
                field=spec.key,
                question=item["question"],
                choices=_valid_choices(parser, spec, item["options"]),
            ))

        request_type = raw["request_type"]
        return Extraction(
            intent=Intent(raw["intent"]),
            request_type=RequestType(request_type) if request_type != "unknown" else None,
            values=values,
            ambiguities=ambiguities,
            question=raw["question"],
            source=self._llm.model_name,
        )


def _describe_field(spec: FieldSpec) -> dict[str, Any]:
    described: dict[str, Any] = {"key": spec.key, "label": spec.label, "kind": spec.kind, "required": spec.required}
    if spec.choices:
        described["choices"] = spec.choices
    return described


def _valid_choices(parser: FieldParser, spec: FieldSpec, options: list[dict[str, str]]) -> list[Choice]:
    choices = []
    for option in options:
        parsed = parser.parse(spec, option["value"])
        if parsed.value is not None:
            choices.append(Choice(label=option["label"], values={spec.key: parsed.value}))
    return choices
