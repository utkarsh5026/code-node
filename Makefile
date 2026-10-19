# The commands in CLAUDE.md, by name. `make` alone lists them.
# Everything runs from .venv; `make install` makes it (with uv).

VENV   := .venv
PY     := $(VENV)/bin/python
BIN    := $(VENV)/bin
REPO   ?= examples/orders-service
OUT    ?= /tmp/code-node-page.html
PORT   ?= 8765

.DEFAULT_GOAL := help
.PHONY: help install docs-install test lint fix try serve mermaid shots site-graph docs docs-serve package check \
	tool clean

help: ## list the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[1m%-13s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  REPO=<folder> picks the code for try, serve and mermaid (default $(REPO))"

$(PY):
	uv venv
	uv pip install -e . -r requirements-dev.txt

install: $(PY) ## make .venv and install code-node with the dev tools

docs-install: $(PY) ## install MkDocs into .venv
	uv pip install -q -r requirements-docs.txt

test: $(PY) ## run the tests
	$(PY) -m pytest -q

lint: $(PY) ## ruff check
	$(BIN)/ruff check .

fix: $(PY) ## ruff check --fix
	$(BIN)/ruff check --fix .

try: $(PY) ## draw REPO's page to OUT without opening it
	$(BIN)/code-node $(REPO) --no-open -o $(OUT)

serve: $(PY) ## serve REPO's page on PORT, redrawn on every save
	$(BIN)/code-node $(REPO) --serve --port $(PORT)

mermaid: $(PY) ## print REPO's graph as Mermaid
	$(BIN)/code-node $(REPO) --mermaid

shots: $(PY) ## remake docs/images/ (needs Chrome)
	$(PY) scripts/shots.py

site-graph: $(PY) ## remake the home page's graph (docs/snippets/graph-trace.svg)
	$(PY) scripts/site_graph.py

docs: docs-install ## build the docs site, failing on a broken link
	$(BIN)/mkdocs build --strict

docs-serve: docs-install ## serve the docs site locally
	$(BIN)/mkdocs serve

package: $(PY) ## build the sdist and wheel, and check them as PyPI would
	rm -rf dist
	$(PY) -m build -q
	$(BIN)/twine check --strict dist/*

check: lint test try docs package ## everything CI runs

tool: ## put code-node on your PATH, live-edited
	uv tool install -e .

clean: ## remove build output and caches (keeps .venv)
	rm -rf dist build site .pytest_cache .ruff_cache .mypy_cache src/*.egg-info
	find . -path ./$(VENV) -prune -o -name __pycache__ -type d -exec rm -rf {} +
