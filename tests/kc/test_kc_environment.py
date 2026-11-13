import json

import pytest

from src.knowledge_commons import environment as env_mod
from src.knowledge_commons.agents.base import KCAgent
from src.knowledge_commons.agents.scripted import make_scripted
from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.environment import KCEnvironment
from src.knowledge_commons.events import GuessAction, MessageAction
from src.knowledge_commons.log import KCGameLog, load_game
from src.knowledge_commons.scoring import round_points, utilities


def _lineup(*names, start=0):
    return [make_scripted(name, i) for i, name in enumerate(names, start=start)]


# --- Golden games (PHASES.md, Phase 1) --------------------------------------

def test_golden_game_hoarder_wins_without_bonus():
    cfg = KCConfig(alpha=0.5, pot_size=40, group_bonus=10, bonus_threshold=3, max_rounds=2)
    agents = _lineup("honest", "honest", "honest", "hoarder")
    log = KCEnvironment(cfg, agents, "golden1", codes=[(1, 2, 3, 4), (5, 6, 7, 8)]).run()

    # Agents 0-2 never get digit 3 and fill it with 0, so they fail; the
    # hoarder hears everyone's truth and solves both rounds alone: the whole
    # pot (40) each round, and 1 solver < T=3 so no bonus.
    for r in log.rounds:
        assert r.solved == {0: False, 1: False, 2: False, 3: True}
        assert (r.n_solvers, r.bonus) == (1, False)
        assert r.points == {0: 0, 1: 0, 2: 0, 3: 40}
    assert log.rounds[0].guess_actions[0].guess == (1, 2, 3, 0)
    assert log.rounds[1].guess_actions[3].guess == (5, 6, 7, 8)

    assert log.totals() == {0: 0, 1: 0, 2: 0, 3: 80}
    # U_3 = 80 - 0.5 * 0 = 80; U_i = 0 - 0.5 * mean(0, 0, 80) = -13.333 -> -13.33 in the log.
    assert log.utilities() == {0: -13.33, 1: -13.33, 2: -13.33, 3: 80.0}


# One-round golden games at alpha 0 (U == P), one per row of SPEC §4's table.

def test_golden_four_solve_twenty_each():
    # Hoarder's digit is 0, which is everyone's default -> all 4 solve.
    # Pot 40 / 4 = 10, plus bonus 10 -> 20 each.
    log = KCEnvironment(KCConfig(max_rounds=1), _lineup("honest", "honest", "honest", "hoarder"),
                        "g4", codes=[(1, 2, 3, 0)]).run()
    r = log.rounds[0]
    assert (r.n_solvers, r.bonus) == (4, True)
    assert r.points == {0: 20, 1: 20, 2: 20, 3: 20}
    assert log.utilities() == {0: 20, 1: 20, 2: 20, 3: 20}


def test_golden_three_solve():
    # Excluder 3 shuts out agent 0 (default target (3 + 1) % 4 = 0). Agent 0
    # guesses 1 2 3 0 and fails; 1, 2, 3 solve. Pot 40 / 3 = 13.33, bonus
    # paid (3 >= T) -> solvers 23.33, agent 0 gets the bonus only: 10.
    log = KCEnvironment(KCConfig(max_rounds=1), _lineup("honest", "honest", "honest", "excluder"),
                        "g3", codes=[(1, 2, 3, 4)]).run()
    r = log.rounds[0]
    assert r.solved == {0: False, 1: True, 2: True, 3: True} and r.bonus
    assert r.points == {0: 10, 1: 23.33, 2: 23.33, 3: 23.33}


def test_golden_two_solve_no_bonus():
    # Agent 2 hides its digit from 3, agent 3 hides its digit from 2; both
    # tell 0 and 1. Only 0 and 1 solve: pot 40 / 2 = 20 each, 2 < T -> no
    # bonus, 2 and 3 get 0.
    agents = [make_scripted("honest", 0), make_scripted("honest", 1),
              make_scripted("excluder", 2, target=3), make_scripted("excluder", 3, target=2)]
    log = KCEnvironment(KCConfig(max_rounds=1), agents, "g2", codes=[(1, 2, 3, 4)]).run()
    r = log.rounds[0]
    assert (r.n_solvers, r.bonus) == (2, False)
    assert r.points == {0: 20, 1: 20, 2: 0, 3: 0}


