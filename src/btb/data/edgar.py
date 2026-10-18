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
    with header {"User-Agent": USER_AGENT}. Put your real name and email in USER_AGENT
    below; the SEC blocks requests without one. No API key needed.
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

USER_AGENT = "Your Name your.email@ucdavis.edu"   # change to your real name and email
ACCEPTANCE_TZ = None   # "America/New_York" or "UTC", set after the timezone check
TEST_CIKS = [1065280, 1318605, 320193]   # NFLX, TSLA, AAPL


def download(snapshot: str | None = None, ciks: list[int] | None = None) -> None:
    raise NotImplementedError


def parse_filings(snapshot_dir) -> "pd.DataFrame":  # noqa: F821
    """Return the "filings" table from one raw snapshot folder. Rules in the module docstring."""
    raise NotImplementedError


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
