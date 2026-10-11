from datetime import date

import pytest

from moveflow.agents.intake import parsing
from moveflow.domain.enums import OccupancyType, RequestType

TODAY = date(2026, 10, 12)  # Monday


@pytest.mark.parametrize("text,expected", [
    ("on 2026-10-24", date(2026, 10, 24)),
    ("24th October", date(2026, 10, 24)),
    ("oct 24", date(2026, 10, 24)),
    ("24/10/2026", date(2026, 10, 24)),
    ("on the 24th", date(2026, 10, 24)),
    ("on the 5th", date(2026, 11, 5)),  # already past this month
    ("5 jan", date(2027, 1, 5)),
    ("tomorrow", date(2026, 10, 13)),
    ("this saturday", date(2026, 10, 17)),
])
def test_dates(text, expected):
    assert parsing.parse_date(text, TODAY).value == expected


def test_weekend_is_ambiguous_with_both_days_offered():
    guess = parsing.parse_date("sometime this weekend", TODAY)
    assert guess.value is None
    assert guess.options == (date(2026, 10, 17), date(2026, 10, 18))


def test_words_that_look_like_months_are_ignored():
    assert parsing.parse_date("4 decent rooms", TODAY).value is None


@pytest.mark.parametrize("text,expected", [
    ("flat B-1204 please", "B-1204"),
    ("b1204", "B-1204"),
    ("T1 0901", "T1-0901"),
    ("moving on 2026-10-24", None),
])
def test_units(text, expected):
    assert parsing.find_unit(text) == expected


def test_unit_without_tower_is_detected():
    assert parsing.mentions_unit_without_tower("flat 1204")


def test_phone_numbers():
    assert parsing.find_phone("call me on +91 98765 43210") == "9876543210"
    assert parsing.find_phone("12345") is None


def test_request_type_and_occupancy():
    assert parsing.detect_request_type("we are moving out next week") is RequestType.MOVE_OUT
    assert parsing.detect_request_type("I'm moving into B-1204") is RequestType.MOVE_IN
    assert parsing.find_occupancy("we rented it") is OccupancyType.TENANT
    assert parsing.find_occupancy("I bought the flat") is OccupancyType.OWNER


def test_slots_by_alias_and_clock_time(green):
    assert parsing.find_slot("morning works", green.time_slots) == "morning"
    assert parsing.find_slot("around 2 pm", green.time_slots) == "afternoon"
    assert parsing.find_slot("10 pm", green.time_slots) is None


def test_yes_no_and_skip():
    assert parsing.parse_yes_no("Yes please") is True
    assert parsing.parse_yes_no("no pets") is False
    assert parsing.parse_yes_no("maybe") is None
    assert parsing.is_skip("None.")
