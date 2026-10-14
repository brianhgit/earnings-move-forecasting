## What this changes

## How it was tested
- [ ] `python -m pytest -q` passes, and tests for the functions this PR implements now run instead of skip
- [ ] If this changes a table's columns, `src/btb/schema.py` is updated in the same PR
- [ ] If this changes modeling or evaluation: the backtest was rerun and its ledger row is committed (even if the result got worse)
- [ ] No data files committed; notebooks only under `notebooks/<name>/`
- [ ] Nothing reads `events_lockbox.parquet`
