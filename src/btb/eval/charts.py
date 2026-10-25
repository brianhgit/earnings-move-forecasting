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
    fig = go.Figure()

    comparisons = [
        (
            "Model vs simple guess",
            met["bootstrap_week"]["point"],
            met["bootstrap_week"]["ci_low"],
            met["bootstrap_week"]["ci_high"],
            MODEL,
        )
    ]

    if "shrinkage" in met:
        comparisons.append(
            (
                "Model vs shrunk guess",
                met["shrinkage"]["rel_improvement_vs_shrunk"],
                met["shrinkage"]["ci_low"],
                met["shrinkage"]["ci_high"],
                SHRUNK,
            )
        )

    for label, point, ci_low, ci_high, color in comparisons:
        improvement = point * 100
        lower = ci_low * 100
        upper = ci_high * 100

        fig.add_trace(go.Scatter(
            x=[improvement],
            y=[label],
            mode="markers",
            name=label,
            marker=dict(color=color, size=12),
            error_x=dict(
                type="data",
                symmetric=False,
                array=[upper - improvement],
                arrayminus=[improvement - lower],
            ),
        ))

    fig.add_vline(
        x=0,
        line_dash="dash",
        line_color=MUTED,
    )

    fig.add_vline(
        x=threshold * 100,
        line_dash="dot",
        line_color=POS,
        annotation_text="3% target",
    )

    return _style(
        fig,
        title="Model improvement over baseline",
        x_title="Smaller average prediction error (%)",
    )


def fold_mae(pred: pd.DataFrame) -> go.Figure:
    """Grouped bars per fold: average miss of the simple guess (orange) and the model (blue).
    Use metrics.by_group(pred, "fold")."""
    df = M.by_group(pred, "fold")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["fold"],
        y=df["mae_baseline"],
        name="Simple guess",
        marker_color=BASE,
    ))

    fig.add_trace(go.Bar(
        x=df["fold"],
        y=df["mae_model"],
        name="Model",
        marker_color=MODEL,
    ))

    fig.update_layout(barmode="group")

    return _style(
        fig,
        title="Average prediction error by fold",
        y_title="Mean absolute error",
        x_title="Fold",
    )


def cumulative_edge(pred: pd.DataFrame) -> go.Figure:
    """Running total over time (sorted by report_date) of
    |y - pred_baseline| - |y - pred_model|. Rising line = model pulling ahead.
    A steady climb means a real edge; one big jump means one lucky week."""
    df = pred.sort_values("report_date").copy()

    baseline_error = (df["y_true"] - df["pred_baseline"]).abs()
    model_error = (df["y_true"] - df["pred_model"]).abs()

    df["cumulative_edge"] = (
        baseline_error - model_error
    ).cumsum()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["report_date"],
        y=df["cumulative_edge"],
        mode="lines",
        name="Cumulative edge",
        line=dict(color=MODEL, width=2),
    ))

    fig.add_hline(y=0, line_dash="dash", line_color=MUTED)

    return _style(
        fig,
        title="Cumulative model advantage over time",
        y_title="Cumulative error reduction",
        x_title="Report date",
    )


def bootstrap_hist(met: dict) -> go.Figure:
    """Histogram of met["bootstrap_draws_week"] (x 100), dotted lines at the 95% range, a red
    line at 0 labeled "no improvement"."""
    draws = np.asarray(met["bootstrap_draws_week"]) * 100

    ci_low = met["bootstrap_week"]["ci_low"] * 100
    ci_high = met["bootstrap_week"]["ci_high"] * 100

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=draws,
        nbinsx=40,
        name="Bootstrap improvements",
        marker_color=MODEL,
        opacity=0.75,
    ))

    fig.add_vline(
        x=ci_low,
        line_dash="dot",
        line_color=MUTED,
        annotation_text="95% CI lower",
    )

    fig.add_vline(
        x=ci_high,
        line_dash="dot",
        line_color=MUTED,
        annotation_text="95% CI upper",
    )

    fig.add_vline(
        x=0,
        line_dash="dash",
        line_color=NEG,
        annotation_text="No improvement",
    )

    return _style(
        fig,
        title="Bootstrap distribution of model improvement",
        x_title="Relative improvement (%)",
        y_title="Number of bootstrap samples",
    )


