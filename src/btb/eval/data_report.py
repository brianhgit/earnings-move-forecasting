"""The data report.

    python -m btb.eval.data_report          -> results/data_report.md + charts

Turns what the build and the hand checks produced into the tables and charts for
the "what we kept, what we threw out" part of the final report:

  1. Kept vs dropped reports, by reason and by year
     (data/processed/exclusions.csv + results/build_report.json)
  2. Hand-check results: precision (out of 60) and recall (out of 30), each with a
     Wilson 95% lower bound (audit/precision_audit.csv, audit/recall_audit.csv)
  3. Timing sanity check: for each report, |move on our "after" day| divided by
     |move on the next trading day|. If our windows are right, our day should be
     much bigger. Show the median of that ratio by year. (Needs a "next day" return
     column from dataset/build.py.)

Must also run on the synthetic fixtures (pass --data synthetic) so you can build
it before the real table exists. No price files go in the output (Yahoo terms):
counts, ratios and charts only.
"""

from __future__ import annotations


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    """Lower end of the Wilson score interval for a proportion."""
    raise NotImplementedError


def main(argv=None):
    raise NotImplementedError


if __name__ == "__main__":
    main()
