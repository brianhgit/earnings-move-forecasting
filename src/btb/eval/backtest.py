"""Run the walk-forward backtest and write a run.

    python -m btb.eval.backtest --name lgbm_v1 --data synthetic --note "first try"
    python -m btb.eval.backtest --name lgbm_v1 --data real

Dev mode only ever loads data/processed/events_dev.parquet. The lockbox has its
own command (python -m btb.eval.lockbox) with its own guard rails.
"""

from __future__ import annotations

import argparse
import hashlib

import pandas as pd

from btb import standins, synthetic
from btb.config import PROCESSED, load
from btb.eval import metrics, runs, splits
from btb.models import baseline, lgbm, shrinkage  # noqa: F401  (predict_folds uses all three)
from btb.schema import validate


def data_hash(df: pd.DataFrame) -> str:
    h = pd.util.hash_pandas_object(df.sort_values("event_id").reset_index(drop=True), index=False)
    return hashlib.sha256(h.to_numpy().tobytes()).hexdigest()[:12]


def load_events(source: str, part: str) -> pd.DataFrame:
    """part: dev (train_only + dev rows), lockbox (everything through Sep 2026), all."""
    if source == "synthetic":
        ev = synthetic.events("demo")
    elif source == "real":
        standins.assert_off()
        if part == "dev":
            ev = pd.read_parquet(PROCESSED / "events_dev.parquet")
        else:
            ev = pd.concat([pd.read_parquet(PROCESSED / "events_dev.parquet"),
                            pd.read_parquet(PROCESSED / "events_lockbox.parquet")], ignore_index=True)
    else:
        raise ValueError(source)
    keep = {"dev": ["train_only", "dev"], "lockbox": ["train_only", "dev", "lockbox"],
            "all": ["train_only", "dev", "lockbox", "live"]}[part]
    ev = ev[ev["split"].isin(keep)].reset_index(drop=True)
    validate(ev, "events")
    return ev


def predict_folds(events: pd.DataFrame, folds: list[splits.Fold], cfg: dict) -> pd.DataFrame:
    """For each fold: fit LightGBM and the shrinkage diagnostic on the fold's training
    rows ONLY, then predict its test rows with the baseline, the model and shrinkage.

    Return ONE table for all folds with these columns (the "predictions" schema in
    src/btb/schema.py plus a few extras):
      event_id, ticker, sector, report_date, week_id   copied from events
      fold                                              the fold's label, e.g. "2023Q2"
      y_true                                            move_adj
      pred_baseline, pred_model, pred_shrunk            the three predictions
      vix, in_index_at_cutoff                           copied from events
      n_train                                           how many training rows that fold used
      model_fp                                          lgbm.fingerprint(model)

    Call the models through their modules: baseline.predict(test),
    lgbm.fit(train, cfg) / lgbm.predict(model, test, cfg), shrinkage.fit(train) /
    shrinkage.predict(params, test). n_train is len(train), model_fp is a string.
    Stack the folds with pd.concat(..., ignore_index=True). Column order doesn't matter.
    Finish with validate(pred, "predictions").
    Done when tests/test_eval.py::test_backtest_* pass.
    """
    parts = []
    for f in folds:
        train = events.loc[f.train_idx]
        test = events.loc[f.test_idx]

        model = lgbm.fit(train, cfg)
        params = shrinkage.fit(train)

        out = test[["event_id", "ticker", "sector", "report_date", "week_id", "vix", "in_index_at_cutoff"]].copy()
        out["fold"] = f.label
        out["y_true"] = test["move_adj"]
        out["pred_baseline"] = baseline.predict(test)
        out["pred_model"] = lgbm.predict(model, test, cfg)
        out["pred_shrunk"] = shrinkage.predict(params, test)
        out["n_train"] = len(train)
        out["model_fp"] = lgbm.fingerprint(model)
        parts.append(out)

    pred = pd.concat(parts, ignore_index=True)
    validate(pred, "predictions")
    return pred


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--data", choices=["synthetic", "real"], default="synthetic")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)

    cfg = load()
    ev = load_events(a.data, "dev")
    folds = splits.walk_forward(ev, "dev", cfg)
    splits.check_no_leak(ev, folds)
    pred = predict_folds(ev, folds, cfg)
    met = metrics.evaluate(pred, cfg)
    out = runs.write_run(name=a.name, kind="dev", data_source=a.data, predictions=pred, metrics=met,
                         data_hash=data_hash(ev), note=a.note)
    o, w = met["overall"], met["bootstrap_week"]
    print(f"run {out.name}: {o['n_events']} events over {len(folds)} quarters")
    print(f"  MAE baseline {o['mae_baseline']:.3f}  model {o['mae_model']:.3f}")
    print(f"  improvement {w['point']:+.1%}  95% range [{w['ci_low']:+.1%}, {w['ci_high']:+.1%}]  win rate {o['win_rate']:.1%}")
    if "shrinkage" in met:
        print(f"  vs shrunk baseline {met['shrinkage']['rel_improvement_vs_shrunk']:+.1%}")
    if met["tripwire"]:
        print("  TRIPWIRE: improvement above 30%. Stop and look for a leak before doing anything else.")


if __name__ == "__main__":
    main()
