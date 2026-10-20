"""
What git says about a function, as HTML: who changed it last and when, with a link to the commit when the repository
is on GitHub or GitLab, how many commits and people its lines come from, and its lines not committed yet. The same
in the graph's hover card and the walk's card, and in the graph's panel line by line, beside its code.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..kit.text import _esc

from ..analysis.model import Commit, History


def history_html(history: History | None, short: bool = False) -> str:
    """
    The function's history as a few lines, or '' without one. short: the last change alone, for a hover card.
    """
    if history is None or not (history.last or history.uncommitted):
        return ""
    said = []
    last = history.last
    if last:
        day = datetime.fromtimestamp(last.time, timezone.utc).strftime("%Y-%m-%d")
        sha = f"<code>{_esc(last.short)}</code>"
        if last.url and not short:
            sha = f'<a href="{_esc(last.url)}" target="_blank" rel="noopener" title="The commit">{sha} ↗</a>'
        said.append(
            f'Last changed <b title="{day}">{_esc(history.ago(last.time))}</b> by {_esc(last.author)} in {sha}'
            + (f": <q>{_esc(last.subject)}</q>" if last.subject else "")
        )
        if history.commits > 1 and not short:
            people = f"{len(history.authors)} people" if len(history.authors) > 1 else _esc(history.authors[0])
            said.append(
                f"Its lines come from {history.commits} commits by {people}, the oldest "
                f"{_esc(history.ago(history.first))}"
            )
    if history.uncommitted:
        changed = f"{history.uncommitted} line{'' if history.uncommitted == 1 else 's'} changed since the last commit"
        said.append(f'<span class="cnhu">{changed if last else "Not committed yet"}</span>')
    return '<div class="cnh">' + "".join(f"<p>{line}</p>" for line in said) + "</div>"


_AGES = 4  # shades of a line's bar, oldest to newest


def blame_keys(history: History) -> dict[str, int]:
    """
    The commits its lines come from, oldest first, each with its place in that order: what a line's mark names to
    find its commit in the panel's last row.
    """
    commits = {c.sha: c for c in history.lines.values() if c}
    return {sha: k for k, sha in enumerate(sorted(commits, key=lambda sha: (commits[sha].time, sha)))}


def blame_mark(history: History, line: int, keys: dict[str, int], same: bool) -> str:
    """
    What goes beside a line of the panel's code: who changed it last and how long ago (left out when the line above
    says the same, same), over a bar darker the newer the line, amber for one not committed yet. Pointing at it says
    the commit; '' for a line blame didn't cover, so the code stays in line.
    """
    if line not in history.lines:
        return '<span class="sb"></span>'
    commit = history.lines[line]
    if commit is None:
        return (
            f'<span class="sb au{" same" if same else ""}" data-k="u" title="Changed since the last commit">'
            "<span>Uncommitted</span></span>"
        )
    k = keys[commit.sha]
    shade = _AGES - 1 if len(keys) == 1 else round(k * (_AGES - 1) / (len(keys) - 1))
    said = f"{commit.subject} · {commit.author}, {history.ago(commit.time)} · {commit.short}"
    return (
        f'<span class="sb a{shade}{" same" if same else ""}" data-k="{k}" title="{_esc(said)}">'
        f"<span>{_esc(commit.author.split(' ')[0] or commit.author)} · {_esc(history.since(commit.time))}</span></span>"
    )


def blame_row(history: History, keys: dict[str, int]) -> str:
    """
    The panel's last row: when its code was last changed and by whom, then hidden, a row for each commit its lines come
    from, which a script shows in its place while a line from that commit is pointed at.
    """

    def sha(commit: Commit) -> str:
        short = f"<code>{_esc(commit.short)}</code>"
        if not commit.url:
            return f'<span class="csfh">{short}</span>'
        return (
            f'<a class="csfh" href="{_esc(commit.url)}" target="_blank" rel="noopener" title="The commit">{short}</a>'
        )

    last = history.last
    if last:
        day = datetime.fromtimestamp(last.time, timezone.utc).strftime("%Y-%m-%d")
        said = f'Changed <b title="{day}">{_esc(history.ago(last.time))}</b> by {_esc(last.author)}'
        if history.commits > 1:
            people = len(history.authors)
            said += f" · {history.commits} commits" + (f" by {people} people" if people > 1 else "")
    else:
        said = "Not committed yet"
    if history.uncommitted and last:
        lines = f"{history.uncommitted} line{'' if history.uncommitted == 1 else 's'}"
        said += f' · <span class="cnhu">{lines} not committed</span>'
    rows = [f'<p class="csfs"><span>{said}</span>{sha(last) if last else ""}</p>']
    commits = {c.sha: c for c in history.lines.values() if c}
    for found, k in keys.items():
        commit = commits[found]
        rows.append(
            f'<p data-k="{k}" hidden><span><b>{_esc(commit.subject or commit.short)}</b> · {_esc(commit.author)}, '
            f"{_esc(history.ago(commit.time))}</span>{sha(commit)}</p>"
        )
    if history.uncommitted:
        rows.append('<p data-k="u" hidden><span class="cnhu">Changed since the last commit</span></p>')
    return f'<div class="csf">{"".join(rows)}</div>'
