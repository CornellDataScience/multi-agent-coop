"""Network-free stand-in model for ``--model mock`` runs.

The responder reads only the prompt text (so it sits behind the same
firewall as a real model), mostly shares truthfully, sometimes withholds or
sends a false digit, and now and then wraps its JSON in prose or emits junk
so the retry and fallback paths get exercised. It answers the pre-game quiz
from a separate RNG stream, so the quiz never shifts game play. Seeded.
"""
from __future__ import annotations

import random
import re
from typing import Callable

from ...agents.backends import ChatResult, MockBackend

_DIGIT = re.compile(r"Your digit \(position (\d+)\) this round is (\d)")
_RECIPIENT = re.compile(r'"(\d+)": <digit 0-9 or null>')
_RECEIVED = re.compile(r"agent (\d+) sent you (\d|nothing)")
_N_DIGITS = re.compile(r"exactly (\d+) digits")
_ALPHA = re.compile(r"your total points - ([\d.]+) x")
_REASONS = ("Sharing seems to pay off here.", "Keeping my options open this round.")


def _quiz_reply(prompt: str, rng: random.Random) -> str:
    """Correct answers ~85% of the time, else a sign error."""
    m = _ALPHA.search(prompt)
    size = float(m.group(1)) * 20 if m else 0.0
    direction = "same" if size == 0 else "down"
    if rng.random() < 0.15:
        direction = "up"
    return '{"q1_direction": "%s", "q1_amount": %g, "q2_amount": 10}' % (direction, size)


def mock_responder(seed: int) -> Callable[[str, str], str]:
    rng = random.Random(seed)
    quiz_rng = random.Random(seed + 1_000_003)  # separate stream: the quiz can't shift game play

    def respond(system: str, prompt: str) -> str:
        if '"q1_direction"' in prompt:
            return _quiz_reply(prompt, quiz_rng)
        roll = rng.random()
        if roll < 0.03:
            return "I am not sure what to do here."  # invalid: triggers a retry
        m = _DIGIT.search(prompt)
        pos, digit = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        if '"messages"' in prompt:
            parts = []
            for j in _RECIPIENT.findall(prompt):
                r = rng.random()
                if r < 0.7:
                    value = str(digit)
                elif r < 0.85:
                    value = "null"
                else:
                    value = str((digit + rng.randint(1, 9)) % 10)
                parts.append(f'"{j}": {value}')
            body = '{"messages": {%s}' % ", ".join(parts)
        else:
            n_match = _N_DIGITS.search(prompt)
            n = int(n_match.group(1)) if n_match else pos + 1
            guess = [0] * n
            for j, d in _RECEIVED.findall(prompt):
                if d != "nothing" and int(j) < n:
                    guess[int(j)] = int(d)
            if pos < n:
                guess[pos] = digit
            body = '{"guess": [%s], "confidence": %.2f' % (", ".join(map(str, guess)), rng.random())
        # About half of replies carry a reason; no extra RNG draws.
        body += (', "reason": "%s"}' % _REASONS[int(roll * 100) % 2]) if roll < 0.5 else "}"
        if roll < 0.08:
            return f"Here is my answer:\n```json\n{body}\n```"
        return body

    return respond


class KCMockBackend(MockBackend):
    """MockBackend that also reports rough token usage (chars / 4), so cost
    plumbing can be checked end to end without a real model."""

    def __call__(self, system: str, prompt: str) -> ChatResult:
        result = super().__call__(system, prompt)
        result.usage = {"input_tokens": (len(system) + len(prompt)) // 4,
                        "output_tokens": len(result.text) // 4}
        return result
