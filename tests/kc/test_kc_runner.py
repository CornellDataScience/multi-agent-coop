"""Runner, conditions, and CLI. Only --model mock or injected chat_fn; no network."""
import json
from types import SimpleNamespace as NS

import pytest

from src.knowledge_commons.agents.mock import KCMockBackend, mock_responder
from src.knowledge_commons.agents.parsing import parse_guess_output, parse_message_output
from src.knowledge_commons.configs import KC_CONDITIONS, get_condition
from src.knowledge_commons.log import load_game
from src.knowledge_commons.metrics import summarize_game
from src.knowledge_commons.runner import run_condition
from src.main import main

EXPECTED = {"kc_all_honest", "kc_all_hoarder", "kc_reciprocators_vs_liar", "kc_mixed_scripted",
            "kc_llm", "kc_probe_honest", "kc_probe_recip_liar", "kc_probe_grudgers"}


def test_conditions_defined():
    assert set(KC_CONDITIONS) == EXPECTED
    llm = get_condition("kc_llm")
    assert [s["type"] for s in llm.agent_specs] == ["llm"] * 4
    assert llm.agent_specs[0]["model"] == "claude-haiku-5-5"
    probe = get_condition("kc_probe_recip_liar")
    assert [s.get("policy", s["type"]) for s in probe.agent_specs] == ["llm", "reciprocator", "reciprocator", "liar"]
    assert [s.get("policy") for s in get_condition("kc_probe_grudgers").agent_specs[1:]] == ["grudger"] * 3
    with pytest.raises(KeyError):
        get_condition("nope")


def test_scripted_run_writes_one_log_per_seed(tmp_path):
    res = run_condition(get_condition("kc_all_honest"), tmp_path, seeds=[0, 1, 2])
    assert not res.aborted and res.calls == 0
    assert [p.name for p in res.paths] == [f"kc_all_honest_scripted_a0_private_memory_seed{s}.jsonl"
                                           for s in range(3)]
    for p in res.paths:
        assert summarize_game(p)["game"]["information_flow"] == 1.0


def test_mock_llm_run_is_deterministic_and_logged(tmp_path):
    a = run_condition(get_condition("kc_llm"), tmp_path / "a", model="mock", seeds=[0, 1])
    b = run_condition(get_condition("kc_llm"), tmp_path / "b", model="mock", seeds=[0, 1])
    assert len(a.paths) == 2 and not a.aborted
    assert a.paths[0].name == "kc_llm_mock_a0_private_memory_neutral_seed0.jsonl"
    assert [p.read_text() for p in a.paths] == [p.read_text() for p in b.paths]
    game = load_game(a.paths[0])
    assert game["meta"]["agents"][0] == {"id": 0, "type": "mock", "model": "mock", "prompt_variant": "neutral"}
    assert game["meta"]["run_parameters"]["model"] == "mock"
    statuses = {act["parse_status"] for r in game["rounds"] for ph in ("message", "guess")
                for act in r["actions"][ph].values()}
    assert statuses <= {"ok", "retry_ok", "fallback"} and "ok" in statuses
    # Calls inferred from the logs match the runner's live counter.
    assert sum(summarize_game(p)["game"]["calls"] for p in a.paths) == a.calls
    assert summarize_game(a.paths[0])["game"]["input_tokens"] > 0  # mock reports approximate usage


def test_overrides_and_filenames_never_collide(tmp_path):
    cond = get_condition("kc_llm")
    p1 = run_condition(cond, tmp_path, model="mock", seeds=[3], alpha=1.5, info="public_reputation",
                       rounds=3, n_agents=5).paths[0]
    p2 = run_condition(cond, tmp_path, model="mock", seeds=[3], alpha=0.0, info="no_memory").paths[0]
    assert p1 != p2
    assert p1.name == "kc_llm_mock_a1.5_public_reputation_neutral_n5_r3_seed3.jsonl"
    meta = load_game(p1)["meta"]
    assert meta["config"]["alpha"] == 1.5 and meta["config"]["info_condition"] == "public_reputation"
    assert meta["config"]["max_rounds"] == 3 and meta["config"]["n_agents"] == 5
    assert len(load_game(p1)["rounds"]) == 3


def test_probe_lineup_keeps_one_llm_when_resized(tmp_path):
    p = run_condition(get_condition("kc_probe_recip_liar"), tmp_path, model="mock", seeds=[0], n_agents=6).paths[0]
    agents = load_game(p)["meta"]["agents"]
    assert [a.get("policy", a["type"]) for a in agents] == [
        "mock", "reciprocator", "reciprocator", "liar", "reciprocator", "reciprocator"]


def test_same_seed_same_codes_across_conditions(tmp_path):
    a = run_condition(get_condition("kc_all_honest"), tmp_path, seeds=[7]).paths[0]
    b = run_condition(get_condition("kc_llm"), tmp_path, model="mock", seeds=[7], alpha=1.0).paths[0]
    assert [r["code"] for r in load_game(a)["rounds"]] == [r["code"] for r in load_game(b)["rounds"]]


