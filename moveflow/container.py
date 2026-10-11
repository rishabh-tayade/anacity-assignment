"""Builds the object graph. The only place that knows which implementations are used.

Swapping SQLite for Postgres, the mock property system for real ANACITY APIs,
or Claude for another model only touches this file.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from moveflow.agents.intake.extractor import FieldExtractor, LLMExtractor, RuleBasedExtractor
from moveflow.agents.intake.intake_agent import IntakeAgent
from moveflow.agents.intake.planner import IntakePlanner
from moveflow.agents.intake.replies import ReplyBuilder
from moveflow.agents.knowledge import CommunityKnowledge, KeywordAnswerer, LLMAnswerer, QuestionAnswerer
from moveflow.agents.review.admin_copilot import AdminCopilot
from moveflow.agents.review.message_drafter import LLMDrafter, MessageDrafter, TemplateDrafter
from moveflow.agents.review.recommender import Recommender
from moveflow.agents.review.summarizer import LLMSummarizer, Summarizer, TemplateSummarizer
from moveflow.config.loader import CommunityCatalog
from moveflow.integrations.notifier import LogNotifier
from moveflow.integrations.property_system import MockPropertySystem
from moveflow.llm.base import LLMClient
from moveflow.repositories.base import RequestRepository
from moveflow.services.autonomy_service import AutonomyPolicy
from moveflow.services.compliance_service import ComplianceService
from moveflow.services.request_service import RequestService
from moveflow.services.slot_service import SlotFinder

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class AIComponents:
    """The pieces that use a model when one is configured, and rules otherwise."""

    extractor: FieldExtractor
    answerer: QuestionAnswerer
    summarizer: Summarizer
    drafter: MessageDrafter
    model_name: str | None

    @classmethod
    def build(cls, llm: LLMClient | None) -> AIComponents:
        rules_extractor, keyword_answerer = RuleBasedExtractor(), KeywordAnswerer()
        template_summarizer, template_drafter = TemplateSummarizer(), TemplateDrafter()
        if llm is None:
            return cls(rules_extractor, keyword_answerer, template_summarizer, template_drafter, None)
        return cls(
            extractor=LLMExtractor(llm, fallback=rules_extractor),
            answerer=LLMAnswerer(llm, fallback=keyword_answerer),
            summarizer=LLMSummarizer(llm, fallback=template_summarizer),
            drafter=LLMDrafter(llm, fallback=template_drafter),
            model_name=llm.model_name,
        )


class Container:
    def __init__(
        self,
        catalog: CommunityCatalog,
        repository: RequestRepository,
        property_system: MockPropertySystem,
        llm: LLMClient | None,
        today: Callable[[], date] = date.today,
    ):
        self.catalog = catalog
        self.repository = repository
        self.today = today
        self.ai = AIComponents.build(llm)

        self.compliance = ComplianceService(catalog, repository, property_system, property_system, today)
        self.slot_finder = SlotFinder(self.compliance)
        self.requests = RequestService(repository, catalog, self.compliance, AutonomyPolicy(), LogNotifier())
        self.copilot = AdminCopilot(
            catalog,
            self.compliance,
            self.slot_finder,
            Recommender(),
            self.ai.summarizer,
            self.ai.drafter,
            today,
        )
        self._planner = IntakePlanner(self.compliance, self.slot_finder)

    def intake_agent(self, community_id: str) -> IntakeAgent:
        config = self.catalog.get(community_id)
        rule_texts = [description for _, description, _ in self.compliance.describe_rules(community_id)]
        return IntakeAgent(
            config=config,
            extractor=self.ai.extractor,
            planner=self._planner,
            replies=ReplyBuilder(config),
            answerer=self.ai.answerer,
            knowledge=CommunityKnowledge(config, rule_texts),
            requests=self.requests,
            resident_requests=lambda phone: self.repository.list_for_resident(community_id, phone),
            today=self.today,
        )


def build_container(
    repository: RequestRepository,
    llm: LLMClient | None,
    communities_dir: Path = PROJECT_ROOT / "communities",
    property_data: Path = PROJECT_ROOT / "data" / "mock_property_data.yaml",
    today: Callable[[], date] = date.today,
) -> Container:
    return Container(
        catalog=CommunityCatalog.from_directory(communities_dir),
        repository=repository,
        property_system=MockPropertySystem.from_file(property_data),
        llm=llm,
        today=today,
    )
