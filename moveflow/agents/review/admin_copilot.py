from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from moveflow.agents.review.message_drafter import SCHEDULING_RULES, MessageDrafter
from moveflow.agents.review.recommender import Decision, Recommendation, Recommender
from moveflow.agents.review.summarizer import Summarizer
from moveflow.config.loader import CommunityCatalog
from moveflow.domain.models import MoveRequest
from moveflow.policies.base import CheckResult
from moveflow.services.compliance_service import ComplianceService
from moveflow.services.slot_service import SlotFinder, SlotOption


@dataclass
class ReviewBrief:
    request_id: str
    summary: str
    summary_source: str
    checks: list[CheckResult]
    recommendation: Recommendation | None
    alternatives: list[SlotOption] = field(default_factory=list)
    days_to_move: int | None = None

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [check for check in self.checks if not check.passed]


class AdminCopilot:
    """Prepares everything an admin needs to decide on a request in one look.

    It re-runs the policy checks at review time (slots may have filled up since
    submission), recommends an action with reasons, and drafts the message to
    the resident. It never changes a request itself; the admin acts.
    """

    def __init__(
        self,
        catalog: CommunityCatalog,
        compliance: ComplianceService,
        slot_finder: SlotFinder,
        recommender: Recommender,
        summarizer: Summarizer,
        drafter: MessageDrafter,
        today: Callable[[], date] = date.today,
    ):
        self._catalog = catalog
        self._compliance = compliance
        self._slot_finder = slot_finder
        self._recommender = recommender
        self._summarizer = summarizer
        self._drafter = drafter
        self._today = today

    def brief(self, request: MoveRequest) -> ReviewBrief:
        config = self._catalog.get(request.community_id)
        checks = self._compliance.check(request)
        needs_new_slot = any(not check.passed and check.rule in SCHEDULING_RULES for check in checks)
        return ReviewBrief(
            request_id=request.id,
            summary=self._summarizer.summarize(request, checks, config),
            summary_source=self._summarizer.source,
            checks=checks,
            recommendation=self._recommender.recommend(request, checks),
            alternatives=self._slot_finder.alternatives(request) if needs_new_slot else [],
            days_to_move=(request.move_date - self._today()).days if request.move_date else None,
        )

    def draft_message(self, request: MoveRequest, brief: ReviewBrief, decision: Decision) -> str:
        config = self._catalog.get(request.community_id)
        return self._drafter.draft(request, decision, brief.failed_checks, brief.alternatives, config)
