from datetime import date, timedelta

from moveflow.config.schema import CommunityConfig
from moveflow.domain.models import MoveRequest
from moveflow.domain.slots import count_bookings
from moveflow.policies.base import CheckResult, PolicyContext, PolicyRule


def _fmt(day: date) -> str:
    return day.strftime("%a, %d %b %Y")


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


class BookingWindowRule(PolicyRule):
    """The move date must be far enough ahead, but not too far."""

    name = "booking_window"
    title = "Notice period"
    fields = ("move_date",)

    @property
    def min_notice_days(self) -> int:
        return int(self.params.get("min_notice_days", 0))

    @property
    def max_advance_days(self) -> int:
        return int(self.params.get("max_advance_days", 90))

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        move_date = request.move_date
        if move_date is None:
            return None
        days_ahead = (move_date - context.today).days
        if days_ahead < 0:
            return self._failed(f"{_fmt(move_date)} is in the past.")
        if days_ahead < self.min_notice_days:
            earliest = context.today + timedelta(days=self.min_notice_days)
            return self._failed(
                f"Moves need at least {_days(self.min_notice_days)} notice. "
                f"The earliest possible date is {_fmt(earliest)}."
            )
        if days_ahead > self.max_advance_days:
            return self._failed(f"Moves can be booked at most {_days(self.max_advance_days)} in advance.")
        return self._passed(f"Booked {_days(days_ahead)} ahead.")

    def describe(self, config: CommunityConfig) -> str:
        return (
            f"Book at least {_days(self.min_notice_days)} and at most "
            f"{_days(self.max_advance_days)} before the move."
        )


class BlockedDaysRule(PolicyRule):
    """No moves on certain weekdays or specific dates (festivals, society events)."""

    name = "blocked_days"
    title = "Allowed move days"
    fields = ("move_date",)

    @property
    def weekdays(self) -> list[str]:
        return [day.lower() for day in self.params.get("weekdays", [])]

    @property
    def dates(self) -> dict[str, str]:
        return {str(entry["date"]): entry.get("reason", "") for entry in self.params.get("dates", [])}

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        move_date = request.move_date
        if move_date is None:
            return None
        weekday = move_date.strftime("%A")
        if weekday.lower() in self.weekdays:
            return self._failed(f"Moves are not allowed on {weekday}s.")
        reason = self.dates.get(move_date.isoformat())
        if reason is not None:
            return self._failed(f"{_fmt(move_date)} is blocked ({reason or 'community event'}).")
        return self._passed(f"{_fmt(move_date)} is an allowed move day.")

    def describe(self, config: CommunityConfig) -> str:
        parts = []
        if self.weekdays:
            parts.append("No moves on " + ", ".join(day.title() for day in self.weekdays) + ".")
        for day, reason in self.dates.items():
            parts.append(f"No moves on {day}" + (f" ({reason})." if reason else "."))
        return " ".join(parts) or "Moves are allowed on all days."


class SlotCapacityRule(PolicyRule):
    """Each time slot can only take so many moves (lifts, security staff, parking)."""

    name = "slot_capacity"
    title = "Slot availability"
    fields = ("move_date", "time_slot")

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        if request.move_date is None or request.time_slot is None:
            return None
        slot = context.config.slot(request.time_slot)
        if slot is None:
            return self._failed(f"'{request.time_slot}' is not a valid time slot.")
        booked = count_bookings(context.active_requests, request.move_date, slot.id, request.id)
        if booked >= slot.capacity:
            return self._failed(f"The {slot.label} slot on {_fmt(request.move_date)} is fully booked.")
        return self._passed(f"{slot.capacity - booked} of {slot.capacity} spots free in the {slot.label} slot.")

    def describe(self, config: CommunityConfig) -> str:
        slots = ", ".join(f"{slot.label} ({slot.capacity} moves)" for slot in config.time_slots)
        return f"Moves happen in fixed slots: {slots}."
