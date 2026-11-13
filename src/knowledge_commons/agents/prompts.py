"""Build system/user prompts from a ``KCObservation``. Wording lives in
``prompt_variants.py``; this module only fills it in. The observation is the
only input, so prompts cannot leak anything the firewall withheld."""
from __future__ import annotations

import re

from ..observation import KCObservation
from .prompt_variants import DEFAULT_VARIANT, get_variant

_PLACEHOLDER = re.compile(
    r"\{(agent_id|n_agents|n_others|last_position|round|my_digit|reward_correct|group_bonus|"
    r"bonus_threshold|alpha|recipient_keys|message_example|guess_example|received_list)\}"
)


def _digits(seq) -> str:
    return " ".join(str(d) for d in seq)


def _sent_word(d) -> str:
    return "nothing" if d is None else str(d)


def _received_list(received: dict[int, int | None]) -> str:
    return ", ".join(f"agent {j} sent you {_sent_word(d)}" for j, d in sorted(received.items()))


def _values(obs: KCObservation) -> dict[str, str]:
    others = [j for j in range(obs.n_agents) if j != obs.agent_id]
    msg_example = '{"messages": {%s}}' % ", ".join(f'"{j}": <digit 0-9 or null>' for j in others)
    guess_example = '{"guess": [%s], "confidence": <number 0-1>}' % ", ".join(["<digit>"] * obs.n_agents)
    return {
        "agent_id": str(obs.agent_id),
        "n_agents": str(obs.n_agents),
        "n_others": str(obs.n_agents - 1),
        "last_position": str(obs.n_agents - 1),
        "round": "" if obs.round is None else str(obs.round),
        "my_digit": str(obs.my_digit),
        "reward_correct": str(obs.reward_correct),
        "group_bonus": str(obs.group_bonus),
        "bonus_threshold": str(obs.bonus_threshold),
        "alpha": f"{obs.alpha:g}",
        "recipient_keys": ", ".join(f'"{j}"' for j in others),
        "message_example": msg_example,
        "guess_example": guess_example,
        "received_list": _received_list(obs.received or {}),
    }


def _fill(template: str, values: dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


def _history_line(h: dict) -> str:
    sent = ", ".join(f"agent {j} got {_sent_word(d)}" for j, d in sorted(h["sent"].items()))
    received = ", ".join(f"agent {j} sent {_sent_word(d)}" for j, d in sorted(h["received"].items()))
    solvers = h["n_solvers"]
    return (
        f"- Round {h['round']}: the code was {_digits(h['code'])}. "
        f"You sent: {sent}. You received: {received}. "
        f"Your guess was {_digits(h['my_guess'])} ({'correct' if h['solved'] else 'wrong'}); "
        f"you earned {h['points']} points. {solvers} agent{'' if solvers == 1 else 's'} "
        f"guessed the code; the bonus was {'paid' if h['bonus'] else 'not paid'}."
    )


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _reputation_lines(obs: KCObservation) -> list[str]:
    lines = []
    for j, r in sorted(obs.reputation.items()):
        who = f"agent {j}" + (" (you)" if j == obs.agent_id else "")
        if not r["n"]:
            lines.append(f"- {who}: no messages yet")
        else:
            lines.append(f"- {who}: true {_pct(r['truthful'])}, nothing {_pct(r['withheld'])}, "
                         f"false {_pct(r['lie'])} ({r['n']} chances to send)")
    return lines


def build_prompts(obs: KCObservation, variant: str = DEFAULT_VARIANT) -> tuple[str, str]:
    """Return ``(system, user)`` for this observation's phase."""
    t = get_variant(variant)
    v = _values(obs)
    sections = [_fill(t["rules"], v)]

    if obs.info_condition != "no_memory":
        if obs.history:
            sections.append("\n".join([t["history_header"], *(_history_line(h) for h in obs.history)]))
        else:
            sections.append(t["history_empty"])
    if obs.reputation is not None:
        sections.append("\n".join([t["reputation_header"], *_reputation_lines(obs)]))

    # no_memory presents every round as if it were the first: no round number.
    state_key = "state_no_round" if obs.info_condition == "no_memory" else "state"
    state = [_fill(t[state_key], v)]
    if obs.phase == "guess":
        state.append(_fill(t["received"], v))
    sections.append("\n".join(state))

    sections.append(_fill(t["schema_message" if obs.phase == "message" else "schema_guess"], v))
    return _fill(t["system"], v), "\n\n".join(sections)
