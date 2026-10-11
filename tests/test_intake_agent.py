from typing import Any

from moveflow.agents.intake.conversation import Intent
from moveflow.agents.intake.extractor import LLMExtractor, RuleBasedExtractor
from moveflow.agents.intake.planner import StepKind
from moveflow.agents.knowledge import CommunityKnowledge, KeywordAnswerer, LLMAnswerer
from moveflow.domain.enums import Actor, RequestStatus, RequestType
from moveflow.domain.models import UploadedDocument
from moveflow.llm.base import LLMError

from tests.conftest import TODAY, new_session


def chat(agent, session, *messages):
    reply = None
    for message in messages:
        reply = agent.handle(session, message)
    return reply


def upload(agent, session, *doc_types):
    reply = None
    for doc_type in doc_types:
        reply = agent.add_document(session, UploadedDocument(doc_type=doc_type, file_name=f"{doc_type}.pdf"))
    return reply


def test_full_tenant_move_in_reaches_admin_queue(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    reply = chat(agent, session, "I'm moving into B-1204 on 22 Oct in the morning, I'm a tenant", "3", "none", "skip")
    assert reply.step.kind is StepKind.ASK_DOCUMENTS
    assert not reply.step.documents_optional  # documents are a blocker in Green Meadows

    reply = upload(agent, session, "id_proof", "rental_agreement", "police_verification")
    assert reply.step.kind is StepKind.CONFIRM

    reply = chat(agent, session, "yes")
    assert reply.submitted is not None
    stored = container.repository.get(reply.submitted.id)
    assert stored.status is RequestStatus.UNDER_REVIEW
    assert stored.answers["household_size"] == 3
    assert stored.answers["vehicle_numbers"] is None


def test_everything_in_one_message_is_understood(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    reply = chat(agent, session, "Moving into B-1204 on 22nd October, afternoon slot, as the owner")
    assert session.request_type is RequestType.MOVE_IN
    assert session.answers["unit"] == "B-1204"
    assert session.answers["move_date"] == "2026-10-22"
    assert session.answers["time_slot"] == "afternoon"
    assert reply.step.field.key == "household_size"  # straight to the first unanswered question


def test_profile_fields_are_not_asked(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    reply = chat(agent, session, "move in")
    assert reply.step.field.key == "unit"


def test_blocked_date_offers_alternatives_that_can_be_picked_by_number(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    reply = chat(agent, session, "Moving into B-1204 on Sunday 18 October morning as owner")
    assert reply.step.kind is StepKind.FIX_ISSUES
    assert "Sundays" in reply.text
    first_option = reply.step.choices[0]

    reply = chat(agent, session, "1")
    assert session.answers["move_date"] == first_option.values["move_date"]
    assert reply.step.kind is StepKind.ASK_FIELD


def test_ambiguous_answers_are_clarified_one_at_a_time(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    reply = chat(agent, session, "I'm moving into flat 1204 this weekend as a tenant")
    assert reply.step.kind is StepKind.CLARIFY and reply.step.ambiguity.field == "unit"

    reply = chat(agent, session, "B-1204")
    assert reply.step.kind is StepKind.CLARIFY and reply.step.ambiguity.field == "move_date"

    chat(agent, session, "1")
    assert session.answers["move_date"] == "2026-10-17"


def test_questions_are_answered_without_changing_the_draft(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    chat(agent, session, "moving into B-1204 as owner")
    reply = chat(agent, session, "Can I move on a Sunday?")
    assert "Sundays" in reply.text
    assert "move_date" not in session.answers
    assert reply.step.field.key == "move_date"  # and then carries on where it was


def test_required_fields_cannot_be_skipped(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    reply = chat(agent, session, "moving out", "skip")
    assert "need this one" in reply.text
    assert "unit" not in session.answers


def test_change_after_summary(container):
    agent, session = container.intake_agent("skyline-towers"), new_session("skyline-towers", "Ishaan Verma")
    chat(agent, session, "moving into T2-1101 on 22 oct, first half, as owner", "yes", "no")
    reply = upload(agent, session, "id_proof")
    assert reply.step.kind is StepKind.CONFIRM

    reply = chat(agent, session, "no")
    assert "change" in reply.text
    reply = chat(agent, session, "make it the second half")
    assert session.answers["time_slot"] == "second_half"
    assert reply.step.kind is StepKind.CONFIRM


def test_skyline_owner_is_auto_approved(container):
    agent = container.intake_agent("skyline-towers")
    session = new_session("skyline-towers", "Kavita Joshi", "9811111111")
    reply = chat(agent, session, "Moving out of T1-1203 on 20 Oct, first half, I'm the owner", "kavita@upi", "yes")
    request = container.repository.get(reply.submitted.id)
    assert request.status is RequestStatus.APPROVED
    assert request.timeline[-1].actor is Actor.AGENT


def test_skyline_tenant_with_dues_goes_to_review(container):
    agent = container.intake_agent("skyline-towers")
    session = new_session("skyline-towers", "Arjun Desai", "9811111114")
    reply = chat(agent, session, "moving out of T2-0502 on 22 oct second half, tenant", "arjun@upi")
    assert "1,200" in reply.text  # warned before submitting
    reply = chat(agent, session, "yes")
    assert container.repository.get(reply.submitted.id).status is RequestStatus.UNDER_REVIEW


def test_cancel_clears_the_draft_but_keeps_profile(container):
    agent, session = container.intake_agent("green-meadows"), new_session()
    chat(agent, session, "moving into B-1204", "cancel")
    assert session.request_type is None
    assert session.answers == {"resident_name": "Ananya Rao", "phone": "9876543210"}


class FakeLLM:
    model_name = "fake-model"

    def __init__(self, json_reply: dict[str, Any] | None = None, fail: bool = False):
        self.json_reply = json_reply
        self.fail = fail

    def generate_json(self, system, prompt, schema):
        if self.fail:
            raise LLMError("offline")
        return self.json_reply

    def generate_text(self, system, prompt):
        if self.fail:
            raise LLMError("offline")
        return "From the model."


def test_llm_extraction_values_are_validated(green):
    llm = FakeLLM({
        "intent": "provide_info",
        "request_type": "move_in",
        "fields": [
            {"key": "move_date", "value": "2026-10-22"},
            {"key": "time_slot", "value": "midnight"},  # not a real slot: dropped
            {"key": "made_up_field", "value": "x"},  # not in config: dropped
        ],
        "ambiguities": [],
        "question": "",
    })
    extraction = LLMExtractor(llm, RuleBasedExtractor()).extract("...", new_session(), green, TODAY)
    assert extraction.source == "fake-model"
    assert extraction.values == {"move_date": "2026-10-22"}


def test_llm_failure_falls_back_to_rules(green):
    extractor = LLMExtractor(FakeLLM(fail=True), RuleBasedExtractor())
    extraction = extractor.extract("moving into B-1204", new_session(), green, TODAY)
    assert extraction.source == "rules"
    assert extraction.intent is Intent.PROVIDE_INFO
    assert extraction.values["unit"] == "B-1204"


def test_llm_answerer_falls_back_to_keywords(container, green):
    knowledge = CommunityKnowledge(green, ["No moves on Sundays."])
    assert LLMAnswerer(FakeLLM(), KeywordAnswerer()).answer("lift fee?", knowledge) == "From the model."
    fallback = LLMAnswerer(FakeLLM(fail=True), KeywordAnswerer()).answer("Is there a lift fee?", knowledge)
    assert "Rs. 2,000" in fallback
