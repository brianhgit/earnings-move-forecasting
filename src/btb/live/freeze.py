"""Lock a forecast drop with a fingerprint.

    python -m btb.live.freeze --drop drop1       (make freeze DROP=drop1)

Git timestamps can be faked, so the proof that we forecast first uses outside clocks:
  1. The SHA-256 of forecasts.csv, posted publicly before the deadline
     (Discord stamps the time).
  2. A GitHub Release named <drop>-forecasts with forecasts.csv attached.
Anyone can recompute the hash with `python -m btb.live.freeze --verify --drop drop1`
or `shasum -a 256 live/drops/drop1/forecasts.csv`.

After freezing, forecasts.csv is never edited. Missed the deadline? The drop is void
and none of its reports get scored. No backfilling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from btb.live.drops import drop_cfg, drop_dir


def sha256_file(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(drop_id: str, data_source: str = "real", now: datetime | None = None) -> dict:
    d = drop_cfg(drop_id)
    out = drop_dir(drop_id, data_source)
    if (out / "FREEZE.json").exists():
        raise SystemExit(f"{drop_id} is already frozen. Posted forecasts are never changed.")
    fc_path = out / "forecasts.csv"
    now = now or datetime.now(timezone.utc)
    deadline = pd.Timestamp(d["post_by"]).tz_convert("UTC")
    rec = {
        "drop_id": drop_id, "sha256": sha256_file(fc_path),
        "n_companies": int(sum(1 for _ in fc_path.open()) - 1),
        "frozen_utc": now.isoformat(timespec="seconds"), "post_by": d["post_by"],
        "on_time": bool(pd.Timestamp(now) <= deadline), "window": d["window"],
    }
    (out / "FREEZE.json").write_text(json.dumps(rec, indent=2))
    (out / "forecasts.sha256").write_text(f"{rec['sha256']}  forecasts.csv\n")
    return rec


def verify(drop_id: str, data_source: str = "real") -> bool:
    out = drop_dir(drop_id, data_source)
    rec = json.loads((out / "FREEZE.json").read_text())
    return sha256_file(out / "forecasts.csv") == rec["sha256"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", required=True)
    ap.add_argument("--data", choices=["synthetic", "real"], default="real")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    if a.verify:
        print("MATCH" if verify(a.drop, a.data) else "MISMATCH: forecasts.csv changed after freezing")
        return
    rec = freeze(a.drop, a.data)
    if not rec["on_time"]:
        print("LATE: past the deadline. This drop is void; post that it was missed, don't score it.")
    print("\nPost this publicly now:\n")
    print(f"Beat the Baseline {a.drop} is locked. {rec['n_companies']} companies forecast for reports "
          f"{rec['window'][0]} to {rec['window'][1]}.\nSHA-256: {rec['sha256']}")


if __name__ == "__main__":
    main()
