# Decision log

Every judgment call is recorded here with its date and reason.

| Date | Decision | Why |
|---|---|---|
| 2026-10-14 | Target is market-adjusted: the stock's log move minus SPY's over the same window | A raw close-to-close move mixes in market-wide days ([AUDIT](AUDIT.md) I1) |
| 2026-10-14 | LightGBM objective is L1 | Matches the mean absolute error used for scoring; L2 targets the mean of a heavy-tailed target ([AUDIT](AUDIT.md) I2) |
| 2026-10-14 | Timing hand check includes a recall sample (30 company-quarters) | 60 found events only measure precision ([AUDIT](AUDIT.md) F1b) |
| 2026-10-14 | Uncertainty from a cluster bootstrap over report weeks | Reports in the same week share one market environment ([AUDIT](AUDIT.md) F4) |
| 2026-10-18 | EDGAR `acceptanceDateTime` timezone: UTC, converted to America/New_York (verified on NFLX 2024-07-18, NFLX 2025-01-21, NFLX 2026-07-16, TSLA 2025-10-22, TSLA 2026-01-28 after-close reports) | Raw values are 20:0xZ in summer and 21:0xZ in winter, a shift that follows daylight saving time; converted, all five are 16:0x–16:1x ET. The 2017–2020 older pages convert to 16:xx ET the same way. `ACCEPTANCE_TZ = "UTC"` in `edgar.py` |
| 2026-10-20 | EDGAR `acceptanceDateTime` changed: it now reads as Eastern time plus twice the UTC offset (8 h ahead in summer, 10 h in winter). `ACCEPTANCE_TZ = "UTC_TWICE"` converts UTC to Eastern twice | Checked 12 AAPL, NFLX and TSLA filings against the "Accepted" time on their SEC filing index pages; all 12 match after the double conversion. Example: AAPL 0000320193-22-000006 raw 2022-01-28T02:30:36Z, SEC page 2022-01-27 16:30:36 ET. Two filings are pinned in `KNOWN_ACCEPTANCE_ET`, and parsing stops if they ever disagree, so another change by the SEC cannot slip through |
| | Wikipedia revision id of the S&P 500 snapshot: 1379247819 (edit of 21:08 UTC, Oct 8, 2026; the list as of the Oct 9 snapshot date) | |
| | Price snapshot folder: `data/raw/prices/________` | |
| | Timing plan: A / B / D (precision ___/60, recall ___/30) | |
