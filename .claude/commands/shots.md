---
description: Remake the screenshots in docs/images/ and check the README and docs still describe them
argument-hint: "[figure ...]  (page, graph, outline, summary; default all)"
---

1. Run `.venv/bin/python scripts/shots.py $ARGUMENTS`. It needs Chrome: set `CHROME=` if it isn't found
   (Playwright's `~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome` is picked up). It also needs pillow
   (in requirements-dev.txt).
2. Look at each new `docs/images/*-light.webp` and `*-dark.webp` with the Read tool. Check that nothing is cut off,
   the text is readable, and the dark one really is dark.
3. Check the alt text in `README.md` and the captions in `docs/*.md` still match what each picture shows. The figures
   come from `examples/orders-service`, so a change there changes every picture.
4. If the example's shape changed (new functions or services), update `NODES` / `EDGES` in
   `scripts/site_graph.py`, run it, and fix the trace lines' `data-on` in `docs/index.md` to match.
5. Run `.venv/bin/mkdocs build --strict`.
