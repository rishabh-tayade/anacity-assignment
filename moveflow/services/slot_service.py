from dataclasses import dataclass
from datetime import date, timedelta

from moveflow.domain.models import MoveRequest
from moveflow.policies.base import PolicyContext
from moveflow.services.compliance_service import ComplianceService

SCHEDULING_FIELDS = {"move_date", "time_slot"}


@dataclass(frozen=True)
class SlotOption:
    move_date: date
    slot_id: str
    label: str

    def describe(self) -> str:
        return f"{self.move_date.strftime('%a, %d %b')} - {self.label}"


class SlotFinder:
    """Suggests alternative date/slot combinations that pass the scheduling rules.

    Instead of duplicating the rules, it tries candidate dates and slots on a copy
    of the request and keeps the ones the policy engine is happy with.
    """

    def __init__(self, compliance: ComplianceService, search_days: int = 21):
        self._compliance = compliance
        self._search_days = search_days

    def alternatives(self, request: MoveRequest, limit: int = 3) -> list[SlotOption]:
        context = self._compliance.context_for(request.community_id)
        preferred_slot = request.time_slot
        slots = sorted(context.config.time_slots, key=lambda slot: slot.id != preferred_slot)
        start = max(request.move_date or context.today, context.today)

        options: list[SlotOption] = []
        for offset in range(self._search_days):
            candidate_date = start + timedelta(days=offset)
            for slot in slots:
                if candidate_date == request.move_date and slot.id == preferred_slot:
                    continue  # that's the combination that just failed
                if self._is_schedulable(request, candidate_date, slot.id, context):
                    options.append(SlotOption(candidate_date, slot.id, slot.label))
                    if len(options) >= limit:
                        return options
        return options

    def _is_schedulable(self, request: MoveRequest, move_date: date, slot_id: str, context: PolicyContext) -> bool:
        candidate = request.model_copy(
            update={"answers": {**request.answers, "move_date": move_date.isoformat(), "time_slot": slot_id}}
        )
        checks = self._compliance.check(candidate, context)
        return not any(check.is_blocking and SCHEDULING_FIELDS & set(check.fields) for check in checks)
