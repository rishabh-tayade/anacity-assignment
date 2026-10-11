from moveflow.config.schema import CommunityConfig
from moveflow.domain.models import MoveRequest
from moveflow.policies.base import CheckResult, PolicyContext, PolicyRule
from moveflow.policies.registry import build_rules


class PolicyEngine:
    """Runs a community's configured rules against a request."""

    def __init__(self, rules: list[PolicyRule]):
        self._rules = rules

    @classmethod
    def for_community(cls, config: CommunityConfig) -> "PolicyEngine":
        return cls(build_rules(config.rules))

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def evaluate(self, request: MoveRequest, context: PolicyContext) -> list[CheckResult]:
        results = (rule.check(request, context) for rule in self._rules)
        return [result for result in results if result is not None]
