from moveflow.config.schema import CommunityConfig
from moveflow.domain.enums import RequestType
from moveflow.domain.models import MoveRequest
from moveflow.domain.state_machine import ACTIVE_STATUSES
from moveflow.policies.base import CheckResult, PolicyContext, PolicyRule


class UnitExistsRule(PolicyRule):
    name = "unit_exists"
    title = "Unit verified"
    fields = ("unit",)

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        if not request.unit:
            return None
        if context.units.find_unit(request.community_id, request.unit) is None:
            return self._failed(f"Unit {request.unit} does not exist in {context.config.name}.")
        return self._passed(f"Unit {request.unit} found in the unit registry.")

    def describe(self, config: CommunityConfig) -> str:
        return "The unit must exist in the community's unit registry."


class OccupancyConsistencyRule(PolicyRule):
    """Cross-checks the request against who the registry says lives in the unit."""

    name = "occupancy_consistency"
    title = "Matches unit records"
    fields = ("unit",)

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        if not request.unit:
            return None
        record = context.units.find_unit(request.community_id, request.unit)
        if record is None:
            return None  # UnitExistsRule reports this

        if request.request_type is RequestType.MOVE_OUT:
            if record.is_vacant:
                return self._failed(f"Unit {request.unit} has no registered occupant to move out.")
            if request.resident_name and not _same_person(record.occupant, request.resident_name):
                return self._failed(
                    f"Registered occupant of {request.unit} is {record.occupant}, "
                    f"but the request is from {request.resident_name}."
                )
            return self._passed(f"{record.occupant} is the registered occupant of {request.unit}.")

        if record.is_vacant:
            return self._passed(f"Unit {request.unit} is vacant.")
        if _has_pending_move_out(request, context):
            return self._passed(f"Current occupant {record.occupant} has a move-out on file.")
        return self._failed(f"Unit {request.unit} is still occupied by {record.occupant} with no move-out on file.")

    def describe(self, config: CommunityConfig) -> str:
        return (
            "Move-ins should be for vacant units (or units with a move-out on file); "
            "move-outs should come from the registered occupant."
        )


class DuesClearanceRule(PolicyRule):
    name = "dues_clearance"
    title = "Maintenance dues cleared"
    applies_to = frozenset({RequestType.MOVE_OUT})
    fields = ("unit",)

    @property
    def max_outstanding(self) -> float:
        return float(self.params.get("max_outstanding", 0))

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        if not request.unit:
            return None
        dues = context.dues.outstanding_dues(request.community_id, request.unit)
        if dues > self.max_outstanding:
            return self._failed(f"Rs. {dues:,.0f} in maintenance dues is outstanding for {request.unit}.")
        return self._passed("No outstanding maintenance dues.")

    def describe(self, config: CommunityConfig) -> str:
        return "Maintenance dues must be cleared before a move-out is approved."


class NoDuplicateRequestRule(PolicyRule):
    name = "no_duplicate_request"
    title = "No duplicate request"
    fields = ("unit",)

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        if not request.unit:
            return None
        duplicate = next(
            (
                other
                for other in context.active_requests
                if other.id != request.id
                and other.unit == request.unit
                and other.request_type is request.request_type
            ),
            None,
        )
        if duplicate:
            return self._failed(
                f"There is already an open {request.request_type.label.lower()} request "
                f"({duplicate.id}) for {request.unit}."
            )
        return self._passed("No other open request of this type for the unit.")

    def describe(self, config: CommunityConfig) -> str:
        return "Only one open move-in and one open move-out request per unit at a time."


class RequiredDocumentsRule(PolicyRule):
    name = "required_documents"
    title = "Documents"

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        if request.occupancy is None:
            return None
        required = context.config.documents_for(request.request_type, request.occupancy)
        missing = [doc.label for doc in required if doc.doc_type not in request.uploaded_doc_types]
        if missing:
            return self._failed("Missing: " + ", ".join(missing) + ".")
        if not required:
            return self._passed("No documents needed.")
        return self._passed("All required documents uploaded.")

    def describe(self, config: CommunityConfig) -> str:
        return "Required documents depend on the request type and whether you are an owner or a tenant."


def _same_person(registered: str | None, given: str) -> bool:
    if not registered:
        return False
    registered_parts = set(registered.lower().split())
    given_parts = set(given.lower().split())
    return bool(registered_parts & given_parts)


def _has_pending_move_out(request: MoveRequest, context: PolicyContext) -> bool:
    return any(
        other.unit == request.unit
        and other.request_type is RequestType.MOVE_OUT
        and other.status in ACTIVE_STATUSES
        for other in context.active_requests
    )

