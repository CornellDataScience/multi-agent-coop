"""SQLite storage (WAL, stdlib sqlite3, no ORM). Results are append-only: a
finished run is only touched by re-judge / recompute, which keep prior outputs
in a history key instead of overwriting them."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .settings import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, name TEXT, created_at TEXT, status TEXT,
  test_model TEXT, config_json TEXT, progress_json TEXT,
  cost_usd REAL DEFAULT 0, budget_usd REAL, aggregates_json TEXT,
  code_version TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
  id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
  task TEXT, seed INTEGER, counterpart_model TEXT, is_control INTEGER,
  condition_json TEXT, status TEXT, scenario_json TEXT, turns_json TEXT,
  outcome_json TEXT, metrics_json TEXT, events_json TEXT, fields_json TEXT,
  survey_json TEXT, detection_json TEXT, judge_json TEXT, judge_model TEXT,
  judge_failed INTEGER DEFAULT 0, excluded INTEGER DEFAULT 0,
  tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0,
  cost_anthropic REAL DEFAULT 0, cost_openrouter REAL DEFAULT 0,
  error TEXT, started_at TEXT, finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes_run ON episodes(run_id, task, counterpart_model);
CREATE INDEX IF NOT EXISTS idx_runs_test_model ON runs(test_model);
"""

_local = threading.local()
_override_path: Path | None = None  # tests point this at a temp file


def set_db_path(path: str | Path | None) -> None:
    global _override_path
    _override_path = Path(path) if path else None
    if hasattr(_local, "conn"):
        _local.conn.close()
        del _local.conn


def connect() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        path = _override_path or db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        _migrate(conn)
        _local.conn = conn
    return _local.conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations for databases created by earlier versions."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(episodes)")}
    for col in ("cost_anthropic", "cost_openrouter"):
        if col not in cols:
            conn.execute(f"ALTER TABLE episodes ADD COLUMN {col} REAL DEFAULT 0")
    conn.commit()


def _j(value) -> str | None:
    return None if value is None else json.dumps(value)


def _load(row: sqlite3.Row | None, json_fields: tuple) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for f in json_fields:
        key = f + "_json"
        if key in d:
            d[f] = json.loads(d.pop(key)) if d[key] else None
    return d


RUN_JSON = ("config", "progress", "aggregates")
EP_JSON = ("condition", "scenario", "turns", "outcome", "metrics", "events",
           "fields", "survey", "detection", "judge")


# ---------------------------------------------------------------- runs

def insert_run(run: dict) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO runs (id, name, created_at, status, test_model, config_json, "
        "progress_json, cost_usd, budget_usd, aggregates_json, code_version, error) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (run["id"], run.get("name"), run["created_at"], run["status"], run["test_model"],
         _j(run.get("config")), _j(run.get("progress")), run.get("cost_usd", 0.0),
         run.get("budget_usd"), _j(run.get("aggregates")), run.get("code_version"),
         run.get("error")))
    conn.commit()


def update_run(run_id: str, **fields) -> None:
    conn = connect()
    sets, vals = [], []
    for k, v in fields.items():
        if k in RUN_JSON:
            sets.append(f"{k}_json = ?")
            vals.append(_j(v))
        else:
            sets.append(f"{k} = ?")
            vals.append(v)
    vals.append(run_id)
    conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def run_cost_split(run_id: str) -> dict:
    """Live per-provider cost totals for a run, summed over its episodes."""
    row = connect().execute(
        "SELECT COALESCE(SUM(cost_anthropic), 0) a, COALESCE(SUM(cost_openrouter), 0) o "
        "FROM episodes WHERE run_id = ?", (run_id,)).fetchone()
    return {"anthropic": round(row["a"], 6), "openrouter": round(row["o"], 6)}


def add_run_cost(run_id: str, cost: float) -> float:
    conn = connect()
    conn.execute("UPDATE runs SET cost_usd = cost_usd + ? WHERE id = ?", (cost, run_id))
    conn.commit()
    row = conn.execute("SELECT cost_usd FROM runs WHERE id = ?", (run_id,)).fetchone()
    return row["cost_usd"] if row else 0.0


def get_run(run_id: str) -> dict | None:
    row = connect().execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return _load(row, RUN_JSON)


def list_runs(status: str | None = None, test_model: str | None = None,
              q: str | None = None) -> list[dict]:
    sql = "SELECT * FROM runs"
    conds, vals = [], []
    if status:
        conds.append("status = ?")
        vals.append(status)
    if test_model:
        conds.append("test_model = ?")
        vals.append(test_model)
    if q:
        conds.append("(name LIKE ? OR id LIKE ?)")
        vals += [f"%{q}%", f"%{q}%"]
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY created_at DESC"
    return [_load(r, RUN_JSON) for r in connect().execute(sql, vals)]


def delete_run(run_id: str) -> None:
    conn = connect()
    conn.execute("DELETE FROM episodes WHERE run_id = ?", (run_id,))
    conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
    conn.commit()


# ---------------------------------------------------------------- episodes

