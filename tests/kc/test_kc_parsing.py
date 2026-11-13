import pytest

from src.knowledge_commons.agents.parsing import ParseError, parse_guess_output, parse_message_output


# --- Message phase -----------------------------------------------------------

def test_valid_message_parses():
    assert parse_message_output('{"messages": {"1": 7, "2": null, "3": 7}}', 0, 4) == {1: 7, 2: None, 3: 7}
    assert parse_message_output('{"messages": {"0": 0, "2": 9, "3": null}}', 1, 4) == {0: 0, 2: 9, 3: None}


def test_message_json_inside_prose_parses():
    text = ('Let me think {carefully}. I will share.\n```json\n'
            '{"messages": {"1": 3, "2": 3, "3": null}}\n```\nDone.')
    assert parse_message_output(text, 0, 4) == {1: 3, 2: 3, 3: None}


def test_message_accepts_digit_strings_and_integral_floats():
    assert parse_message_output('{"messages": {"1": "4", "2": 5.0, "3": null}}', 0, 4) == {1: 4, 2: 5, 3: None}


@pytest.mark.parametrize("text", [
    '{"messages": {"1": 7, "2": 7}}',                      # missing recipient 3
    '{"messages": {"1": 7, "2": 7, "3": 7, "0": 7}}',      # includes self
    '{"messages": {"1": 7, "2": 7, "4": 7}}',              # unknown recipient
    '{"messages": {"1": 10, "2": 7, "3": 7}}',             # digit 10
    '{"messages": {"1": -1, "2": 7, "3": 7}}',             # negative
    '{"messages": {"1": true, "2": 7, "3": 7}}',           # bool
    '{"messages": {"1": "seven", "2": 7, "3": 7}}',        # word
    '{"messages": {"1": 7.5, "2": 7, "3": 7}}',            # non-integral
    '{"messages": [7, 7, 7]}',                             # wrong shape
    '{"msgs": {"1": 7, "2": 7, "3": 7}}',                  # missing key
    'I would rather not say.',                             # no JSON
    '',
])
def test_invalid_message_fails(text):
    with pytest.raises(ParseError):
        parse_message_output(text, 0, 4)


# --- Guess phase -------------------------------------------------------------

def test_valid_guess_parses():
    assert parse_guess_output('{"guess": [3, 7, 1, 4], "confidence": 0.8}', 4) == ((3, 7, 1, 4), 0.8)
    assert parse_guess_output('{"guess": [0, 0, 0, 0]}', 4) == ((0, 0, 0, 0), None)


def test_guess_inside_prose_parses():
    text = 'My guess: {"guess": [1, 2, 3, 4], "confidence": 1} -- good luck'
    assert parse_guess_output(text, 4) == ((1, 2, 3, 4), 1.0)


@pytest.mark.parametrize("conf", ['1.5', '-0.1', '"high"', 'true', 'null'])
def test_bad_confidence_is_dropped_not_fatal(conf):
    assert parse_guess_output(f'{{"guess": [1, 2, 3, 4], "confidence": {conf}}}', 4) == ((1, 2, 3, 4), None)


@pytest.mark.parametrize("text", [
    '{"guess": [1, 2, 3]}',            # too short
    '{"guess": [1, 2, 3, 4, 5]}',      # too long
    '{"guess": [1, 2, 3, 10]}',        # digit 10
    '{"guess": [1, 2, null, 4]}',      # null digit
    '{"guess": "1234"}',               # not a list
    '{"code": [1, 2, 3, 4]}',          # missing key
    'no idea',
])
def test_invalid_guess_fails(text):
    with pytest.raises(ParseError):
        parse_guess_output(text, 4)
