"""eval/charts.py and eval/data_report.py."""

import plotly.graph_objects as go
import pytest

from btb.eval import charts, metrics
from btb.eval.data_report import wilson_lower


@pytest.fixture(scope="module")
def pred(fake_pred):
    return fake_pred


@pytest.mark.parametrize("name", ["fold_mae", "cumulative_edge", "calibration"])
def test_pred_charts_return_figures(pred, name):
    fig = getattr(charts, name)(pred)
    assert isinstance(fig, go.Figure) and len(fig.data) >= 1


def test_group_and_stock_charts(pred):
    assert len(charts.group_improvement(pred, "sector", "x").data) >= 1
    assert len(charts.group_improvement(pred, "vix_bucket", "x").data) >= 1
    assert len(charts.stock_history(pred, pred["ticker"].iloc[0]).data) >= 2


def test_metric_charts(pred):
    met = metrics.evaluate(pred)
    assert len(charts.headline(met).data) >= 1
    assert len(charts.bootstrap_hist(met).data) >= 1


def test_wilson_lower():
    assert wilson_lower(57, 60) == pytest.approx(0.863, abs=0.002)
    assert wilson_lower(0, 30) == pytest.approx(0.0, abs=1e-9)
