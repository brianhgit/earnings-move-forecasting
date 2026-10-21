"""Every earnings 8-K from SEC EDGAR.

    python -m btb.data.edgar                 all companies in data/interim/universe.parquet
    python -m btb.data.edgar --test          only NFLX, TSLA, AAPL (use this first)

What to build:
  download(snapshot=None, ciks=None)
      Fetch the raw JSON for every CIK and save it. Saves files, returns nothing.
  parse_filings(snapshot_dir)
      Read one snapshot folder and return the "filings" table.
  main()  (already wired below)
      download, then parse, then write data/interim/filings.parquet. That file is what
      the dataset build reads, so this module is the one that writes it.

Downloading:
  - For each CIK, GET https://data.sec.gov/submissions/CIK{cik:010d}.json
    with header {"User-Agent": USER_AGENT}. Set the SEC_USER_AGENT environment variable
    to your real name and email before downloading (USER_AGENT below reads it; names are
    not committed); the SEC blocks requests without one. No API key needed.
  - Stay under 10 requests per second: time.sleep(0.15) after every request.
  - That JSON only holds the most recent ~1000 filings, under json["filings"]["recent"].
    Older filings are listed in json["filings"]["files"], a list like
    [{"name": "CIK0000320193-submissions-001.json", ...}]. Fetch each one from
    https://data.sec.gov/submissions/<name> too. Skipping these loses 2017 to 2020.
  - Save every response as-is under data/raw/edgar/<snapshot>/, where snapshot defaults
    to today's date as YYYYMMDD, using the same file name the SEC uses
    (CIK##########.json and the -submissions-### pages).
  - Never overwrite a snapshot: if data/raw/edgar/<snapshot>/ already has files, raise
    an error. A new download goes in a new dated folder.
  - ciks=None means every cik in data/interim/universe.parquet. --test passes the three
    test CIKs: NFLX 1065280, TSLA 1318605, AAPL 320193.

Parsing (the important part):
  - The main file keeps its columns under json["filings"]["recent"]. The older pages
    (-submissions-###.json) are shaped differently: the same columns sit at the TOP LEVEL
    of the file, with no "filings"/"recent" wrapper. Handle both.
  - Each is a dict of parallel lists. Row i is form[i], items[i], acceptanceDateTime[i],
    accessionNumber[i]. Build a DataFrame from those four lists.
  - Keep rows where form == "8-K" exactly (drop "8-K/A") and "2.02" is one of the items.
    items is a comma-separated string like "2.02,9.01": split on "," and strip, so "12.02"
    never matches.
  - The same accession can appear in more than one page: drop duplicates on accession.
  - accept_ts_et: parse acceptanceDateTime, then express it in Eastern time as a NAIVE
    timestamp (no tz attached), matching fixtures/tiny_filings.parquet. See the timezone
    check below for how to convert.
  - Keep accept_ts_et >= cfg dates.edgar_start (2017-01-01). Older rows aren't needed.
  - Return columns cik (int), accession (str), form (str), items (str), accept_ts_et,
    sorted by cik then accept_ts_et, and passing validate(df, "filings").

THE TIMEZONE CHECK (do this first, on the --test download).
  acceptanceDateTime ends in "Z", which normally means UTC. Don't assume it. Find a few
  after-close earnings reports for the three test companies (they report after 4 pm ET):
    raw value about 16:0x  -> the field is really Eastern, just strip the Z
    raw value about 20:0x or 21:0x -> it really is UTC, convert UTC to America/New_York
  Set ACCEPTANCE_TZ below to what you found and write it in docs/DECISIONS.md. Every
  before-open / after-close label in the project depends on this.

Data checks you own (post the counts in the channel):
  D-dup      company-quarters with 2+ Item 2.02 filings (build.py drops the second one)
  D-missing  company-quarters with zero filings (the recall check)

Backup if the API is slow: https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from btb.config import INTERIM, RAW, load
from btb.schema import validate

USER_AGENT = os.environ.get("SEC_USER_AGENT", "Your Name your.email@ucdavis.edu")
# How to read acceptanceDateTime. Checked against SEC filing index pages, see docs/DECISIONS.md.
#   "UTC"              the raw value is real UTC (what the API returned on 2026-10-18)
#   "UTC_TWICE"        the raw value is Eastern time plus twice the UTC offset (8 h in summer,
#                      10 h in winter), so converting UTC -> Eastern twice gives the real time
#                      (what the API returns since 2026-10-20, all 12 checked filings)
#   "America/New_York" the raw value is already Eastern wall-clock time with a wrong "Z"
ACCEPTANCE_TZ = "UTC_TWICE"

# Acceptance times read off the SEC's own filing index pages (the "Accepted" field).
# parse_filings checks every one it finds and stops if they don't match, so a change in
# how the SEC reports times can never slip into the table unnoticed.
KNOWN_ACCEPTANCE_ET = {
    "0000320193-19-000007": "2019-01-29 16:30:18",   # AAPL, winter
    "0000320193-22-000006": "2022-01-27 16:30:36",   # AAPL, winter
}
TEST_CIKS = [1065280, 1318605, 320193]   # NFLX, TSLA, AAPL

BASE_URL = "https://data.sec.gov/submissions"
SLEEP_S = 0.15   # keeps us under the SEC's 10 requests per second


def download(snapshot: str | None = None, ciks: list[int] | None = None) -> None:
    snapshot = snapshot or date.today().strftime("%Y%m%d")
    out = RAW / "edgar" / snapshot
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} already has files. Snapshots are never overwritten; use a new dated folder.")
    if ciks is None:
        ciks = pd.read_parquet(INTERIM / "universe.parquet")["cik"].astype(int).unique().tolist()
    out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    def fetch(name: str) -> dict:
        r = session.get(f"{BASE_URL}/{name}", timeout=30)
        time.sleep(SLEEP_S)
        r.raise_for_status()
        with open(out / name, "xb") as f:   # "x": fail rather than overwrite
            f.write(r.content)
        return r.json()

    for n, cik in enumerate(ciks, 1):
        main = fetch(f"CIK{int(cik):010d}.json")
        for page in main.get("filings", {}).get("files", []):
            fetch(page["name"])
        if n % 50 == 0:
            print(f"{n}/{len(ciks)} companies downloaded")


def _to_eastern(raw: pd.Series) -> pd.Series:
    """acceptanceDateTime strings -> naive America/New_York timestamps, per ACCEPTANCE_TZ."""
    ts = pd.to_datetime(raw, utc=True, format="ISO8601")   # parses the trailing Z as UTC
    if ACCEPTANCE_TZ == "America/New_York":
        ts = ts.dt.tz_localize(None)                        # the Z is wrong: keep the wall-clock time
    elif ACCEPTANCE_TZ == "UTC":
        ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    elif ACCEPTANCE_TZ == "UTC_TWICE":
        once = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
        ts = once.dt.tz_localize("UTC").dt.tz_convert("America/New_York").dt.tz_localize(None)
    else:
        raise ValueError(f"ACCEPTANCE_TZ must be 'America/New_York', 'UTC' or 'UTC_TWICE', got {ACCEPTANCE_TZ!r}")
    return ts.astype("datetime64[us]")


def check_known_times(df: "pd.DataFrame") -> int:  # noqa: F821
    """Compare accept_ts_et with KNOWN_ACCEPTANCE_ET for every known accession in df.
    Raises ValueError on any mismatch. Returns how many were checked."""
    checked = 0
    for acc, want in KNOWN_ACCEPTANCE_ET.items():
        got = df.loc[df["accession"] == acc, "accept_ts_et"]
        if got.empty:
            continue
        checked += 1
        if got.iloc[0] != pd.Timestamp(want):
            raise ValueError(
                f"Acceptance time for {acc} came out {got.iloc[0]}, but the SEC filing page says {want} ET. "
                f"The SEC changed how it reports times: re-check ACCEPTANCE_TZ in edgar.py against a few "
                f"filing index pages before building anything.")
    return checked


def _has_item(items: str, item: str) -> bool:
    return item in [s.strip() for s in (items or "").split(",")]


def parse_filings(snapshot_dir) -> "pd.DataFrame":  # noqa: F821
    """Return the "filings" table from one raw snapshot folder. Rules in the module docstring."""
    cfg = load()
    paths = sorted(Path(snapshot_dir).glob("CIK*.json"))
    if not paths:
        raise FileNotFoundError(f"no CIK*.json files in {snapshot_dir}")

    frames = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Main file: columns under filings.recent. Older -submissions-### pages: at the top level.
        cols = data["filings"]["recent"] if "filings" in data else data
        forms = cols.get("form", [])
        frames.append(pd.DataFrame({
            "cik": int(re.match(r"CIK(\d{10})", path.name).group(1)),
            "accession": cols.get("accessionNumber", []),
            "form": forms,
            "items": cols.get("items", [""] * len(forms)),
            "acceptanceDateTime": cols.get("acceptanceDateTime", []),
        }))
    df = pd.concat(frames, ignore_index=True)

    keep = df["form"].isin(cfg["event"]["filing_forms"]) & df["items"].map(
        lambda s: _has_item(s, cfg["event"]["required_item"]))
    df = df[keep].drop_duplicates("accession").copy()
    df["accept_ts_et"] = _to_eastern(df["acceptanceDateTime"])
    check_known_times(df)
    df = df[df["accept_ts_et"] >= pd.Timestamp(cfg["dates"]["edgar_start"])]

    df = (df[["cik", "accession", "form", "items", "accept_ts_et"]]
          .astype({"cik": "int64"})
          .sort_values(["cik", "accept_ts_et"], kind="stable")
          .reset_index(drop=True))
    validate(df, "filings")
    return df


def main() -> None:
    from datetime import date

    from btb.config import INTERIM, RAW

    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="only the three test companies")
    ap.add_argument("--snapshot", default=date.today().strftime("%Y%m%d"))
    a = ap.parse_args()
    download(a.snapshot, TEST_CIKS if a.test else None)
    df = parse_filings(RAW / "edgar" / a.snapshot)
    if a.test:
        print(df.groupby("cik").size())
        return
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM / "filings.parquet", index=False)
    print(f"wrote {len(df)} filings")


if __name__ == "__main__":
    main()
