"""The standard charts.

The app, the report and the slides all use these, so every picture of a result
comes from the same code and the same run files. Each function returns a
plotly.graph_objects.Figure; finish every one with _style(...) so they match.
docs/RESULTS_FORMAT.md lists what question each chart answers.

    python -m btb.eval.charts --run <run_id> --data synthetic   # writes results/.../charts/*.html

Colors are fixed per series, never by order: model = blue, baseline = orange,
shrunk baseline = aqua, actual = gray. (Checked for color-blind separation.)
"""

from __future__ import annotations

import argparse

import numpy as np  # noqa: F401
import pandas as pd
import plotly.graph_objects as go

from btb.eval import metrics as M  # noqa: F401
from btb.eval import runs

MODEL, BASE, SHRUNK = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#52514e", "#898781", "rgba(137,135,129,0.25)"
POS, NEG = "#2a78d6", "#e34948"
FONT = dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', size=13, color=INK)


def _style(fig: go.Figure, title: str, y_title: str = "", x_title: str = "", height: int = 380) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)), font=FONT, height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=56, r=16, t=56, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1), hovermode="closest",
        bargap=0.25, bargroupgap=0.08,
    )
    fig.update_xaxes(title=x_title, showgrid=False, linecolor=MUTED, tickfont=dict(color=MUTED))
    fig.update_yaxes(title=y_title, gridcolor=GRID, zeroline=True, zerolinecolor=MUTED, tickfont=dict(color=MUTED))
    return fig


def headline(met: dict, threshold: float = 0.03) -> go.Figure:
    """One dot per comparison with its 95% range as error bars, horizontal.
    Row 1 "Model vs simple guess" from met["bootstrap_week"] (blue). Row 2 "Model vs shrunk guess"
    from met["shrinkage"] if present (aqua). Vertical lines at 0 and at the 3% success bar.
    x axis: "% smaller average miss" (multiply by 100)."""
    raise NotImplementedError


def fold_mae(pred: pd.DataFrame) -> go.Figure:
    """Grouped bars per fold: average miss of the simple guess (orange) and the model (blue).
    Use metrics.by_group(pred, "fold")."""
    raise NotImplementedError


def cumulative_edge(pred: pd.DataFrame) -> go.Figure:
    """Running total over time (sorted by report_date) of
    |y - pred_baseline| - |y - pred_model|. Rising line = model pulling ahead.
    A steady climb means a real edge; one big jump means one lucky week."""
    raise NotImplementedError


def bootstrap_hist(met: dict) -> go.Figure:
    """Histogram of met["bootstrap_draws_week"] (x 100), dotted lines at the 95% range, a red
    line at 0 labeled "no improvement"."""
    raise NotImplementedError


def calibration(pred: pd.DataFrame, bins: int = 10) -> go.Figure:
    """Bin pred_model into `bins` quantile bins. Per bin: mean prediction (x) vs median actual (y).
    Add a dotted diagonal: points on it mean "when we say 6%, moves land near 6%"."""
    raise NotImplementedError


def group_improvement(pred: pd.DataFrame, col: str, title: str) -> go.Figure:
    """Horizontal bars of rel_improvement (x 100) per value of `col`, sorted. Blue if >= 0, red if < 0.
    col="vix_bucket" means: add metrics.vix_bucket(pred["vix"]) as strings first."""
    raise NotImplementedError


def ledger_progress(ledger: pd.DataFrame) -> go.Figure:
    """Every DEV run in the ledger in order (x = run #), dot at rel_improvement with its ci_low/ci_high
    as error bars, hover shows name, note and git_sha. Red line at 0. This shows how many
    things we tried before locking the model."""
    raise NotImplementedError


def stock_history(pred: pd.DataFrame, ticker: str) -> go.Figure:
    """For one ticker over time: gray bars = actual move, orange line+markers = simple guess,
    blue line+markers = model. Used by the app's "Next up" tab."""
    raise NotImplementedError



ALL = {
    "headline": lambda pred, met: headline(met),
    "fold_mae": lambda pred, met: fold_mae(pred),
    "cumulative_edge": lambda pred, met: cumulative_edge(pred),
    "bootstrap": lambda pred, met: bootstrap_hist(met),
    "calibration": lambda pred, met: calibration(pred),
    "by_sector": lambda pred, met: group_improvement(pred, "sector", "Where does the model help? By sector"),
    "by_vix": lambda pred, met: group_improvement(pred, "vix_bucket", "By market mood (VIX at cutoff)"),
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--data", choices=["synthetic", "real", "fixture"], default="real",
                    help="fixture = the frozen sample run in fixtures/demo_results")
    a = ap.parse_args(argv)
    _, pred, met = runs.load_run(a.run, a.data)
    # the fixture folder is read-only sample data, so its charts go under results/demo/
    out_root = runs.results_root("synthetic" if a.data == "fixture" else a.data)
    out = out_root / "runs" / a.run / "charts"
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in ALL.items():
        fn(pred, met).write_html(out / f"{name}.html", include_plotlyjs="cdn")
    ledger_progress(runs.read_ledger(a.data)).write_html(out / "ledger_progress.html", include_plotlyjs="cdn")
    print(f"wrote {len(ALL) + 1} charts to {out}")


if __name__ == "__main__":
    main()
