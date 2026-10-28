.PHONY: check lint test

check: lint test

lint:
	python -m ruff check src

test:
	python -m pytest -q src
