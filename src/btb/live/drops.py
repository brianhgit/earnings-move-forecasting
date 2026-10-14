"""Where each forecast drop lives and what its settings are (plumbing, not a task)."""

from __future__ import annotations

from pathlib import Path

from btb.config import LIVE, load


def drop_cfg(drop_id: str, cfg: dict | None = None) -> dict:
    for d in (cfg or load())["live"]["drops"]:
        if d["id"] == drop_id:
            return d
    raise KeyError(drop_id)


def drop_dir(drop_id: str, data_source: str) -> Path:
    from btb.config import ROOT

    base = {"real": LIVE / "drops", "synthetic": LIVE / "demo_drops",
            "fixture": ROOT / "fixtures" / "demo_results" / "live"}[data_source]
    p = base / drop_id
    p.mkdir(parents=True, exist_ok=True)
    return p
