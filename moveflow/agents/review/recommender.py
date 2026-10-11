from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from moveflow.domain.enums import RequestStatus
from moveflow.domain.models import MoveRequest
from moveflow.domain.state_machine import AWAITING_ADMIN
from moveflow.policies.base import CheckResult


class Decision(StrEnum):
    APPROVE = "approve"
    REQUEST_INFO = "request_info"
    REJECT = "reject"
    WAIT = "wait"

    @property
    def label(self) -> str:
        return {
            Decision.APPROVE: "Approve",
            Decision.REQUEST_INFO: "Ask resident for more information",
            Decision.REJECT: "Reject",
            Decision.WAIT: "Wait for the resident",
        }[self]


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"


@dataclass
class Recommendation:
    decision: Decision
    confidence: Confidence
    reasons: list[str] = field(default_factory=list)


# A unit that doesn't exist can't be fixed by the resident sending more papers.
REJECT_RULES = {"unit_exists"}


class Recommender:
    """Recommends what the admin should do, based only on the policy check results.

    Deterministic so the same request always gets the same recommendation and
    the reasoning can be shown line by line. The admin always makes the call.
    """

    def recommend(self, request: MoveRequest, checks: list[CheckResult]) -> Recommendation | None:
        if request.status is RequestStatus.NEEDS_INFO:
            return Recommendation(Decision.WAIT, Confidence.HIGH, ["Waiting for the resident to respond."])
        if request.status not in AWAITING_ADMIN:
            return None

        failed = [check for check in checks if not check.passed]
        if not failed:
            return Recommendation(
                Decision.APPROVE, Confidence.HIGH, [f"All {len(checks)} community checks passed."]
            )

        reject_reasons = [check.message for check in failed if check.rule in REJECT_RULES]
        if reject_reasons:
            return Recommendation(Decision.REJECT, Confidence.MEDIUM, reject_reasons)

        confidence = Confidence.HIGH if len(failed) == 1 else Confidence.MEDIUM
        return Recommendation(Decision.REQUEST_INFO, confidence, [check.message for check in failed])
