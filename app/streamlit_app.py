"""Beat the Baseline: forecast app.

    streamlit run app/streamlit_app.py      (make app)

Reads only files the pipeline wrote. It never trains, downloads or changes anything,
so what it shows is exactly what was locked.

Where it reads from, first match wins:
  1. real results (results/, live/drops/)          once the lockbox has been opened
  2. the fake-data demo (results/demo/)            after `make demo`
  3. the frozen sample run (fixtures/demo_results/) always present, so the app can be
                                                   built before any pipeline step exists
Sources 2 and 3 show a DEMO DATA banner.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btb.eval import runs  # noqa: E402

st.set_page_config(page_title="Beat the Baseline", page_icon="📈", layout="wide")


# ---------------- plumbing (done) ----------------
def has_real() -> bool:
    led = runs.read_ledger("real")
    return not led.empty and (led["kind"] == "lockbox").any()


@st.cache_data
def load_run(run_id: str, source: str):
    """Returns (run.json dict, predictions DataFrame, metrics dict)."""
    return runs.load_run(run_id, source)


def drops_dir(source: str) -> Path:
    from btb.live.drops import drop_dir

    return drop_dir("drop1", source).parent


def pick_source() -> str:
    if has_real():
        return "real"
    if runs.latest_run("lockbox", "synthetic") or runs.latest_run("dev", "synthetic"):
        return "synthetic"
    return "fixture"


source = pick_source()
ledger = runs.read_ledger(source)
lock_id = runs.latest_run("lockbox", source)
dev_id = runs.latest_run("dev", source)
head_id = lock_id or dev_id

st.title("Can ML beat the simple guess?")
if source != "real":
    st.warning("DEMO DATA: synthetic numbers to show the layout. Not a result.")
if head_id is None:
    st.info("No runs yet. Once the pipeline works, `make demo` builds the synthetic demo this app shows.")
    st.stop()

meta, pred_head, met_head = load_run(head_id, source)

# Two tabs. Keep it simple: big numbers, few words. Detailed charts live in the report.
tab_calls, tab_game = st.tabs(["This week's calls", "Beat the model"])

with tab_calls:
    # TODO (design A, "One stock, two guesses"):
    #   - read drops_dir(source) / "drop3" / "forecasts.csv"
    #   - a selectbox of companies reporting this week (default NVDA if it's there)
    #   - two big side-by-side numbers: "The simple guess ±X%" (orange) and "Our model ±Y%" (blue),
    #     each with one short line under it ("How much it usually moves" / "Expects a bigger move than usual")
    #   - a dark bar at the bottom: "Actual move" once the company has reported (from the live scores),
    #     otherwise "Shows up after they report. Come back and see who was closer."
    st.info("TODO: one stock, two guesses")

with tab_game:
    # TODO (design C, "Beat the model"):
    #   - pick a random past report from pred_head (the locked-test predictions)
    #   - show "Can you beat our model?" and one sentence: company, report date
    #   - the visitor sets a guess (- / + buttons or st.number_input), presses Reveal
    #   - show four boxes: You, Simple guess, Our model, Actual, then one line saying who was closest
    #   - keep a running "visitors vs model" tally in st.session_state
    st.info("TODO: Beat the model game")

st.caption(f"Run {head_id} · commit {meta['git_sha']} · config {meta['config_hash']} · data {meta['data_hash']}")
