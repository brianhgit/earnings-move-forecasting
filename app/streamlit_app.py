"""Beat the Baseline: showcase app.

    streamlit run app/streamlit_app.py      (make app)

Reads only files the pipeline wrote. It never trains, downloads or changes anything,
so what it shows is exactly what was locked. The page itself is app/page.html; this file
gathers the numbers, drops them into the page and shows it full screen.

Data it reads:
  live/drops/<newest scored drop>/forecasts.csv + scores.csv   "Our live test"
  results/runs/<lockbox run>/predictions.parquet               "Try a past report"
  app/past_clues.csv                                           last 8 moves and jumpiness for each past report
  results/runs/<lockbox run>/metrics.json                      the locked-test result
  app/companies.csv                                            ticker,name (from the universe file)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(ROOT / "src"))

from btb.eval import runs  # noqa: E402

st.set_page_config(page_title="Beat the Baseline", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

# Let the page fill the window; it scrolls inside its own frame.
st.markdown(
    """
<style>
header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
iframe { height: 100vh !important; display: block; border: 0; }
</style>
""",
    unsafe_allow_html=True,
)

_SUFFIX = re.compile(
    r"(,?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.|plc|PLC|Ltd\.?|Limited|N\.V\.|S\.A\.|AG|SE"
    r"|Holdings?|Group|Technologies|Systems))+$"
)
# Names that read badly after the general rule. Add more here if one looks off on screen.
NAME_FIX = {"AIG": "AIG", "IBM": "IBM"}


def short_name(ticker: str, name: str) -> str:
    if ticker in NAME_FIX:
        return NAME_FIX[ticker]
    name = re.sub(r"\s*\(.*?\)\s*$", "", str(name)).strip()
    cut = _SUFFIX.sub("", name).strip(" ,")
    return cut or name


@st.cache_data
def build_data() -> tuple[dict, bool]:
    """Everything the page needs, as one JSON-ready dict. Second value: real data or demo."""
    led = runs.read_ledger("real")
    real = not led.empty and (led["kind"] == "lockbox").any()
    source = "real" if real else "fixture"

    names = {}
    if (APP / "companies.csv").exists():
        df = pd.read_csv(APP / "companies.csv")
        names = {str(t): short_name(str(t), n) for t, n in zip(df["ticker"], df["name"])}

    # Live test: the newest frozen drop that has been scored.
    drops = ROOT / "live" / "drops" if real else ROOT / "fixtures" / "demo_results" / "live"
    live, found = [], []
    for d in drops.glob("*"):
        if (d / "forecasts.csv").exists() and (d / "scores.csv").exists():
            freeze = d / "FREEZE.json"
            frozen = json.loads(freeze.read_text()).get("frozen_utc", "") if freeze.exists() else ""
            found.append((frozen, d.name, d))
    if found:
        d = max(found)[2]
        fc = pd.read_csv(d / "forecasts.csv").merge(pd.read_csv(d / "scores.csv")[["ticker", "y_true"]], on="ticker")
        for r in fc.itertuples():
            live.append({"t": r.ticker, "n": names.get(r.ticker, r.ticker), "u": round(r.pred_baseline, 3),
                         "m": round(r.pred_model, 3), "v21": round(r.vol_21d, 3), "v63": round(r.vol_63d, 3),
                         "vix": round(r.vix, 2), "y": round(r.y_true, 3)})
        live.sort(key=lambda c: c["n"].lower())

    # Past reports: the locked test set, with the clues each report had beforehand.
    past, met = [], {}
    run_id = runs.latest_run("lockbox", source)
    if run_id:
        _, pred, m = runs.load_run(run_id, source)
        o, b = m["overall"], m["bootstrap_week"]
        met = {"n": o["n_events"], "mm": o["mae_model"], "mb": o["mae_baseline"], "pt": b["point"],
               "lo": b["ci_low"], "hi": b["ci_high"], "wr": o["win_rate"]}
        if (APP / "past_clues.csv").exists():
            clues = pd.read_csv(APP / "past_clues.csv")
            pr = pred.merge(clues, on="event_id").dropna(subset=["y_true", "pred_model", "pred_baseline"])
            for r in pr.itertuples():
                last8 = [round(float(x), 1) for x in str(r.last8).split()]
                ratio = round(r.vol_21d / r.vol_63d, 3) if r.vol_63d else 1.0
                past.append([r.ticker, str(pd.Timestamp(r.report_date).date()), round(r.y_true, 2),
                             round(r.pred_model, 2), round(r.pred_baseline, 2), last8, ratio, round(r.vix, 1)])
    return {"live": live, "past": past, "names": names, "met": met}, real


data, is_real = build_data()
if not is_real:
    st.warning("DEMO DATA: sample numbers to show the layout. Not a result.")
if not data["live"] or not data["past"]:
    st.info("Some results are missing (scores.csv, past_clues.csv or the lockbox run). The page shows what it can.")

page = (APP / "page.html").read_text(encoding="utf-8")
components.html(page.replace("__DATA__", json.dumps(data, separators=(",", ":")), 1), height=900, scrolling=True)