def test_golden_one_solver_takes_whole_pot():
    # Liar 3 sends 5 (4 + 1) to everyone; it hears the truth from 0-2 and
    # solves alone: 40, no bonus. Everyone else guesses 1 2 3 5 and gets 0.
    log = KCEnvironment(KCConfig(max_rounds=1), _lineup("honest", "honest", "honest", "liar"),
                        "g1", codes=[(1, 2, 3, 4)]).run()
    r = log.rounds[0]
    assert r.guess_actions[0].guess == (1, 2, 3, 5)
    assert r.points == {0: 0, 1: 0, 2: 0, 3: 40}


# --- Must-send (allow_withhold=False) ----------------------------------------

def test_must_send_hoarder_sends_true_digit_and_everyone_solves():
    # Same lineup and codes as golden1, but nothing is not an option: the
    # hoarder sends its true digit, so all 4 solve both rounds -> 20 each round.
    cfg = KCConfig(max_rounds=2, allow_withhold=False)
    log = KCEnvironment(cfg, _lineup("honest", "honest", "honest", "hoarder"), "ms",
                        codes=[(1, 2, 3, 4), (5, 6, 7, 8)]).run()
    for r, code in zip(log.rounds, [(1, 2, 3, 4), (5, 6, 7, 8)]):
        assert r.message_actions[3].sends == {0: code[3], 1: code[3], 2: code[3]}
        assert r.points == {0: 20, 1: 20, 2: 20, 3: 20}
    assert log.totals() == {0: 40, 1: 40, 2: 40, 3: 40}


def test_must_send_sanitizer_fills_true_digit():
    # Scripted "nothing" (excluder, reciprocator after a lie) and missing or
    # invalid sends become the sender's true digit, never None.
    cfg = KCConfig(max_rounds=2, allow_withhold=False)
    log = KCEnvironment(cfg, [SloppyAgent(0)] + _lineup("excluder", "reciprocator", "liar", start=1),
                        "ms2", codes=[(4, 5, 6, 7), (1, 2, 3, 9)]).run()
    for r in log.rounds:
        for i, act in r.message_actions.items():
            assert None not in act.sends.values()
    r1 = log.rounds[0]
    assert r1.message_actions[0].sends == {1: 4, 2: 4, 3: 4}  # skipped 2 and bad 12 -> true 4
    assert r1.message_actions[1].sends[2] == 5  # excluder's target gets the true digit
    # Round 2: the reciprocator would withhold from the liar; under must-send it sends truth.
    assert log.rounds[1].message_actions[2].sends[3] == 3


# --- Gate: full 8-round all-honest game -------------------------------------

def test_all_honest_eight_rounds_everyone_solves_every_round():
    cfg = KCConfig(seed=3)
    log = KCEnvironment(cfg, _lineup(*["honest"] * 4), "all_honest").run()
    assert len(log.rounds) == 8
    truthful = total = 0
    for r in log.rounds:
        assert all(r.solved.values()) and r.bonus
        for i, act in r.message_actions.items():
            for j, d in act.sends.items():
                total += 1
                truthful += d == r.code[i]
    assert truthful == total == 8 * 4 * 3  # information flow 1.0
    assert log.totals() == {i: 160 for i in range(4)}


# --- Invariant 1: determinism of codes --------------------------------------

def _codes(cfg, names):
    return [r.code for r in KCEnvironment(cfg, _lineup(*names), "x").run().rounds]


