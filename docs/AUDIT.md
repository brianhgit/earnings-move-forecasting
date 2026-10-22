# Methods audit: could we fool ourselves?

We ran the skeptical-reviewer checklist (fake signal, leakage, biased evaluation, irreproducibility) against our own plan. Every item below is ranked, explained, and tied to the smallest fix that keeps the project at one baseline vs one model. The fixes are already built into the repo or the prereg; the "Where" column says where.

**Fatal** = we can't claim a real result without fixing it. **Important** = the result is weaker or narrower without it. **Nice** = polish.

## Ranked findings

| ID | Issue | Rank | Why it matters | Smallest fix | Where |
|---|---|---|---|---|---|
| F1 | EDGAR acceptance time may not be the public release time | Fatal | Companies put out the press release on a newswire, then file the 8-K, sometimes minutes later, sometimes hours or the next morning. A 16:05 release filed at 07:30 next day gets labeled "before open" a day late, so we measure the wrong day. A 07:00 release filed at 09:45 gets labeled "market hours" and dropped. Also, Item 2.02 is used for things besides quarterly results (preliminary numbers, restatements). | Two-part hand check with pass rules fixed in advance (below). Exclude 8-K/A. Dedupe within 45 days. Verify the timezone of acceptanceDateTime before building anything on it. | `audit/`, `edgar.py`, prereg §2 |
| F1b | The 60-report hand check only measures precision | Fatal | Sampling 60 events we *found* tells us how often our window is right when we have an event (precision). It says nothing about real earnings releases we missed or wrongly dropped (recall). A filter can be 100% precise and miss a third of reports. | Add a recall check: 30 random company-quarters from the universe, look up whether a real release happened and whether our table has it with the right window. Also hand-check 10 of the "market hours" drops. | `audit/recall_audit_template.csv`, prereg §2 |
| F2 | Something the model sees wasn't knowable at the cutoff | Fatal | One leaked input (a past move that hadn't finished, a training row whose reaction happened after the forecast date) makes the backtest look better than live ever could. | One rule everywhere: inputs use data through the Friday cutoff; a past move counts only if its `after_date` <= cutoff; a training row is allowed only if its `after_date` <= the earliest cutoff in the test quarter. Checked in code every run plus tests L1 to L4. No price *levels* as inputs. | `splits.py`, `history.py`, `price.py`, `tests/test_leakage.py` |
| F3 | The "locked" test set isn't actually locked | Fatal | If anyone plots 2025-26 moves while cleaning data, or we tweak code after seeing the locked result and rerun, the test set becomes a second dev set and the headline is optimistic. | Build writes `events_dev` and `events_lockbox` as separate files. Dev code refuses lockbox rows. `make lockbox` requires a clean, `model-final`-tagged commit, refuses a second run without a written reason, and every opening is reported. Model settings are fixed in advance (no tuning). The live model can't train until the lockbox is opened, which forces the order. | `lockbox.py`, `splits.py`, `forecast.py` |
| F4 | Treating reports as independent overstates certainty | Fatal | Reports in the same week share one market mood, and the same company shows up 30 times. A per-report test would produce a range that is far too narrow and could call luck a signal. | Pre-specified week-cluster bootstrap (resample whole weeks). Company-cluster bootstrap as a sensitivity check. A practical bar: at least 3% smaller average miss. | `bootstrap.py`, prereg §8 |
| I1 | Close-to-close return includes the whole market's move | Important | On a day the S&P falls 3%, every stock "moves" 3% for reasons that have nothing to do with its earnings. | Target is market-adjusted: `100 * abs(ln(P_after/P_before) - ln(SPY_after/SPY_before))`. Raw move kept as a side number. Adjusted closes handle splits; dividends are tiny inside a 1-day window and also appear in SPY. | `configs/project.yaml`, `build.py` |
| I2 | Model trained for a different loss than we score | Important | LightGBM's default (squared error) aims at the mean of a heavy-tailed target; we score absolute error, which rewards the median. The baseline (a median) would win for a dumb reason. Our synthetic demo shows exactly this. | `objective: l1`. | `configs/project.yaml` |
| I3 | A "win" might just be shrinkage | Important | Pulling every stock's guess toward the overall median beats the raw per-stock median with no real learning. | Diagnostic predictor: per-stock median shrunk toward the global median, weight fit on training data only. We only say "beyond shrinkage" if the model also beats that (95% range above 0). | `models/shrinkage.py` |
| I4 | Survivorship: Oct 2026 list used for 2019-26 | Important | Companies that left the index (acquired, shrank, went bust) are missing, and companies that only joined later are in. That biases which kinds of stocks we test on. | Scope the claim: "S&P 500 members as of Oct 9, 2026." Point-in-time membership is not used; the bias is stated as a limitation. | `universe.py`, prereg §8 |
| I5 | Ticker changes, share classes, delistings | Important | FB became META; GOOG/GOOGL are one company with two tickers (double counting); delisted names can't be priced. | Key everything by CIK. Keep one share class per CIK (list in config). Every drop is logged with a reason. | `universe.py`, `schema.EXCLUSION_REASONS` |
| I6 | Plan B changes what we measure | Important | A two-day window adds a day of ordinary noise and measures a 2-day move, not the earnings-day move. The claim must change with it. | Plan B uses the 2-day definition for the target AND the history inputs, is never mixed with plan A rows, is chosen at the timing check before any model sees real targets, and the claim is reworded to "2-day earnings-window move." | prereg §2, §4 |
| I7 | Yahoo and EDGAR data change between downloads | Important | Re-downloads can differ (corrections, re-adjustments), so "rerun from scratch" could legitimately give different numbers and nobody could tell a bug from drift. | Immutable dated snapshots, `data/MANIFEST.json` checksums, pinned versions, fixed seed, deterministic LightGBM (`deterministic`, `force_row_wise`, 1 thread). Rerun test uses the shared snapshot and must reproduce the predictions exactly. | `repro/manifest.py`, `requirements.txt`, Makefile `rerun-check` |
| I8 | Live test leaves room for choices | Important | Picking which companies to forecast, scoring a late drop, or quietly adding reports we forgot invites cherry-picking. | Forecast every company each drop; score by code: report filed after the freeze, inside the window, company has a forecast row. Late drop = void. No backfill. Date changes don't matter because everyone is forecast. | `live/`, prereg §10 |
| I9 | Dropped reports aren't random | Important | "Market hours" filers and companies with price gaps may be different kinds of companies, so the scored set can drift from the universe. | Exclusions log with reason x year counts in the data report. | `build.py`, `exclusions.csv` |
| N1 | Holidays and 1 pm early closes | Nice | Business-day math silently shifts windows around July 3, Black Friday, Good Friday. | NYSE calendar via `exchange_calendars`; 22 hand-checked contract tests. | `tests/test_calendar_windows.py` |
| N2 | Cheap automatic timing check | Nice | If our window is right, the move on our day should dwarf the move on the day after. | In the data report: median of abs(our-day move) / abs(next-day move), by year. | data report |
| N3 | Sector labels are from the 2026 snapshot | Nice | GICS reshuffled some sectors in 2023. Only matters for the by-sector chart; sector is not a model input. | Note it in the report. | REPORT |
| N4 | 30%-improvement tripwire | Nice | Results that good on this problem usually mean a leak. | Backtest prints a warning and we stop to investigate. | `backtest.py` |

