# Every step of the project is one make command. Nothing downloads except `make data`.
PY ?= python
DATA ?= real


.PHONY: setup test status demo app data data-universe data-prices data-edgar manifest verify-data dataset \
        backtest charts lockbox forecast freeze score rerun-check

setup:            ## install pinned packages + this repo
	$(PY) -m pip install -r requirements.txt && $(PY) -m pip install -e .

test:             ## all checks (tests for unbuilt pieces show as skipped)
	$(PY) -m pytest -q

status:           ## functions not yet implemented
	@$(PY) -m btb.status

demo:             ## whole pipeline on fake data -> results/demo, live/demo_drops (works once everything is built)
	$(PY) -m btb.demo

app:              ## the forecast app
	streamlit run app/streamlit_app.py

# ---------- data (week 1) ----------
data-universe:    ## OLDID = Wikipedia revision id of the snapshot date
	$(PY) -m btb.data.universe $(OLDID)
data-prices:      ## daily prices
	$(PY) -m btb.data.prices
data-edgar:       ## SEC earnings filings
	$(PY) -m btb.data.edgar
data: data-universe data-prices data-edgar manifest

manifest:         ## checksum every raw file -> data/MANIFEST.json (commit it)
	$(PY) -m btb.repro.manifest --write
verify-data:      ## prove your raw files match the team's
	$(PY) -m btb.repro.manifest --verify

dataset:          ## build events_dev / events_lockbox / exclusions
	$(PY) -m btb.dataset.build

# ---------- modeling ----------
backtest:         ## NAME=lgbm_v1 NOTE="..." DATA=real|synthetic
	$(PY) -m btb.eval.backtest --name $(NAME) --data $(DATA) --note "$(NOTE)"
charts:           ## RUN=<run_id> DATA=real|synthetic
	$(PY) -m btb.eval.charts --run $(RUN) --data $(DATA)
lockbox:          ## once, after `git tag model-final`
	$(PY) -m btb.eval.lockbox --data real

# ---------- live ----------
forecast:         ## DROP=drop1
	$(PY) -m btb.live.forecast --drop $(DROP) --data $(DATA)
freeze:           ## DROP=drop1, then post the printed hash publicly
	$(PY) -m btb.live.freeze --drop $(DROP) --data $(DATA)
score:            ## DROP=drop1
	$(PY) -m btb.live.score --drop $(DROP) --data $(DATA)

rerun-check:      ## independent rerun from the shared snapshot
	$(MAKE) verify-data && $(MAKE) test && $(MAKE) dataset && \
	$(PY) -m btb.eval.backtest --name rerun_check --data real --note "independent rerun"
