"""Beat the Baseline: forecast app.

    streamlit run app/streamlit_app.py      (make app)

Reads only files the pipeline wrote. It never trains, downloads or changes anything,
so what it shows is exactly what was locked.

Two tabs:
  Our live test         the newest frozen drop (live/drops/<drop>/forecasts.csv), plus the
                        real moves once that drop is scored (scores.csv). Before scoring
                        the tab is called "This week's guesses"
  Try a past report     a random report from the locked test set; the visitor guesses first

Where it reads from: real results once the lockbox has been opened, otherwise the frozen
sample run in fixtures/demo_results/ with a DEMO DATA banner.
Company names come from app/companies.csv (ticker,name), falling back to
data/interim/universe.parquet, then to the ticker itself.
"""

from __future__ import annotations

import json
import random
import re
import sys
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btb.eval import runs  # noqa: E402

st.set_page_config(page_title="Beat the Baseline", page_icon="📈", layout="centered")

# Colors stay the same on every screen (warm paper theme).
USUAL, MODEL, YOU = "#A2431A", "#1B5654", "#74398A"
TEXT, MUTED, LINE, CARD = "#2B2620", "#675C4D", "#E0D5C2", "#F2EADB"
FINE_PRINT = ("The 2-day move around the report, compared with the overall market. "
              "A student project, not investment advice.")

