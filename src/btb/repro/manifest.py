"""Checksums for every raw file, so "it works on my laptop" becomes provable.

    python -m btb.repro.manifest --write     (make manifest)  -> data/MANIFEST.json, committed
    python -m btb.repro.manifest --verify    (make verify-data)

Yahoo and EDGAR data can change between downloads (late corrections, dividend
re-adjustments), so the project runs on ONE frozen snapshot. The raw files are
shared privately; this manifest proves every copy is identical. An independent
rerun starts with --verify.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata

from btb.config import DATA, RAW

MANIFEST = DATA / "MANIFEST.json"
PACKAGES = ["numpy", "pandas", "pyarrow", "lightgbm", "yfinance", "exchange_calendars", "scikit-learn"]


def _sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan() -> dict[str, dict]:
    files = {}
    for p in sorted(RAW.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            files[str(p.relative_to(DATA))] = {"sha256": _sha(p), "bytes": p.stat().st_size}
    return files


def versions() -> dict[str, str]:
    out = {"python": sys.version.split()[0], "platform": platform.platform()}
    for pkg in PACKAGES:
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "missing"
    return out


def write() -> dict:
    files = scan()
    man = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_files": len(files), "files": files, "versions": versions()}
    MANIFEST.write_text(json.dumps(man, indent=2))
    return man


def verify() -> list[str]:
    man = json.loads(MANIFEST.read_text())
    now = scan()
    problems = [f"missing: {k}" for k in man["files"] if k not in now]
    problems += [f"changed: {k}" for k, v in man["files"].items() if k in now and now[k]["sha256"] != v["sha256"]]
    problems += [f"extra (not in manifest): {k}" for k in now if k not in man["files"]]
    mine = versions()
    problems += [f"version {k}: manifest {v} vs yours {mine.get(k)}" for k, v in man["versions"].items()
                 if k in PACKAGES and v != mine.get(k)]
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    a = ap.parse_args(argv)
    if a.write:
        m = write()
        print(f"wrote {MANIFEST} ({m['n_files']} files)")
    else:
        probs = verify()
        print("data matches the manifest" if not probs else "\n".join(probs))
        sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
