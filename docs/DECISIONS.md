# Decision log

Every judgment call is recorded here with its date and reason.

| Date | Decision | Why |
|---|---|---|
| 2026-10-14 | Target is market-adjusted: the stock's log move minus SPY's over the same window | A raw close-to-close move mixes in market-wide days ([AUDIT](AUDIT.md) I1) |
| 2026-10-14 | LightGBM objective is L1 | Matches the mean absolute error used for scoring; L2 targets the mean of a heavy-tailed target ([AUDIT](AUDIT.md) I2) |
| 2026-10-14 | Timing hand check includes a recall sample (30 company-quarters) | 60 found events only measure precision ([AUDIT](AUDIT.md) F1b) |
| 2026-10-14 | Uncertainty from a cluster bootstrap over report weeks | Reports in the same week share one market environment ([AUDIT](AUDIT.md) F4) |
| | EDGAR `acceptanceDateTime` timezone: ___ (verified on ___) | |
| | Wikipedia revision id of the S&P 500 snapshot: ___ | |
| | Price snapshot folder: `data/raw/prices/________` | |
| | Timing plan: A / B / D (precision ___/60, recall ___/30) | |