## Must fix before claiming a real signal

- [ ] Timezone of `acceptanceDateTime` verified on 5 known reports and written in DECISIONS.md
- [ ] Precision check (60 events) and recall check (30 company-quarters) done and scored against the pre-set rules
- [ ] Timing plan chosen at the gate **before** anyone runs the model on real targets
- [ ] Target is market-adjusted; history inputs use the same definition
- [ ] All leakage tests pass on the real table (L1 to L4), split check passes inside every run
- [ ] PREREGISTRATION.md tagged `prereg-v1` before the first real backtest
- [ ] LightGBM trained with L1 loss and the locked settings, no tuning
- [ ] Every dev run is in `results/ledger.csv`, including the bad ones
- [ ] Lockbox opened once from a `model-final` commit; any rerun reported next to it
- [ ] Headline uses the week-cluster 95% range and the 3% bar; company-cluster result reported alongside
- [ ] Shrinkage diagnostic reported; "beyond shrinkage" only if its range is above 0
- [ ] Independent rerun from the shared snapshot reproduces the lockbox predictions exactly

## Minimal revised experiment (still one baseline, one model)

1. **Events:** first 8-K (not 8-K/A) with Item 2.02 per company within 45 days, S&P 500 members as of Oct 9 2026, reports Jan 2019 to Sep 2026, one share class per CIK.
2. **Window:** plan A (before-open / after-close, market-hours dropped) if it passes the hand check; else plan B as a separately labeled 2-day estimand; else plan D (data-reliability study).
3. **Target:** market-adjusted absolute log move vs SPY.
4. **Predictors:** median of the last 8 completed moves vs LightGBM (L1 loss, 9 inputs, fixed settings).
5. **Dev:** quarterly walk-forward 2022Q1 to 2024Q4, everything logged.
6. **Test:** quarterly walk-forward over the locked Jan 2025 to Sep 2026 set, opened once.
7. **Inference:** relative MAE improvement, 95% week-cluster bootstrap range (2,000 resamples, seed 2026), success = point >= 3% and lower bound > 0.
8. **Diagnostics (pre-specified, not headline):** company-cluster range, shrunk baseline, by sector, by VIX bucket.
9. **Live:** one frozen drop (cutoff Oct 30, 2026) forecasting every company, scored by rule, reported as a sanity check only.

The exact preregistration wording is in [PREREGISTRATION.md](PREREGISTRATION.md).
