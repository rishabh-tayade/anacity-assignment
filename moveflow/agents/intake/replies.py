"""Turns a planner step into the message the resident sees.

Replies are templates rather than LLM output: they carry policy facts, dates and
next steps that must be exactly right, and they read the same every time.
"""

from __future__ import annotations

from typing import Any

from moveflow.agents.intake.conversation import Choice, IntakeSession
from moveflow.agents.intake.planner import Step, StepKind
from moveflow.config.schema import CommunityConfig
from moveflow.domain.enums import RequestStatus
from moveflow.domain.models import MoveRequest
from moveflow.formatting import format_answer


class ReplyBuilder:
    def __init__(self, config: CommunityConfig):
        self._config = config

    def for_step(self, step: Step, session: IntakeSession, captured: dict[str, Any]) -> str:
        builders = {
            StepKind.ASK_REQUEST_TYPE: self._ask_request_type,
            StepKind.CLARIFY: self._clarify,
            StepKind.FIX_ISSUES: self._fix_issues,
            StepKind.ASK_FIELD: self._ask_field,
            StepKind.ASK_DOCUMENTS: self._ask_documents,
            StepKind.CONFIRM: self._confirm,
        }
        body = builders[step.kind](step, session)
        acknowledgement = self.acknowledge(captured)
        return f"{acknowledgement}\n\n{body}" if acknowledgement else body

    def greeting(self, session: IntakeSession) -> str:
        first_name = (session.answers.get("resident_name") or "there").split()[0]
        return (
            f"Hi {first_name}! I can help you plan a move-in or a move-out at {self._config.name}.\n\n"
            "Tell me what you're planning. You can say it all in one go, for example: "
            "*\"I'm moving into B-1204 on 24 October in the morning, as a tenant.\"*"
        )

    def acknowledge(self, captured: dict[str, Any]) -> str:
        parts = [
            f"{self._label(key)}: **{format_answer(self._config, key, value)}**"
            for key, value in captured.items()
            if value is not None and not self._is_profile_field(key)
        ]
        return "Noted - " + ", ".join(parts) + "." if parts else ""

    def submitted(self, request: MoveRequest) -> str:
        if request.status is RequestStatus.APPROVED:
            return (
                f"Done! Your request **{request.id}** met every {self._config.name} rule, "
                "so I've approved it straight away. You'll find the move-day checklist under **My requests**."
            )
        return (
            f"Submitted! Your request id is **{request.id}**. The {self._config.admin_desk} will review it, "
            "and you can follow its status and any messages under **My requests**."
        )

    def already_submitted(self, request_id: str) -> str:
        return (
            f"This conversation already created request **{request_id}**. "
            "Use **Start a new request** to plan another move, or check **My requests** for updates."
        )

    def ask_what_to_change(self) -> str:
        return "Sure - what would you like to change? For example: *\"make it the afternoon slot\"*."

    def cancelled(self) -> str:
        return "No problem, I've cleared this draft. Tell me whenever you want to start again."

    def field_required(self, step: Step) -> str:
        return "I need this one to continue. " + (step.field.question if step.field else "")

    def documents_required(self) -> str:
        return f"{self._config.name} needs these documents before the request can be submitted."

    def document_received(self, doc_type: str) -> str:
        return f"Thanks, I've got your {self._config.document_label(doc_type).lower()}."

    def status_summary(self, requests: list[MoveRequest]) -> str:
        if not requests:
            return "You don't have any move requests yet. Tell me what you're planning and I'll set one up."
        lines = ["Here's where your requests stand:"]
        for request in requests[:5]:
            when = request.move_date.strftime("%d %b") if request.move_date else "-"
            label = f"{request.request_type.label} {request.unit} on {when}"
            lines.append(f"- **{request.id}** {label}: {request.status.label}")
        return "\n".join(lines)

    # Step builders

    def _ask_request_type(self, step: Step, session: IntakeSession) -> str:
        return "Is this a **move-in** or a **move-out**?"

    def _clarify(self, step: Step, session: IntakeSession) -> str:
        assert step.ambiguity is not None
        return step.ambiguity.question + _numbered(step.choices)

    def _fix_issues(self, step: Step, session: IntakeSession) -> str:
        lines = ["I can't book that yet:"] + [f"- {issue.message}" for issue in step.issues]
        if step.choices:
            lines.append("\nThese are available instead:" + _numbered(step.choices))
            lines.append("\nReply with a number, or suggest another date or slot.")
        else:
            keys = dict.fromkeys(key for issue in step.issues for key in issue.fields)
            labels = " and ".join(self._label(key).lower() for key in keys) or "details"
            lines.append(f"\nCould you check the {labels} and send me the correct one?")
        return "\n".join(lines)

    def _ask_field(self, step: Step, session: IntakeSession) -> str:
        assert step.field is not None
        question = step.field.question
        if not step.field.required:
            question += " *(optional - say \"skip\")*"
        return question + _numbered(step.choices)

    def _ask_documents(self, step: Step, session: IntakeSession) -> str:
        lines = ["Almost there. Please upload these documents using the panel on the right:"]
        for doc in step.missing_documents:
            lines.append(f"- **{doc.label}**" + (f" - {doc.description}" if doc.description else ""))
        if step.documents_optional:
            lines.append("\nIf you don't have them handy, say **later** - you can add them after submitting.")
        else:
            lines.append(f"\n{self._config.name} needs these before the request can be submitted.")
        return "\n".join(lines)

    def _confirm(self, step: Step, session: IntakeSession) -> str:
        assert session.request_type is not None
        lines = [f"Here's your **{session.request_type.label.lower()}** request:"]
        for spec in self._config.fields_for(session.request_type):
            value = session.answers.get(spec.key)
            if value is not None:
                lines.append(f"- {spec.label}: {format_answer(self._config, spec.key, value)}")
        if session.documents:
            names = ", ".join(self._config.document_label(doc.doc_type) for doc in session.documents)
            lines.append(f"- Documents: {names}")
        if step.warnings:
            lines.append("\nHeads-up - the admin desk will look at these:")
            lines += [f"- {warning.message}" for warning in step.warnings]
        guidelines = self._config.guidelines.get(session.request_type, [])
        if guidelines:
            lines.append("\nGood to know:")
            lines += [f"- {item}" for item in guidelines]
        lines.append("\nShall I submit it? Reply **yes**, or tell me what to change.")
        return "\n".join(lines)

    def _label(self, key: str) -> str:
        spec = self._config.field(key)
        return spec.label if spec else key.replace("_", " ").capitalize()

    def _is_profile_field(self, key: str) -> bool:
        spec = self._config.field(key)
        return bool(spec and spec.from_profile)


def _numbered(choices: list[Choice]) -> str:
    if not choices:
        return ""
    return "\n" + "\n".join(f"{index}. {choice.label}" for index, choice in enumerate(choices, start=1))
