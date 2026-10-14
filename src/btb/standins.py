"""Stand-ins: crude placeholders for another module's function while it's still unbuilt.

They let each module be tested before the modules it depends on are implemented:

  - the table build calls the history and price inputs
  - the live forecast calls the model and the shrinkage check

When a stand-in is on and the real function still raises NotImplementedError, the
stand-in answers instead. The moment the real function exists, it's used and the
stand-in is ignored. Stand-ins return obviously fake constant values: right shape,
meaningless numbers. They are NOT the answers, so don't copy them.

How to use them: in a test, ask for the `standins` fixture (see tests/conftest.py).
They only work inside pytest, and loading real data refuses to run while they're on,
so fake numbers can never end up in a real result.

Call a dependency through its module (`history.add_history_features(...)`, not a
bare `add_history_features(...)` imported with `from ... import`), or the stand-in
can't step in.
"""

from __future__ import annotations

import functools
import importlib
import sys
import warnings

import pandas as pd

_ACTIVE = False
_ORIGINALS: dict[tuple[str, str], object] = {}


# ---- the stand-ins (fake on purpose) ----
def _history(df: pd.DataFrame, k: int = 8) -> pd.DataFrame:
    out = df.copy()
    for c in ["hist_median8", "hist_mean8", "hist_max8", "hist_last"]:
        out[c] = 4.0
    out["n_prior"] = 8
    return out


def _price_features(prices, ticker, cutoff) -> dict[str, float]:
    return {"vol_21d": 30.0, "vol_63d": 30.0, "ret_21d": 0.0, "absret_21d": 0.0, "vix": 20.0}


class _Booster:
    @staticmethod
    def model_to_string() -> str:
        return "stand-in model"


class _StandInModel:
    booster_ = _Booster()


def _lgbm_fit(train, cfg=None):
    return _StandInModel()


def _lgbm_predict(model, events, cfg=None):
    return events["hist_median8"].astype(float)


def _shrink_fit(train):
    return {"w": 1.0, "global_median": float(train["move_adj"].median())}


def _shrink_predict(params, events):
    return events["hist_median8"].astype(float)


TARGETS = [
    ("btb.features.history", "add_history_features", _history),
    ("btb.features.price", "price_features", _price_features),
    ("btb.models.lgbm", "fit", _lgbm_fit),
    ("btb.models.lgbm", "predict", _lgbm_predict),
    ("btb.models.shrinkage", "fit", _shrink_fit),
    ("btb.models.shrinkage", "predict", _shrink_predict),
]


def _wrap(real, standin):
    @functools.wraps(real)
    def wrapper(*args, **kwargs):
        try:
            return real(*args, **kwargs)
        except NotImplementedError:
            warnings.warn(f"stand-in used for {real.__module__}.{real.__name__} (not built yet)", stacklevel=2)
            return standin(*args, **kwargs)
    return wrapper


def enable() -> None:
    global _ACTIVE
    if "pytest" not in sys.modules:
        raise RuntimeError("Stand-ins only run inside tests.")
    for mod_name, attr, standin in TARGETS:
        mod = importlib.import_module(mod_name)
        real = getattr(mod, attr)
        _ORIGINALS[(mod_name, attr)] = real
        setattr(mod, attr, _wrap(real, standin))
    _ACTIVE = True


def disable() -> None:
    global _ACTIVE
    for (mod_name, attr), real in _ORIGINALS.items():
        setattr(importlib.import_module(mod_name), attr, real)
    _ORIGINALS.clear()
    _ACTIVE = False


def active() -> bool:
    return _ACTIVE


def assert_off() -> None:
    if _ACTIVE:
        raise RuntimeError("Stand-ins are on. Real data can't be used with fake placeholder numbers.")
