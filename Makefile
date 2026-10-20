# The commands in CLAUDE.md, by name. `make` alone lists them.
# Everything runs with `uv run`, which first brings .venv in line with pyproject.toml and uv.lock.

VENV   := .venv
RUN    := uv run
REPO   ?= examples/orders-service
OUT    ?= /tmp/code-node-page.html
PORT   ?= 8765

.DEFAULT_GOAL := help
.PHONY: help install test lint fix try serve mermaid shots site-graph logos figures docs docs-serve package check \
	tool clean

help: ## list the targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  \033[1m%-13s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  REPO=<folder> picks the code for try, serve and mermaid (default $(REPO))"

install: ## make .venv with code-node and every dependency group in pyproject.toml
	uv sync

test: ## run the tests
	$(RUN) pytest -q

lint: ## ruff check and ruff format --check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fix: ## ruff check --fix and ruff format
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

try: ## draw REPO's page to OUT without opening it
	$(RUN) code-node $(REPO) --no-open -o $(OUT)

serve: ## serve REPO's page on PORT, redrawn on every save
	$(RUN) code-node $(REPO) --serve --port $(PORT)

mermaid: ## print REPO's graph as Mermaid
	$(RUN) code-node $(REPO) --mermaid

shots: ## remake docs/images/ (needs Chrome)
	$(RUN) python scripts/shots.py

site-graph: ## remake the home page's graph (docs/snippets/graph-trace.svg)
	$(RUN) python scripts/site_graph.py

logos: ## download the pinned logos into src/code_node/report/logos/
	$(RUN) python scripts/logos.py

figures: ## remake the docs' plugin figures (docs/images/plugins-mix-*.svg, reaches-*.svg)
	$(RUN) python scripts/docs_figures.py

docs: ## build the docs site, failing on a broken link
	$(RUN) mkdocs build --strict

docs-serve: ## serve the docs site locally
	$(RUN) mkdocs serve

package: ## build the sdist and wheel, check them, and install that wheel on your PATH
	rm -rf dist
	$(RUN) python -m build -q
	$(RUN) twine check --strict dist/*
	uv tool install --force --reinstall dist/*.whl

check: lint test try docs package ## everything CI runs

tool: ## put code-node on your PATH, live-edited
	uv tool install -e .

clean: ## remove build output and caches (keeps .venv)
	rm -rf dist build site .pytest_cache .ruff_cache .mypy_cache src/*.egg-info
	find . -path ./$(VENV) -prune -o -name __pycache__ -type d -exec rm -rf {} +
