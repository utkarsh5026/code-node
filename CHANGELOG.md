# Changelog

Every change a user would notice, newest first ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)). Versions
follow [Semantic Versioning](https://semver.org/); before 1.0, a minor version may change what a command does.

## [Unreleased]

## [0.1.0] - 2026-10-19

### Added

- `code-node [folder]` reads a folder of Python code with `ast` (nothing is run) and opens a page showing how it works
  from an entry point: a graph of what comes in, who calls whom and what each path reaches (AWS calls with their IAM
  permissions, HTTP requests, environment variables), each call step by step, findings, and tables.
- Entry points are found for you: `pyproject.toml` console scripts, Lambda handlers, FastAPI / Flask apps (each
  route), Typer apps (each command), what runs under `if __name__ == "__main__":`, and functions named `main`.
  When there are several, it asks which one.
- Start from a file with `code-node path/to/main.py` or `code-node main.py:function` (or `Class.method`), from a
  dotted name with `-e pkg.cli.main`, or search by part of a name with `-e save`.
- `code-node --serve` puts the page on http://localhost:8765 and redraws it whenever a `.py` file changes. The
  browser reloads at the same scroll position, and a page that can't be drawn says why until the next save.
- `--all` draws every function however deep; `--depth` and `--functions` set the limits; `--mermaid` prints the
  graph as Mermaid; `--list` lists the entry points.

[Unreleased]: https://github.com/utkarsh5026/code-node/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/utkarsh5026/code-node/releases/tag/v0.1.0
