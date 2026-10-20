"""
_Tabs: blocks in tabs, one shown at a time (the graph, and the walk through its steps).

No JavaScript: each tab is a radio button with its label as the tab, and the page's CSS shows the panel after the
checked one (`#tab:checked ~ .tp`, not :has(), which would look through the whole page each time a step changes).
In text every tab's blocks are shown one after the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..kit.blocks import _Report, _draws
from ..kit.render import _block_html, _block_lines
from ..kit.text import _esc
from .style import _ROOT


@dataclass
class _Tabs:
    """
    Tabs, each (its name, a few words beside it, its blocks). The first is open. caption (code) and about (words) sit
    at the right of the tab bar, and foot is a quiet line under every tab.
    """

    tabs: list[tuple[str, str, list[Any]]]
    caption: str = ""
    about: str = ""
    foot: str = ""


@_draws(_Tabs, "html")
def _tabs_html(block: _Tabs, report: _Report) -> str:
    root = report.root or _ROOT
    made = report.shared("tabs", lambda: [0])  # tab groups drawn so far, so each has ids of its own
    group = f"cnd-tab{made[0]}"
    made[0] += 1
    radios, heads, panels = [], [], []
    for i, (name, sub, blocks) in enumerate(block.tabs):
        tab = f"{group}-{i}"
        checked = " checked" if i == 0 else ""
        radios.append(f'<input type="radio" class="tr" name="{group}" id="{tab}"{checked}>')
        heads.append(
            f'<label class="tl" for="{tab}">{_esc(name)}{f"<small>{_esc(sub)}</small>" if sub else ""}</label>'
        )
        panels.append(f'<div class="tp tp{i}" role="tabpanel">{"".join(_block_html(b, report) for b in blocks)}</div>')
        report.rules.add(f".{root} #{tab}:checked~.tp{i}{{display:block}}")
        report.rules.add(f".{root} #{tab}:checked~.tbar [for={tab}]{{opacity:1;border-bottom-color:currentColor}}")
        report.rules.add(
            f".{root} #{tab}:focus-visible~.tbar [for={tab}]"
            "{outline:2px solid light-dark(#2563eb,#60a5fa);outline-offset:-2px;border-radius:6px 6px 0 0}"
        )
    if block.caption or block.about:
        heads.append(
            f'<span class="tcap">{f"<code>{_esc(block.caption)}</code>" if block.caption else ""}'
            f"{f'<small>{_esc(block.about)}</small>' if block.about else ''}</span>"
        )
    foot = f'<p class="tfoot">{_esc(block.foot)}</p>' if block.foot else ""
    return (
        f'<div class="tabs">{"".join(radios)}<div class="tbar" role="tablist">{"".join(heads)}</div>'
        f"{''.join(panels)}{foot}</div>"
    )


@_draws(_Tabs, "text")
def _tabs_lines(block: _Tabs, report: _Report) -> list[str]:
    head = [" · ".join(filter(None, [block.caption, block.about]))] if block.caption or block.about else []
    return (
        head
        + [line for _, _, blocks in block.tabs for b in blocks for line in _block_lines(b, report)]
        + ([block.foot] if block.foot else [])
    )
