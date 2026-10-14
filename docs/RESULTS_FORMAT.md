# How every backtest and iteration is recorded

Every time anyone runs the backtest, opens the lockbox, or scores a live drop, the code writes a **run**. You never write these files by hand, and you never delete one.

```
results/                       real data (synthetic demo runs go to results/demo/, same layout)
  ledger.csv                   one row per run, append-only, COMMITTED
  build_report.json            counts kept/dropped by reason and year
  lockbox/OPENED.json          every time the locked test was opened, and why
  runs/<run_id>/               run_id = <UTC timestamp>_<name>, e.g. 20261018-031502_lgbm_l1
    run.json                   author, git commit, dirty flag, config hash, data hash, note
    predictions.parquet        one row per scored event
    metrics.json               headline, 95% ranges, breakdowns
    charts/*.html              made by `make charts RUN=<run_id>`
```

## ledger.csv (the iteration log)

| column | meaning |
|---|---|
| run_id, created_utc, author | who ran what, when |
| kind | `dev`, `lockbox`, or `live` |
| data_source | `real` or `synthetic` |
| name, note | your label and one line on what you changed and why |
| git_sha, git_dirty | the exact code; a dirty run can't be a headline |
| config_hash, data_hash | the exact settings and the exact table |
| n_events, n_weeks | sample size and number of independent-ish clusters |
| mae_baseline, mae_model | average miss in percentage points |
| rel_improvement | 1 - mae_model / mae_baseline (0.05 = model's miss is 5% smaller) |
| ci_low, ci_high | 95% range from resampling whole weeks |
| win_rate | share of events where the model was closer |
| beats_shrinkage | model also beats the shrunk baseline (range above 0) |
| tripwire | improvement above 30%: stop and look for a leak |

Because every row carries `git_sha` and `config_hash`, any reported number can be traced to the code and settings that produced it, and the "Every dev run we tried" chart shows how many things we tried before locking.

## predictions.parquet

`event_id, ticker, sector, report_date, week_id, fold, y_true, pred_baseline, pred_model, pred_shrunk, vix, in_index_at_cutoff, n_train, model_fp`

One table shape for backtest, lockbox and live, so every chart works on all three.

## metrics.json

```
overall                      n_events, n_weeks, n_companies, mae_baseline, mae_model, rel_improvement, win_rate
bootstrap_week               point, ci_low, ci_high, n_clusters, share_above_zero      <- the headline
bootstrap_company            same, clustered by company                                <- sensitivity
shrinkage                    model vs shrunk baseline, with its own range
point_in_time_members_only   overall stats on events where the company was in the index then
by_fold, by_sector, by_vix   breakdown tables
success, tripwire            the pre-registered decision and the leak alarm
bootstrap_draws_week         the 2,000 resampled values (for the histogram)
```

## Standard charts (`src/btb/eval/charts.py`)

| chart | question it answers |
|---|---|
| headline | How much smaller is the model's miss, and how sure are we? (dot + 95% range vs 0 and the 3% bar) |
| fold_mae | Does it hold every quarter or just some? |
| cumulative_edge | Steady edge or one lucky week? |
| bootstrap | What does the uncertainty look like? |
| calibration | When we say 6%, do moves land near 6%? |
| by_sector, by_vix | Where does it help or hurt? |
| ledger_progress | Every dev run we tried, in order |
| stock_history | One ticker's moves vs both guesses (for the app) |

Colors are fixed per series everywhere: model blue, simple guess orange, shrunk guess aqua, actual gray.
