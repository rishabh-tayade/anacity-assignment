from collections.abc import Callable
from datetime import date

from moveflow.config.loader import CommunityCatalog
from moveflow.domain.models import MoveRequest
from moveflow.domain.state_machine import ACTIVE_STATUSES
from moveflow.integrations.property_system import DuesProvider, UnitDirectory
from moveflow.policies.base import CheckResult, PolicyContext
from moveflow.policies.engine import PolicyEngine
from moveflow.repositories.base import RequestRepository


class ComplianceService:
    """Runs the right community's policy rules against a request.

    Used in three places: live checks while the resident is talking to the
    intake agent, the admin review brief, and the auto-approval decision.
    """

    def __init__(
        self,
        catalog: CommunityCatalog,
        repository: RequestRepository,
        units: UnitDirectory,
        dues: DuesProvider,
        today: Callable[[], date] = date.today,
    ):
        self._catalog = catalog
        self._repository = repository
        self._units = units
        self._dues = dues
        self._today = today
        self._engines = {config.id: PolicyEngine.for_community(config) for config in catalog.all()}

    def context_for(self, community_id: str) -> PolicyContext:
        return PolicyContext(
            config=self._catalog.get(community_id),
            today=self._today(),
            active_requests=self._repository.list(community_id, ACTIVE_STATUSES),
            units=self._units,
            dues=self._dues,
        )

    def check(self, request: MoveRequest, context: PolicyContext | None = None) -> list[CheckResult]:
        context = context or self.context_for(request.community_id)
        return self._engines[request.community_id].evaluate(request, context)

    def describe_rules(self, community_id: str) -> list[tuple[str, str, str]]:
        """(title, description, severity) for every active rule; used for help text."""
        config = self._catalog.get(community_id)
        return [
            (rule.title, rule.describe(config), rule.severity.value)
            for rule in self._engines[community_id].rules
        ]


def blocking(checks: list[CheckResult]) -> list[CheckResult]:
    return [check for check in checks if check.is_blocking]


def warnings(checks: list[CheckResult]) -> list[CheckResult]:
    return [check for check in checks if check.is_warning]
