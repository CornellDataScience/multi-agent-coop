"""Network-free stand-in model for ``--model mock`` runs.

The responder reads only the prompt text (so it sits behind the same
firewall as a real model), mostly shares truthfully, sometimes withholds or
sends a false digit, and now and then wraps its JSON in prose or emits junk
so the retry and fallback paths get exercised. Seeded, so runs reproduce.
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


def mock_responder(seed: int) -> Callable[[str, str], str]:
    rng = random.Random(seed)

    def respond(system: str, prompt: str) -> str:
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
            body = '{"messages": {%s}}' % ", ".join(parts)
        else:
            n_match = _N_DIGITS.search(prompt)
            n = int(n_match.group(1)) if n_match else pos + 1
            guess = [0] * n
            for j, d in _RECEIVED.findall(prompt):
                if d != "nothing" and int(j) < n:
                    guess[int(j)] = int(d)
            if pos < n:
                guess[pos] = digit
            body = '{"guess": [%s], "confidence": %.2f}' % (", ".join(map(str, guess)), rng.random())
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
