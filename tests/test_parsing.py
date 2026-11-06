import pytest

from src.agents.parsing import ParseError, parse_first_phase_output, parse_second_phase_output


# --- first phase -------------------------------------------------------------


def test_first_phase_valid_json_with_surrounding_text():
    text = 'Sure! Here is my move:\n{"first_announcement": 2, "first_take": 4}\nGood luck.'
    assert parse_first_phase_output(text) == (2, 4)


def test_first_phase_integral_float_accepted():
    assert parse_first_phase_output('{"first_announcement": 1.0, "first_take": 3.0}') == (1, 3)


def test_first_phase_missing_announcement_raises():
    with pytest.raises(ParseError):
        parse_first_phase_output('{"first_take": 2}')


def test_first_phase_missing_take_raises():
    with pytest.raises(ParseError):
        parse_first_phase_output('{"first_announcement": 2}')


def test_first_phase_negative_raises():
    with pytest.raises(ParseError):
        parse_first_phase_output('{"first_announcement": -1, "first_take": 0}')


def test_first_phase_non_integral_float_raises():
    with pytest.raises(ParseError):
        parse_first_phase_output('{"first_announcement": 2.5, "first_take": 0}')


def test_first_phase_bool_rejected():
    with pytest.raises(ParseError):
        parse_first_phase_output('{"first_announcement": true, "first_take": 0}')


def test_first_phase_no_json_raises():
    with pytest.raises(ParseError):
        parse_first_phase_output("I refuse to answer.")


# --- second phase ------------------------------------------------------------


def test_second_phase_valid_json_with_surrounding_text():
    text = (
        'Here goes:\n{"revise": "yes", "second_announcement": 2, "final_take": 4}\nDone.'
    )
    assert parse_second_phase_output(text) == (True, 2, 4)


def test_second_phase_revise_no():
    assert parse_second_phase_output(
        '{"revise": "no", "second_announcement": 5, "final_take": 5}'
    ) == (False, 5, 5)


def test_second_phase_revise_accepts_bool():
    assert parse_second_phase_output(
        '{"revise": true, "second_announcement": 1, "final_take": 1}'
    ) == (True, 1, 1)


def test_second_phase_revise_case_insensitive():
    assert parse_second_phase_output(
        '{"revise": "YES", "second_announcement": 1, "final_take": 1}'
    ) == (True, 1, 1)


def test_second_phase_invalid_revise_raises():
    with pytest.raises(ParseError):
        parse_second_phase_output(
            '{"revise": "maybe", "second_announcement": 1, "final_take": 1}'
        )


def test_second_phase_missing_field_raises():
    with pytest.raises(ParseError):
        parse_second_phase_output('{"revise": "no", "final_take": 1}')


def test_second_phase_negative_raises():
    with pytest.raises(ParseError):
        parse_second_phase_output(
            '{"revise": "no", "second_announcement": -1, "final_take": 1}'
        )


def test_second_phase_no_json_raises():
    with pytest.raises(ParseError):
        parse_second_phase_output("I refuse to answer.")
