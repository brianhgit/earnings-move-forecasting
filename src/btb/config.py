"""Load configs/project.yaml once and hand out a plain dict.

Everything frozen about the project lives in that YAML file, so code never
hard-codes a date, a feature list or a model setting.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "project.yaml"

DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
RESULTS = ROOT / "results"
RUNS = RESULTS / "runs"
LEDGER = RESULTS / "ledger.csv"
LOCKBOX_DIR = RESULTS / "lockbox"
LIVE = ROOT / "live"


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict:
    with open(path or CONFIG_PATH) as f:
        return yaml.safe_load(f)


def config_hash(cfg: dict | None = None) -> str:
    """Short fingerprint of the config so every run says which settings it used."""
    cfg = cfg if cfg is not None else load()
    blob = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def features(cfg: dict | None = None) -> list[str]:
    return list((cfg or load())["features"])
