# Preregistration: Beat the Baseline

**Status: DRAFT.** Locked by tagging the commit `prereg-v1` after the timing check (§2) and before the model is run on any real target. After that, nothing in this file changes. Any later change is written in the "Changes after locking" section with the date and reason, and both versions of the result are reported.

Settings referenced here live in `configs/project.yaml` (marked LOCKED there).

## 1. Question and claim

Can a LightGBM model using 9 simple inputs forecast the **size** of an S&P 500 stock's market-adjusted earnings-day move more accurately (lower mean absolute error) than the median of that stock's last 8 earnings moves, using only information available at the Friday close before the report week?

If the success rule in §9 is met, the claim we will make is exactly: *"On S&P 500 members as of Oct 9, 2026, over Jan 2025 to Sep 2026, our model's average miss was X% smaller than the simple guess (95% range A% to B%)."* We will not say "edge," "alpha," or anything about trading.

## 2. Event definition

An **event** is the first Form 8-K (amendments 8-K/A excluded) that lists Item 2.02 filed by a company (identified by SEC CIK) in any 45-day period. A second Item 2.02 filing within 45 days of the first is excluded and logged.

The announcement time is the filing's EDGAR acceptance time, converted to US Eastern time (the timezone of the raw field is verified on 5 known reports and recorded in DECISIONS.md).

**Plan A windows.** Accepted before 09:30 ET on a trading day: before = previous session close, after = that session's close. Accepted at or after the session close (16:00, or 13:00 on early-close days): before = that session's close, after = next session's close. Accepted on a non-trading day: treated as before-open of the next session. Accepted between 09:30 and the close: excluded and logged.

**Plan B windows.** before = close of the session before the report date, after = close of the session after it (a 2-day move; market-hours filings included). If Plan B is used, every target and history input uses this definition, the result is described as a "2-day earnings-window move," and Plan A and Plan B rows are never combined.

**Timing gate (decided before seeing any model result).** Two hand checks against company press releases:
- Precision: 60 events drawn at random (seed 2026) from our table. A check passes if our before/after closes are the right ones for the press release time.
- Recall: 30 company-quarters drawn at random (seed 2026) from universe x 2019Q1 to 2026Q3. A check passes if the company released earnings that quarter AND our table has that release with the right before/after closes (or correctly excluded it as market-hours).
- Filings: at least 90% of company-quarters have exactly one Item 2.02 filing.

Use Plan A if precision >= 57/60 AND recall >= 27/30 AND filings >= 90%. Otherwise use Plan B if, re-scored with Plan B windows, precision >= 57/60 AND recall >= 27/30. Otherwise Plan D: the project becomes a study of how reliable free earnings-timing data is, plus baseline forecasts on the 29 company-confirmed reports. We report the Wilson 95% lower bound for each proportion alongside the count.

## 3. Universe and exclusions

Companies in the S&P 500 per the Wikipedia list revision of Oct 9, 2026 (revision id in DECISIONS.md), one share class per CIK (GOOGL, FOXA, NWSA, BRK-B, BF-B kept). Events with report dates Jan 1, 2019 to Sep 30, 2026.

An event is excluded, with the reason logged, if: it falls in market hours (Plan A), it is a duplicate filing, the stock or SPY lacks an adjusted close on the before or after date, any session is missing between 63 sessions before the cutoff and the after date, a non-event daily return above 40% without a split appears in that span, or fewer than 8 earlier events of the same company had completed by the cutoff. Excluded events are excluded for both predictors. No event is excluded for any other reason, and no exclusion is decided by looking at a move.

## 4. Target

`move_adj = 100 * | ln(P_after / P_before) - ln(SPY_after / SPY_before) |`, using split- and dividend-adjusted closes. The raw move `100 * | ln(P_after / P_before) |` is reported as a side number only.

## 5. Inputs and what each forecast may see

