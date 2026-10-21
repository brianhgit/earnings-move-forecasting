"""The company list and point-in-time membership.

    python -m btb.data.universe        (make data-universe)

1. S&P 500 snapshot as of configs/project.yaml universe.snapshot_date.
   Use the Wikipedia page REVISION from that date, not today's page, so a rerun gets
   the same list: https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid=<id>
   Save the raw HTML under data/raw/universe/ and record the oldid in docs/DECISIONS.md.
2. yahoo_ticker = ticker with "." -> "-" (BRK.B -> BRK-B).
3. One share class per CIK: keep the one listed in universe.share_class_keep.
4. Point-in-time membership from github.com/fja05680/sp500
   (sp_500_historical_components.csv) saved to data/raw/membership/. Used ONLY for the
   in_index_at_cutoff sensitivity column: the headline uses the snapshot universe and
   says so (survivorship limitation, docs/AUDIT.md item I4).
"""

from __future__ import annotations

from io import StringIO

import pandas as pd

from btb.config import INTERIM, RAW, load

WIKI = "https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid={oldid}"


def from_html(html: str) -> pd.DataFrame:
    table = pd.read_html(StringIO(html), attrs={"id": "constituents"})[0]
    df = pd.DataFrame({
        "ticker": table["Symbol"].astype(str),
        "yahoo_ticker": table["Symbol"].astype(str).str.replace(".", "-", regex=False),
        "cik": table["CIK"].astype(int),
        "name": table["Security"].astype(str),
        "sector": table["GICS Sector"].astype(str),
    })
    keep = set(load()["universe"]["share_class_keep"])
    dup = df["cik"].duplicated(keep=False)
    return pd.concat([df[~dup], df[dup & df["yahoo_ticker"].isin(keep)]]).sort_values("ticker").reset_index(drop=True)


def build(oldid: str) -> pd.DataFrame:
    import requests

    html = requests.get(WIKI.format(oldid=oldid), timeout=30,
                        headers={"User-Agent": "earnings-move-forecasting (research project)"}).text
    (RAW / "universe").mkdir(parents=True, exist_ok=True)
    (RAW / "universe" / f"wikipedia_{oldid}.html").write_text(html, encoding="utf-8")
    df = from_html(html)
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM / "universe.parquet", index=False)
    return df


if __name__ == "__main__":
    import sys

    print(build(sys.argv[1]).shape)
