"""The LightGBM model.

LightGBM regressor (lightgbm.LGBMRegressor), trained on the 9 inputs listed under
`features` in configs/project.yaml to predict move_adj.

Rules:
  - Every setting comes from cfg["model"]["params"], plus random_state = cfg["project"]["seed"].
    Don't hard-code or tune anything. Those settings are locked in the prereg.
  - Use exactly the columns from btb.config.features(cfg), in that order.
  - Predictions can't be negative (a move size), so clip at 0.
  - Same data in, same predictions out, every time (the config already sets
    deterministic mode and 1 thread; don't override it).

Why objective "l1": we score with mean absolute error, which rewards predicting the
median, and L1 loss targets the median. The default L2 loss targets the mean, which a
heavy-tailed target pulls upward.

Done when tests/test_models.py passes.
fingerprint/save/load_model below are plumbing and already done.
"""

from __future__ import annotations

import hashlib
import pickle

import lightgbm as lgb
import pandas as pd

from btb.config import features, load  # noqa: F401  (you'll need both)


def fit(train: pd.DataFrame, cfg: dict | None = None) -> lgb.LGBMRegressor:
    """Train on every row of `train` (target column: move_adj). Return the fitted model."""
    raise NotImplementedError


def predict(model: lgb.LGBMRegressor, events: pd.DataFrame, cfg: dict | None = None) -> pd.Series:
    """One non-negative prediction per row, same index as events."""
    raise NotImplementedError


# ---------- plumbing (done) ----------
def fingerprint(model: lgb.LGBMRegressor) -> str:
    """Hash of the trained trees, so a posted forecast can be tied to one exact model."""
    dump = model.booster_.model_to_string()
    return hashlib.sha256(dump.encode()).hexdigest()[:16]


def save(model: lgb.LGBMRegressor, path) -> None:
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load_model(path) -> lgb.LGBMRegressor:
    with open(path, "rb") as f:
        return pickle.load(f)