The cutoff is the last session on or before the Friday before the report's Monday-to-Sunday week. Every input uses data from the cutoff or earlier.

Inputs: `hist_median8`, `hist_mean8`, `hist_max8`, `hist_last` (the company's last 8 completed `move_adj` values, where completed means after_date <= cutoff), `vol_21d`, `vol_63d` (annualized std of daily log returns over 21 and 63 sessions ending at the cutoff, x100), `ret_21d` and `absret_21d` (21-session log return to the cutoff, x100, signed and absolute), `vix` (VIX close on the cutoff date). Nothing else.

## 6. Predictors

- **Baseline:** `hist_median8`.
- **Model:** LightGBM regressor, objective L1 (absolute error), learning rate 0.03, 400 trees, 15 leaves, min 50 rows per leaf, lambda 1.0, no row or column sampling, deterministic mode, 1 thread, seed 2026. Never tuned.
- **Diagnostic (not a competitor):** shrunk baseline `w * hist_median8 + (1 - w) * median(training targets)`, w chosen on training rows from {0, 0.05, ..., 1} to minimize MAE.

## 7. Evaluation design

**Dev:** quarterly walk-forward, test quarters 2022Q1 to 2024Q4. For each test quarter, training uses every event whose after_date is on or before the earliest cutoff in that quarter. Every dev run is logged in `results/ledger.csv`. Dev results are used for debugging only.

**Locked test:** quarterly walk-forward over 2025Q1 to 2026Q3 with the same rule, run once from the commit tagged `model-final`. If a bug forces a rerun, the first result, the bug, and the rerun are all reported, and the headline is the rerun only if the bug is shown to be a pipeline error unrelated to model choices.

## 8. Loss, test statistic and confidence interval

Loss: absolute error in percentage points. Test statistic: relative MAE improvement, `1 - MAE_model / MAE_baseline`, over all locked-test events. Confidence interval: 95% percentile interval from a cluster bootstrap that resamples report weeks (ISO week of the report date) with replacement, 2,000 resamples, seed 2026.

Pre-specified secondary results (reported, never substituted for the headline): the same statistic with company clusters; the same statistic on events where the company was an index member at the cutoff (point-in-time list from fja05680/sp500); improvement vs the shrunk baseline with week clusters; results by sector and by VIX bucket (<15, 15-20, 20-30, 30+); win rate.

## 9. Success criterion

**The model beats the baseline** if, on the locked test, the relative MAE improvement is at least 3% AND the lower end of its 95% week-cluster interval is above 0. **The gain goes beyond shrinkage** if, in addition, the improvement over the shrunk baseline has a 95% interval lower end above 0. If the improvement exceeds 30%, we treat it as a probable leak and investigate before reporting.

Project success does not depend on model success: a clean negative result reported per this plan is a successful project.

## 10. Live protocol

Two forecast drops (cutoffs Oct 16 and Oct 23, 2026; post deadlines Mon Oct 19 21:00 PT and Sun Oct 25 21:00 PT), plus an extra demonstration drop (cutoff Nov 13) that is not part of this evaluation. Each drop forecasts every universe company with enough history, using a model trained once per drop on every event completed by the cutoff. The file is frozen and its SHA-256 posted publicly and attached to a GitHub Release before the deadline. A drop posted late is void.

An event is scored if its company has a forecast row, its EDGAR acceptance time is after the freeze, its report date is inside the drop's window (Oct 20 to 23; Oct 26 to 30), and it passes the §3 rules. Everything else is listed as unscored with a reason. Nothing is backfilled. Live results are descriptive: their interval resamples trading days and is not used for the §9 decision.

## 11. Reported no matter what

Counts kept and dropped by reason and year; both hand-check tallies; every dev run; the locked-test result and every reopening; all §8 secondary results; both live drops, scored or void.

## 12. Changes after locking

| Date | Change | Reason | Effect on results |
|---|---|---|---|
| | | | |

Locked by: ______  Commit: ______  Date: ______
