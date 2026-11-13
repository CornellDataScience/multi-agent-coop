"""Metrics are computed from saved JSONL only. Expected values are worked out
by hand in the comments."""
import pytest

from src.knowledge_commons.agents.base import KCAgent
from src.knowledge_commons.agents.scripted import make_scripted
from src.knowledge_commons.config import KCConfig
from src.knowledge_commons.environment import KCEnvironment
from src.knowledge_commons.events import GuessAction, MessageAction
from src.knowledge_commons.metrics import aggregate, bootstrap_ci, summarize_game
from src.knowledge_commons.replay import format_game


def _write(tmp_path, cfg, agents, codes, name="g"):
    return KCEnvironment(cfg, agents, name, codes=codes).run().write_jsonl(tmp_path / f"{name}.jsonl")


# --- Golden game 1: [honest x3, hoarder], codes (1,2,3,4), (5,6,7,8) --------

def test_golden_game_metrics(tmp_path):
    cfg = KCConfig(alpha=0.5, max_rounds=2)
    agents = [make_scripted(n, i) for i, n in enumerate(["honest", "honest", "honest", "hoarder"])]
    m = summarize_game(_write(tmp_path, cfg, agents, [(1, 2, 3, 4), (5, 6, 7, 8)]))
    g, a = m["game"], m["agents"]
    # 4 senders * 3 recipients * 2 rounds = 24 dyad-rounds.
    # Honest: 3 senders * 3 * 2 = 18 truthful. Hoarder: 3 * 2 = 6 withheld.
    assert g["dyad_rounds"] == 24
    assert (g["truthful"], g["withheld"], g["lie"]) == (18, 6, 0)
    assert g["information_flow"] == pytest.approx(18 / 24)  # 0.75
    assert g["truthful_share"] == pytest.approx(0.75) and g["withheld_share"] == pytest.approx(0.25)
    assert g["flow_by_round"] == [pytest.approx(0.75)] * 2
    assert g["first_half_flow"] == g["second_half_flow"] == pytest.approx(0.75)
    assert g["bonus_rate"] == 0.0
    assert g["mean_n_solvers"] == 1.0                 # only the hoarder solves
    assert g["welfare"] == 20                         # 0 + 0 + 0 + 20
    assert g["efficiency"] == pytest.approx(20 / 160)  # 4 * 20 * 2 rounds = 160
    assert a[3]["withhold_rate"] == 1.0 and a[3]["truthful_rate"] == 0.0
    for i in range(3):
        assert a[i]["truthful_rate"] == 1.0
        assert a[i]["solve_rate"] == 0.0 and a[i]["P"] == 0
        assert a[i]["U"] == pytest.approx(-20 / 6)    # 0 - 0.5 * 20/3
        assert a[i]["rank"] == 2
    assert a[3]["solve_rate"] == 1.0 and a[3]["P"] == 20 and a[3]["U"] == 20.0 and a[3]["rank"] == 1
    assert a[3]["calibration"] is None
    # Scripted actions make no model calls.
    assert g["model_actions"] == 0 and g["calls"] == 0
    assert g["retry_rate"] is None and g["fallback_rate"] is None


# --- Reciprocity / forgiveness / uptake on a 4-round log ---------------------
#
# Lineup: 0 reciprocator, 1 liar, 2 grudger, 3 honest.
# Codes: (1,2,3,4), (5,6,7,8), (2,4,6,8), (3,5,7,9). Liar's digit is never 9,
# so its false digit is never 0 and can't match a 0 default by accident.
#
# Sends:
#   R1: 0, 2, 3 truthful to all; 1 lies to all.
#   R2-R4: 0 withholds from 1 (1 lied last round), truthful to 2, 3.
#          2 withholds from 1 forever (1 lied in R1), truthful to 0, 3.
#          3 truthful to all. 1 lies to all.
# Dyads: 48. Truthful: R1 9, R2-R4 7 each -> 30. Lies: 12. Withheld: 6.

@pytest.fixture
def recip_path(tmp_path):
    cfg = KCConfig(alpha=0.5, max_rounds=4)
    agents = [make_scripted(n, i) for i, n in enumerate(["reciprocator", "liar", "grudger", "honest"])]
    return _write(tmp_path, cfg, agents, [(1, 2, 3, 4), (5, 6, 7, 8), (2, 4, 6, 8), (3, 5, 7, 9)], "recip")


