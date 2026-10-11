from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from moveflow.agents.intake.choices import resolve_choice
from moveflow.agents.intake.conversation import Extraction, IntakeSession, Intent
from moveflow.agents.intake.extractor import FieldExtractor
from moveflow.agents.intake.planner import IntakePlanner, Step, StepKind
from moveflow.agents.intake.replies import ReplyBuilder
from moveflow.agents.knowledge import CommunityKnowledge, QuestionAnswerer
from moveflow.config.schema import CommunityConfig
from moveflow.domain.models import MoveRequest, UploadedDocument
from moveflow.services.request_service import RequestService


@dataclass
class AgentReply:
    text: str
    step: Step | None = None
    extraction: Extraction | None = None
    submitted: MoveRequest | None = None


class IntakeAgent:
    """Guides a resident from "I'm moving" to a submitted request.

    Each turn: understand the message (extractor), update the session, decide the
    next step (planner), and say it (reply builder). Questions are answered from
    the community's own information along the way.
    """

    def __init__(
        self,
        config: CommunityConfig,
        extractor: FieldExtractor,
        planner: IntakePlanner,
        replies: ReplyBuilder,
        answerer: QuestionAnswerer,
        knowledge: CommunityKnowledge,
        requests: RequestService,
        resident_requests: Callable[[str], list[MoveRequest]],
        today: Callable[[], date] = date.today,
    ):
        self._config = config
        self._extractor = extractor
        self._planner = planner
        self._replies = replies
        self._answerer = answerer
        self._knowledge = knowledge
        self._requests = requests
        self._resident_requests = resident_requests
        self._today = today

    def greet(self, session: IntakeSession) -> AgentReply:
        return self._say(session, AgentReply(self._replies.greeting(session)))

    def handle(self, session: IntakeSession, message: str) -> AgentReply:
        session.add_turn("resident", message)
        if session.submitted_request_id:
            return self._say(session, AgentReply(self._replies.already_submitted(session.submitted_request_id)))

        extraction = resolve_choice(message, session.offered_choices) or self._extractor.extract(
            message, session, self._config, self._today()
        )
        reply = self._respond(session, extraction)
        reply.extraction = extraction
        return self._say(session, reply)

    def add_document(self, session: IntakeSession, document: UploadedDocument) -> AgentReply:
        session.add_document(document)
        if session.submitted_request_id:
            return self._say(session, AgentReply(self._replies.document_received(document.doc_type)))
        step = self._planner.next_step(session, self._config)
        self._remember(session, step)
        text = self._replies.document_received(document.doc_type) + "\n\n" + self._replies.for_step(step, session, {})
        return self._say(session, AgentReply(text, step))

    def _respond(self, session: IntakeSession, extraction: Extraction) -> AgentReply:
        match extraction.intent:
            case Intent.CANCEL:
                session.reset()
                return AgentReply(self._replies.cancelled())
            case Intent.CHECK_STATUS:
                requests = self._resident_requests(session.answers.get("phone", ""))
                return AgentReply(self._replies.status_summary(requests))
            case Intent.CHANGE:
                session.awaiting_confirmation = False
                return AgentReply(self._replies.ask_what_to_change())

        preface = ""
        if extraction.intent is Intent.ASK_QUESTION:
            preface = self._answerer.answer(extraction.question, self._knowledge)
        elif extraction.intent is Intent.SKIP:
            preface = self._handle_skip(session)

        captured = session.apply(extraction)
        confirmed = extraction.intent is Intent.CONFIRM and session.awaiting_confirmation
        step = self._planner.next_step(session, self._config, confirmed=confirmed)

        if step.kind is StepKind.SUBMIT:
            request = self._requests.submit(session.to_draft())
            session.submitted_request_id = request.id
            self._remember(session, step)
            return AgentReply(self._replies.submitted(request), step, submitted=request)

        self._remember(session, step)
        if extraction.intent is Intent.ASK_QUESTION and session.request_type is None:
            # A question before anything else: just answer it and invite them to start.
            return AgentReply(preface + "\n\nWhenever you're ready, tell me about your move.", step)
        body = self._replies.for_step(step, session, captured)
        return AgentReply(f"{preface}\n\n{body}" if preface else body, step)

    def _handle_skip(self, session: IntakeSession) -> str:
        spec = self._config.field(session.pending_field) if session.pending_field else None
        if spec and spec.required:
            return "I need this one to continue."
        session.skip_pending()
        return ""

    @staticmethod
    def _remember(session: IntakeSession, step: Step) -> None:
        """Stores what we just asked so the next short reply can be understood."""
        session.pending_field = step.field.key if step.kind is StepKind.ASK_FIELD and step.field else None
        session.offered_choices = list(step.choices)
        session.awaiting_confirmation = step.kind is StepKind.CONFIRM
        session.awaiting_documents = step.kind is StepKind.ASK_DOCUMENTS

    @staticmethod
    def _say(session: IntakeSession, reply: AgentReply) -> AgentReply:
        session.add_turn("agent", reply.text)
        return reply
