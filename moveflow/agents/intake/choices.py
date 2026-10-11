import re

from moveflow.agents.intake import parsing
from moveflow.agents.intake.conversation import Choice, Extraction

_NUMBER_PICK = re.compile(r"(?:option|choice|no\.?)?\s*#?\s*(\d)")
_WORD_PICK = re.compile(r"(?:the\s+)?(first|second|third|1st|2nd|3rd)(?:\s+(?:one|option))?(?:\s+please)?")
_ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3}


def resolve_choice(message: str, choices: list[Choice]) -> Extraction | None:
    """Recognises replies like "2", "option 1" or "the second one" to options we offered.

    This runs before any extraction because it is unambiguous and doesn't need a model.
    """
    if not choices:
        return None
    text = parsing.normalise(message).rstrip(".!")

    index = None
    if match := _NUMBER_PICK.fullmatch(text):
        index = int(match.group(1))
    elif match := _WORD_PICK.fullmatch(text):
        index = _ORDINALS[match.group(1)]
    else:
        index = next((i + 1 for i, choice in enumerate(choices) if parsing.normalise(choice.label) == text), None)

    if index is None or not 1 <= index <= len(choices):
        return None
    return Extraction(values=dict(choices[index - 1].values), source="choice")
