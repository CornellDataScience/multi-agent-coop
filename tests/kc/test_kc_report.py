"""Report from mock-generated logs. No network: --model mock only."""
import importlib.util
import json
import sys

import pytest

from src.knowledge_commons.configs import get_condition
from src.knowledge_commons.report import CHART_FILES, build_report
from src.knowledge_commons.runner import run_condition
from src.main import main

HAS_MPL = importlib.util.find_spec("matplotlib") is not None


@pytest.fixture(scope="module")
def log_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("kc_logs")
    llm = get_condition("kc_llm")
    for alpha in (0.0, 1.0):
        run_condition(llm, root / "sweep", model="mock", seeds=[0, 1], alpha=alpha, rounds=4)
    for info in ("no_memory", "public_reputation"):
        run_condition(llm, root / "info", model="mock", seeds=[0], alpha=1.0, info=info, rounds=4)
    run_condition(get_condition("kc_reciprocators_vs_liar"), root / "e0", seeds=[0, 1], rounds=4)
    return [root / "sweep", root / "info", root / "e0"]


def test_data_json_has_documented_keys(log_dirs, tmp_path):
    data = build_report(log_dirs, tmp_path, charts=False)
    on_disk = json.loads((tmp_path / "data.json").read_text())
    assert on_disk == json.loads(json.dumps(data))
    assert set(on_disk) >= {"generated_at", "groups", "episodes", "cost"}
    keys = {(g["condition"], g["model"], g["alpha"], g["info_condition"]) for g in on_disk["groups"]}
    assert keys == {
        ("kc_llm", "mock", 0.0, "private_memory"), ("kc_llm", "mock", 1.0, "private_memory"),
        ("kc_llm", "mock", 1.0, "no_memory"), ("kc_llm", "mock", 1.0, "public_reputation"),
        ("kc_reciprocators_vs_liar", "scripted", 0.5, "private_memory"),
    }
    for g in on_disk["groups"]:
        assert g["n_games"] == (1 if g["info_condition"] != "private_memory" else 2)
        flow = g["metrics"]["information_flow"]
        assert set(flow) >= {"mean", "lo", "hi", "n"} and flow["lo"] <= flow["mean"] <= flow["hi"]
        assert len(g["flow_by_round"]) == 4
    scripted = next(g for g in on_disk["groups"] if g["model"] == "scripted")
    assert scripted["metrics"]["lie_share"]["mean"] == pytest.approx(0.25)
    assert "llm_truthful_rate" not in scripted["metrics"]  # no LLM agents in that group
    mock = next(g for g in on_disk["groups"] if g["model"] == "mock")
    assert mock["metrics"]["llm_truthful_rate"]["n"] == mock["n_games"]
    assert set(on_disk["cost"]) == {"calls", "input_tokens", "output_tokens"}
    assert on_disk["cost"]["calls"] > 0
    for e in on_disk["episodes"]:
        assert set(e) >= {"file", "round", "why"}


def test_episodes_found_in_scripted_games(log_dirs, tmp_path):
    data = build_report([log_dirs[2]], tmp_path, charts=False)
    whys = [e["why"] for e in data["episodes"]]
    # The liar lies in round 1 of every game; from round 2 all three
    # reciprocators withhold from it, so it is excluded by everyone.
    assert any(w.startswith("first lie") for w in whys)
    assert any("excluded by all others" in w and "agent 3" in w for w in whys)
    first_lie = next(e for e in data["episodes"] if e["why"].startswith("first lie"))
    assert first_lie["round"] == 1
    drop = [e for e in data["episodes"] if e["why"].startswith("largest drop")]
    assert drop and drop[0]["round"] == 2  # 9/12 -> 6/12


def test_results_md_lists_groups(log_dirs, tmp_path):
    build_report(log_dirs, tmp_path, charts=False)
    md = (tmp_path / "RESULTS.md").read_text()
    assert "| kc_llm | mock | 0 | private_memory |" in md
    assert "kc_reciprocators_vs_liar" in md and "Episodes worth reading" in md
    assert "Charts skipped" not in md  # charts=False is a choice, not a failure


def test_charts_skipped_gracefully_without_matplotlib(log_dirs, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib", None)  # import now raises ImportError
    data = build_report(log_dirs, tmp_path)
    assert data["charts"] == []
    assert not list(tmp_path.glob("*.png"))
    assert (tmp_path / "data.json").exists()
    assert "Charts skipped" in (tmp_path / "RESULTS.md").read_text()


@pytest.mark.skipif(not HAS_MPL, reason="viz extra not installed")
def test_charts_written_with_matplotlib(log_dirs, tmp_path):
    data = build_report(log_dirs, tmp_path)
    assert data["charts"] == list(CHART_FILES)
    for name in CHART_FILES:
        assert (tmp_path / name).stat().st_size > 1000


def test_cli_report(log_dirs, tmp_path, capsys):
    out = tmp_path / "report"
    assert main(["kc", "report", *map(str, log_dirs), "--out", str(out), "--no-charts"]) == 0
    assert (out / "data.json").exists() and (out / "RESULTS.md").exists()
    assert "5 group(s)" in capsys.readouterr().out
    assert main(["kc", "report", str(tmp_path / "nothing"), "--out", str(out)]) == 1
