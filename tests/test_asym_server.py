"""API endpoint tests with FastAPI's test client, including a full mock run
launched through POST /api/runs (the New Run path) and every download."""

import csv
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from asymbench import db
from asymbench.server import app

MOCK_CONFIG = {
    "name": "ui mock run",
    "test_model": "mock/strong",
    "counterparts": ["mock/weak", "control"],
    "tasks": ["sale", "claim"],
    "conditions": {"instruction": ["neutral"], "oversight": ["none"], "label": ["none"]},
    "seeds": {"start": 0, "count": 2},
    "judge_model": "mock/judge",
    "concurrency": 4,
    "budget_usd": 5,
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db.set_db_path(tmp_path / "server.db")
    monkeypatch.setenv("ASYMBENCH_RUNS_DIR", str(tmp_path / "runs"))
    with TestClient(app) as c:
        yield c
    db.set_db_path(None)


def wait_done(client, run_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(0.1)
    raise TimeoutError("run did not finish")


def test_health_tasks_presets_models(client):
    assert client.get("/api/health").json()["ok"] is True
    tasks = client.get("/api/tasks").json()
    assert [t["id"] for t in tasks] == ["commons", "sale", "contract", "claim"]
    presets = client.get("/api/presets").json()
    assert "core" in presets and "label_sweep" in presets
    models = client.get("/api/models").json()
    assert models["keys"]["mock"] is True
    assert any(m["id"] == "mock/strong" for m in models["models"])
    # no API key ever appears in any response
    body = json.dumps(models)
    assert "sk-" not in body and "API_KEY" not in body


def test_estimate_endpoint(client):
    res = client.post("/api/estimate", json=MOCK_CONFIG)
    assert res.status_code == 200
    assert res.json()["episodes"] == 8
    bad = client.post("/api/estimate", json={**MOCK_CONFIG, "budget_usd": None})
    assert bad.status_code == 400 and "error" in bad.json()


def test_models_check(client):
    res = client.post("/api/models/check", json={"model_ids": ["mock/strong", "not-routable"]})
    out = res.json()["results"]
    assert out["mock/strong"]["available"] is True
    assert out["not-routable"]["available"] is False


def test_full_run_via_api_and_downloads(client, tmp_path):
    res = client.post("/api/runs", json=MOCK_CONFIG)
    assert res.status_code == 200, res.text
    run_id = res.json()["run_id"]

    runs = client.get("/api/runs").json()
    assert any(r["id"] == run_id for r in runs)

    run = wait_done(client, run_id)
    assert run["status"] == "done"
    assert run["aggregates"]["overall"]["recognition_gap"]["mean"] > 0
    assert run["aggregates"]["overall"]["attempt_shift"]["mean"] > 0
    assert run["aggregates"]["overall"]["post_recognition_change"]["mean"] > 0

    # episodes list + filters
    eps = client.get(f"/api/runs/{run_id}/episodes").json()
    assert eps["total"] == 8 and len(eps["items"]) == 8
    assert all("outcome_summary" in e for e in eps["items"])
    flagged = client.get(f"/api/runs/{run_id}/episodes?flags=attempts").json()
    assert 0 < flagged["total"] <= 8

    # single episode
    ep_id = eps["items"][0]["id"]
    ep = client.get(f"/api/episodes/{ep_id}").json()
    assert ep["turns"]["turns"] and ep["fields"]

    # ZIP download with expected contents
    z = client.get(f"/api/runs/{run_id}/download.zip")
    assert z.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    assert set(zf.namelist()) == {"config.json", "episodes.jsonl", "aggregates.json",
                                  "summary.csv", "README.txt"}
    inner = json.loads(zf.read("config.json"))
    assert inner["test_model"] == "mock/strong"
    rows = list(csv.DictReader(io.StringIO(zf.read("summary.csv").decode())))
    assert len(rows) == 8 and "attempt_events" in rows[0]

    # other downloads
    s = client.get(f"/api/runs/{run_id}/summary.csv")
    assert s.status_code == 200 and "episode_id" in s.text
    a = client.get(f"/api/runs/{run_id}/aggregates.json")
    assert a.status_code == 200 and "contrasts" in a.json()
    e = client.get(f"/api/episodes/{ep_id}/download.json")
    assert e.status_code == 200 and e.json()["id"] == ep_id
    h = client.get(f"/api/runs/{run_id}/handlabel.csv?frac=0.5&seed=0")
    assert h.status_code == 200
    hrows = list(csv.DictReader(io.StringIO(h.text)))
    assert len(hrows) == 4 and "transcript" in hrows[0] and "human_events" in hrows[0]

    # leaderboard: mock runs excluded by default, included on demand
    assert client.get("/api/leaderboard").json() == []
    lb = client.get("/api/leaderboard?include_mock=true").json()
    assert lb and lb[0]["model"] == "mock/strong" and lb[0]["per_task"]
    lcsv = client.get("/api/leaderboard.csv?include_mock=true")
    assert "attempt_shift" in lcsv.text

    # model usage
    u = client.get("/api/models/usage?id=mock/strong").json()
    assert u["episodes"] == 8 and u["as_test"]

    # recompute + rejudge endpoints
    assert client.post(f"/api/runs/{run_id}/recompute").json()["ok"] is True
    assert client.post(f"/api/runs/{run_id}/rejudge",
                       json={"judge_model": "mock/judge"}).json()["ok"] is True
    wait_done(client, run_id)

    # cancel on a finished run still responds; resume requires non-running
    assert client.post(f"/api/runs/{run_id}/cancel").json()["ok"] is True

    # delete
    assert client.delete(f"/api/runs/{run_id}").json()["ok"] is True
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_about_and_static(client):
    about = client.get("/api/about").json()
    assert len(about["tasks"]) == 4 and about["defaults"]["test_model"]
    index = client.get("/")
    assert index.status_code == 200 and "Asymmetry Bench" in index.text
    js = client.get("/static/app.js")
    assert js.status_code == 200
    css = client.get("/static/styles.css")
    assert css.status_code == 200


def test_404s(client):
    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/episodes/nope").status_code == 404
    assert client.post("/api/runs/nope/cancel").status_code == 404
