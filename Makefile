PYTHON ?= python3.11
PREVIEW_PORT ?= 8766
export PYTHONDONTWRITEBYTECODE = 1

.PHONY: install test test-python test-dashboard lint preview validate publish

install:
	$(PYTHON) -m pip install -r requirements.lock
	npm ci --ignore-scripts

test: test-python test-dashboard

test-python:
	$(PYTHON) -m pytest -q -p no:cacheprovider

test-dashboard:
	npm run check
	npm test

lint:
	$(PYTHON) -m ruff check --no-cache .

preview:
	$(PYTHON) -m http.server $(PREVIEW_PORT) -d dashboard

validate:
	$(PYTHON) -c "from pathlib import Path; from ufc_mentions.payload_validation import load_payload; load_payload(Path('dashboard/data.js')); print('Dashboard data passed validation')"

publish: validate
	$(PYTHON) scripts/live/publish_site.py
