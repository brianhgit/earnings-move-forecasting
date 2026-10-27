"""The data report.

    python -m btb.eval.data_report --data synthetic    build it now, on fake data
    python -m btb.eval.data_report --data real         once the real table exists

Turns what the build and the hand checks produced into the tables and charts for
the "what we kept, what we threw out" part of the final report. It writes one
markdown file (tables via DataFrame.to_markdown) plus plotly charts as .html:
    real       -> results/data_report.md and results/data_report/*.html
    synthetic  -> results/demo/data_report.md and results/demo/data_report/*.html

Sections:
  1. Kept vs dropped reports, by reason and by year.
       real:      kept per year = kept_by_year in results/build_report.json (counts only, so
                  every year is fine to show; never open events_lockbox.parquet itself),
                  dropped = data/processed/exclusions.csv, by reason and by the year of
                  accept_ts_et
       synthetic: kept = btb.synthetic.events("demo") by year of report_date; dropped = the
                  rows of btb.synthetic.measured("demo") with report_date on or after
                  2019-01-01 whose f"{cik}-{accession}" isn't an event_id in events("demo"),
                  all with reason "insufficient_history" (measured has no event_id column;
                  rows before 2019 are history only and aren't counted as drops)
     Table: rows = year, columns = kept plus one column per drop reason. Chart: stacked bars.
  2. Hand-check results, from audit/precision_audit.csv and audit/recall_audit.csv (same
     columns as the *_template.csv files next to them):
       precision = rows with correct_window_plan_a == "yes" out of all rows (target 57/60)
       recall    = rows with (in_our_table_yes_no == "yes" AND correct_window_plan_a == "yes")
                   or in_our_table_yes_no == "market hours" (released 9:30 to 4 ET, which
                   plan A excludes on purpose), out of rows with release_found_yes_no == "yes"
                   (target 27/30). For plan B, "market hours" rows need correct_window_plan_b.
                   in_our_table_yes_no == "plan B only" means plan A excluded the filing as
                   market hours although the release came out outside market hours (8-K
                   filed later): a plan A miss, but plan B keeps it, so it counts for plan B
                   when correct_window_plan_b == "yes".
     Compare answers case-insensitively and ignore spaces.
     Show each as k/n with its wilson_lower(k, n). Same for plan B columns.
  3. Timing sanity check (real only): for each kept report, compare |ret_stock| with the
     absolute log return of the stock on the NEXT session after after_date (read the
     adj_close column of data/interim/prices.parquet, matched on ticker and date; events
     have ticker, after_date and ret_stock). Use events_dev.parquet only. If our windows are right, our move
     should usually be the bigger one. Show the median of |ret_stock| / |next-day return|
     by year, and the share of reports where ours is bigger.

If an input file doesn't exist yet (no audit CSVs, no prices on synthetic), write
"Not available yet: <which file>" in that section instead of crashing. That's normal
on synthetic data for sections 2 and 3.

No price levels in the output (Yahoo terms): counts, ratios and charts only.

Done when tests/test_charts.py::test_wilson_lower passes and
`python -m btb.eval.data_report --data synthetic` writes results/demo/data_report.md.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from btb import standins, synthetic
from btb.config import INTERIM, PROCESSED, RESULTS, ROOT, load
from btb.eval import runs
from btb.eval.charts import MODEL, BASE, MUTED, _style

AUDIT = ROOT / "audit"
TARGETS = {"precision": (57, 60), "recall": (27, 30)}


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    """Lower end of the Wilson score interval for a proportion."""
    if n == 0:
        return 0.0
    p = successes / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (center - margin) / (1 + z * z / n))


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def _missing(*paths: Path) -> str:
    return "Not available yet: " + ", ".join(_rel(p) for p in paths)


# ---------------------------------------------------------------- 1. kept vs dropped
def kept_vs_dropped(data: str, cfg: dict) -> pd.DataFrame | str:
    """Table indexed by year: kept, then one column per drop reason."""
    if data == "synthetic":
        ev = synthetic.events("demo")
        ms = synthetic.measured("demo")
        kept = pd.to_datetime(ev["report_date"]).dt.year.value_counts()
        ms = ms[pd.to_datetime(ms["report_date"]) >= pd.Timestamp(cfg["dates"]["events_start"])]
        ids = ms["cik"].astype(str) + "-" + ms["accession"].astype(str)
        drop = ms[~ids.isin(set(ev["event_id"]))]
        dropped = pd.DataFrame({"year": pd.to_datetime(drop["report_date"]).dt.year,
                                "reason": "insufficient_history"})
    else:
        report, excl = RESULTS / "build_report.json", PROCESSED / "exclusions.csv"
        absent = [p for p in (report, excl) if not p.exists()]
        if absent:
            return _missing(*absent)
        kept_by_year = json.loads(report.read_text())["kept_by_year"]
        kept = pd.Series({int(y): n for y, n in kept_by_year.items()}, dtype=int)
        ex = pd.read_csv(excl)
        years = pd.to_datetime(ex["accept_ts_et"], utc=True).dt.tz_convert("America/New_York").dt.year
        dropped = pd.DataFrame({"year": years, "reason": ex["reason"]})

    table = pd.crosstab(dropped["year"], dropped["reason"]) if len(dropped) else pd.DataFrame()
    table = table.reindex(table.index.union(kept.index), fill_value=0)
    table.insert(0, "kept", kept.reindex(table.index, fill_value=0))
    table.index.name = "year"
    table.columns.name = None
    return table.astype(int).sort_index()


def kept_vs_dropped_chart(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for col in table.columns:
        fig.add_bar(x=table.index.astype(str), y=table[col], name=col,
                    marker_color=MODEL if col == "kept" else None)
    fig.update_layout(barmode="stack")
    return _style(fig, "Reports kept and dropped, by year", y_title="reports", x_title="year")


# ---------------------------------------------------------------- 2. hand check
def _norm(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.lower().str.replace(" ", "", regex=False)


def hand_check() -> pd.DataFrame | str:
    """One row per (check, plan): k, n, share, Wilson lower bound and the target."""
    prec_path, rec_path = AUDIT / "precision_audit.csv", AUDIT / "recall_audit.csv"
    absent = [p for p in (prec_path, rec_path) if not p.exists()]
    if absent:
        return _missing(*absent)
    prec, rec = pd.read_csv(prec_path), pd.read_csv(rec_path)
    rec = rec[_norm(rec["release_found_yes_no"]) == "yes"]
    in_table = _norm(rec["in_our_table_yes_no"])

    rows = []
    for plan in ("a", "b"):
        ok_p = _norm(prec[f"correct_window_plan_{plan}"]) == "yes"
        ok_r = _norm(rec[f"correct_window_plan_{plan}"]) == "yes"
        if plan == "a":
            hit = ((in_table == "yes") & ok_r) | (in_table == "markethours")
        else:
            hit = in_table.isin(["yes", "markethours", "planbonly"]) & ok_r
        for check, k, n in (("precision", int(ok_p.sum()), len(prec)),
                            ("recall", int(hit.sum()), len(rec))):
            tk, tn = TARGETS[check]
            rows.append({"check": check, "plan": plan.upper(), "k/n": f"{k}/{n}",
                         "share": k / n if n else float("nan"),
                         "wilson_lower": wilson_lower(k, n), "target": f"{tk}/{tn}",
                         "passes": n > 0 and k / n >= tk / tn})
    return pd.DataFrame(rows)


def hand_check_chart(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for plan, color in (("A", MODEL), ("B", BASE)):
        t = table[table["plan"] == plan]
        fig.add_bar(x=t["check"], y=t["share"] * 100, name=f"plan {plan}", marker_color=color,
                    error_y=dict(type="data", symmetric=False, array=[0] * len(t),
                                 arrayminus=(t["share"] - t["wilson_lower"]) * 100))
    for check, (tk, tn) in TARGETS.items():
        fig.add_hline(y=100 * tk / tn, line_dash="dot", line_color=MUTED,
                      annotation_text=f"{check} target {tk}/{tn}", annotation_position="bottom right")
    fig.update_layout(barmode="group")
    fig.update_yaxes(range=[0, 100])
    return _style(fig, "Hand check: share right, with Wilson 95% lower bound", y_title="% right")


# ---------------------------------------------------------------- 3. timing sanity check
def timing_check(data: str) -> pd.DataFrame | str:
    """By year: median |our move| / |next-session move| and the share where ours is bigger."""
    ev_path, px_path = PROCESSED / "events_dev.parquet", INTERIM / "prices.parquet"
    if data == "synthetic":
        return _missing(px_path) + " (no prices on synthetic data)"
    absent = [p for p in (ev_path, px_path) if not p.exists()]
    if absent:
        return _missing(*absent)

    ev = pd.read_parquet(ev_path, columns=["ticker", "report_date", "after_date", "ret_stock"])
    px = pd.read_parquet(px_path, columns=["ticker", "date", "adj_close"])
    px["date"] = pd.to_datetime(px["date"])
    px = px.sort_values(["ticker", "date"])
    px["next_absret"] = np.log(px.groupby("ticker")["adj_close"].shift(-1) / px["adj_close"]).abs()

    ev = ev.assign(yahoo_ticker=ev["ticker"].str.replace(".", "-", regex=False),
                   after_date=pd.to_datetime(ev["after_date"]),
                   year=pd.to_datetime(ev["report_date"]).dt.year)
    m = ev.merge(px[["ticker", "date", "next_absret"]], how="left",
                 left_on=["yahoo_ticker", "after_date"], right_on=["ticker", "date"], suffixes=("", "_px"))
    m["ours"] = m["ret_stock"].abs()
    m = m[m["next_absret"].notna() & (m["next_absret"] > 0)]
    if m.empty:
        return "No reports matched a next-session price."
    m["ratio"] = m["ours"] / m["next_absret"]
    m["ours_bigger"] = m["ours"] > m["next_absret"]
    return m.groupby("year").agg(n=("ratio", "size"), median_ratio=("ratio", "median"),
                                 share_ours_bigger=("ours_bigger", "mean"))


def timing_chart(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=table.index.astype(str), y=table["share_ours_bigger"] * 100, name="ours bigger",
                marker_color=MODEL)
    fig.add_hline(y=50, line_dash="dot", line_color=MUTED, annotation_text="coin flip")
    fig.update_yaxes(range=[0, 100])
    return _style(fig, "Is our move bigger than the next day's?", y_title="% of reports", x_title="year")


# ---------------------------------------------------------------- the report
SECTIONS = [
    ("1. Kept vs dropped reports", "kept_vs_dropped", kept_vs_dropped_chart),
    ("2. Hand-check results", "hand_check", hand_check_chart),
    ("3. Timing sanity check", "timing_check", timing_chart),
]


def build(data: str, cfg: dict | None = None) -> Path:
    cfg = cfg or load()
    root = runs.results_root(data)
    chart_dir = root / "data_report"
    chart_dir.mkdir(parents=True, exist_ok=True)

    results = {"kept_vs_dropped": kept_vs_dropped(data, cfg), "hand_check": hand_check(),
               "timing_check": timing_check(data)}
    lines = ["# Data report", ""]
    if data == "synthetic":
        lines += ["**DEMO: fake data. Never quote a number from this report.**", ""]
    for title, key, chart in SECTIONS:
        lines += [f"## {title}", ""]
        res = results[key]
        if isinstance(res, str):
            lines += [res, ""]
            continue
        chart(res).write_html(chart_dir / f"{key}.html", include_plotlyjs="cdn")
        lines += [res.round(3).to_markdown(), "", f"Chart: [data_report/{key}.html](data_report/{key}.html)", ""]

    out = root / "data_report.md"
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", choices=["synthetic", "real"], default="synthetic")
    a = ap.parse_args(argv)
    if a.data == "real":
        standins.assert_off()
    print(f"wrote {build(a.data)}")


if __name__ == "__main__":
    main()
