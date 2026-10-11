"""Read-only views of data that already exists elsewhere in ANACITY.

The agent and the policy rules only see these protocols. The prototype backs
them with a YAML file; production would call the ANACITY unit registry and
billing services instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from moveflow.domain.enums import OccupancyType


@dataclass(frozen=True)
class UnitRecord:
    unit: str
    occupant: str | None
    occupancy: OccupancyType | None
    outstanding_dues: float = 0.0

    @property
    def is_vacant(self) -> bool:
        return self.occupant is None


class UnitDirectory(Protocol):
    def find_unit(self, community_id: str, unit: str) -> UnitRecord | None: ...


class DuesProvider(Protocol):
    def outstanding_dues(self, community_id: str, unit: str) -> float: ...


class MockPropertySystem:
    """Implements both UnitDirectory and DuesProvider from a YAML fixture."""

    def __init__(self, units: dict[str, dict[str, UnitRecord]]):
        self._units = units

    @classmethod
    def from_file(cls, path: Path) -> MockPropertySystem:
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        units = {
            community_id: {
                entry["unit"]: UnitRecord(
                    unit=entry["unit"],
                    occupant=entry.get("occupant"),
                    occupancy=OccupancyType(entry["occupancy"]) if entry.get("occupancy") else None,
                    outstanding_dues=float(entry.get("outstanding_dues", 0)),
                )
                for entry in entries
            }
            for community_id, entries in raw.items()
        }
        return cls(units)

    def find_unit(self, community_id: str, unit: str) -> UnitRecord | None:
        return self._units.get(community_id, {}).get(unit)

    def outstanding_dues(self, community_id: str, unit: str) -> float:
        record = self.find_unit(community_id, unit)
        return record.outstanding_dues if record else 0.0
