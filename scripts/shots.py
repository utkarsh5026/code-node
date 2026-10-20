"""
Remakes the screenshots in docs/images/ (README and the docs site use them): code-node's own pages for
examples/orders-service (and examples/cart-service for the plugins figure), each figure a page holding only the
blocks it shows, drawn by headless Chrome in light and
dark and trimmed to what's drawn.

    python scripts/shots.py                 # every figure
    python scripts/shots.py graph steps     # some of them
    CHROME=/path/to/chrome python scripts/shots.py

Needs Chrome or Chromium (CHROME, else the first of chromium, google-chrome, or Playwright's in ~/.cache) and pillow.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from code_node.analysis.mapping import map_code
from code_node.pages import PageOptions, map_entry
from code_node.project import entry_points, read_project
from code_node.report.build import page_blocks
from code_node.report.graph import _Graph
from code_node.report.style import render_page
from code_node.report.tabs import _Tabs
from code_node.report.walk import _Walk

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "orders-service"
CART = ROOT / "examples" / "cart-service"  # every kind of plugin: its SAM template, Redis, PostgreSQL, OpenAI
IMAGES = ROOT / "docs" / "images"
WIDTH = 1240  # the browser window: the figures are trimmed to what's drawn in it
WIDE = 1800  # ...for the figures that are only the graph, so it's drawn at its real size
SCALE = 2  # device pixels per CSS pixel, for sharp text
MARGIN = 24  # kept around what's drawn, in device pixels



def _inside(blocks: list[Any]) -> list[Any]:
    """
    The blocks, with what's in each tab in place of the tabs.
    """
    return [inner for b in blocks for inner in (
        [x for _, _, tab in b.tabs for x in tab] if isinstance(b, _Tabs) else [b])]


FIGURES: dict[str, Callable[[list[Any]], list[Any]]] = {
    "page": lambda blocks: blocks,
    "graph": lambda blocks: [b for b in _inside(blocks) if isinstance(b, _Graph)],
    "steps": lambda blocks: [b for b in _inside(blocks) if isinstance(b, _Walk)],
    "plugins": lambda blocks: [b for b in _inside(blocks) if isinstance(b, _Graph)],  # drawn from the cart example
}

STEP_SHOWN = 14  # the step the steps figure has open: inside read_orders(), its S3 call lit


def _chrome() -> str:
    found = os.environ.get("CHROME") or shutil.which("chromium") or shutil.which("google-chrome")
    found = found or next(iter(sorted(glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))), None)
    if not found:
        sys.exit("No Chrome found: set CHROME=/path/to/chrome")
    return found


def _blocks() -> list[Any]:
    project = read_project(EXAMPLE)
    entry = entry_points(project)[0]
    cmap = map_code(project.files, entry.name, libraries=project.libraries(), file=entry.file, platform="lambda")
    return page_blocks(cmap, project="orders-service", max_functions=24, max_depth=5, sources=project.files)


def _cart_blocks() -> list[Any]:
    cmap, project = map_entry(CART, entry_points(read_project(CART))[0], PageOptions())  # with its template.yaml
    return page_blocks(cmap, project="cart-service", max_functions=24, max_depth=5, sources=project.files)


def _trim(path: Path) -> tuple[int, int]:
    """
    Crops a screenshot to what's drawn on it (anything not the page's background), with MARGIN around it.
    """
    from PIL import Image, ImageChops

    image = Image.open(path).convert("RGB")
    background = Image.new("RGB", image.size, image.getpixel((2, 2)))
    box = ImageChops.difference(image, background).getbbox() or (0, 0, *image.size)
    left, top = max(box[0] - MARGIN, 0), max(box[1] - MARGIN, 0)
    right, bottom = min(box[2] + MARGIN, image.width), min(box[3] + MARGIN, image.height)
    image = image.crop((left, top, right, bottom))
    image.save(path.with_suffix(".webp"), quality=90, method=6)
    path.unlink()
    return image.width // SCALE, image.height // SCALE


def shoot(name: str, blocks: list[Any], chrome: str, work: Path) -> None:
    page = work / f"{name}.html"
    html = render_page(blocks, f"code-node: {name}")
    # headless Chrome can take the picture mid fade-in: show the open tab at once. The pictures are shown shrunk
    # (the README fits them to its column), so logos are their small marks, as on a 1x screen
    html = html.replace("</head>", "<style>.cnd *{animation:none!important}.cnd .cg .logo.lgf{display:none!important}"
                                   ".cnd .cg .logo.lgs{display:inline!important}</style>\n</head>", 1)
    if name == "steps":  # no clicks in a screenshot: open a step by moving the checked mark to it
        html = html.replace('id="cw0" checked', 'id="cw0"').replace(f'id="cw{STEP_SHOWN}"',
                                                                    f'id="cw{STEP_SHOWN}" checked')
    # all of the graph in the picture, however wide it is: Fit, not Auto
    html = html.replace('id="cn-graph0-auto" checked', 'id="cn-graph0-auto"').replace(
        'id="cn-graph0-fit"', 'id="cn-graph0-fit" checked')
    page.write_text(html, "utf-8")
    width = WIDE if name in ("graph", "plugins") else WIDTH
    for theme in ("light", "dark"):
        out = IMAGES / f"{name}-{theme}.png"
        flags = ["--force-dark-mode"] if theme == "dark" else []
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--force-device-scale-factor={SCALE}", f"--window-size={width},4000", *flags,
                        "--virtual-time-budget=2000",
                        f"--screenshot={out}", page.as_uri()], check=True, capture_output=True)
        width, height = _trim(out)
        print(f"{out.with_suffix('.webp').relative_to(ROOT)}  {width} x {height}")


def main(names: list[str]) -> None:
    chrome = _chrome()
    IMAGES.mkdir(parents=True, exist_ok=True)
    blocks = _blocks()
    cart = _cart_blocks()
    with tempfile.TemporaryDirectory() as work:
        for name in names or list(FIGURES):
            shoot(name, FIGURES[name](cart if name == "plugins" else blocks), chrome, Path(work))


if __name__ == "__main__":
    main(sys.argv[1:])
