"""models/: baseline, LightGBM, shrinkage."""

import lightgbm as lgb
import numpy as np

from btb.config import features, load
from btb.models import baseline, lgbm, shrinkage


def test_baseline_is_the_median_of_last_8(events):
    np.testing.assert_allclose(baseline.predict(events).to_numpy(), events["hist_median8"].to_numpy())


def test_lgbm_uses_locked_settings_and_l1(dev_events):
    m = lgbm.fit(dev_events.head(2000))
    assert isinstance(m, lgb.LGBMRegressor)
    assert m.get_params()["objective"] == "l1"
    assert m.n_features_in_ == len(features())
    assert m.get_params()["n_estimators"] == load()["model"]["params"]["n_estimators"]


def test_lgbm_is_deterministic_and_nonnegative(dev_events):
    a = lgbm.predict(lgbm.fit(dev_events.head(2000)), dev_events.tail(300))
    b = lgbm.predict(lgbm.fit(dev_events.head(2000)), dev_events.tail(300))
    np.testing.assert_array_equal(a.to_numpy(), b.to_numpy())
    assert (a >= 0).all()


def test_shrinkage_weight_in_range_and_fit_on_train_only(dev_events):
    p = shrinkage.fit(dev_events)
    assert 0 <= p["w"] <= 1
    assert p["global_median"] == np.median(dev_events["move_adj"])
    pred = shrinkage.predict(p, dev_events)
    assert len(pred) == len(dev_events)
