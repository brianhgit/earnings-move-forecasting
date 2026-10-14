import pytest

from btb import synthetic


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """A test that hits an unbuilt stub (NotImplementedError) shows as SKIPPED with
    the stub's name, not FAILED. So CI stays green while the team builds, and
    `make status` lists exactly what's left. Once your function exists, its tests
    run for real and must pass."""
    outcome = yield
    rep = outcome.get_result()
    if call.excinfo is not None and call.excinfo.errisinstance(NotImplementedError):
        tb = call.excinfo.traceback
        where = next((e for e in reversed(tb) if "/src/btb/" in str(e.path)), tb[-1])
        rep.outcome = "skipped"
        rep.longrepr = (str(where.path), where.lineno + 1, f"not built yet: {where.frame.code.name} in {where.path.name}")


def call_or_skip(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip(f"not built yet: {fn.__name__} in {fn.__module__}")


@pytest.fixture(scope="session")
def events():
    return synthetic.events("test")


@pytest.fixture(scope="session")
def measured():
    return synthetic.measured("test")


@pytest.fixture(scope="session")
def dev_events(events):
    return events[events["split"].isin(["train_only", "dev"])].reset_index(drop=True)


@pytest.fixture(scope="session")
def null_events():
    """A world where the inputs carry no information beyond history."""
    ev = synthetic.events("null")
    return ev[ev["split"].isin(["train_only", "dev"])].reset_index(drop=True)


@pytest.fixture()
def standins():
    """Fill in for not-yet-implemented dependencies with fake constants (see src/btb/standins.py).
    The module under test always runs for real."""
    from btb import standins as s

    s.enable()
    yield
    s.disable()


@pytest.fixture(scope="session")
def fake_pred(events):
    """A fake "predictions" table built straight from the fixture, no model needed,
    so scoring can be tested without a trained model."""
    import numpy as np

    rng = np.random.default_rng(0)
    p = events[events["split"] == "dev"].copy()
    p["fold"] = p["report_date"].dt.year.astype(str) + "Q" + p["report_date"].dt.quarter.astype(str)
    p["y_true"] = p["move_adj"]
    p["pred_baseline"] = p["hist_median8"]
    p["pred_model"] = 0.8 * p["hist_median8"] + 0.2 * p["move_adj"] + rng.normal(0, 0.3, len(p)).clip(0)
    p["pred_shrunk"] = 0.9 * p["hist_median8"] + 0.1 * p["move_adj"].median()
    return p.reset_index(drop=True)
