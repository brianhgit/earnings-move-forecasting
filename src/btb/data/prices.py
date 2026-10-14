"""Download and cache daily prices.

    python -m btb.data.prices          (make data-prices)

Contract:
  - Tickers: every yahoo_ticker in data/interim/universe.parquet, plus SPY and ^VIX.
  - Range: 2016-07-01 to today. Use yf.download(..., auto_adjust=False, actions=True)
    so you get BOTH "Close" and "Adj Close" (we need the raw close for the split check).
  - Raw snapshots are immutable: data/raw/prices/<YYYYMMDD>/<ticker>.parquet. Never
    overwrite a snapshot folder. A new download goes in a new dated folder.
  - Then write data/interim/prices.parquet in the long "prices" schema, from ONE snapshot
    folder named in configs/project.yaml (add data.prices_snapshot when you pick it).
  - Log every ticker that fails in data/raw/prices/<YYYYMMDD>/failures.csv.
  - Be polite: batches of ~50 tickers, sleep between batches, retry 3 times.

Data checks:
  D-gap   no missing sessions in any ticker's history (use btb.dataset.calendar)
  D-jump  any daily |return| > 40% that isn't on a split date gets flagged
  D-hand  30 random closes match nasdaq.com historical quotes (fill audit/price_spotcheck.csv)

Yahoo's terms don't allow reposting their data, so nothing under data/ is committed.
The snapshot is shared privately; data/MANIFEST.json (committed)
has the checksums so everyone can prove they have the same files.
"""

from __future__ import annotations


def download(snapshot: str | None = None) -> None:
    raise NotImplementedError


def load_long() -> "pd.DataFrame":  # noqa: F821
    raise NotImplementedError


if __name__ == "__main__":
    download()