def test_counts_and_targeting(recip_path):
    m = summarize_game(recip_path)
    g, a = m["game"], m["agents"]
    assert (g["dyad_rounds"], g["truthful"], g["lie"], g["withheld"]) == (48, 30, 12, 6)
    assert g["information_flow"] == pytest.approx(30 / 48)
    # 9/12 in R1, then 7/12; halves are rounds 1-2 vs 3-4.
    assert g["flow_by_round"] == [pytest.approx(x) for x in (9 / 12, 7 / 12, 7 / 12, 7 / 12)]
    assert g["first_half_flow"] == pytest.approx(16 / 24)
    assert g["second_half_flow"] == pytest.approx(14 / 24)
    assert a[1]["lie_rate"] == 1.0
    # Reciprocator: 9 truthful + 3 withheld of 12.
    assert a[0]["truthful_rate"] == pytest.approx(9 / 12) and a[0]["withhold_rate"] == pytest.approx(3 / 12)
    # Targeted: truth to some and not others in R2-R4 -> 3 of 4 rounds.
    assert a[0]["targeted_rounds"] == pytest.approx(0.75)
    assert a[2]["targeted_rounds"] == pytest.approx(0.75)
    assert a[3]["targeted_rounds"] == 0.0 and a[1]["targeted_rounds"] == 0.0


def test_reciprocity(recip_path):
    a = summarize_game(recip_path)["agents"]
    # Agent 0, t = 2..4, j in {1,2,3}:
    #   j = 2, 3 were truthful to 0 at t-1 (6 cases); 0 was truthful to them 6/6 -> 1.0
    #   j = 1 never truthful (3 cases); 0 was truthful to 1 0/3 -> 0.0
    assert a[0]["reciprocity"] == pytest.approx(1.0 - 0.0)
    assert a[2]["reciprocity"] == pytest.approx(1.0)  # grudger: same pattern
    assert a[3]["reciprocity"] == pytest.approx(0.0)  # honest: 1.0 - 1.0
    # Liar: never truthful under either condition -> 0.0 - 0.0
    assert a[1]["reciprocity"] == pytest.approx(0.0)


def test_forgiveness_lag(recip_path):
    a = summarize_game(recip_path)["agents"]
    # Liar lies to everyone in rounds 1-4: 4 lie events per victim.
    # Honest (3) sends the liar the truth the next round: lags 1, 1, 1; the R4
    # lie has no later round -> censored.
    assert a[3]["forgiveness_lag"] == {"mean": 1.0, "n_events": 4, "n_censored": 1}
    # Reciprocator and grudger never send the liar the truth again.
    assert a[0]["forgiveness_lag"] == {"mean": None, "n_events": 4, "n_censored": 4}
    assert a[2]["forgiveness_lag"] == {"mean": None, "n_events": 4, "n_censored": 4}
    # Nobody lies to the liar.
    assert a[1]["forgiveness_lag"] == {"mean": None, "n_events": 0, "n_censored": 0}


def test_uptake_splits_by_prior_liars(recip_path):
    a = summarize_game(recip_path)["agents"]
    # Reciprocator trusts everything: 12 non-null digits received, all used.
    # 3 of them (liar, R2-R4) come from a sender who lied before.
    assert a[0]["uptake"] == {"overall": 1.0, "from_prior_liars": 1.0, "from_others": 1.0,
                              "n_from_prior_liars": 3, "n_from_others": 9}
    # Grudger uses the liar's R1 digit (no prior lie yet) but ignores it in
    # R2-R4: 9 of 12 used overall, 0 of 3 from prior liars.
    assert a[2]["uptake"]["overall"] == pytest.approx(9 / 12)
    assert a[2]["uptake"]["from_prior_liars"] == 0.0
    assert a[2]["uptake"]["from_others"] == 1.0


def test_solves_points_and_rank(recip_path):
    m = summarize_game(recip_path)
    a, g = m["agents"], m["game"]
    # Only the liar solves, in R1 (everyone told it the truth). n_solvers 1 < 3.
    assert a[1]["P"] == 10 and a[1]["solve_rate"] == 0.25
    assert g["bonus_rate"] == 0.0 and g["mean_n_solvers"] == 0.25
    assert a[1]["U"] == 10.0 and a[1]["rank"] == 1
    assert a[0]["U"] == pytest.approx(0 - 0.5 * 10 / 3)


# --- Forgiveness with a longer lag, plus calibration and reliability ---------

