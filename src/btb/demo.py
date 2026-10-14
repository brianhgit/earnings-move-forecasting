"""Run the whole pipeline end to end on SYNTHETIC data.

    python -m btb.demo           (make demo)

Writes results/demo/ and live/demo_drops/ with the exact same file formats the
real pipeline writes, so:
  - the Streamlit app works before real results exist (with a DEMO DATA banner)
  - charts and scoring can be built before the real table exists
  - CI proves the backtest -> lockbox -> live -> scoring chain runs

Nothing here is a real result. Never quote a demo number.
"""

from __future__ import annotations

import copy
import json
import shutil
from datetime import datetime, timezone

import pandas as pd

from btb import synthetic
from btb.config import LIVE, load
from btb.eval import backtest, metrics, runs, splits
from btb.live import forecast, freeze, score


def _dev_run(ev, cfg, name, note):
    folds = splits.walk_forward(ev, "dev", cfg)
    splits.check_no_leak(ev, folds)
    pred = backtest.predict_folds(ev, folds, cfg)
    met = metrics.evaluate(pred, cfg)
    runs.write_run(name=name, kind="dev", data_source="synthetic", predictions=pred, metrics=met,
                   data_hash=backtest.data_hash(ev), note=note)
    return met


def main():
    root = runs.results_root("synthetic")
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(LIVE / "demo_drops", ignore_errors=True)
    cfg = load()
    all_ev = synthetic.events("demo")
    dev = all_ev[all_ev["split"].isin(["train_only", "dev"])].reset_index(drop=True)

    # A few dev iterations so the ledger chart has something to show.
    wrong = copy.deepcopy(cfg)
    wrong["model"]["params"]["objective"] = "l2"
    _dev_run(dev, wrong, "lgbm_l2", "first try: default L2 loss (aims at the mean, wrong for MAE)")
    small = copy.deepcopy(cfg)
    small["model"]["params"]["n_estimators"] = 100
    _dev_run(dev, small, "lgbm_l1_100trees", "L1 loss, fewer trees")
    _dev_run(dev, cfg, "lgbm_l1", "L1 loss, locked settings")

    # Lockbox (synthetic: no git guard rails).
    lb = all_ev[all_ev["split"].isin(["train_only", "dev", "lockbox"])].reset_index(drop=True)
    folds = splits.walk_forward(lb, "lockbox", cfg)
    pred = backtest.predict_folds(lb, folds, cfg)
    met = metrics.evaluate(pred, cfg)
    out = runs.write_run(name="lockbox", kind="lockbox", data_source="synthetic", predictions=pred, metrics=met,
                         data_hash=backtest.data_hash(lb), note="demo lockbox")
    (root / "lockbox").mkdir(parents=True, exist_ok=True)
    (root / "lockbox" / "OPENED.json").write_text(json.dumps({"openings": [{"run_id": out.name}]}, indent=2))

    # Live drops: forecast every company with an event in the window, freeze before the deadline, score.
    live = all_ev[all_ev["split"] == "live"]
    for d in cfg["live"]["drops"]:
        lo, hi = pd.Timestamp(d["window"][0]), pd.Timestamp(d["window"][1])
        inputs = live[live["report_date"].between(lo, hi)].drop_duplicates("cik")
        forecast.make_forecasts(d["id"], "synthetic", inputs=inputs)
        before_deadline = pd.Timestamp(d["post_by"]).tz_convert("UTC") - pd.Timedelta(hours=2)
        freeze.freeze(d["id"], "synthetic", now=before_deadline.to_pydatetime())
        if d["id"] != "drop3":  # drop3 reports land after the demo window
            score.score(d["id"], inputs, "synthetic")

    led = runs.read_ledger("synthetic")
    print(led[["run_id", "kind", "n_events", "rel_improvement", "ci_low", "ci_high"]].to_string(index=False))
    print(f"\nDemo built {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. Run: streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    main()