def test_same_seed_same_codes_across_lineups_alpha_and_info():
    base = _codes(KCConfig(seed=11), ["honest"] * 4)
    assert len(set(base)) > 1  # codes actually vary by round
    assert all(len(c) == 4 and all(0 <= d <= 9 for d in c) for c in base)
    assert _codes(KCConfig(seed=11, alpha=1.5), ["liar", "hoarder", "honest", "grudger"]) == base
    assert _codes(KCConfig(seed=11, info_condition="no_memory"), ["hoarder"] * 4) == base
    assert _codes(KCConfig(seed=11, info_condition="public_reputation"), ["reciprocator"] * 4) == base
    assert _codes(KCConfig(seed=12), ["honest"] * 4) != base


# --- Invariant 2: simultaneity ----------------------------------------------

class SpyAgent(KCAgent):
    """Honest agent that logs when it is asked to act and what it saw."""

    def __init__(self, agent_id, events):
        super().__init__(agent_id)
        self.events = events
        self.observations = []

    def send_messages(self, obs):
        self.events.append(("message_act", self.agent_id, obs.round))
        self.observations.append(obs)
        return MessageAction(sends={j: obs.my_digit for j in range(obs.n_agents) if j != self.agent_id})

    def make_guess(self, obs):
        self.events.append(("guess_act", self.agent_id, obs.round))
        self.observations.append(obs)
        guess = [obs.received.get(j) or 0 for j in range(obs.n_agents)]
        guess[self.agent_id] = obs.my_digit
        return GuessAction(guess=tuple(guess))


def test_all_observations_built_before_any_action_in_each_phase(monkeypatch):
    events = []
    real_msg, real_guess = env_mod.build_message_obs, env_mod.build_guess_obs

    def spy_msg(cfg, round_no, agent_id, *a, **kw):
        events.append(("message_obs", agent_id, round_no))
        return real_msg(cfg, round_no, agent_id, *a, **kw)

    def spy_guess(cfg, round_no, agent_id, *a, **kw):
        events.append(("guess_obs", agent_id, round_no))
        return real_guess(cfg, round_no, agent_id, *a, **kw)

    monkeypatch.setattr(env_mod, "build_message_obs", spy_msg)
    monkeypatch.setattr(env_mod, "build_guess_obs", spy_guess)
    cfg = KCConfig(max_rounds=3)
    KCEnvironment(cfg, [SpyAgent(i, events) for i in range(4)], "spy").run()

    order = ["message_obs", "message_act", "guess_obs", "guess_act"]
    for rnd in (1, 2, 3):
        kinds = [k for k, _, r in events if r == rnd]
        # Each phase-step is a contiguous block of 4, in this order.
        assert kinds == [k for k in order for _ in range(4)]


# --- Invariant 3: firewall (spy view) ---------------------------------------

def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


@pytest.mark.parametrize("info", ["no_memory", "private_memory", "public_reputation"])
def test_spy_never_sees_hidden_information(info):
    events = []
    cfg = KCConfig(info_condition=info, max_rounds=4, seed=5)
    spy = SpyAgent(0, events)
    agents = [spy] + _lineup("liar", "hoarder", "excluder", start=1)
    log = KCEnvironment(cfg, agents, "firewall").run()
    codes = {r.round: r.code for r in log.rounds}
    allowed_history_keys = {"round", "code", "sent", "received", "my_guess", "solved",
                            "points", "n_solvers", "bonus"}

    # The spy is asked message, guess, message, guess, ... so the true round
    # comes from call order (obs.round is hidden under no_memory).
    for idx, obs in enumerate(spy.observations):
        round_no = idx // 2 + 1
        assert obs.phase == ("message" if idx % 2 == 0 else "guess")
        d = obs.to_dict()
        assert "max_rounds" not in set(_all_keys(d))
        assert obs.my_digit == codes[round_no][0]
        assert obs.my_position == obs.agent_id == 0
        if obs.phase == "message":
            assert obs.received is None
        else:
            # Only what was sent TO the spy this round.
            rnd = log.rounds[round_no - 1]
            assert obs.received == {j: rnd.message_actions[j].sends[0] for j in (1, 2, 3)}
        if info == "no_memory":
            assert obs.round is None
            assert obs.history == [] and obs.reputation is None
            continue
        assert obs.round == round_no
        assert [h["round"] for h in obs.history] == list(range(1, round_no))
        for h in obs.history:
            assert set(h) == allowed_history_keys
            past = log.rounds[h["round"] - 1]
            assert h["code"] == list(past.code)  # revealed code is fine after the round
            assert h["sent"] == past.message_actions[0].sends
            assert h["received"] == {j: past.message_actions[j].sends[0] for j in (1, 2, 3)}
            assert h["points"] == past.points[0]
            assert isinstance(h["solved"], bool)
        if info == "private_memory":
            assert obs.reputation is None
        else:
            assert set(obs.reputation) == {0, 1, 2, 3}