class TableAgent(KCAgent):
    """Sends from a per-round table; reports a fixed parse status/usage so
    the reliability metrics can be checked."""

    def __init__(self, agent_id, table, status="ok", usage=None, confidence=None):
        super().__init__(agent_id)
        self.table, self.status, self.usage, self.confidence = table, status, usage or {}, confidence

    def send_messages(self, obs):
        return MessageAction(sends=self.table(obs), parse_status=self.status, usage=dict(self.usage))

    def make_guess(self, obs):
        g = [obs.received.get(j) or 0 for j in range(obs.n_agents)]
        g[self.agent_id] = obs.my_digit
        return GuessAction(guess=tuple(g), confidence=self.confidence, parse_status=self.status,
                           usage=dict(self.usage))


def test_forgiveness_lag_longer_and_calibration_and_reliability(tmp_path):
    cfg = KCConfig(n_agents=2, bonus_threshold=1, max_rounds=4)
    # Agent 0 sends 1 the truth only in round 4. Agent 1 lies in round 1 only.
    a0 = TableAgent(0, lambda o: {1: o.my_digit if o.round == 4 else None},
                    status="retry_ok", usage={"input_tokens": 100, "output_tokens": 10}, confidence=0.9)
    a1 = TableAgent(1, lambda o: {0: (o.my_digit + 1) % 10 if o.round == 1 else o.my_digit},
                    status="fallback", usage={"input_tokens": 50, "output_tokens": 5})
    m = summarize_game(_write(tmp_path, cfg, [a0, a1], [(1, 2)] * 4, "lag"))
    # Lie at t=1, agent 0's next truthful send to 1 is t=4 -> lag 3.
    assert m["agents"][0]["forgiveness_lag"] == {"mean": 3.0, "n_events": 1, "n_censored": 0}
    # Agent 0 says 0.9 every round; solved only when 1 told the truth (R2-R4):
    # Brier = ((0.9-0)^2 + 3 * (0.9-1)^2) / 4 = (0.81 + 0.03) / 4 = 0.21
    assert m["agents"][0]["calibration"] == pytest.approx(0.21)
    g = m["game"]
    # 2 agents * 2 phases * 4 rounds = 16 model actions: 8 retry_ok, 8 fallback.
    assert g["model_actions"] == 16
    assert g["retry_rate"] == 0.5 and g["fallback_rate"] == 0.5
    assert g["calls"] == 32  # each of these took 2 attempts
    assert g["input_tokens"] == 8 * 100 + 8 * 50 and g["output_tokens"] == 8 * 10 + 8 * 5
    assert g["input_tokens_per_call"] == pytest.approx(1200 / 32)


# --- Aggregation -------------------------------------------------------------

def test_bootstrap_ci_is_seeded_and_brackets_mean():
    vals = [0.1, 0.4, 0.5, 0.9, 0.3]
    lo, hi = bootstrap_ci(vals)
    assert (lo, hi) == bootstrap_ci(vals)  # seed 0 -> reproducible
    assert lo <= sum(vals) / len(vals) <= hi
    assert bootstrap_ci([0.7]) == (0.7, 0.7)
    assert bootstrap_ci([2.0, 2.0, 2.0]) == (2.0, 2.0)


def test_aggregate_over_games(tmp_path):
    cfg = KCConfig(max_rounds=2)
    paths = []
    for seed in range(3):
        agents = [make_scripted(n, i) for i, n in enumerate(["honest", "honest", "honest", "hoarder"])]
        c = KCConfig(**{**cfg.to_dict(), "seed": seed})
        paths.append(KCEnvironment(c, agents, "agg").run().write_jsonl(tmp_path / f"agg{seed}.jsonl"))
    agg = aggregate(paths)
    assert agg["n_games"] == 3
    flow = agg["game"]["information_flow"]
    assert flow["mean"] == pytest.approx(0.75) and flow["std"] == 0.0 and flow["n"] == 3
    assert flow["lo"] == pytest.approx(0.75) and flow["hi"] == pytest.approx(0.75)
    assert agg["by_label"]["hoarder"]["withhold_rate"]["mean"] == 1.0
    assert agg["by_label"]["honest"]["truthful_rate"]["n"] == 9  # 3 agents * 3 games


# --- Replay ------------------------------------------------------------------

def test_replay_shows_rounds_and_marks_lies(recip_path):
    text = format_game(recip_path)
    assert "round 1" in text and "round 4" in text
    assert "code 1 2 3 4" in text
    assert "LIE" in text and "--" in text  # a lie and a withheld send
    assert "raw" not in text
