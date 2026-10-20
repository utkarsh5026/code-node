"""
What git says about a function, as HTML: who changed it last and when, with a link to the commit when the repository
is on GitHub or GitLab, how many commits and people its lines come from, and its lines not committed yet. The same
in the graph's panel, its hover card and the walk's card.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..kit.text import _esc

from ..analysis.model import History


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