def insert_episode(ep: dict) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO episodes (id, run_id, task, seed, counterpart_model, is_control, "
        "condition_json, status, scenario_json, turns_json, outcome_json, metrics_json, "
        "events_json, fields_json, survey_json, detection_json, judge_json, judge_model, "
        "judge_failed, excluded, tokens_in, tokens_out, cost_usd, error, started_at, "
        "finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ep["id"], ep["run_id"], ep["task"], ep["seed"], ep["counterpart_model"],
         int(bool(ep["is_control"])), _j(ep.get("condition")), ep["status"],
         _j(ep.get("scenario")), _j(ep.get("turns")), _j(ep.get("outcome")),
         _j(ep.get("metrics")), _j(ep.get("events")), _j(ep.get("fields")),
         _j(ep.get("survey")), _j(ep.get("detection")), _j(ep.get("judge")),
         ep.get("judge_model"), int(bool(ep.get("judge_failed"))),
         int(bool(ep.get("excluded"))), ep.get("tokens_in", 0), ep.get("tokens_out", 0),
         ep.get("cost_usd", 0.0), ep.get("error"), ep.get("started_at"),
         ep.get("finished_at")))
    conn.commit()


def update_episode(ep_id: str, **fields) -> None:
    conn = connect()
    sets, vals = [], []
    for k, v in fields.items():
        if k in EP_JSON:
            sets.append(f"{k}_json = ?")
            vals.append(_j(v))
        elif k in ("is_control", "judge_failed", "excluded"):
            sets.append(f"{k} = ?")
            vals.append(int(bool(v)))
        else:
            sets.append(f"{k} = ?")
            vals.append(v)
    vals.append(ep_id)
    conn.execute(f"UPDATE episodes SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()


def get_episode(ep_id: str) -> dict | None:
    row = connect().execute("SELECT * FROM episodes WHERE id = ?", (ep_id,)).fetchone()
    return _load(row, EP_JSON)


_SUMMARY_COLS = ("id, run_id, task, seed, counterpart_model, is_control, condition_json, "
                 "status, fields_json, metrics_json, judge_failed, excluded, cost_usd, error, "
                 "judge_model, started_at, finished_at")


def list_episodes(run_id: str, task: str | None = None, counterpart: str | None = None,
                  condition: str | None = None, status: str | None = None,
                  limit: int = 100, offset: int = 0,
                  full: bool = False) -> tuple[int, list[dict]]:
    conds, vals = ["run_id = ?"], [run_id]
    if task:
        conds.append("task = ?")
        vals.append(task)
    if counterpart:
        conds.append("counterpart_model = ?")
        vals.append(counterpart)
    if condition:
        conds.append("condition_json = ?")
        vals.append(condition)
    if status:
        conds.append("status = ?")
        vals.append(status)
    where = " AND ".join(conds)
    conn = connect()
    total = conn.execute(f"SELECT COUNT(*) c FROM episodes WHERE {where}", vals).fetchone()["c"]
    cols = "*" if full else _SUMMARY_COLS
    rows = conn.execute(
        f"SELECT {cols} FROM episodes WHERE {where} ORDER BY task, seed, counterpart_model "
        f"LIMIT ? OFFSET ?", vals + [limit, offset]).fetchall()
    json_fields = EP_JSON if full else ("condition", "fields", "metrics")
    return total, [_load(r, json_fields) for r in rows]


def episodes_for_aggregation(run_id: str) -> list[dict]:
    """Light rows (no transcripts) with everything metrics.aggregate_episodes needs."""
    rows = connect().execute(
        f"SELECT {_SUMMARY_COLS} FROM episodes WHERE run_id = ?", (run_id,)).fetchall()
    return [_load(r, ("condition", "fields", "metrics")) for r in rows]


def episodes_for_leaderboard(include_mock: bool = False) -> list[dict]:
    """Done episodes of completed runs, annotated with test_model and has_mock."""
    conn = connect()
    runs = {r["id"]: _load(r, RUN_JSON) for r in conn.execute("SELECT * FROM runs")}
    out = []
    for row in conn.execute(
            f"SELECT {_SUMMARY_COLS} FROM episodes WHERE status = 'done'"):
        ep = _load(row, ("condition", "fields", "metrics"))
        run = runs.get(ep["run_id"])
        if not run or run["status"] not in ("done", "budget_stopped", "cancelled"):
            continue
        has_mock = bool((run.get("config") or {}).get("has_mock"))
        if has_mock and not include_mock:
            continue
        ep["test_model"] = run["test_model"]
        ep["has_mock"] = has_mock
        out.append(ep)
    return out


def model_usage(model_id: str) -> dict:
    conn = connect()
    as_test = [_load(r, RUN_JSON) for r in conn.execute(
        "SELECT * FROM runs WHERE test_model = ? ORDER BY created_at DESC", (model_id,))]
    cp_runs_rows = conn.execute(
        "SELECT DISTINCT run_id FROM episodes WHERE counterpart_model = ?", (model_id,)).fetchall()
    as_cp = [get_run(r["run_id"]) for r in cp_runs_rows]
    n_eps = conn.execute(
        "SELECT COUNT(*) c FROM episodes WHERE counterpart_model = ? OR "
        "run_id IN (SELECT id FROM runs WHERE test_model = ?)",
        (model_id, model_id)).fetchone()["c"]
    return {"as_test": as_test, "as_counterpart": [r for r in as_cp if r], "episodes": n_eps}


def measured_token_averages() -> dict:
    """Per (task, model) measured per-episode token averages from done episodes,
    used to refine cost estimates once real data exists."""
    conn = connect()
    out = {}
    rows = conn.execute(
        "SELECT e.task t, r.test_model m, AVG(e.tokens_in) ti, AVG(e.tokens_out) to_, "
        "AVG(e.cost_usd) c, COUNT(*) n FROM episodes e JOIN runs r ON e.run_id = r.id "
        "WHERE e.status = 'done' GROUP BY e.task, r.test_model").fetchall()
    for r in rows:
        out[(r["t"], r["m"])] = {"tokens_in": r["ti"], "tokens_out": r["to_"],
                                 "cost": r["c"], "n": r["n"]}
    return out
