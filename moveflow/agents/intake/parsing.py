"""Small, deterministic parsers for the things residents type.

The rule-based extractor uses these directly. The LLM extractor also runs the
model's output through them, so whatever the model says is checked and
converted into the same canonical values (ISO dates, slot ids, "B-1204").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from moveflow.config.schema import TimeSlot
from moveflow.domain.enums import OccupancyType, RequestType

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

YES_WORDS = {
    "yes", "y", "yeah", "yep", "sure", "ok", "okay", "confirm", "correct",
    "submit", "go ahead", "looks good", "please do",
}
NO_WORDS = {"no", "n", "nope", "nah", "not really"}
SKIP_WORDS = {"skip", "none", "na", "n/a", "nil", "nothing", "later", "not now", "no vehicles", "self", "self moving"}

# "T1-0901" / "T1 0901" (a tower with a digit needs a separator), or "B-1204" / "b1204".
_UNIT = re.compile(r"\b([A-Za-z]\d)\s?[-\s]\s?(\d{3,4})\b|\b([A-Za-z])\s?-?\s?(\d{3,4})\b")
_UNIT_WITHOUT_TOWER = re.compile(r"\b(?:flat|unit|apartment|apt)\.?\s*(?:no\.?\s*)?#?\s*(\d{3,4})\b", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?91)?([6-9]\d{9})(?!\d)")
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b")
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3,9})\b")
_MONTH_DAY = re.compile(r"\b([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b")
_ORDINAL_DAY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\b")
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b")


@dataclass(frozen=True)
class DateGuess:
    value: date | None = None
    # Set when the text clearly names a date but not a single one, e.g. "this weekend".
    question: str | None = None
    options: tuple[date, ...] = ()


def normalise(text: str) -> str:
    return " ".join(text.lower().strip().split())


def contains_phrase(text: str, phrases: set[str] | list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in phrases)


def detect_request_type(text: str) -> RequestType | None:
    text = normalise(text)
    if re.search(r"\b(move|moving|shift|shifting|relocat\w*)\s*(out|away)\b|\bvacat\w*|\bleaving\b", text):
        return RequestType.MOVE_OUT
    if re.search(r"\b(move|moving|shift|shifting)\s*(in|into)\b|\bmove-in\b|\bnew (flat|home|tenant)\b", text):
        return RequestType.MOVE_IN
    if "move-out" in text:
        return RequestType.MOVE_OUT
    return None


def find_unit(text: str) -> str | None:
    match = _UNIT.search(text)
    if not match:
        return None
    tower = match.group(1) or match.group(3)
    number = match.group(2) or match.group(4)
    return f"{tower.upper()}-{number}"


def mentions_unit_without_tower(text: str) -> bool:
    return find_unit(text) is None and bool(_UNIT_WITHOUT_TOWER.search(text))


def find_phone(text: str) -> str | None:
    digits_joined = re.sub(r"(?<=\d)[\s-](?=\d)", "", text)
    match = _PHONE.search(digits_joined)
    return match.group(1) if match else None


def find_occupancy(text: str) -> OccupancyType | None:
    text = normalise(text)
    if re.search(r"\b(tenant|renting|rented|rent|lease|leased|tenancy)\b", text):
        return OccupancyType.TENANT
    if re.search(r"\b(owner|own|bought|purchased|my own)\b", text):
        return OccupancyType.OWNER
    return None


def find_number(text: str) -> int | None:
    text = normalise(text)
    match = re.search(r"\b(\d{1,2})\b", text)
    if match:
        return int(match.group(1))
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return value
    return None


def parse_yes_no(text: str) -> bool | None:
    text = normalise(text).rstrip(".!")
    if text in YES_WORDS or text.startswith(("yes", "yeah", "sure")):
        return True
    if text in NO_WORDS or text.startswith(("no ", "nope", "not ")) or text == "no":
        return False
    return None


def is_skip(text: str) -> bool:
    return normalise(text).rstrip(".!") in SKIP_WORDS


def find_slot(text: str, slots: list[TimeSlot]) -> str | None:
    text = normalise(text)
    for slot in slots:
        if slot.id == text or contains_phrase(text, [slot.id.replace("_", " "), *slot.aliases]):
            return slot.id
    clock = _CLOCK.search(text)
    if clock:
        hour = int(clock.group(1)) % 12 + (12 if clock.group(3) == "pm" else 0)
        moment = time(hour, int(clock.group(2) or 0))
        return next((slot.id for slot in slots if slot.contains(moment)), None)
    return None


def parse_date(text: str, today: date) -> DateGuess:
    text = normalise(text)

    if match := _ISO_DATE.search(text):
        return _safe_date(int(match[1]), int(match[2]), int(match[3]))

    if "day after tomorrow" in text:
        return DateGuess(today + timedelta(days=2))
    if re.search(r"\btomorrow\b", text):
        return DateGuess(today + timedelta(days=1))
    if re.search(r"\btoday\b", text):
        return DateGuess(today)

    if re.search(r"\bweekend\b", text):
        saturday = _next_weekday(today, 5)
        return DateGuess(
            question="Which day of the weekend works for you?",
            options=(saturday, saturday + timedelta(days=1)),
        )
    if re.search(r"\bnext week\b", text) and not any(day in text for day in WEEKDAYS):
        return DateGuess(question="Which day next week would you like to move? A specific date helps.")

    for index, day in enumerate(WEEKDAYS):
        if re.search(rf"\b{day}\b|\b{day[:3]}\b", text):
            return DateGuess(_next_weekday(today, index))

    for match in _DAY_MONTH.finditer(text):
        if month := _month_number(match[2]):
            return _with_inferred_year(int(match[1]), month, today)
    for match in _MONTH_DAY.finditer(text):
        if month := _month_number(match[1]):
            return _with_inferred_year(int(match[2]), month, today)
    if match := _NUMERIC_DATE.search(text):
        day, month, year = int(match[1]), int(match[2]), match[3]
        if year:
            full_year = int(year) + 2000 if len(year) == 2 else int(year)
            return _safe_date(full_year, month, day)
        return _with_inferred_year(day, month, today)
    if match := _ORDINAL_DAY.search(text):
        day = int(match[1])
        month = today.month if day >= today.day else today.month % 12 + 1
        return _with_inferred_year(day, month, today)
    return DateGuess()


def format_day(value: date) -> str:
    return value.strftime("%a, %d %b %Y")


def _next_weekday(today: date, weekday: int) -> date:
    days_ahead = (weekday - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


def _month_number(word: str) -> int | None:
    """Accepts "oct", "octo", "october"; rejects words that merely start like a month ("decent")."""
    for index, name in enumerate(MONTH_NAMES):
        if len(word) >= 3 and name.startswith(word):
            return index + 1
    return None


def _with_inferred_year(day: int, month: int, today: date) -> DateGuess:
    guess = _safe_date(today.year, month, day)
    if guess.value and guess.value < today:
        return _safe_date(today.year + 1, month, day)
    return guess


def _safe_date(year: int, month: int, day: int) -> DateGuess:
    try:
        return DateGuess(datetime(year, month, day).date())
    except ValueError:
        return DateGuess()
