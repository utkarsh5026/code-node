---
description: Run everything CI runs - lint, tests, the docs build and the package checks - and fix what fails
---

Run these from the repo root and report each result. Fix failures in the code (not the tests, unless the test is wrong).

1. `uv run ruff check .` (`uv run` makes or updates `.venv` from `pyproject.toml` and `uv.lock` first)
2. `uv run pytest -q`
3. `uv run code-node examples/orders-service --no-open -o /tmp/code-node-check.html`: it must say 8 functions and
   4 AWS calls. If those numbers changed, say why.
4. `uv run mkdocs build --strict`
5. `rm -rf dist && uv run python -m build -q && uv run twine check --strict dist/*`

Also check by reading the diff: nothing in `src/code_node/analysis/` does I/O or imports from `report/`, nothing runs
or imports the code being read, Lambda-only wording stays in `src/code_node/platforms/aws_lambda.py`, and a user-visible change
has a `CHANGELOG.md` bullet under `## [Unreleased]`.
