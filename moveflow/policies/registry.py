"""Maps rule names used in community YAML files to rule classes.

To add a new kind of rule: write a PolicyRule subclass and list it here.
Communities then opt in from their YAML; no other code changes.
"""

from moveflow.config.schema import RuleConfig
from moveflow.policies.base import PolicyRule
from moveflow.policies.rules import (
    BlockedDaysRule,
    BookingWindowRule,
    DuesClearanceRule,
    NoDuplicateRequestRule,
    OccupancyConsistencyRule,
    RequiredDocumentsRule,
    SlotCapacityRule,
    UnitExistsRule,
)

AVAILABLE_RULES: dict[str, type[PolicyRule]] = {
    rule.name: rule
    for rule in (
        BookingWindowRule,
        BlockedDaysRule,
        SlotCapacityRule,
        UnitExistsRule,
        OccupancyConsistencyRule,
        DuesClearanceRule,
        NoDuplicateRequestRule,
        RequiredDocumentsRule,
    )
}


class UnknownRuleError(ValueError):
    pass


def build_rules(configs: list[RuleConfig]) -> list[PolicyRule]:
    rules = []
    for config in configs:
        rule_class = AVAILABLE_RULES.get(config.name)
        if rule_class is None:
            raise UnknownRuleError(
                f"Unknown rule '{config.name}'. Available: {', '.join(sorted(AVAILABLE_RULES))}"
            )
        rules.append(rule_class(severity=config.severity, params=config.params))
    return rules
