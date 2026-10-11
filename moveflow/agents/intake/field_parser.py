from dataclasses import dataclass
from datetime import date
from typing import Any

from moveflow.agents.intake import parsing
from moveflow.agents.intake.conversation import Ambiguity, Choice
from moveflow.config.schema import CommunityConfig, FieldSpec

# These kinds can't be spotted reliably in free text ("2" could be anything),
# so we only read them when the agent has just asked for that field.
ONLY_WHEN_ASKED = {"number", "yes_no", "choice", "text"}


@dataclass(frozen=True)
class FieldParse:
    value: Any = None
    ambiguity: Ambiguity | None = None


class FieldParser:
    """Turns text into the canonical value for one intake field."""

    def __init__(self, config: CommunityConfig, today: date):
        self._config = config
        self._today = today

    def parse(self, spec: FieldSpec, text: str) -> FieldParse:
        handler = getattr(self, f"_parse_{spec.kind}")
        return handler(spec, text)

    def _parse_unit(self, spec: FieldSpec, text: str) -> FieldParse:
        unit = parsing.find_unit(text)
        if unit:
            return FieldParse(unit)
        if parsing.mentions_unit_without_tower(text):
            return FieldParse(ambiguity=Ambiguity(
                field=spec.key,
                question="Which tower is that flat in? Please share the full unit number, for example B-1204.",
            ))
        return FieldParse()

    def _parse_occupancy(self, spec: FieldSpec, text: str) -> FieldParse:
        occupancy = parsing.find_occupancy(text)
        return FieldParse(occupancy.value if occupancy else None)

    def _parse_date(self, spec: FieldSpec, text: str) -> FieldParse:
        guess = parsing.parse_date(text, self._today)
        if guess.value:
            return FieldParse(guess.value.isoformat())
        if guess.question:
            choices = [
                Choice(label=parsing.format_day(option), values={spec.key: option.isoformat()})
                for option in guess.options
            ]
            return FieldParse(ambiguity=Ambiguity(field=spec.key, question=guess.question, choices=choices))
        return FieldParse()

    def _parse_slot(self, spec: FieldSpec, text: str) -> FieldParse:
        return FieldParse(parsing.find_slot(text, self._config.time_slots))

    def _parse_phone(self, spec: FieldSpec, text: str) -> FieldParse:
        return FieldParse(parsing.find_phone(text))

    def _parse_number(self, spec: FieldSpec, text: str) -> FieldParse:
        return FieldParse(parsing.find_number(text))

    def _parse_yes_no(self, spec: FieldSpec, text: str) -> FieldParse:
        lowered = parsing.normalise(text)
        if lowered in ("true", "false"):
            return FieldParse(lowered == "true")
        return FieldParse(parsing.parse_yes_no(text))

    def _parse_choice(self, spec: FieldSpec, text: str) -> FieldParse:
        lowered = parsing.normalise(text)
        match = next((choice for choice in spec.choices if choice.lower() in lowered), None)
        return FieldParse(match)

    def _parse_text(self, spec: FieldSpec, text: str) -> FieldParse:
        cleaned = text.strip()
        return FieldParse(cleaned if cleaned and not parsing.is_skip(cleaned) else None)
