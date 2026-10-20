"""
What git says about the functions a map shows: `git blame` on the lines of each one, once per file, for the commit
that last changed it, how many commits and people its lines come from, and the lines changed since the last commit.

git is run on the folder, never the code in it, and only to read: blame with no text conversion and no file system
monitor. A folder whose own git config names a filter command (one git would run on the files) isn't read at all.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .analysis.model import CodeFunction, Commit, History

_TIMEOUT = 20  # seconds a git command may take before its file goes without history

_WORKERS = 8  # files blamed at once

_UNCOMMITTED = "0" * 40  # the commit blame gives lines changed since the last one

_HOSTS = {"github.com": "{}/commit/{}", "gitlab.com": "{}/-/commit/{}"}  # a commit's page, by host

_SAFE = ["-c", "core.fsmonitor=false", "--no-pager"]  # no program of the folder's config runs


def _git(root: Path, *args: str) -> str | None:
    """
    What a git command prints, run in root; None when git isn't there or fails (not a repository, a file it doesn't
    track, a folder it doesn't trust).
    """
    try:
        done = subprocess.run(
            ["git", *_SAFE, "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _runs_filters(root: Path) -> bool:
    """
    Whether the folder's own git config (not the user's) names a filter command, which blame would run on its files.
    """
    found = _git(root, "config", "--show-scope", "--get-regexp", r"^filter\..*\.(clean|process)$")
    return any(line.split("\t", 1)[0] in ("local", "worktree") for line in (found or "").splitlines())


def _commit_page(remote: str) -> str:
    """
    The repository's web address with a {} for the sha, from its origin: 'https://github.com/o/r/commit/{}'.
    """
    found = re.fullmatch(r"(?:https?://(?:[^@/]+@)?|ssh://(?:[^@/]+@)?|[^@/]+@)([^/:]+)[:/](.+?)(?:\.git)?/?", remote)
    if not found or found.group(1) not in _HOSTS:
        return ""
    return _HOSTS[found.group(1)].format(f"https://{found.group(1)}/{found.group(2)}", "{}")


def _blame(root: Path, file: str, start: int, end: int) -> dict[int, tuple[str, dict[str, str]]]:
    """
    Each line from start to end of the file as it is now: line -> (the commit it comes from, that commit's headers).
    """
    out = _git(root, "blame", "--porcelain", "--no-textconv", "-L", f"{start},{end}", "--", file)
    lines: dict[int, tuple[str, dict[str, str]]] = {}
    if not out:
        return lines
    headers: dict[str, dict[str, str]] = {}
    sha = ""
    for row in out.splitlines():
        if row.startswith("\t"):
            continue
        parts = row.split(" ")
        if len(parts) >= 3 and len(parts[0]) == 40 and parts[1].isdigit() and parts[2].isdigit():
            sha = parts[0]
            headers.setdefault(sha, {})
            lines[int(parts[2])] = (sha, headers[sha])
        elif sha:
            key, _, value = row.partition(" ")
            headers[sha].setdefault(key, value)
    return lines


def _history(blamed: dict[int, tuple[str, dict[str, str]]], start: int, end: int, page: str, now: int) -> History:
    """
    A function's history from its lines' blame.
    """
    commits: dict[str, Commit] = {}
    by_author: Counter[str] = Counter()
    uncommitted = 0
    for k in range(start, end + 1):
        if k not in blamed:
            continue
        sha, said = blamed[k]
        if sha == _UNCOMMITTED:
            uncommitted += 1
            continue
        if sha not in commits:
            commits[sha] = Commit(
                sha,
                said.get("author", "?"),
                int(said.get("author-time", "0") or 0),
                said.get("summary", ""),
                page.format(sha) if page else "",
            )
        by_author[commits[sha].author] += 1
    last = max(commits.values(), key=lambda c: c.time, default=None)
    return History(
        last=last,
        commits=len(commits),
        authors=[name for name, _ in by_author.most_common()],
        first=min((c.time for c in commits.values()), default=0),
        uncommitted=uncommitted,
        now=now,
    )


def read_history(root: Path, functions: list[CodeFunction]) -> int:
    """
    Fills in each function's history from git, blaming each file once over the lines its functions take up. How many
    functions it found history for: 0 when the folder isn't in git, git isn't installed, or the folder's config would
    have git run a program of its own.
    """
    spans: dict[str, tuple[int, int]] = {}
    for f in functions:
        if f.file and f.line and f.lines:
            start, end = spans.get(f.file, (f.line, f.line + f.lines - 1))
            spans[f.file] = (min(start, f.line), max(end, f.line + f.lines - 1))
    if not spans or _git(root, "rev-parse", "--is-inside-work-tree") is None or _runs_filters(root):
        return 0
    page = _commit_page((_git(root, "remote", "get-url", "origin") or "").strip())
    now = int(time.time())
    with ThreadPoolExecutor(max_workers=min(_WORKERS, len(spans))) as pool:
        blamed = dict(zip(spans, pool.map(lambda file: _blame(root, file, *spans[file]), spans)))
    found = 0
    for f in functions:
        lines = blamed.get(f.file)
        if lines:
            f.history = _history(lines, f.line, f.line + f.lines - 1, page, now)
            found += 1
    return found
