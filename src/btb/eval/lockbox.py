"""Open the locked test set (Jan 2025 to Sep 2026). Meant to run exactly once.

    python -m btb.eval.lockbox --data real

Guard rails (honor system plus an audit trail, since nothing can stop someone
from computing a move by hand):
  1. Refuses if git has uncommitted changes, so the opened result is tied to a commit.
  2. Refuses if git HEAD is not tagged model-final.
  3. Refuses if results/lockbox/OPENED.json already exists. A rerun after a bug
     needs --rerun-reason, is written as a separate run, and BOTH get reported.
  4. Writes OPENED.json (commit it right away). The live model refuses to train
     until this file exists, which forces the order: lock model, open test, go live.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone

from btb.config import LOCKBOX_DIR, ROOT, config_hash, load
from btb.eval import backtest, metrics, runs, splits


def _tagged_model_final() -> bool:
    r = subprocess.run(["git", "tag", "--points-at", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return "model-final" in r.stdout.split()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", choices=["synthetic", "real"], default="real")
    ap.add_argument("--rerun-reason", default="")
    a = ap.parse_args(argv)

    marker = (LOCKBOX_DIR if a.data == "real" else runs.results_root(a.data) / "lockbox") / "OPENED.json"
    if a.data == "real":
        sha, dirty = runs.git_info()
        if dirty:
            raise SystemExit("Refusing: commit everything first so the result points at one exact commit.")
        if not _tagged_model_final():
            raise SystemExit("Refusing: tag the final model commit first (git tag model-final && git push --tags).")
    if marker.exists() and not a.rerun_reason:
        raise SystemExit(f"Lockbox already opened ({marker}). A rerun needs --rerun-reason and is reported next to the first.")

    cfg = load()
    ev = backtest.load_events(a.data, "lockbox")
    folds = splits.walk_forward(ev, "lockbox", cfg)
    splits.check_no_leak(ev, folds)
    pred = backtest.predict_folds(ev, folds, cfg)
    met = metrics.evaluate(pred, cfg)
    name = "lockbox" if not a.rerun_reason else "lockbox_rerun"
    out = runs.write_run(name=name, kind="lockbox", data_source=a.data, predictions=pred, metrics=met,
                         data_hash=backtest.data_hash(ev), note=a.rerun_reason)

    marker.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(marker.read_text())["openings"] if marker.exists() else []
    history.append({"run_id": out.name, "opened_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "git_sha": runs.git_info()[0], "config_hash": config_hash(), "reason": a.rerun_reason or "first opening"})
    marker.write_text(json.dumps({"openings": history}, indent=2))

    w = met["bootstrap_week"]
    print(f"LOCKBOX {out.name}: improvement {w['point']:+.1%}  95% range [{w['ci_low']:+.1%}, {w['ci_high']:+.1%}]")
    print(f"  pre-registered success: {'YES' if met['success'] else 'NO'}")
    print("  Commit results/ now. This number is the headline whatever it says.")


if __name__ == "__main__":
    main()
