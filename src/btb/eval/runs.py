"""Every backtest, lockbox opening and live scoring writes one "run".

results/                      (real data)      results/demo/  (synthetic data, same layout)
  ledger.csv                  one row per run, append-only, committed to git
  runs/<run_id>/
    run.json                  who, when, git commit, config hash, data hash, note
    predictions.parquet       one row per event: y_true, pred_baseline, pred_model, pred_shrunk
    metrics.json              headline + 95% range + per fold / sector / VIX bucket
    charts/*.html             standard charts (make charts RUN=<run_id>)

The ledger is how we track iterations: every attempt is a row, including the bad
ones, so the final report can say "we tried N things on dev before locking".
"""

from __future__ import annotations

import getpass
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from btb.config import RESULTS, ROOT, config_hash

LEDGER_COLUMNS = [
    "run_id", "created_utc", "kind", "data_source", "name", "author", "git_sha", "git_dirty",
    "config_hash", "data_hash", "n_events", "n_weeks", "mae_baseline", "mae_model",
    "rel_improvement", "ci_low", "ci_high", "win_rate", "beats_shrinkage", "tripwire", "note",
]


def results_root(data_source: str) -> Path:
    """real -> results/, synthetic -> results/demo/ (written by `make demo`),
    fixture -> fixtures/demo_results/results/ (a frozen sample run, always present)."""
    if data_source == "real":
        return RESULTS
    if data_source == "fixture":
        return ROOT / "fixtures" / "demo_results" / "results"
    return RESULTS / "demo"


def git_info() -> tuple[str, bool]:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                                    capture_output=True, text=True).stdout.strip())
        return sha, dirty
    except Exception:
        return "nogit", True


def new_run_id(name: str) -> str:
    return f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}_{name}"


def write_run(*, name: str, kind: str, data_source: str, predictions: pd.DataFrame, metrics: dict,
              data_hash: str, note: str = "", run_id: str | None = None) -> Path:
    root = results_root(data_source)
    run_id = run_id or new_run_id(name)
    out = root / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    sha, dirty = git_info()

    meta = {
        "run_id": run_id, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind, "data_source": data_source, "name": name, "author": getpass.getuser(),
        "git_sha": sha, "git_dirty": dirty, "config_hash": config_hash(), "data_hash": data_hash,
        "note": note,
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2))
    predictions.to_parquet(out / "predictions.parquet", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float))

    head, ci = metrics["overall"], metrics.get("bootstrap_week", {})
    row = {
        **{k: meta[k] for k in ("run_id", "created_utc", "kind", "data_source", "name", "author",
                                 "git_sha", "git_dirty", "config_hash", "data_hash", "note")},
        "n_events": head["n_events"], "n_weeks": head["n_weeks"], "mae_baseline": round(head["mae_baseline"], 4),
        "mae_model": round(head["mae_model"], 4), "rel_improvement": round(head["rel_improvement"], 4),
        "ci_low": round(ci.get("ci_low", float("nan")), 4), "ci_high": round(ci.get("ci_high", float("nan")), 4),
        "win_rate": round(head["win_rate"], 4),
        "beats_shrinkage": metrics.get("shrinkage", {}).get("model_beats_shrunk"),
        "tripwire": metrics.get("tripwire", False),
    }
    ledger = root / "ledger.csv"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row], columns=LEDGER_COLUMNS).to_csv(ledger, mode="a", header=not ledger.exists(), index=False)
    return out


def read_ledger(data_source: str = "real") -> pd.DataFrame:
    p = results_root(data_source) / "ledger.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=LEDGER_COLUMNS)


def load_run(run_id: str, data_source: str = "real") -> tuple[dict, pd.DataFrame, dict]:
    d = results_root(data_source) / "runs" / run_id
    return (json.loads((d / "run.json").read_text()), pd.read_parquet(d / "predictions.parquet"),
            json.loads((d / "metrics.json").read_text()))


def latest_run(kind: str, data_source: str = "real") -> str | None:
    led = read_ledger(data_source)
    led = led[led["kind"] == kind]
    return None if led.empty else str(led.iloc[-1]["run_id"])
