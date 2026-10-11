from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

from moveflow.config.schema import CommunityConfig
from moveflow.domain.enums import RequestType, Severity
from moveflow.domain.models import MoveRequest
from moveflow.integrations.property_system import DuesProvider, UnitDirectory


@dataclass(frozen=True)
class CheckResult:
    rule: str
    title: str
    passed: bool
    severity: Severity
    message: str
    # Answer fields the resident could change to fix a failed check.
    fields: tuple[str, ...] = ()

    @property
    def is_blocking(self) -> bool:
        return not self.passed and self.severity is Severity.BLOCKER

    @property
    def is_warning(self) -> bool:
        return not self.passed and self.severity is Severity.WARNING


@dataclass(frozen=True)
class PolicyContext:
    """Everything a rule may look at besides the request itself."""

    config: CommunityConfig
    today: date
    active_requests: Sequence[MoveRequest]
    units: UnitDirectory
    dues: DuesProvider


class PolicyRule(ABC):
    """One community rule, e.g. "moves need 3 days notice".

    Rules are deterministic on purpose: they decide pass/fail, the agent only
    explains the result. A rule returns None when the request doesn't have
    enough information yet for it to say anything.
    """

    name: ClassVar[str]
    title: ClassVar[str]
    applies_to: ClassVar[frozenset[RequestType]] = frozenset(RequestType)
    fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, severity: Severity = Severity.BLOCKER, params: dict[str, Any] | None = None):
        self.severity = severity
        self.params = params or {}

    def check(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None:
        if request.request_type not in self.applies_to:
            return None
        return self.evaluate(request, context)

    @abstractmethod
    def evaluate(self, request: MoveRequest, context: PolicyContext) -> CheckResult | None: ...

    @abstractmethod
    def describe(self, config: CommunityConfig) -> str:
        """Plain-language statement of the rule, shown to residents and admins."""

    def _passed(self, message: str) -> CheckResult:
        return CheckResult(self.name, self.title, True, self.severity, message, self.fields)

    def _failed(self, message: str, severity: Severity | None = None) -> CheckResult:
        return CheckResult(self.name, self.title, False, severity or self.severity, message, self.fields)
