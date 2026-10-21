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
  - Which snapshot is "the" snapshot is recorded once in configs/project.yaml under
    data.prices_snapshot after the full download, in a separate reviewed change. Until then, pass the
    folder name with --load.

Data checks (post results in the channel after the full download):
  D-gap   no missing sessions in any ticker's history (compare to btb.dataset.calendar)
  D-jump  any daily |return| > 40% that isn't on a split date gets flagged
  D-hand  30 random closes match nasdaq.com historical quotes (audit/price_spotcheck_template.csv)

Yahoo's terms don't allow reposting their data, so nothing under data/ is committed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import time

import pandas as pd

from btb.config import INTERIM, RAW
from btb.schema import validate

TEST_TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "NFLX", "JPM", "XOM", "KO", "BRK-B", "WMT"]
BATCH_SIZE = 50
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2


def download(snapshot: str | None = None, tickers: list[str] | None = None) -> None:
    # Download Yahoo prices into a new immutable snapshot directory.
    import yfinance as yf

    snapshot = snapshot or dt.date.today().strftime("%Y%m%d")
    try:
        dt.datetime.strptime(snapshot, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"snapshot must be YYYYMMDD, got {snapshot!r}") from exc

    if tickers is None:
        universe_path = INTERIM / "universe.parquet"
        if not universe_path.exists():
            raise FileNotFoundError(f"company universe not found: {universe_path}")
        tickers = pd.read_parquet(universe_path)["yahoo_ticker"].astype(str).tolist()
    # Keep required market reference series and avoid duplicate requests.
    tickers = list(dict.fromkeys([*map(str, tickers), "SPY", "^VIX"]))

    # Creating the directory exclusively prevents reruns from changing a snapshot.
    snapshot_dir = RAW / "prices" / snapshot
    snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
    snapshot_dir.mkdir(exist_ok=False)

    failures: dict[str, dict[str, object]] = {}
    batches = [tickers[i:i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    for batch_number, batch in enumerate(batches):
        pending = list(batch)
        last_errors: dict[str, str] = {}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            # Retry only tickers still missing usable adjusted-close data.
            try:
                downloaded = yf.download(
                    pending,
                    start="2016-07-01",
                    auto_adjust=False,
                    actions=True,
                    group_by="ticker",
                    progress=False,
                )
            except Exception as exc:
                downloaded = pd.DataFrame()
                last_errors = {ticker: f"{type(exc).__name__}: {exc}" for ticker in pending}

            remaining: list[str] = []
            for ticker in pending:
                frame = _ticker_frame(downloaded, ticker)
                if frame is None or "Adj Close" not in frame or frame["Adj Close"].notna().sum() == 0:
                    remaining.append(ticker)
                    last_errors.setdefault(ticker, "Yahoo returned no adjusted-close data")
                    continue

                # Preserve Yahoo's original fields for audits; load_long normalizes them later.
                frame = frame.copy()
                frame.index = pd.to_datetime(frame.index).tz_localize(None)
                frame.index.name = "date"
                frame.reset_index().to_parquet(snapshot_dir / f"{ticker}.parquet", index=False)

            pending = remaining
            if not pending:
                break
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

        for ticker in pending:
            failures[ticker] = {
                "ticker": ticker,
                "error": last_errors.get(ticker, "Yahoo returned no adjusted-close data"),
                "attempts": MAX_ATTEMPTS,
            }

        # Pace requests between batches to avoid hammering Yahoo's download endpoint.
        if batch_number < len(batches) - 1:
            time.sleep(RETRY_DELAY_SECONDS)

    # Write even an empty failure report so each snapshot has a consistent audit trail.
    pd.DataFrame(
        failures.values(), columns=["ticker", "error", "attempts"]
    ).to_csv(snapshot_dir / "failures.csv", index=False)


def _ticker_frame(data: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    # Extract one ticker's columns from yfinance's grouped or single-ticker output.
    if data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        match = next(
            (level for level in range(data.columns.nlevels)
             if ticker in data.columns.get_level_values(level)),
            None,
        )
        if match is None:
            return None
        try:
            data = data.xs(ticker, axis=1, level=match)
        except KeyError:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(-1)
    elif len(data.columns) == 0:
        return None
    return data


def load_long(snapshot: str) -> pd.DataFrame:
    # Return the long "prices" table from one snapshot folder; rules are in the module docstring.
    snapshot_dir = RAW / "prices" / snapshot
    if not snapshot_dir.is_dir():
        raise FileNotFoundError(f"price snapshot not found: {snapshot_dir}")

    frames = []
    for path in sorted(snapshot_dir.glob("*.parquet")):
        raw = pd.read_parquet(path)
        # Yahoo column labels are normalized here; ticker identity comes from each filename.
        columns = {str(column).casefold(): column for column in raw.columns}
        required = {"date", "adj close", "close", "volume"}
        missing = required - columns.keys()
        if missing:
            raise ValueError(f"{path} is missing Yahoo price columns: {sorted(missing)}")
        frame = pd.DataFrame({
            "date": pd.to_datetime(raw[columns["date"]]).dt.date,
            "ticker": path.stem,
            "adj_close": pd.to_numeric(raw[columns["adj close"]], errors="coerce"),
            "close": pd.to_numeric(raw[columns["close"]], errors="coerce"),
            "volume": pd.to_numeric(raw[columns["volume"]], errors="coerce"),
        })
        frames.append(frame.loc[frame["adj_close"].notna()])

    # Validate the exact long-table contract consumed by feature and event building.
    if frames:
        prices = pd.concat(frames, ignore_index=True)
        prices = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
    else:
        # An empty folder means the download failed; stop instead of writing an empty table.
        raise FileNotFoundError(f"no ticker files in {snapshot_dir}; the download probably failed (see failures.csv)")
    validate(prices, "prices")
    return prices


def main() -> None:
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
