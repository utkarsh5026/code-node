---
description: Publish a new version of code-node-graph to PyPI
argument-hint: "[patch|minor|major or a version]"
---

Publishing can't be undone (a version can be uploaded to PyPI only once), so confirm the version with the user
before the tag is pushed.

1. On `main`, up to date with origin. Run `/check`. Everything must pass.
2. Read `CHANGELOG.md`'s `## [Unreleased]` section and `git log v<last>..HEAD` (or the whole log for the first
   release). Make sure every user-visible change has a bullet. If the section is empty, stop: there's nothing to
   release.
3. Pick the version: $ARGUMENTS, or patch for fixes, minor for new commands or options (before 1.0, also for changed
   behaviour). Tell the user which and why.
4. On a branch `release/v<version>`: set `__version__` in `src/code_node/__init__.py`. In `CHANGELOG.md`, rename
   `## [Unreleased]` to `## [<version>] - <today>`, add a fresh empty `## [Unreleased]` above it, and update the
   compare links at the bottom. Commit "Release <version>", push, and open a pull request
   (`gh pr create --title "Release <version>"`).
5. After the user confirms and it's merged: `gh release create v<version> --target main --title "v<version>"
   --notes "<that version's CHANGELOG section>"`. That runs `.github/workflows/release.yml`, which builds, checks the
   tag against `__version__`, and uploads with trusted publishing. Watch it with `gh run watch`.
6. The first time only: PyPI needs a pending trusted publisher (project `code-node-graph`, repository
   `utkarsh5026/code-node`, workflow `release.yml`, environment `pypi`), and the repo needs a `pypi` environment.
   The steps are at the top of `release.yml`. Check with the user that both exist before step 5.
