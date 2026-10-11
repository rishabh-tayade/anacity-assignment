from moveflow.config.loader import CommunityCatalog
from moveflow.domain.enums import Actor, RequestStatus
from moveflow.domain.models import MoveRequest, UploadedDocument
from moveflow.domain.state_machine import ensure_transition
from moveflow.integrations.notifier import Notifier
from moveflow.repositories.base import RequestNotFoundError, RequestRepository
from moveflow.services.autonomy_service import AutonomyPolicy
from moveflow.services.compliance_service import ComplianceService, blocking


class SubmissionBlockedError(Exception):
    pass


class RequestService:
    """All changes to a submitted request go through here.

    Each action validates the status change, records who did it on the
    timeline, saves, and notifies the other side.
    """

    def __init__(
        self,
        repository: RequestRepository,
        catalog: CommunityCatalog,
        compliance: ComplianceService,
        autonomy: AutonomyPolicy,
        notifier: Notifier,
    ):
        self._repository = repository
        self._catalog = catalog
        self._compliance = compliance
        self._autonomy = autonomy
        self._notifier = notifier

    def get(self, request_id: str) -> MoveRequest:
        request = self._repository.get(request_id)
        if request is None:
            raise RequestNotFoundError(request_id)
        return request

    # Resident actions

    def submit(self, draft: MoveRequest) -> MoveRequest:
        checks = self._compliance.check(draft)
        if blocking(checks):
            raise SubmissionBlockedError("; ".join(check.message for check in blocking(checks)))

        request = draft.model_copy(deep=True)
        self._move(request, RequestStatus.SUBMITTED, Actor.RESIDENT, "Submitted")

        config = self._catalog.get(request.community_id)
        decision = self._autonomy.decide(request, config, checks)
        if decision.auto_approve:
            self._move(request, RequestStatus.APPROVED, Actor.AGENT, "Auto-approved", decision.reason)
            request.add_message(Actor.AGENT, _approval_message(request, config.admin_desk))
            self._notifier.notify_resident(request, "Your request has been approved.")
        else:
            self._move(request, RequestStatus.UNDER_REVIEW, Actor.SYSTEM, "Sent for admin review", decision.reason)
            self._notifier.notify_admin(request, "New request waiting for review.")

        self._repository.save(request)
        return request

    def reply_to_admin(
        self, request_id: str, text: str, documents: list[UploadedDocument] | None = None
    ) -> MoveRequest:
        request = self.get(request_id)
        request.documents.extend(documents or [])
        if text.strip():
            request.add_message(Actor.RESIDENT, text.strip())
        note = f"{len(documents)} document(s) added" if documents else ""
        if request.status is RequestStatus.NEEDS_INFO:
            self._move(request, RequestStatus.UNDER_REVIEW, Actor.RESIDENT, "Resident responded", note)
        else:
            request.record(Actor.RESIDENT, "Resident added information", note)
        self._repository.save(request)
        self._notifier.notify_admin(request, "Resident responded.")
        return request

    def cancel(self, request_id: str, reason: str = "", actor: Actor = Actor.RESIDENT) -> MoveRequest:
        request = self.get(request_id)
        self._move(request, RequestStatus.CANCELLED, actor, "Cancelled", reason)
        self._repository.save(request)
        return request

    # Admin actions

    def approve(self, request_id: str, message: str = "") -> MoveRequest:
        request = self.get(request_id)
        self._move(request, RequestStatus.APPROVED, Actor.ADMIN, "Approved")
        config = self._catalog.get(request.community_id)
        request.add_message(Actor.ADMIN, message or _approval_message(request, config.admin_desk))
        self._repository.save(request)
        self._notifier.notify_resident(request, "Your request has been approved.")
        return request

    def request_info(self, request_id: str, message: str) -> MoveRequest:
        request = self.get(request_id)
        self._move(request, RequestStatus.NEEDS_INFO, Actor.ADMIN, "More information requested")
        request.add_message(Actor.ADMIN, message)
        self._repository.save(request)
        self._notifier.notify_resident(request, message)
        return request

    def reject(self, request_id: str, reason: str) -> MoveRequest:
        request = self.get(request_id)
        self._move(request, RequestStatus.REJECTED, Actor.ADMIN, "Rejected", reason)
        request.add_message(Actor.ADMIN, reason)
        self._repository.save(request)
        self._notifier.notify_resident(request, reason)
        return request

    def complete(self, request_id: str, note: str = "") -> MoveRequest:
        request = self.get(request_id)
        self._move(request, RequestStatus.COMPLETED, Actor.ADMIN, "Move completed", note)
        self._repository.save(request)
        return request

    @staticmethod
    def _move(request: MoveRequest, target: RequestStatus, actor: Actor, action: str, note: str = "") -> None:
        ensure_transition(request.status, target)
        request.status = target
        request.record(actor, action, note)


def _approval_message(request: MoveRequest, desk: str) -> str:
    return (
        f"Your {request.request_type.label.lower()} for {request.unit} on "
        f"{request.move_date:%d %b %Y} is approved. Please follow the move-day checklist "
        f"and contact the {desk} if your plans change."
    )