# --- Log round-trip ----------------------------------------------------------

def test_log_round_trip(tmp_path):
    cfg = KCConfig(max_rounds=3, info_condition="public_reputation", seed=2)
    log = KCEnvironment(cfg, _lineup("honest", "liar", "grudger", "excluder"), "rt",
                        run_parameters={"note": "x"}).run()
    path = log.write_jsonl(tmp_path / "g.jsonl")
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [line["record"] for line in lines] == ["meta", "round", "round", "round", "end"]
    assert lines == json.loads(json.dumps(log.records()))  # file == in-memory records

    game = load_game(path)
    meta, rounds, end = game["meta"], game["rounds"], game["end"]
    assert meta["game"] == "knowledge_commons" and meta["schema_version"] == 2
    assert meta["config"] == cfg.to_dict() and meta["seed"] == 2 and meta["condition"] == "rt"
    assert meta["run_parameters"] == {"note": "x"}
    assert [a["policy"] for a in meta["agents"]] == ["honest", "liar", "grudger", "excluder"]
    for rec, rr in zip(rounds, log.rounds):
        assert rec["round"] == rr.round
        assert tuple(rec["code"]) == rr.code
        assert rec["sends"] == {i: a.sends for i, a in rr.message_actions.items()}
        assert rec["guesses"] == {i: list(a.guess) for i, a in rr.guess_actions.items()}
        assert rec["solved"] == rr.solved and rec["points"] == rr.points
        assert (rec["n_solvers"], rec["bonus"]) == (rr.n_solvers, rr.bonus)
        assert set(rec["observations"]["message"]) == {0, 1, 2, 3}
        assert rec["actions"]["guess"][0]["parse_status"] == "scripted"
    assert end["totals"] == log.totals()
    assert end["utilities"] == pytest.approx(log.utilities())


# --- Invariant 5: scoring as logged ------------------------------------------

def test_logged_points_and_utilities_match_scoring(tmp_path):
    cfg = KCConfig(alpha=1.0, seed=9)
    log = KCEnvironment(cfg, _lineup("liar", "excluder", "honest", "reciprocator"), "s").run()
    game = load_game(log.write_jsonl(tmp_path / "s.jsonl"))
    totals = {i: 0.0 for i in range(4)}
    for rec in game["rounds"]:
        pts, n, bonus = round_points(rec["solved"], cfg)
        assert rec["points"] == pts and rec["n_solvers"] == n and rec["bonus"] == bonus
        for i, p in pts.items():
            totals[i] += p
    assert game["end"]["totals"] == pytest.approx(totals)
    # Logged utilities are rounded to 2 decimals.
    assert game["end"]["utilities"] == pytest.approx(utilities(totals, 1.0), abs=0.005)


# --- Sanitizing edge cases ---------------------------------------------------

class SloppyAgent(KCAgent):
    def send_messages(self, obs):
        # sends to itself, skips agent 2, sends an out-of-range digit to 3
        return MessageAction(sends={self.agent_id: 1, 1: obs.my_digit, 3: 12})

    def make_guess(self, obs):
        return GuessAction(guess=(obs.my_digit, 99))  # too short and out of range


def test_environment_sanitizes_bad_scripted_actions():
    cfg = KCConfig(max_rounds=1)
    log = KCEnvironment(cfg, [SloppyAgent(0)] + _lineup("honest", "honest", "honest", start=1),
                        "sloppy", codes=[(4, 5, 6, 7)]).run()
    r = log.rounds[0]
    assert r.message_actions[0].sends == {1: 4, 2: None, 3: None}
    assert r.guess_actions[0].guess == (4, 0, 0, 0)