def test_max_calls_stops_cleanly(tmp_path):
    res = run_condition(get_condition("kc_llm"), tmp_path, model="mock", seeds=[0, 1], max_calls=10)
    assert res.aborted and res.calls == 10 and res.paths == []
    assert list(tmp_path.glob("*.jsonl")) == []  # partial game not written
    # Budget for exactly one game: first game written, second aborted.
    one = run_condition(get_condition("kc_llm"), tmp_path / "one", model="mock", seeds=[0])
    res = run_condition(get_condition("kc_llm"), tmp_path / "two", model="mock", seeds=[0, 1],
                        max_calls=one.calls + 1)
    assert res.aborted and len(res.paths) == 1


def test_claude_path_uses_injected_chat_fn(tmp_path):
    seen = []

    def chat_fn(**kw):
        seen.append(kw)
        prompt = kw["messages"][0]["content"]
        text = (mock_responder(0)(kw["system"], prompt))
        return NS(content=[NS(type="text", text=text)], stop_reason="end_turn", model=kw["model"],
                  usage=NS(input_tokens=500, output_tokens=20))

    res = run_condition(get_condition("kc_probe_honest"), tmp_path, seeds=[0], rounds=2, effort="low",
                        chat_fn=chat_fn)
    assert seen and all(kw["model"] == "claude-haiku-5-5" for kw in seen)
    assert all(kw["output_config"] == {"effort": "low"} for kw in seen)
    meta = load_game(res.paths[0])["meta"]
    assert meta["agents"][0]["type"] == "claude"
    assert res.paths[0].name == "kc_probe_honest_claude-haiku-5-5_a0_private_memory_neutral_low_r2_seed0.jsonl"
    assert summarize_game(res.paths[0])["game"]["input_tokens"] == 500 * len(seen)


def test_mock_responder_outputs_parse():
    from src.knowledge_commons.agents.prompts import build_prompts
    from src.knowledge_commons.config import KCConfig
    from src.knowledge_commons.observation import build_guess_obs, build_message_obs

    cfg = KCConfig()
    respond = mock_responder(1)
    ok = 0
    for _ in range(50):
        s, p = build_prompts(build_message_obs(cfg, 1, 2, (1, 2, 3, 4), []))
        try:
            sends = parse_message_output(respond(s, p), 2, 4)
            ok += 1
            assert set(sends) == {0, 1, 3}
        except ValueError:
            pass
    assert ok >= 40  # mostly valid, occasionally invalid on purpose
    s, p = build_prompts(build_guess_obs(cfg, 1, 2, (1, 2, 3, 4), [], {0: {2: 1}, 1: {2: None}, 3: {2: 9}}))
    guesses = []
    for _ in range(20):
        try:
            guesses.append(parse_guess_output(respond(s, p), 4)[0])
        except ValueError:
            pass
    assert (1, 0, 3, 9) in guesses  # own digit + received digits, 0 for nothing
    assert KCMockBackend(responder=respond).model == "mock"


# --- CLI ---------------------------------------------------------------------

def test_cli_list(capsys):
    assert main(["kc", "list"]) == 0
    out = capsys.readouterr().out
    for name in EXPECTED:
        assert name in out


def test_cli_run_metrics_show(tmp_path, capsys):
    out_dir = tmp_path / "kc"
    assert main(["kc", "run", "kc_llm", "--model", "mock", "--seeds", "2", "--out", str(out_dir)]) == 0
    files = sorted(out_dir.glob("*.jsonl"))
    assert len(files) == 2
    capsys.readouterr()
    assert main(["kc", "metrics", str(out_dir)]) == 0
    agg = json.loads(capsys.readouterr().out)
    assert agg["n_games"] == 2 and "information_flow" in agg["game"]
    assert main(["kc", "metrics", str(files[0])]) == 0
    assert json.loads(capsys.readouterr().out)["game"]["rounds"] == 8
    assert main(["kc", "show", str(files[0]), "--raw"]) == 0
    assert "raw message" in capsys.readouterr().out


def test_cli_max_calls_and_bad_args(tmp_path, capsys):
    assert main(["kc", "run", "kc_llm", "--model", "mock", "--seeds", "2", "--max-calls", "10",
                 "--out", str(tmp_path), "--no-metrics"]) == 0
    assert "--max-calls" in capsys.readouterr().out
    assert list(tmp_path.glob("*.jsonl")) == []
    with pytest.raises(SystemExit):
        main(["kc", "run", "kc_llm", "--model", "mock", "--alpha", "-1", "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(["kc", "run", "kc_llm", "--info", "gossip"])
    assert main(["kc", "metrics", str(tmp_path / "empty")]) == 1
