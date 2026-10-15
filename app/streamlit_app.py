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
    #   - read forecasts.csv from the newest drop folder under drops_dir(source) that has one
    #     (drop3 in the fake run)
    #   - a selectbox of the companies in that file, sorted by ticker (default NVDA if it's there,
    #     otherwise the first one)
    #   - two big side-by-side numbers: "The simple guess ±X%" (pred_baseline, orange) and
    #     "Our model ±Y%" (pred_model, blue), rounded to 1 decimal. Under the simple guess:
    #     "How much it usually moves". Under the model: "Expects a bigger move than usual" if
    #     pred_model > 1.1 x pred_baseline, "Expects a smaller move than usual" if < 0.9 x,
    #     otherwise "Expects about the usual move"
    #   - a dark bar at the bottom: "Actual move ±Z%" if that drop folder has a scores.csv with a
    #     row for this ticker (y_true), otherwise "Shows up after they report. Come back and see
    #     who was closer." The fake drop3 has no scores yet, so point it at drop2 once to test the
    #     actual-move branch
    st.info("TODO: one stock, two guesses")

with tab_game:
    # TODO (design C, "Beat the model"):
    #   - pick a random past report from pred_head (the locked-test predictions)
    #   - show "Can you beat our model?" and one sentence: company, report date
    #   - the visitor sets a guess with st.number_input (0 to 30, step 0.5, in %), presses Reveal
    #   - show four boxes: You (purple), Simple guess (orange), Our model (blue), Actual (gray),
    #     then one line saying who was closest (smallest |guess - actual|)
    #   - keep a running "visitors vs model" tally in st.session_state: visitor wins if strictly
    #     closer than the model, model wins if strictly closer than the visitor, ties count for nobody
    #   - a "Play again" button that picks a new report (store the current one in session_state so
    #     it doesn't change on every rerun)
    st.info("TODO: Beat the model game")

st.caption(f"Run {head_id} · commit {meta['git_sha']} · config {meta['config_hash']} · data {meta['data_hash']}")