st.markdown(
    f"""
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
.stApp {{ font-family: 'IBM Plex Sans', Arial, sans-serif; }}
.stMarkdown p, .stButton button p, .stNumberInput input, .stSelectbox div {{ font-family: 'IBM Plex Sans', Arial, sans-serif; }}
.block-container {{ max-width: 880px; padding-top: 2.5rem; padding-bottom: 3rem; }}
.stMarkdown p, .stMarkdown li {{ font-size: 19px; line-height: 1.5; }}
[role="tablist"] {{ justify-content: center; gap: 12px; }}
button[role="tab"] {{ min-height: 44px; padding: 8px 18px; }}
button[role="tab"] * {{ font-size: 19px !important; font-weight: 600; }}
[data-testid="stExpander"] summary p {{ font-size: 18px; }}
.btb-h {{ font-family: 'Fraunces', Georgia, serif; font-weight: 600; color: {TEXT}; text-align: center; }}
.btb-big {{ font-size: 44px; line-height: 1.2; margin: 18px 0 14px; }}
.btb-q {{ font-size: 32px; line-height: 1.25; margin: 10px 0 4px; }}
.btb-mid {{ text-align: center; font-size: 19px; margin: 6px 0; }}
.btb-muted {{ color: {MUTED}; }}
.btb-usual {{ color: {USUAL}; }} .btb-model {{ color: {MODEL}; }} .btb-you {{ color: {YOU}; }}
.btb-real {{ text-align: center; margin: 18px 0 8px; }}
.btb-real .lbl {{ font-weight: 600; font-size: 19px; }}
.btb-real .num {{ font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 64px; line-height: 1.05; }}
.btb-row {{ display: flex; justify-content: space-between; align-items: baseline; padding: 10px 0;
            border-top: 1px solid {LINE}; font-size: 19px; }}
.btb-row .who {{ font-weight: 600; }}
.btb-row .val {{ font-weight: 600; font-size: 24px; }}
.btb-row .off {{ color: {MUTED}; font-size: 16px; display: inline-block; min-width: 96px; text-align: right; }}
.btb-verdict {{ font-weight: 600; font-size: 24px; margin: 12px 0 6px; text-align: center; }}
.btb-fine {{ text-align: center; font-size: 15px; color: {MUTED}; margin-top: 40px; }}
.stButton button {{ min-height: 44px; font-weight: 600; font-size: 18px; }}
.stNumberInput input {{ font-size: 20px; min-height: 44px; }}
@media (max-width: 640px) {{
  .btb-big {{ font-size: 30px; }} .btb-q {{ font-size: 25px; }} .btb-real .num {{ font-size: 52px; }}
}}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------- data ----------------
def has_real() -> bool:
    led = runs.read_ledger("real")
    return not led.empty and (led["kind"] == "lockbox").any()


SOURCE = "real" if has_real() else "fixture"
DROPS = {"real": ROOT / "live" / "drops", "fixture": ROOT / "fixtures" / "demo_results" / "live"}[SOURCE]

_SUFFIX = re.compile(
    r"(,?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.|plc|PLC|Ltd\.?|Limited|N\.V\.|S\.A\.|AG|SE|Holdings?|Group|Technologies|Systems))+$"
)


def short_name(name: str) -> str:
    name = re.sub(r"\s*\(.*?\)\s*$", "", str(name)).strip()
    cut = _SUFFIX.sub("", name).strip(" ,")
    return cut or name


@st.cache_data
def company_names() -> dict[str, str]:
    csv = ROOT / "app" / "companies.csv"
    uni = ROOT / "data" / "interim" / "universe.parquet"
    if csv.exists():
        df = pd.read_csv(csv)
    elif uni.exists():
        df = pd.read_parquet(uni, columns=["ticker", "name"])
    else:
        return {}
    return {str(t): short_name(n) for t, n in zip(df["ticker"], df["name"])}


def name_of(ticker: str) -> str:
    return company_names().get(ticker, ticker)


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def pct(x: float) -> str:
    return f"{x:.1f}%"


@st.cache_data
def newest_drop() -> dict | None:
    """The most recently frozen drop folder that has a forecasts.csv."""
    found = []
    for d in DROPS.glob("*"):
        if not (d / "forecasts.csv").exists():
            continue
        freeze = {}
        if (d / "FREEZE.json").exists():
            freeze = json.loads((d / "FREEZE.json").read_text())
        found.append((freeze.get("frozen_utc", ""), d.name, d, freeze))
    if not found:
        return None
    _, drop_id, d, freeze = max(found)
    fc = pd.read_csv(d / "forecasts.csv")
    nf = pd.read_csv(d / "not_forecast.csv") if (d / "not_forecast.csv").exists() else pd.DataFrame(columns=["ticker"])
    sc = pd.read_csv(d / "scores.csv") if (d / "scores.csv").exists() else None
    return {"id": drop_id, "freeze": freeze, "forecasts": fc, "not_forecast": nf, "scores": sc}


@st.cache_data
def locked_test():
    """(predictions, metrics) of the locked test set run."""
    run_id = runs.latest_run("lockbox", SOURCE)
    if run_id is None:
        return None, None
    _, pred, met = runs.load_run(run_id, SOURCE)
    pred = pred.dropna(subset=["y_true", "pred_model", "pred_baseline"]).reset_index(drop=True)
    return pred, met


# ---------------- wording rules ----------------
def guess_sentence(name: str, usual: float, model: float, past: bool = False) -> str:
    ratio = model / usual if usual > 0 else 1.0
    if ratio < 0.9:
        how = "a smaller jump"
    elif ratio > 1.1:
        how = "a bigger jump"
    else:
        how = "about the same"
    return (f"{escape(possessive(name))} stock usually jumps about "
            f"<span class='btb-usual'>{pct(usual)}</span> after earnings. "
            f"Our model {'guessed' if past else 'guesses'} {how}, <span class='btb-model'>{pct(model)}</span>.")


def context_sentence(vol_21d: float, vol_63d: float, vix: float, past: bool = False) -> str:
    text = _context_now(vol_21d, vol_63d, vix)
    if past:
        text = ("Before the report, " + text[0].lower() + text[1:]).replace(" lately", "")
        text = text.replace("has been", "had been").replace("so has", "so had")
    return text


def _context_now(vol_21d: float, vol_63d: float, vix: float) -> str:
    r = vol_21d / vol_63d if vol_63d and vol_63d > 0 else 1.0
    stock = "calm" if r < 0.85 else ("jumpy" if r > 1.15 else "normal")
    market = "calm" if vix < 20 else ("a little nervous" if vix <= 30 else "nervous")
    if stock == "calm" and market == "calm":
        return "The stock has been calmer than usual lately, and so has the market."
    if stock == "jumpy" and market == "nervous":
        return "The stock has been jumpier than usual lately, and the market has been nervous."
    first = {"calm": "The stock has been calmer than usual lately",
             "jumpy": "The stock has been jumpier than usual lately",
             "normal": "The stock has been about as jumpy as usual lately"}[stock]
    second = {"calm": "the market has been calm",
              "a little nervous": "the market has been a little nervous",
              "nervous": "the market has been nervous"}[market]
    return f"{first}, and {second}."


def result_rows(real: float, entries: list[tuple[str, str, float]]) -> tuple[str, str]:
    """entries: (label, css class, guess). Returns (rows html, who was closest)."""
    # Compare on the rounded numbers people see, so a tie on screen is a tie.
    offs = [round(abs(round(g, 1) - round(real, 1)), 1) for _, _, g in entries]
    rows = "".join(
        f"<div class='btb-row'><span class='who {c}'>{escape(lbl)}</span>"
        f"<span><span class='val {c}'>{pct(g)}</span> <span class='off'>off by {off:.1f}</span></span></div>"
        for (lbl, c, g), off in zip(entries, offs)
    )
    best = min(offs)
    winners = [lbl for (lbl, _, _), off in zip(entries, offs) if off == best]
    if len(winners) == 1:
        w = winners[0]
        verdict = "You were closest!" if w == "You" else f"{w} was closest."
    else:
        names = ["you" if w == "You" else w.lower() for w in winners]
        joined = " and ".join(names) if len(names) == 2 else ", ".join(names[:-1]) + " and " + names[-1]
        verdict = f"Tie: {joined} were equally close."
    return rows, verdict


def day(ts) -> str:
    """'Nov 2' (strftime's %-d doesn't work on Windows)."""
    ts = pd.Timestamp(ts)
    return f"{ts:%b} {ts.day}"


def fine_print():
    st.markdown(f"<div class='btb-fine'>{FINE_PRINT}</div>", unsafe_allow_html=True)


# ---------------- page ----------------
if SOURCE != "real":
    st.warning("DEMO DATA: sample numbers to show the layout. Not a result.")

drop = newest_drop()
pred_lock, met_lock = locked_test()

graded = drop is not None and drop["scores"] is not None and not drop["scores"].empty
tab_week, tab_past = st.tabs(["Our live test" if graded else "This week's guesses", "Try a past report"])

# ---- Tab 1 ----
with tab_week:
    if drop is None:
        st.info("No forecasts have been locked in yet.")
    else:
        fc = drop["forecasts"].copy()
        fc["name"] = fc["ticker"].map(name_of)
        nf_tickers = [t for t in drop["not_forecast"]["ticker"].astype(str) if t not in set(fc["ticker"])]
        options = sorted(list(fc["ticker"]) + nf_tickers, key=lambda t: name_of(t).lower())
        reported = sorted(set(drop["scores"]["ticker"]) & set(options), key=lambda t: name_of(t).lower()) if graded else []
        window = drop["freeze"].get("window")
        if graded and window:
            st.markdown(
                f"<p class='btb-mid btb-muted'>On {day(pd.Timestamp(drop['freeze']['frozen_utc']).tz_convert('America/Los_Angeles'))} we locked in a guess for every company. "
                f"Then {len(reported)} of them reported earnings from {day(window[0])} to {day(window[1])}. "
                "Pick one to see how we did.</p>",
                unsafe_allow_html=True,
            )
        if "PLTR" in options and (not graded or "PLTR" in reported):
            default = "PLTR"
        else:
            default = reported[0] if reported else options[0]
        ticker = st.selectbox(
            "Pick a company", options, index=options.index(default),
            format_func=lambda t: f"{name_of(t)} ({t})", label_visibility="collapsed",
            placeholder="Search for a company",
        )
        name = name_of(ticker)
        row = fc[fc["ticker"] == ticker]

        if row.empty:
            st.markdown(f"<div class='btb-h btb-big'>{escape(name)}</div>", unsafe_allow_html=True)
            st.markdown(
                f"<p class='btb-mid'>We didn't make a guess for {escape(name)}. It has fewer than 8 past "
                "earnings reports in our data, and the usual jump needs 8 to work out.</p>",
                unsafe_allow_html=True,
            )
        else:
            r = row.iloc[0]
            usual, model = float(r["pred_baseline"]), float(r["pred_model"])
            sc = drop["scores"]
            scored = sc[sc["ticker"] == ticker] if sc is not None else pd.DataFrame()
            st.markdown(f"<div class='btb-h btb-big'>{guess_sentence(name, usual, model, past=not scored.empty)}</div>",
                        unsafe_allow_html=True)
            st.markdown(f"<p class='btb-mid btb-muted'>{context_sentence(r['vol_21d'], r['vol_63d'], r['vix'], past=not scored.empty)}</p>",
                        unsafe_allow_html=True)

            if not scored.empty:
                real = float(scored.iloc[-1]["y_true"])
                rows, verdict = result_rows(real, [("Our model", "btb-model", model),
                                                   ("Its usual jump", "btb-usual", usual)])
                st.markdown(
                    f"<div class='btb-real'><div class='lbl'>The real jump</div><div class='num'>{pct(real)}</div></div>"
                    f"{rows}<div class='btb-verdict'>{verdict}</div>",
                    unsafe_allow_html=True,
                )
            elif sc is not None and window:
                st.markdown(
                    f"<p class='btb-mid'>{escape(name)} didn't report during our test week "
                    f"({day(window[0])} to {day(window[1])}), "
                    "so this guess never got checked.</p>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"<p class='btb-mid'>We'll see which number was closer after {escape(name)} reports.</p>",
                            unsafe_allow_html=True)

        frozen = drop["freeze"].get("frozen_utc")
        if frozen and not graded:
            when = pd.Timestamp(frozen).tz_convert("America/Los_Angeles")
            st.markdown(f"<p class='btb-mid btb-muted' style='font-size:16px;margin-top:22px'>"
                        f"All {len(fc)} guesses were locked in on {day(when)}, {when.year}, before any of these reports came out.</p>",
                        unsafe_allow_html=True)

        sc = drop["scores"]
        if sc is not None and not sc.empty:
            with st.expander("How the whole week went"):
                mae_m = (sc["y_true"] - sc["pred_model"]).abs().mean()
                mae_b = (sc["y_true"] - sc["pred_baseline"]).abs().mean()
                closer = ((sc["y_true"] - sc["pred_model"]).abs() < (sc["y_true"] - sc["pred_baseline"]).abs()).mean()
                st.markdown(
                    f"{len(sc)} companies reported that week. On average our model was off by "
                    f"**{mae_m:.2f}** points and the usual jump by **{mae_b:.2f}**. "
                    f"Our model was closer for {closer:.0%} of them."
                )
                st.markdown("One week can be luck, so the bigger test below is the one we trust more.")

        if met_lock:
            with st.expander("How it works"):
                o, b = met_lock["overall"], met_lock["bootstrap_week"]
                st.markdown(
                    "**Its usual jump** is the median size of the company's last 8 earnings moves. "
                    "**Our model** is a LightGBM model that also looks at how jumpy the stock has been lately "
                    "and how nervous the market is (VIX)."
                )
                st.markdown(
                    f"Before this week, we locked the model and tested it once on {o['n_events']:,} past reports "
                    f"it had never seen. Our model missed by {o['mae_model']:.2f} points on average and the usual "
                    f"jump by {o['mae_baseline']:.2f}. That's {b['point']:.1%} smaller misses "
                    f"(range {b['ci_low']:.1%} to {b['ci_high']:.1%}), short of the 3% goal we set beforehand. "
                    f"Our model was closer about {o['win_rate']:.0%} of the time."
                )
                st.markdown("A move is the 2-day stock move around the report minus the overall market's move, "
                            "size only.")
    fine_print()

# ---- Tab 2 ----
with tab_past:
    if pred_lock is None or pred_lock.empty:
        st.info("No past reports to show yet.")
    else:
        ss = st.session_state
        if "past_idx" not in ss:
            ss.past_idx = random.randrange(len(pred_lock))
            ss.revealed = False
            ss.guess_key = 0

        p = pred_lock.iloc[ss.past_idx]
        pname = name_of(str(p["ticker"]))
        st.markdown(
            f"<div class='btb-h btb-q'>{escape(pname)} shared its earnings on "
            f"{day(p['report_date'])}, {pd.Timestamp(p['report_date']).year}. How big was the jump?</div>",
            unsafe_allow_html=True,
        )
        st.markdown("<p class='btb-mid btb-muted' style='font-size:17px'>Up or down doesn't matter, just the size.</p>",
                    unsafe_allow_html=True)

        if not ss.revealed:
            _, mid, _ = st.columns([1, 2, 1])
            with mid:
                with st.form(key=f"guess_form_{ss.guess_key}", border=False):
                    g_col, b_col = st.columns([3, 2], vertical_alignment="bottom")
                    with g_col:
                        guess = st.number_input("Your guess, in %", min_value=0.0, max_value=100.0, value=None,
                                                step=0.5, format="%.1f", placeholder="e.g. 4.5")
                    with b_col:
                        show = st.form_submit_button("Show me", type="primary", use_container_width=True)
                if show:
                    if guess is None:
                        st.caption("Type a number first, like 4.5.")
                    else:
                        ss.revealed, ss.guess = True, float(guess)
                        st.rerun()

        if ss.revealed:
            real = float(p["y_true"])
            rows, verdict = result_rows(real, [
                ("You", "btb-you", ss.guess),
                ("Our model", "btb-model", float(p["pred_model"])),
                ("Its usual jump", "btb-usual", float(p["pred_baseline"])),
            ])
            st.markdown(
                f"<div class='btb-real'><div class='lbl'>The real jump</div><div class='num'>{pct(real)}</div></div>"
                f"{rows}<div class='btb-verdict'>{verdict}</div>",
                unsafe_allow_html=True,
            )
            _, c, _ = st.columns([1, 2, 1])
            with c:
                if st.button("Try another report", use_container_width=True):
                    old = ss.past_idx
                    while len(pred_lock) > 1 and ss.past_idx == old:
                        ss.past_idx = random.randrange(len(pred_lock))
                    ss.revealed = False
                    ss.guess_key += 1
                    st.rerun()
    fine_print()
