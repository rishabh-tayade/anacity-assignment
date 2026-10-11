from dataclasses import dataclass

from moveflow.config.schema import CommunityConfig
from moveflow.domain.models import MoveRequest
from moveflow.policies.base import CheckResult


@dataclass(frozen=True)
class AutonomyDecision:
    auto_approve: bool
    reason: str


class AutonomyPolicy:
    """Decides whether the agent may approve a request without a human.

    The bar is deliberately high: the community must have opted in for this
    request type and occupancy, and every single check must pass, warnings
    included. Anything less goes to the admin queue.
    """

    def decide(self, request: MoveRequest, config: CommunityConfig, checks: list[CheckResult]) -> AutonomyDecision:
        autonomy = config.autonomy
        if not autonomy.auto_approve:
            return AutonomyDecision(False, f"{config.name} reviews every request manually.")
        if request.request_type not in autonomy.request_types:
            return AutonomyDecision(False, f"{request.request_type.label} requests need manual review.")
        if request.occupancy not in autonomy.occupancy:
            return AutonomyDecision(False, f"Requests from {request.occupancy} residents need manual review.")
        failed = [check for check in checks if not check.passed]
        if failed:
            titles = ", ".join(check.title for check in failed)
            return AutonomyDecision(False, f"Needs a human look: {titles}.")
        return AutonomyDecision(True, "All community rules passed and auto-approval is enabled for this request type.")
