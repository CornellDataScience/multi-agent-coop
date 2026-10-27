import pytest

from src.agents.parsing import ParseError, parse_model_output


def test_valid_json_with_surrounding_text():
    text = 'Sure! Here is my move:\n{"take": 4, "claimed_take": 2}\nGood luck.'
    assert parse_model_output(text, communication=True) == (4, 2)


def test_claimed_ignored_without_communication():
    assert parse_model_output('{"take": 7}', communication=False) == (7, None)


def test_integral_float_accepted():
    assert parse_model_output('{"take": 3.0, "claimed_take": 1.0}', True) == (3, 1)


def test_missing_take_raises():
    with pytest.raises(ParseError):
        parse_model_output('{"claimed_take": 2}', communication=True)


def test_missing_claimed_raises_when_communicating():
    with pytest.raises(ParseError):
        parse_model_output('{"take": 2}', communication=True)


def test_negative_raises():
    with pytest.raises(ParseError):
        parse_model_output('{"take": -1, "claimed_take": 0}', communication=True)


def test_non_integral_float_raises():
    with pytest.raises(ParseError):
        parse_model_output('{"take": 2.5, "claimed_take": 0}', communication=True)


def test_bool_rejected():
    with pytest.raises(ParseError):
        parse_model_output('{"take": true, "claimed_take": 0}', communication=True)


def test_no_json_raises():
    with pytest.raises(ParseError):
        parse_model_output("I refuse to answer.", communication=True)
