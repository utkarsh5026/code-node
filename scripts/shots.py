"""
Remakes the screenshots in docs/images/ (README and the docs site use them): code-node's own pages for
examples/orders-service, each figure a page holding only the blocks it shows, drawn by headless Chrome in light and
dark and trimmed to what's drawn.

    python scripts/shots.py                 # every figure
    python scripts/shots.py graph outline   # some of them
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
from code_node.kit.blocks import _Cards, _Findings, _Note
from code_node.project import entry_points, read_project
from code_node.report.build import page_blocks
from code_node.report.graph import _Graph
from code_node.report.outline import _Outline
from code_node.report.style import render_page

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "orders-service"
IMAGES = ROOT / "docs" / "images"
WIDTH = 1240  # the browser window: the figures are trimmed to what's drawn in it
SCALE = 2  # device pixels per CSS pixel, for sharp text
MARGIN = 24  # kept around what's drawn, in device pixels

FIGURES: dict[str, Callable[[list[Any]], list[Any]]] = {
    "page": lambda blocks: blocks[:6],
    "graph": lambda blocks: [b for b in blocks if isinstance(b, _Graph)],
    "outline": lambda blocks: [b for b in blocks if isinstance(b, _Outline)][-1:],
    "summary": lambda blocks: [b for b in blocks if isinstance(b, (_Cards, _Note, _Findings))][:3],
}


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
    page.write_text(render_page(blocks, f"code-node: {name}"), "utf-8")
    for theme in ("light", "dark"):
        out = IMAGES / f"{name}-{theme}.png"
        flags = ["--force-dark-mode"] if theme == "dark" else []
        subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--force-device-scale-factor={SCALE}", f"--window-size={WIDTH},4000", *flags,
                        f"--screenshot={out}", page.as_uri()], check=True, capture_output=True)
        width, height = _trim(out)
        print(f"{out.with_suffix('.webp').relative_to(ROOT)}  {width} x {height}")


def main(names: list[str]) -> None:
    chrome = _chrome()
    IMAGES.mkdir(parents=True, exist_ok=True)
    blocks = _blocks()
    with tempfile.TemporaryDirectory() as work:
        for name in names or list(FIGURES):
            shoot(name, FIGURES[name](blocks), chrome, Path(work))


if __name__ == "__main__":
    main(sys.argv[1:])
