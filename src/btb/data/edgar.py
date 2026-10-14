"""Every earnings 8-K from SEC EDGAR.

    python -m btb.data.edgar           (make data-edgar)

Contract:
  - For each CIK in data/interim/universe.parquet, GET
    https://data.sec.gov/submissions/CIK##########.json (10-digit zero-padded).
  - Header: {"User-Agent": "earnings-move-forecasting <your.email@example.com>"}. Stay under
    10 requests/second (sleep 0.15s). No API key needed.
  - The JSON only holds recent filings. Older ones are in filings.files[] -> fetch each
    https://data.sec.gov/submissions/<name> too. Missing this = missing 2017-2020 history.
  - Save every raw JSON under data/raw/edgar/<YYYYMMDD>/ (immutable snapshot).
  - Keep rows where form == "8-K" (NOT "8-K/A") and "2.02" is in the items string.
  - accept_ts_et: from acceptanceDateTime, converted to America/New_York.

THE TIMEZONE TRAP. acceptanceDateTime ends in "Z", which normally means UTC. Do not
assume it. Before anything else, pull 5 reports we already know were after the close (e.g. NFLX,
TSLA from the appendix list) and check: if the raw value reads ~16:0x, the field is
really Eastern; if it reads ~20:0x / 21:0x, it is UTC. Write what you found in
docs/DECISIONS.md. Every BMO/AMC label depends on this.

Data checks you own:
  D-dup      company-quarters with 2+ Item 2.02 filings (count them, build.py drops the 2nd)
  D-missing  company-quarters with ZERO filings (this is the recall check; feeds the gate)
  D-pattern  flag reports whose timing breaks the company's usual BMO/AMC habit

Backup if the API is slow: https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
"""

from __future__ import annotations

USER_AGENT = "earnings-move-forecasting <CHANGE-ME@example.com>"


def download(snapshot: str | None = None) -> None:
    raise NotImplementedError


def parse_filings(snapshot_dir) -> "pd.DataFrame":  # noqa: F821
    """Return the "filings" schema table from a raw snapshot folder."""
    raise NotImplementedError


if __name__ == "__main__":
    download()
