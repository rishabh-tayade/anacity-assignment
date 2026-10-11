from __future__ import annotations

import logging
from typing import Protocol

from moveflow.agents.prompts import load_prompt
from moveflow.config.schema import CommunityConfig
from moveflow.domain.enums import RequestType
from moveflow.domain.models import MoveRequest
from moveflow.llm.base import LLMClient, LLMError
from moveflow.policies.base import CheckResult

logger = logging.getLogger(__name__)


class Summarizer(Protocol):
    source: str

    def summarize(self, request: MoveRequest, checks: list[CheckResult], config: CommunityConfig) -> str: ...


class TemplateSummarizer:
    source = "template"

    def summarize(self, request: MoveRequest, checks: list[CheckResult], config: CommunityConfig) -> str:
        direction = "into" if request.request_type is RequestType.MOVE_IN else "out of"
        occupancy = request.occupancy.value if request.occupancy else "resident"
        when = request.move_date.strftime("%a %d %b") if request.move_date else "an unspecified date"
        passed = sum(1 for check in checks if check.passed)
        summary = (
            f"{request.resident_name} ({occupancy}) wants to move {direction} {request.unit} on {when}, "
            f"{config.slot_label(request.time_slot).lower()}. {passed} of {len(checks)} checks passed."
        )
        failed = [check.title.lower() for check in checks if not check.passed]
        if failed:
            summary += " Needs attention: " + ", ".join(failed) + "."
        return summary


class LLMSummarizer:
    def __init__(self, llm: LLMClient, fallback: Summarizer):
        self._llm = llm
        self._fallback = fallback

    @property
    def source(self) -> str:
        return self._llm.model_name

    def summarize(self, request: MoveRequest, checks: list[CheckResult], config: CommunityConfig) -> str:
        try:
            return self._llm.generate_text(load_prompt("admin_summary"), _facts(request, checks, config))
        except LLMError as error:
            logger.warning("LLM summary failed, using template: %s", error)
            return self._fallback.summarize(request, checks, config)


def _facts(request: MoveRequest, checks: list[CheckResult], config: CommunityConfig) -> str:
    lines = [
        f"Community: {config.name}",
        f"Request: {request.request_type.label} {request.id}, status {request.status.label}",
    ]
    for spec in config.fields_for(request.request_type):
        lines.append(f"{spec.label}: {request.answers.get(spec.key, 'not provided')}")
    lines.append("Documents uploaded: " + (", ".join(sorted(request.uploaded_doc_types)) or "none"))
    lines.append("Policy checks:")
    lines += [f"- {'PASS' if c.passed else 'FAIL'} [{c.severity}] {c.title}: {c.message}" for c in checks]
    if request.messages:
        lines.append("Messages so far:")
        lines += [f"- {message.sender}: {message.text}" for message in request.messages[-4:]]
    return "\n".join(lines)
