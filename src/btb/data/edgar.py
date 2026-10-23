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
import csv
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
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
    "0001628280-24-043432": "2024-10-23 16:09:26",   # TSLA, summer
    "0001324404-24-000024": "2024-10-30 16:43:01",   # CF, summer (raw value was real UTC)
    "0000936340-24-000115": "2024-04-25 07:05:24",   # DTE, summer (raw value was real UTC)
}

# The submissions JSON is not consistent: for some companies acceptanceDateTime is real UTC,
# for others Eastern plus twice the offset (checked 2026-10-22 against filing pages: TSLA
# twice, CF and DTE real UTC), so no single ACCEPTANCE_TZ is right for every company. The
# fix: read each earnings filing's own SEC header, whose ACCEPTANCE-DATETIME is Eastern
# wall-clock time, into ACCEPT_FILE inside the snapshot folder (python -m btb.data.edgar
# --accept-times <snapshot>). parse_filings uses that file whenever it exists.
ACCEPT_FILE = "acceptance_et.csv"
HEADER_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{acc}-index-headers.html"
_ACCEPT_RE = re.compile(r"(?:<|&lt;)ACCEPTANCE-DATETIME(?:>|&gt;)\s*(\d{14})")
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


def _read_earnings_filings(snapshot_dir) -> "pd.DataFrame":  # noqa: F821
    """8-K item 2.02 rows from one raw snapshot folder, raw acceptanceDateTime, one row per accession."""
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
    return df[keep].drop_duplicates("accession").copy()


def _read_accept_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["accession"]: r["accept_ts_et"] for r in csv.DictReader(f)}


def fetch_acceptance_times(snapshot: str, workers: int = 6) -> int:
    """Write ACCEPT_FILE (accession, accept_ts_et) in the snapshot folder: the ACCEPTANCE-DATETIME
    from each earnings filing's SEC header (Eastern time). Safe to rerun: accessions already in
    the file are skipped, so a crash just means running it again. Stays under 10 requests per
    second across all threads. Returns how many were fetched this run."""
    snap = RAW / "edgar" / snapshot
    raw = _read_earnings_filings(snap)
    start = pd.Timestamp(load()["dates"]["edgar_start"]) - pd.Timedelta(days=2)
    raw_ts = pd.to_datetime(raw["acceptanceDateTime"], utc=True, format="ISO8601").dt.tz_localize(None)
    raw = raw[raw_ts >= start]
    out = snap / ACCEPT_FILE
    done = _read_accept_file(out)
    todo = raw[~raw["accession"].isin(done)][["cik", "accession"]].to_dict("records")
    print(f"{len(done)} already in {ACCEPT_FILE}, fetching {len(todo)}")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    rate_lock, write_lock = threading.Lock(), threading.Lock()
    last = [0.0]

    def get(url: str) -> str:
        for attempt in range(4):
            with rate_lock:                       # at most one request start per SLEEP_S
                wait = last[0] + SLEEP_S - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                last[0] = time.monotonic()
            try:
                r = session.get(url, timeout=30)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                return r.text
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("unreachable")

    new_file = not out.exists()
    with open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["accession", "accept_ts_et"])
        count = [0]

        def one(row: dict) -> None:
            acc = row["accession"]
            text = get(HEADER_URL.format(cik=int(row["cik"]), nodash=acc.replace("-", ""), acc=acc))
            m = _ACCEPT_RE.search(text)
            if not m:
                raise ValueError(f"no ACCEPTANCE-DATETIME in the SEC header for {acc}")
            ts = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
            with write_lock:
                w.writerow([acc, ts.strftime("%Y-%m-%d %H:%M:%S")])
                f.flush()
                count[0] += 1
                if count[0] % 500 == 0:
                    print(f"{count[0]}/{len(todo)} acceptance times fetched")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, todo))
    return count[0]


def parse_filings(snapshot_dir) -> "pd.DataFrame":  # noqa: F821
    """Return the "filings" table from one raw snapshot folder. Rules in the module docstring."""
    cfg = load()
    df = _read_earnings_filings(snapshot_dir)
    accept = _read_accept_file(Path(snapshot_dir) / ACCEPT_FILE)
    if accept:
        # True Eastern times from each filing's SEC header (see ACCEPT_FILE above).
        df["accept_ts_et"] = pd.to_datetime(df["accession"].map(accept)).astype("datetime64[us]")
        raw_ts = pd.to_datetime(df["acceptanceDateTime"], utc=True, format="ISO8601").dt.tz_localize(None)
        missing = df["accept_ts_et"].isna() & (raw_ts >= pd.Timestamp(cfg["dates"]["edgar_start"]))
        if missing.any():
            raise ValueError(f"{int(missing.sum())} filings have no time in {ACCEPT_FILE}; "
                             f"rerun python -m btb.data.edgar --accept-times <snapshot>")
        df = df[df["accept_ts_et"].notna()]
    else:
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
    ap.add_argument("--accept-times", metavar="SNAPSHOT",
                    help="fetch each filing's true acceptance time for an existing snapshot, "
                         "then rewrite data/interim/filings.parquet")
    a = ap.parse_args()
    if a.accept_times:
        fetch_acceptance_times(a.accept_times)
        df = parse_filings(RAW / "edgar" / a.accept_times)
        INTERIM.mkdir(parents=True, exist_ok=True)
        df.to_parquet(INTERIM / "filings.parquet", index=False)
        print(f"wrote {len(df)} filings with SEC header times")
        return
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
