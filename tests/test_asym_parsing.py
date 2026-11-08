"""Parsing ladder tests (benchmark spec 4.3). At least 25 messy fixtures."""

import pytest

from asymbench.parsing import (coerce_number, first_balanced_object,
                               parse_agent_output)

GOOD = {"private_notes": "n", "message": "m", "action": {"type": "none"}}
GOOD_TEXT = '{"private_notes": "n", "message": "m", "action": {"type": "none"}}'

# (name, input text, expected object or None)
FIXTURES = [
    ("clean", GOOD_TEXT, GOOD),
    ("leading_prose", "Sure! Here is my reply:\n" + GOOD_TEXT, GOOD),
    ("trailing_prose", GOOD_TEXT + "\nLet me know if that works.", GOOD),
    ("fence_json", "```json\n" + GOOD_TEXT + "\n```", GOOD),
    ("fence_plain", "```\n" + GOOD_TEXT + "\n```", GOOD),
    ("fence_and_prose", "My answer:\n```json\n" + GOOD_TEXT + "\n```\nDone.", GOOD),
    ("think_block", "<think>I should accept.</think>" + GOOD_TEXT, GOOD),
    ("thinking_block", "<thinking>\nhmm\n</thinking>\n" + GOOD_TEXT, GOOD),
    ("think_uppercase", "<THINK>reasoning</THINK>" + GOOD_TEXT, GOOD),
    ("trailing_comma_obj", '{"message": "m", "action": {"type": "none"},}',
     {"message": "m", "action": {"type": "none"}}),
    ("trailing_comma_array", '{"xs": [1, 2,], "action": {"type": "none"}}',
     {"xs": [1, 2], "action": {"type": "none"}}),
    ("smart_quotes", "“private_notes”: “n”".join(["{", ", \"action\": {\"type\": \"none\"}}"]),
     {"private_notes": "n", "action": {"type": "none"}}),
    ("numbers_as_strings", '{"action": {"type": "take", "amount": "20"}}',
     {"action": {"type": "take", "amount": "20"}}),
    ("missing_fields", '{"action": {"type": "none"}}', {"action": {"type": "none"}}),
    ("two_objects", GOOD_TEXT + "\n" + '{"action": {"type": "accept"}}', GOOD),
    ("nested_braces_in_string", '{"message": "I take {x} fish", "action": {"type": "none"}}',
     {"message": "I take {x} fish", "action": {"type": "none"}}),
    ("escaped_quotes", '{"message": "she said \\"hi\\"", "action": {"type": "none"}}',
     {"message": 'she said "hi"', "action": {"type": "none"}}),
    ("raw_newline_in_string", '{"message": "line one\nline two", "action": {"type": "none"}}',
     {"message": "line one\nline two", "action": {"type": "none"}}),
    ("prose_with_braces_before", "Consider {this}. " + GOOD_TEXT, None),  # first balanced obj is not JSON
    ("totally_broken", "I think I'll take 20 fish this round.", None),
    ("empty", "", None),
    ("whitespace", "   \n\t  ", None),
    ("only_think", "<think>all reasoning no answer</think>", None),
    ("json_array", '[{"action": {"type": "none"}}]',
     {"action": {"type": "none"}}),  # balanced-object extraction rescues the inner dict
    ("unclosed_object", '{"message": "hi", "action": {"type": "none"', None),
    ("single_quotes", "{'message': 'hi', 'action': {'type': 'none'}}", None),
    ("fenced_trailing_comma_smart", "```json\n{“message”: “hi”, \"action\": {\"type\": \"none\"},}\n```",
     {"message": "hi", "action": {"type": "none"}}),
    ("crlf_fence", "```json\r\n" + GOOD_TEXT + "\r\n```", GOOD),
]


@pytest.mark.parametrize("name,text,expected", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_fixture(name, text, expected):
    obj, stage, error = parse_agent_output(text)
    if expected is None:
        assert obj is None, f"{name}: expected failure, got {obj!r} at stage {stage}"
        assert error
    else:
        assert obj == expected, f"{name}: got {obj!r} (stage {stage}, error {error})"
        assert stage in (2, 3, 4, 5)


def test_fixture_count():
    assert len(FIXTURES) >= 25


def test_stages_reported():
    assert parse_agent_output(GOOD_TEXT)[1] == 2
    assert parse_agent_output("```json\n" + GOOD_TEXT + "\n```")[1] in (2, 3)
    assert parse_agent_output("prose first\n" + GOOD_TEXT)[1] == 4
    broken = 'reply: {"message": "m", "action": {"type": "none"},}'
    assert parse_agent_output(broken)[1] == 5


def test_first_balanced_object_string_aware():
    text = 'noise {"a": "has } brace", "b": {"c": 1}} tail {"d": 2}'
    assert first_balanced_object(text) == '{"a": "has } brace", "b": {"c": 1}}'
    assert first_balanced_object("no braces") is None


@pytest.mark.parametrize("value,expected", [
    (20, 20.0), (20.5, 20.5), ("20", 20.0), ("$450", 450.0), ("1,200", 1200.0),
    (" $1,250.50 ", 1250.5), (True, None), (None, None), ("abc", None), ([1], None),
])
def test_coerce_number(value, expected):
    assert coerce_number(value) == expected