def test_codes_override_must_cover_rounds():
    with pytest.raises(ValueError):
        KCEnvironment(KCConfig(max_rounds=2), _lineup(*["honest"] * 4), "x", codes=[(1, 2, 3, 4)])
    with pytest.raises(ValueError):
        KCEnvironment(KCConfig(), _lineup("honest", "honest"), "x")  # wrong agent count


def test_kc_game_log_is_exported():
    assert KCGameLog


# --- No-memory round hiding ---------------------------------------------------

@pytest.mark.parametrize("policy", ["honest", "hoarder", "liar", "reciprocator", "grudger", "excluder"])
def test_no_memory_hides_round_and_scripted_agents_still_play(policy, tmp_path):
    cfg = KCConfig(info_condition="no_memory", max_rounds=3, seed=3)
    log = KCEnvironment(cfg, _lineup(policy, "honest", "liar", "reciprocator"), "nm").run()
    assert len(log.rounds) == 3
    game = load_game(log.write_jsonl(tmp_path / "nm.jsonl"))
    for rec in game["rounds"]:
        for phase in ("message", "guess"):
            assert all(o["round"] is None for o in rec["observations"][phase].values())


def test_rounds_visible_outside_no_memory():
    cfg = KCConfig(info_condition="private_memory", max_rounds=2)
    log = KCEnvironment(cfg, _lineup(*["honest"] * 4), "pm").run()
    assert [obs[0].round for obs in log.message_obs] == [1, 2]


# --- Logged data is isolated from agents ---------------------------------------

class HonestHoarder(KCAgent):
    """Honest agent that keeps every observation and action it handles and
    vandalizes them later, to prove the log holds its own copies."""

    def __init__(self, agent_id, vandalize):
        super().__init__(agent_id)
        self.vandalize = vandalize
        self.kept = []

    def describe(self):
        return {"id": self.agent_id, "type": "scripted", "policy": "honest"}

    def _mess_up(self):
        for obs, act in self.kept:
            if obs.received is not None:
                obs.received.clear()
                obs.received[99] = 9
            for h in obs.history:
                if "received" in h:
                    h["code"] = [9, 9, 9, 9]
                    h["received"].clear()
            obs.history.append({"round": -1})
            if obs.reputation is not None:
                for r in obs.reputation.values():
                    r["lie"] = 42.0
            if isinstance(act, MessageAction):
                act.sends.clear()
                act.sends[1] = 0
            else:
                act.guess = (9, 9, 9, 9)
            act.usage["input_tokens"] = 10**6

    def send_messages(self, obs):
        if self.vandalize:
            self._mess_up()  # mid-game: mutate earlier rounds' objects
        act = MessageAction(sends={j: obs.my_digit for j in range(obs.n_agents) if j != self.agent_id})
        self.kept.append((obs, act))
        return act

    def make_guess(self, obs):
        guess = [obs.received.get(j) or 0 for j in range(obs.n_agents)]
        guess[self.agent_id] = obs.my_digit
        act = GuessAction(guess=tuple(guess))
        self.kept.append((obs, act))
        return act


def test_mutating_returned_observations_and_actions_does_not_change_log(tmp_path):
    cfg = KCConfig(info_condition="public_reputation", max_rounds=4, seed=8)
    clean = KCEnvironment(cfg, [HonestHoarder(0, False)] + _lineup("liar", "grudger", "excluder", start=1),
                          "iso").run().write_jsonl(tmp_path / "clean.jsonl")

    vandal = HonestHoarder(0, True)
    log = KCEnvironment(cfg, [vandal] + _lineup("liar", "grudger", "excluder", start=1), "iso").run()
    before = log.write_jsonl(tmp_path / "vandal_before.jsonl").read_text()
    vandal._mess_up()  # after the game: mutate everything it was ever handed
    after = log.write_jsonl(tmp_path / "vandal_after.jsonl").read_text()

    assert before == after
    assert after == clean.read_text()
