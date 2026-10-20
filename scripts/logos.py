"""
Downloads the logos the graph draws (code_node.report.brands names them) into src/code_node/report/logos/, one .svg
file each, from a pinned version of Iconify's @iconify-json/logos (gilbarbara/logos, CC0). The download is checked
against its hash and only read as JSON. Each logo's ids get its own prefix, so two logos on one page don't share a gradient, and
near-black fills follow the text colour, so a black logo (OpenAI's) shows in dark mode too.

    python scripts/logos.py

Run it after adding a logo to brands.py, or to move to another version (VERSION and INTEGRITY below, from
https://registry.npmjs.org/@iconify-json/logos/<version>).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from code_node.report.brands import logo_names  # noqa: E402

VERSION = "1.2.17"
URL = f"https://registry.npmjs.org/@iconify-json/logos/-/logos-{VERSION}.tgz"
INTEGRITY = "sha512-ruCr6y5h8FW+loXwRJkz+6cJj3njyX5Ccpi+ifMgaWZPbTSCbsCccNyGomZxIdhoyDKNOmNdZuURC3tyBvDr7A=="
OUT = ROOT / "src" / "code_node" / "report" / "logos"

MARKS = {  # a logo that's a wordmark -> the path that writes the word (dropped) and the box its mark fills
    "sqlite": ("M194.52 112.044", (0, 0, 206, 228)),
}

_COLOUR = re.compile(r'(fill|stroke|stop-color)="(#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6})"')


def _dark(hex_colour: str) -> bool:
    """
    Whether a colour is near black: drawn in the text's colour instead, or it vanishes in dark mode.
    """
    digits = hex_colour[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    r, g, b = (int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.16


def _clean(name: str, body: str) -> str:
    prefix = "cnl-" + re.sub(r"[^a-z0-9]+", "-", name)
    for found in set(re.findall(r'id="([^"]+)"', body)):
        body = body.replace(f'id="{found}"', f'id="{prefix}-{found}"').replace(f"#{found}", f"#{prefix}-{found}")
    return _COLOUR.sub(lambda m: f'{m.group(1)}="currentColor"' if _dark(m.group(2)) else m.group(0), body)


def main() -> None:
    with urllib.request.urlopen(URL, timeout=60) as answer:  # noqa: S310  a fixed https URL
        data = answer.read()
    got = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != INTEGRITY:
        sys.exit(f"{URL} doesn't match its pinned hash: {got}")
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        member = archive.extractfile("package/icons.json")
        icons = json.load(member) if member is not None else sys.exit("no icons.json in the package")
    width, height = icons.get("width", 256), icons.get("height", 256)
    wanted = sorted(logo_names())
    missing = [name for name in wanted if name not in icons["icons"]]
    if missing:
        sys.exit(f"not in @iconify-json/logos {VERSION}: {', '.join(missing)}")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for name in wanted:
        icon = icons["icons"][name]
        w, h = icon.get("width", width), icon.get("height", height)
        body = _clean(name, icon["body"])
        if name in MARKS:  # the mark alone, which reads at the size of a badge
            word, (left, top, w, h) = MARKS[name]
            body = re.sub(rf'<path[^>]*d="{re.escape(word)}[^"]*"/>', "", body, count=1)
            if left or top:
                body = f'<g transform="translate({-left} {-top})">{body}</g>'
        (OUT / f"{name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'fill="currentColor">{body}</svg>\n', "utf-8")
    (OUT / "README.md").write_text(
        f"# Logos\n\nThe logos code-node's graph draws, from [gilbarbara/logos](https://github.com/gilbarbara/logos) "
        f"through Iconify's `@iconify-json/logos` {VERSION}, under CC0-1.0. Each is its company's trademark, shown "
        "to name the service the code reaches.\n\nWritten by `scripts/logos.py` (`make logos`): don't edit them. "
        "Each one's ids carry its name, and near-black fills are `currentColor`, so they show in dark mode.\n",
        "utf-8")
    size = sum(f.stat().st_size for f in OUT.glob("*.svg"))
    print(f"{OUT.relative_to(ROOT)}/: {len(wanted)} logos, {size // 1024} KB")


if __name__ == "__main__":
    main()
