---
description: Run code-node on a repository and review the page it draws - what it got right, what it missed
argument-hint: "<path to a repo, file or file:function> [-e entry]"
---

Run `uv run code-node $ARGUMENTS --no-open -o /tmp/code-node-map.html` (the installed `code-node` works too), with
`--list` first if no entry point is given, so you can say which one it picked.

Then review the result against the code:

1. Screenshot the page (`$CHROME --headless=new --no-sandbox --hide-scrollbars --window-size=1500,2400
   --screenshot=/tmp/code-node-map.png file:///tmp/code-node-map.html`) and look at it.
2. Read the entry point and the functions it calls. List what the page **missed**, meaning calls, AWS operations,
   HTTP requests or env vars that are in the code but not on the page, and say why: a value from outside, a
   dispatch it can't follow, the depth limit. List what it **got wrong**, if anything.
3. For each miss that's a pattern many codebases use (a framework's decorators, dependency injection, a dispatch
   dict), propose where in `src/code_node/analysis/reader.py` (or `project.py` for entry points) it would be
   followed, with a test for `tests/unit/test_reader.py` (or `tests/unit/test_project.py`). Don't change code unless asked.
