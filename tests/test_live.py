import json
from datetime import datetime, timezone

import pandas as pd
import pytest

import btb.live.drops as fc_mod
from btb.live import forecast, freeze, score


@pytest.fixture()
def tmp_live(tmp_path, monkeypatch):
    monkeypatch.setattr(fc_mod, "LIVE", tmp_path)
    return tmp_path


def _make_drop(events, drop_id="drop1"):
    d = fc_mod.drop_cfg(drop_id)
    lo, hi = pd.Timestamp(d["window"][0]), pd.Timestamp(d["window"][1])
    inputs = events[(events["split"] == "live") & events["report_date"].between(lo, hi)].drop_duplicates("cik")
    return d, inputs


def test_forecast_freeze_verify_score(events, tmp_live, standins):
    d, inputs = _make_drop(events)
    fc = forecast.make_forecasts("drop1", "synthetic", inputs=inputs)
    assert fc["ticker"].is_monotonic_increasing
    early = pd.Timestamp(d["post_by"]).tz_convert("UTC") - pd.Timedelta(hours=1)
    rec = freeze.freeze("drop1", "synthetic", now=early.to_pydatetime())
    assert rec["on_time"] and freeze.verify("drop1", "synthetic")

    with pytest.raises(SystemExit):
        freeze.freeze("drop1", "synthetic")      # can't re-freeze

    scored, unscored = score.eligible("drop1", inputs, "synthetic")
    assert len(scored) + len(unscored) == len(inputs)


def test_tampering_is_caught(events, tmp_live, standins):
    _, inputs = _make_drop(events)
    forecast.make_forecasts("drop1", "synthetic", inputs=inputs)
    freeze.freeze("drop1", "synthetic", now=datetime(2026, 10, 18, tzinfo=timezone.utc))
    path = tmp_live / "demo_drops" / "drop1" / "forecasts.csv"
    path.write_text(path.read_text().replace("SYN", "SYX", 1))
    assert not freeze.verify("drop1", "synthetic")
    with pytest.raises(SystemExit):
        score.eligible("drop1", inputs, "synthetic")


def test_late_drop_is_void(events, tmp_live, standins):
    _, inputs = _make_drop(events)
    forecast.make_forecasts("drop1", "synthetic", inputs=inputs)
    rec = freeze.freeze("drop1", "synthetic", now=datetime(2026, 10, 21, tzinfo=timezone.utc))
    assert not rec["on_time"]
    scored, unscored = score.eligible("drop1", inputs, "synthetic")
    assert scored.empty and (unscored["reason"] == "drop_void_late").all()


def test_reports_before_freeze_are_not_scored(events, tmp_live, standins):
    d, inputs = _make_drop(events)
    forecast.make_forecasts("drop1", "synthetic", inputs=inputs)
    freeze.freeze("drop1", "synthetic", now=datetime(2026, 10, 19, 20, tzinfo=timezone.utc))
    early = inputs.copy()
    early.loc[early.index[0], "accept_ts_et"] = pd.Timestamp("2026-10-19 07:00")
    early.loc[early.index[0], "report_date"] = pd.Timestamp("2026-10-20")  # inside window but filed before freeze
    _, unscored = score.eligible("drop1", early, "synthetic")
    assert "reported_before_freeze" in set(unscored["reason"])


def test_freeze_alone(tmp_live):
    """Freeze is plumbing (already built): hash, deadline, no re-freeze."""
    out = fc_mod.drop_dir("drop2", "synthetic")
    (out / "forecasts.csv").write_text("ticker,pred_model\nAAA,4.1\n")
    rec = freeze.freeze("drop2", "synthetic", now=datetime(2026, 10, 25, 12, tzinfo=timezone.utc))
    assert rec["on_time"] and rec["n_companies"] == 1 and freeze.verify("drop2", "synthetic")
    assert json.loads((out / "FREEZE.json").read_text())["sha256"] == rec["sha256"]
