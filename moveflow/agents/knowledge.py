"""Answers residents' questions using only what the community config says.

The config is the single source of truth for rules, documents and timings, so
the same facts drive the policy checks, the agent's answers and the admin view.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from moveflow.agents.intake import parsing
from moveflow.agents.prompts import load_prompt
from moveflow.config.schema import CommunityConfig
from moveflow.domain.enums import OccupancyType, RequestType
from moveflow.llm.base import LLMClient, LLMError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeEntry:
    topic: str
    keywords: tuple[str, ...]
    answer: str


class CommunityKnowledge:
    def __init__(self, config: CommunityConfig, rule_descriptions: list[str]):
        self.config = config
        self._rule_descriptions = rule_descriptions

    def entries(self) -> list[KnowledgeEntry]:
        config = self.config
        entries = [
            KnowledgeEntry(
                faq.question,
                tuple(faq.keywords) or tuple(parsing.normalise(faq.question).split()),
                faq.answer,
            )
            for faq in config.faqs
        ]
        entries.append(KnowledgeEntry(
            "documents",
            ("document", "documents", "papers", "upload", "agreement", "verification", "noc", "proof", "id"),
            self._documents_text(),
        ))
        entries.append(KnowledgeEntry(
            "timings",
            ("slot", "slots", "timing", "timings", "hours", "time", "what time"),
            "Move slots: " + "; ".join(slot.label for slot in config.time_slots) + ".",
        ))
        entries.append(KnowledgeEntry(
            "rules",
            ("rule", "rules", "notice", "advance", "allowed", "policy", "book"),
            " ".join(self._rule_descriptions),
        ))
        return entries

    def as_text(self) -> str:
        config = self.config
        lines = [f"Community: {config.name}, {config.city}. Admin contact: {config.admin_desk}.", "", "Rules:"]
        lines += [f"- {text}" for text in self._rule_descriptions]
        lines += ["", "Move slots:"] + [f"- {slot.label}" for slot in config.time_slots]
        lines += ["", "Documents:", self._documents_text()]
        for request_type, items in config.guidelines.items():
            lines += ["", f"{request_type.label} guidelines:"] + [f"- {item}" for item in items]
        lines += ["", "FAQs:"] + [f"Q: {faq.question}\nA: {faq.answer}" for faq in config.faqs]
        return "\n".join(lines)

    def _documents_text(self) -> str:
        parts = []
        for request_type in RequestType:
            for occupancy in OccupancyType:
                docs = self.config.documents_for(request_type, occupancy)
                names = ", ".join(doc.label for doc in docs) if docs else "no documents"
                parts.append(f"{request_type.label} as {occupancy.value}: {names}.")
        return " ".join(parts)


class QuestionAnswerer(Protocol):
    def answer(self, question: str, knowledge: CommunityKnowledge) -> str: ...


class KeywordAnswerer:
    """Picks the knowledge entry whose keywords best match the question."""

    def answer(self, question: str, knowledge: CommunityKnowledge) -> str:
        text = parsing.normalise(question)
        scored = [
            (sum(1 for keyword in entry.keywords if re.search(rf"\b{re.escape(keyword)}\b", text)), entry)
            for entry in knowledge.entries()
        ]
        score, best = max(scored, key=lambda pair: pair[0], default=(0, None))
        if best is None or score == 0:
            return (
                f"I don't have that information. The {knowledge.config.admin_desk} can help, "
                "and I'll make sure your request carries the question."
            )
        return best.answer


class LLMAnswerer:
    """Answers in natural language, grounded strictly in the community's config."""

    def __init__(self, llm: LLMClient, fallback: QuestionAnswerer):
        self._llm = llm
        self._fallback = fallback

    def answer(self, question: str, knowledge: CommunityKnowledge) -> str:
        prompt = f"Community information:\n{knowledge.as_text()}\n\nResident's question:\n{question}"
        try:
            return self._llm.generate_text(load_prompt("answer_question"), prompt)
        except LLMError as error:
            logger.warning("LLM answer failed, using keyword lookup: %s", error)
            return self._fallback.answer(question, knowledge)
