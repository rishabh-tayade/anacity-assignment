from __future__ import annotations

import logging
from typing import Protocol

from moveflow.agents.prompts import load_prompt
from moveflow.agents.review.recommender import Decision
from moveflow.config.schema import CommunityConfig
from moveflow.domain.enums import RequestType
from moveflow.domain.models import MoveRequest
from moveflow.llm.base import LLMClient, LLMError
from moveflow.policies.base import CheckResult
from moveflow.services.slot_service import SlotOption

logger = logging.getLogger(__name__)

SCHEDULING_RULES = {"booking_window", "blocked_days", "slot_capacity"}


class MessageDrafter(Protocol):
    def draft(
        self,
        request: MoveRequest,
        decision: Decision,
        failed_checks: list[CheckResult],
        alternatives: list[SlotOption],
        config: CommunityConfig,
    ) -> str: ...


class TemplateDrafter:
    """Drafts the message the admin sends the resident. The admin can edit it before sending."""

    def draft(
        self,
        request: MoveRequest,
        decision: Decision,
        failed_checks: list[CheckResult],
        alternatives: list[SlotOption],
        config: CommunityConfig,
    ) -> str:
        first_name = request.resident_name.split()[0] if request.resident_name else "there"
        about = f"your {request.request_type.label.lower()} request {request.id} for {request.unit}"

        if decision is Decision.APPROVE:
            return (
                f"Hi {first_name}, {about} on {request.move_date:%d %b} is approved. "
                f"Please follow the move-day checklist and reach out to the {config.admin_desk} if anything changes."
            )
        if decision is Decision.REJECT:
            reasons = " ".join(check.message for check in failed_checks)
            return (
                f"Hi {first_name}, we're unable to approve {about}. {reasons} "
                f"Please contact the {config.admin_desk} if you think this is a mistake."
            )

        asks = [self._ask_for(check, request, alternatives, config) for check in failed_checks]
        return (
            f"Hi {first_name}, thanks for {about}. Before we can approve it, we need the following:\n"
            + "\n".join(f"- {ask}" for ask in dict.fromkeys(asks))
            + "\nPlease reply here once done."
        )

    @staticmethod
    def _ask_for(
        check: CheckResult, request: MoveRequest, alternatives: list[SlotOption], config: CommunityConfig
    ) -> str:
        if check.rule == "required_documents":
            return "Please upload the missing documents. " + check.message
        if check.rule == "dues_clearance":
            return check.message + " Please clear it and share the payment reference."
        if check.rule == "occupancy_consistency":
            if request.request_type is RequestType.MOVE_IN:
                return (
                    check.message
                    + " Please confirm when the current occupant is leaving, or share your agreement with the owner."
                )
            return check.message + " Please confirm your relationship to the unit or upload supporting proof."
        if check.rule in SCHEDULING_RULES:
            options = "; ".join(option.describe() for option in alternatives)
            return check.message + (f" Available options: {options}." if options else " Please pick another date.")
        return check.message


class LLMDrafter:
    def __init__(self, llm: LLMClient, fallback: MessageDrafter):
        self._llm = llm
        self._fallback = fallback

    def draft(
        self,
        request: MoveRequest,
        decision: Decision,
        failed_checks: list[CheckResult],
        alternatives: list[SlotOption],
        config: CommunityConfig,
    ) -> str:
        # The template version carries every required fact; the model only makes it read better.
        baseline = self._fallback.draft(request, decision, failed_checks, alternatives, config)
        prompt = (
            f"Decision: {decision.label}\nCommunity: {config.name} ({config.admin_desk})\n"
            f"Resident: {request.resident_name}\nDraft to improve:\n{baseline}"
        )
        try:
            return self._llm.generate_text(load_prompt("resident_message"), prompt)
        except LLMError as error:
            logger.warning("LLM draft failed, using template: %s", error)
            return baseline
