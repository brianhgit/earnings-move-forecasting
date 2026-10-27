# Beat the Baseline: Earnings Move Forecasting

Can a machine learning model forecast how large an S&P 500 stock's move will be after an earnings announcement more accurately than the stock's own historical typical move?

This project forecasts the **size** (not the direction) of 2-day earnings-window stock moves for S&P 500 companies. A LightGBM model is compared against a simple historical baseline on seven years of earnings reports, using a preregistered evaluation with a held-out test set that is opened once, uncertainty estimates that account for market-wide correlation, and live forecasts published before the reports they predict.

## Approach

**Target.** The market-adjusted absolute log return across the earnings announcement:

```
move = 100 × | ln(P_after / P_before) − ln(SPY_after / SPY_before) |
```

`P_before` and `P_after` are the adjusted closes immediately before and after the announcement. Announcements before the open use the previous close and that day's close. Announcements after the close use that day's close and the next day's close. Announcement times come from SEC EDGAR filing timestamps, and subtracting SPY's move over the same window removes market-wide moves.

**Baseline.** The median of the company's last 8 earnings moves.

**Model.** A LightGBM regressor trained with L1 loss, matching the mean absolute error used for scoring. It has nine inputs, all known at the Friday close before the report week:

| Input | Description |
|---|---|
| `hist_median8`, `hist_mean8`, `hist_max8`, `hist_last` | The company's last 8 completed earnings moves |
| `vol_21d`, `vol_63d` | Annualized volatility of daily returns over 1 and 3 months |
| `ret_21d`, `absret_21d` | One-month return, signed and absolute |
| `vix` | VIX close at the cutoff |

Model settings are fixed in advance in [`configs/project.yaml`](configs/project.yaml) and never tuned.

## Data

| Source | Used for |
|---|---|
| [SEC EDGAR submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Form 8-K Item 2.02 filings and their acceptance timestamps, 2017 onward |
| [yfinance](https://github.com/ranaroussi/yfinance) | Daily adjusted and raw closes for every company, SPY and ^VIX, 2016 onward |
| [Wikipedia S&P 500 list](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies) | The company universe, frozen at a fixed revision |

About 14,000 to 15,000 earnings reports from January 2019 to September 2026 after cleaning. Raw data is not committed. Every download is saved as an immutable dated snapshot, and [`data/MANIFEST.json`](data/) records its checksums so any rerun can prove it uses identical inputs.

## Evaluation design

- **Walk-forward development.** Train on everything known before a quarter, test on that quarter, then repeat for 2022Q1 through 2024Q4. A training report is used only if its move had fully played out by the earliest forecast cutoff of the test quarter.
- **Locked test set.** January 2025 to September 2026 is held out and evaluated exactly once, from a tagged commit, after the model is final.
- **Metric.** Relative improvement in mean absolute error, `1 − MAE_model / MAE_baseline`.
- **Uncertainty.** A 95% interval from a cluster bootstrap that resamples whole report weeks, since reports in the same week share one market environment.
- **Success criterion.** At least a 3% improvement, with the interval's lower bound above zero. This is fixed before any model result exists.
- **Diagnostics.**
  - The same metric with company-level clustering.
  - A shrinkage control that tests whether any gain is just pulling forecasts toward the overall median.
  - Breakdowns by sector and by VIX level.
- **Leakage controls.** Automated tests confirm that:
  - Inputs don't change when future prices are scrambled.
  - History inputs use only completed moves.
  - No training report finishes after its test quarter's cutoff.
  - A model trained on shuffled targets can't beat the baseline.
- **Live forecasts.** Before each report week, forecasts for every company are frozen and their SHA-256 fingerprint is published. Every company that reports during the window is then scored, with no selection.

The full protocol is in [`docs/PREREGISTRATION.md`](docs/PREREGISTRATION.md), and the threats to validity it addresses are in [`docs/AUDIT.md`](docs/AUDIT.md).

## Repository layout

```
configs/project.yaml     every fixed setting: dates, inputs, model parameters, evaluation rules
src/btb/
  data/                  downloads: company universe, prices, SEC filings
  dataset/               trading calendar, announcement windows, events table build
  features/              history and price inputs
  models/                baseline, LightGBM, shrinkage control
  eval/                  walk-forward splits, backtest, metrics, bootstrap, locked test, charts
  live/                  forecast, freeze and score live drops
  repro/                 data checksum manifest
  schema.py              column contracts between pipeline stages
  synthetic.py           frozen synthetic data with the real schema
app/                     Streamlit app
fixtures/                synthetic datasets and a sample run for development and tests
tests/                   unit, contract and leakage tests
docs/                    preregistration, methods audit, architecture, results format, decision log
audit/                   timing hand-check templates
results/                 run ledger and per-run predictions and metrics
```

## Getting started

Requires Python 3.11 or newer.

```bash
git clone https://github.com/brianhgit/earnings-move-forecasting
cd earnings-move-forecasting
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m pytest -q
```

Tests run entirely on synthetic data and never touch the network. Functions that are not implemented yet are reported as skipped, and `python -m btb.status` lists them.

## Running the pipeline

| Step | Command | `make` shortcut |
|---|---|---|
| Download data | `python -m btb.data.universe <revision-id>`, `python -m btb.data.prices`, `python -m btb.data.edgar` | `make data` |
| Verify data checksums | `python -m btb.repro.manifest --verify` | `make verify-data` |
| Build the events table | `python -m btb.dataset.build` | `make dataset` |
| Backtest | `python -m btb.eval.backtest --name <name> --data real` | `make backtest NAME=<name>` |
| Open the locked test (once) | `python -m btb.eval.lockbox --data real` | `make lockbox` |
| Live forecast and freeze | `python -m btb.live.forecast --drop drop2b`, then `python -m btb.live.freeze --drop drop2b` | `make forecast DROP=drop2b`, `make freeze DROP=drop2b` |
| Full pipeline on synthetic data | `python -m btb.demo` | `make demo` |
| App | `streamlit run app/streamlit_app.py` | `make app` |

Every backtest, locked-test opening and live scoring writes a run to `results/` and a row to `results/ledger.csv`, including its git commit, configuration hash and data hash. See [`docs/RESULTS_FORMAT.md`](docs/RESULTS_FORMAT.md).

## Status

In progress. Results will be reported here, including results that do not favor the model.

| | Baseline MAE | Model MAE | Improvement (95% interval) |
|---|---|---|---|
| Locked test, Jan 2025 to Sep 2026 | | | |
| Live drop, Nov 2 to 6, 2026 | | | descriptive |

## Limitations

- The universe is the S&P 500 as of October 2026, so companies that left the index before then are missing. Point-in-time index membership is not used, so the claim covers today's members only.
- Announcement times come from EDGAR filing timestamps, which can lag the actual press release. A hand check against press releases decides whether one-day windows are reliable enough to use.
- Free price data can contain errors, so missing sessions and suspicious jumps are flagged in the data report.
- Live results cover a short period of a single market environment, so they are a sanity check rather than the main evidence.

This project forecasts the size of price moves for research purposes. It is not a trading strategy or financial advice.
