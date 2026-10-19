---
description: Run everything CI runs - lint, tests, the docs build and the package checks - and fix what fails
---

Run these from the repo root and report each result. Fix failures in the code (not the tests, unless the test is wrong).

1. `.venv/bin/ruff check .` (create the venv first if it's missing: `uv venv && uv pip install -e . -r requirements-dev.txt`)
2. `.venv/bin/python -m pytest -q`
3. `.venv/bin/code-node examples/orders-service --no-open -o /tmp/code-node-check.html`: it must say 8 functions and
   4 AWS calls. If those numbers changed, say why.
4. `uv pip install -q -r requirements-docs.txt && .venv/bin/mkdocs build --strict`
5. `rm -rf dist && .venv/bin/python -m build -q && .venv/bin/twine check --strict dist/*`

Also check by reading the diff: nothing in `src/code_node/analysis/` does I/O or imports from `report/`, nothing runs
or imports the code being read, Lambda-only wording stays behind `cmap.platform == "lambda"`, and a user-visible change
has a `CHANGELOG.md` bullet under `## [Unreleased]`.
