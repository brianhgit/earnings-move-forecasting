"""Download and cache daily prices.

    python -m btb.data.prices                 download every company, plus SPY and ^VIX
    python -m btb.data.prices --test          download about 10 tickers (use this first)
    python -m btb.data.prices --load <YYYYMMDD>   write data/interim/prices.parquet from one snapshot

What to build:
  download(snapshot=None, tickers=None)
      Fetch prices and save one raw file per ticker. Saves files, returns nothing.
  load_long(snapshot)
      Read one snapshot folder and return the long "prices" table.
  main()  (already wired below)

Downloading:
  - tickers=None means every yahoo_ticker in data/interim/universe.parquet. Always add
    "SPY" and "^VIX" whatever list you get. --test uses TEST_TICKERS below.
  - yf.download(batch, start="2016-07-01", auto_adjust=False, actions=True,
    group_by="ticker", progress=False). auto_adjust=False gives you BOTH "Close" and
    "Adj Close"; the raw close is needed for the split check.
  - Batches of 50 tickers, time.sleep(2) between batches. With group_by="ticker" the
    result has MultiIndex columns (ticker, field). A ticker that failed comes back all NaN
    (or missing). Retry just the failed tickers of a batch, up to 3 tries in total.
  - Save each ticker as data/raw/prices/<snapshot>/<ticker>.parquet with columns
    date, Close, Adj Close, Volume (plus whatever else yfinance gives). snapshot defaults
    to today as YYYYMMDD.
  - Never overwrite: if data/raw/prices/<snapshot>/ already exists, raise an error.
  - Tickers that still fail after 3 tries go in data/raw/prices/<snapshot>/failures.csv
    with columns ticker, error, attempts.

load_long(snapshot):
  - Read every <ticker>.parquet in data/raw/prices/<snapshot>/ (skip failures.csv).
  - Return one long table: date (datetime.date), ticker (str), adj_close, close, volume
    (floats), sorted by ticker then date, dropping rows where adj_close is NaN. It must
    pass validate(df, "prices").
  - Which snapshot is "the" snapshot is set once by Brian in configs/project.yaml under
    data.prices_snapshot after the full download. Don't edit the config yourself; pass the
    folder name with --load.

Data checks (post results in the channel after the full download):
  D-gap   no missing sessions in any ticker's history (compare to btb.dataset.calendar)
  D-jump  any daily |return| > 40% that isn't on a split date gets flagged
  D-hand  30 random closes match nasdaq.com historical quotes (audit/price_spotcheck_template.csv)

Yahoo's terms don't allow reposting their data, so nothing under data/ is committed.
"""

from __future__ import annotations

import argparse

TEST_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "NFLX", "JPM", "XOM", "KO", "BRK-B", "WMT"]


def download(snapshot: str | None = None, tickers: list[str] | None = None) -> None:
    raise NotImplementedError


def load_long(snapshot: str) -> "pd.DataFrame":  # noqa: F821
    """Return the long "prices" table from one snapshot folder. Rules in the module docstring."""
    raise NotImplementedError


def main() -> None:
    from btb.config import INTERIM

    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="only TEST_TICKERS")
    ap.add_argument("--snapshot", default=None, help="folder name, default today YYYYMMDD")
    ap.add_argument("--load", metavar="SNAPSHOT", help="write data/interim/prices.parquet from this snapshot")
    a = ap.parse_args()
    if a.load:
        df = load_long(a.load)
        INTERIM.mkdir(parents=True, exist_ok=True)
        df.to_parquet(INTERIM / "prices.parquet", index=False)
        print(f"wrote {len(df)} rows for {df['ticker'].nunique()} tickers")
        return
    download(a.snapshot, TEST_TICKERS if a.test else None)


if __name__ == "__main__":
    main()
