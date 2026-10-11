from datetime import date
from typing import Any

from moveflow.config.schema import CommunityConfig


def format_answer(config: CommunityConfig, key: str, value: Any) -> str:
    """Human-readable version of a stored answer, e.g. a slot id becomes its label."""
    if value is None:
        return "-"
    spec = config.field(key)
    kind = spec.kind if spec else "text"
    if kind == "date":
        return date.fromisoformat(value).strftime("%a, %d %b %Y")
    if kind == "slot":
        return config.slot_label(value)
    if kind == "yes_no":
        return "Yes" if value else "No"
    if kind == "occupancy":
        return str(value).capitalize()
    return str(value)
