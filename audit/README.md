# Timing hand checks

Two checks of the EDGAR-derived announcement times against company press releases. Both are scored against the pass rules fixed in `docs/PREREGISTRATION.md` §2 **before** any model result exists.

## 1. Precision: 60 events
60 events are drawn at random (seed 2026) from the events table into `precision_audit.csv`. For each one:
1. Find the company's earnings press release (investor relations site, or the EX-99.1 exhibit of the 8-K).
2. Record the time it became public (newswire timestamp, ET).
3. Mark `correct_window_plan_a` = yes if the table's before/after closes are the right ones for that time. Do the same for plan B.

## 2. Recall: 30 company-quarters
30 (company, quarter) pairs are drawn at random (seed 2026) into `recall_audit.csv`. For each one:
1. Did the company release earnings that quarter? Find the release.
2. Is that release in the table (or correctly excluded as a market-hours filing), with the right window?

This catches releases the EDGAR filter misses entirely.

## 3. Market-hours exclusions
10 events excluded as "during market hours" are checked by hand. If many were actually released before the open and only filed later, plan A is discarding valid events.

## Pass rules
Plan A if precision >= 57/60 and recall >= 27/30 (and 90%+ of company-quarters have exactly one filing). Otherwise plan B with the same thresholds. Otherwise plan D. Wilson 95% lower bounds are reported with each count.
