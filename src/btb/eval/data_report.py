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


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    """Lower end of the Wilson score interval for a proportion."""
    raise NotImplementedError


def main(argv=None):
    raise NotImplementedError


if __name__ == "__main__":
    main()
