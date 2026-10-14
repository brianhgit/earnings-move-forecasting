"""features/history.py."""

import numpy as np
import pandas as pd
import pytest

from btb.features.history import HIST_COLS, add_history_features


def test_reproduces_the_synthetic_table(measured, events):
    """Your function on the raw measured reports must give the same inputs as the frozen table."""
    out = add_history_features(measured.copy())
    out["event_id"] = out["cik"].astype(str) + "-" + out["accession"]
    got = out.set_index("event_id").loc[events["event_id"], HIST_COLS]
    exp = events.set_index("event_id")[HIST_COLS]
    pd.testing.assert_frame_equal(got.astype(float), exp.astype(float), check_exact=False, rtol=1e-9)


def _co(cik, rows):
    return pd.DataFrame([dict(cik=cik, report_date=pd.Timestamp(r), after_date=pd.Timestamp(a),
                              cutoff_date=pd.Timestamp(c), move_adj=m) for r, a, c, m in rows])


def test_reaction_after_cutoff_does_not_count():
    # Previous report reacts Mon Jan 8, but the next report's cutoff is Fri Jan 5: must NOT be counted.
    df = _co(1, [("2024-01-05", "2024-01-08", "2023-12-29", 7.0),
                 ("2024-01-09", "2024-01-10", "2024-01-05", 3.0)])
    out = add_history_features(df).sort_values("report_date")
    assert out.iloc[1]["n_prior"] == 0
    assert np.isnan(out.iloc[1]["hist_median8"])


def test_uses_only_last_8():
    rows = [(f"2020-{m:02d}-15", f"2020-{m:02d}-16", f"2020-{m:02d}-10", float(m)) for m in range(1, 11)]
    rows.append(("2020-12-20", "2020-12-21", "2020-12-18", 99.0))
    out = add_history_features(_co(1, rows)).sort_values("report_date").iloc[-1]
    assert out["n_prior"] == 10
    assert out["hist_median8"] == pytest.approx(np.median(range(3, 11)))
    assert out["hist_max8"] == 10 and out["hist_last"] == 10


def test_companies_never_mix():
    a = _co(1, [("2021-01-10", "2021-01-11", "2021-01-08", 50.0)])
    b = _co(2, [("2021-04-10", "2021-04-12", "2021-04-09", 2.0)])
    out = add_history_features(pd.concat([a, b], ignore_index=True))
    assert out[out["cik"] == 2]["n_prior"].iloc[0] == 0
