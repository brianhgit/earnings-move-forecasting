# data/

Nothing in here is committed except MANIFEST.json. Get the shared raw-data snapshot, unzip it here, then run `make verify-data` to confirm it matches the checksums.

- raw/        immutable downloads, one dated folder per snapshot
- interim/    universe, filings, prices in the schema formats
- processed/  events_dev.parquet, events_lockbox.parquet, events_live.parquet, exclusions.csv
