import pytest

from moveflow.agents.review.recommender import Confidence, Decision
from moveflow.agents.review.triage import prioritise
from moveflow.domain.enums import RequestStatus, RequestType
from moveflow.domain.models import UploadedDocument
from moveflow.domain.state_machine import InvalidTransitionError
from moveflow.repositories.sqlite_repository import SqliteRequestRepository

from tests.conftest import TODAY, make_request


def submitted(container, **kwargs):
    request = make_request(status=RequestStatus.UNDER_REVIEW, **kwargs)
    container.repository.save(request)
    return request


def test_clean_request_is_recommended_for_approval(container):
    request = submitted(container, docs=("id_proof", "sale_deed"))
    brief = container.copilot.brief(request)
    assert brief.recommendation.decision is Decision.APPROVE
    assert brief.recommendation.confidence is Confidence.HIGH


def test_pending_dues_lead_to_request_info_with_a_specific_draft(container):
    request = submitted(container, unit="C-305", request_type=RequestType.MOVE_OUT, resident_name="Priya Nair",
                        occupancy="tenant", docs=("owner_noc",))
    brief = container.copilot.brief(request)
    assert brief.recommendation.decision is Decision.REQUEST_INFO
    draft = container.copilot.draft_message(request, brief, Decision.REQUEST_INFO)
    assert "4,500" in draft and "Priya" in draft


def test_unknown_unit_is_recommended_for_rejection(container):
    brief = container.copilot.brief(submitted(container, unit="Z-999", docs=("id_proof", "sale_deed")))
    assert brief.recommendation.decision is Decision.REJECT


def test_slot_that_filled_up_after_submission_gets_alternatives(container):
    container.repository.save(make_request(unit="A-101", time_slot="evening", status=RequestStatus.APPROVED))
    request = submitted(container, unit="B-803", time_slot="evening", docs=("id_proof", "sale_deed"))
    brief = container.copilot.brief(request)
    assert brief.recommendation.decision is Decision.REQUEST_INFO
    assert brief.alternatives
    assert "Available options" in container.copilot.draft_message(request, brief, Decision.REQUEST_INFO)


def test_needs_info_round_trip(container):
    request = submitted(container, occupancy="tenant", docs=("id_proof", "rental_agreement"))
    container.requests.request_info(request.id, "Please upload the police verification.")
    assert container.copilot.brief(container.requests.get(request.id)).recommendation.decision is Decision.WAIT

    document = UploadedDocument(doc_type="police_verification", file_name="pv.pdf")
    updated = container.requests.reply_to_admin(request.id, "Uploaded it.", [document])
    assert updated.status is RequestStatus.UNDER_REVIEW
    assert [message.text for message in updated.messages][-1] == "Uploaded it."
    assert container.copilot.brief(updated).recommendation.decision is Decision.APPROVE


def test_admin_cannot_approve_a_finished_request(container):
    request = submitted(container)
    container.requests.reject(request.id, "Unit is under renovation.")
    with pytest.raises(InvalidTransitionError):
        container.requests.approve(request.id)


def test_queue_puts_waiting_requests_first_then_soonest(container):
    later = make_request(status=RequestStatus.UNDER_REVIEW, move_date="2026-10-30")
    sooner = make_request(status=RequestStatus.UNDER_REVIEW, move_date="2026-10-16")
    approved = make_request(status=RequestStatus.APPROVED, move_date="2026-10-14")
    assert prioritise([approved, later, sooner], TODAY) == [sooner, later, approved]


def test_sqlite_repository_round_trip(tmp_path):
    repository = SqliteRequestRepository(tmp_path / "test.db")
    request = make_request(status=RequestStatus.UNDER_REVIEW, docs=("id_proof",))
    repository.save(request)
    request.status = RequestStatus.APPROVED
    repository.save(request)

    loaded = repository.get(request.id)
    assert loaded == request
    assert repository.list("green-meadows", [RequestStatus.APPROVED]) == [request]
    assert repository.list_for_resident("green-meadows", "9000000000") == [request]
    assert repository.list("skyline-towers") == []