def calibration(pred: pd.DataFrame, bins: int = 10) -> go.Figure:
    """Bin pred_model into `bins` quantile bins. Per bin: mean prediction (x) vs median actual (y).
    Add a dotted diagonal: points on it mean "when we say 6%, moves land near 6%"."""
    df = pred[["pred_model", "y_true"]].dropna().copy()

    df["bin"] = pd.qcut(
        df["pred_model"],
        q=bins,
        duplicates="drop",
    )

    summary = df.groupby("bin", observed=True).agg(
        mean_prediction=("pred_model", "mean"),
        median_actual=("y_true", "median"),
    ).reset_index()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=summary["mean_prediction"],
        y=summary["median_actual"],
        mode="markers",
        name="Model",
        marker=dict(color=MODEL, size=10),
    ))

    max_value = max(
        summary["mean_prediction"].max(),
        summary["median_actual"].max(),
    )

    fig.add_trace(go.Scatter(
        x=[0, max_value],
        y=[0, max_value],
        mode="lines",
        name="Perfect calibration",
        line=dict(color=MUTED, dash="dot"),
    ))

    return _style(
        fig,
        title="Prediction calibration",
        x_title="Mean predicted move",
        y_title="Median actual move",
    )


def group_improvement(pred: pd.DataFrame, col: str, title: str) -> go.Figure:
    """Horizontal bars of rel_improvement (x 100) per value of `col`, sorted. Blue if >= 0, red if < 0.
    col="vix_bucket" means: add metrics.vix_bucket(pred["vix"]) as strings first."""
    df = pred.copy()

    if col == "vix_bucket":
        df["vix_bucket"] = M.vix_bucket(df["vix"]).astype(str)

    summary = M.by_group(df, col)
    summary = summary.sort_values("rel_improvement")

    values = summary["rel_improvement"] * 100

    colors = [
        POS if value >= 0 else NEG
        for value in values
    ]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=values,
        y=summary[col].astype(str),
        orientation="h",
        marker_color=colors,
        name="Relative improvement",
        customdata=summary["n_events"],
        hovertemplate=(
            "%{y}<br>"
            "Improvement: %{x:.2f}%<br>"
            "Events: %{customdata}<extra></extra>"
        ),
    ))

    fig.add_vline(x=0, line_dash="dash", line_color=MUTED)

    return _style(
        fig,
        title=title,
        x_title="Relative improvement (%)",
        y_title="Group",
        height=max(380, 45 * len(summary) + 100),
    )


def ledger_progress(ledger: pd.DataFrame) -> go.Figure:
    """Every DEV run in the ledger in order (x = run #), dot at rel_improvement with its ci_low/ci_high
    as error bars, hover shows name, note and git_sha. Red line at 0. This shows how many
    things we tried before locking the model."""
    df = ledger.copy()

    if "split" in df.columns:
        df = df[df["split"] == "DEV"].copy()

    df = df.reset_index(drop=True)
    df["run_number"] = np.arange(1, len(df) + 1)

    fig = go.Figure()

    if not df.empty:
        improvement = df["rel_improvement"] * 100
        lower = df["ci_low"] * 100
        upper = df["ci_high"] * 100

        hover = df.apply(
            lambda row: (
                f"Name: {row.get('name', '')}<br>"
                f"Note: {row.get('note', '')}<br>"
                f"Git SHA: {row.get('git_sha', '')}"
            ),
            axis=1,
        )

        fig.add_trace(go.Scatter(
            x=df["run_number"],
            y=improvement,
            mode="markers+lines",
            name="DEV runs",
            marker=dict(color=MODEL, size=9),
            line=dict(color=MODEL),
            error_y=dict(
                type="data",
                symmetric=False,
                array=upper - improvement,
                arrayminus=improvement - lower,
            ),
            text=hover,
            hovertemplate=(
                "Run %{x}<br>"
                "Improvement: %{y:.2f}%<br>"
                "%{text}<extra></extra>"
            ),
        ))

    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color=NEG,
    )

    return _style(
        fig,
        title="Model improvement across DEV runs",
        x_title="Run number",
        y_title="Relative improvement (%)",
    )


def stock_history(pred: pd.DataFrame, ticker: str) -> go.Figure:
    """For one ticker over time: gray bars = actual move, orange line+markers = simple guess,
    blue line+markers = model. Can be used in the app's "This week's calls" tab."""
    df = pred[pred["ticker"] == ticker].copy()
    df = df.sort_values("report_date")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["report_date"],
        y=df["y_true"],
        name="Actual",
        marker_color="#898781",
        opacity=0.5,
    ))

    fig.add_trace(go.Scatter(
        x=df["report_date"],
        y=df["pred_baseline"],
        mode="lines+markers",
        name="Simple guess",
        line=dict(color=BASE, width=2),
    ))

    fig.add_trace(go.Scatter(
        x=df["report_date"],
        y=df["pred_model"],
        mode="lines+markers",
        name="Model",
        line=dict(color=MODEL, width=2),
    ))

    return _style(
        fig,
        title=f"Prediction history: {ticker}",
        x_title="Report date",
        y_title="Absolute move",
    )



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
