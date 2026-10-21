"""
What git says about each function shown.
"""

from __future__ import annotations

import os
from pathlib import Path

from code_node.analysis.mapping import map_code
from code_node.cli import main
from code_node.project import read_project

from support import HANDLER, write


def _commit(root: Path, author: str, when: str, message: str) -> None:
    import subprocess

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": f"{author.lower()}@example.com",
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": f"{author.lower()}@example.com",
        "GIT_COMMITTER_DATE": when,
    }
    for command in (["add", "-A"], ["commit", "-q", "-m", message]):
        subprocess.run(["git", "-C", str(root), *command], check=True, env=env)


def test_each_function_says_what_git_says_about_it(tmp_path: Path) -> None:
    import subprocess

    from code_node.history import read_history

    root = write(tmp_path / "code", {"app.py": HANDLER})
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "git@github.com:ana/app.git"], check=True)
    _commit(root, "Ana", "2024-01-01T12:00:00Z", "First")
    (root / "app.py").write_text(HANDLER.replace('Key=key)["Body"]', 'Key=key, VersionId="1")["Body"]'))
    _commit(root, "Ben", "2024-03-01T12:00:00Z", "Read the first version")
    (root / "app.py").write_text(
        (root / "app.py").read_text().replace("for record", "for one in [1]:\n        pass\n    for record")
    )
    project = read_project(root)
    cmap = map_code(project.files, "app.lambda_handler", libraries=project.libraries(), platform="lambda")
    assert read_history(root, cmap.functions) == 2
    load = next(f for f in cmap.functions if f.name == "app.load").history
    handler = next(f for f in cmap.functions if f.name == "app.lambda_handler").history
    assert load and load.last and (load.last.author, load.last.subject) == ("Ben", "Read the first version")
    assert load.commits == 2 and load.authors == ["Ana", "Ben"] and load.uncommitted == 0
    assert load.last.url == f"https://github.com/ana/app/commit/{load.last.sha}"
    assert handler and handler.last and handler.last.author == "Ana" and handler.uncommitted == 2
    out = tmp_path / "page.html"
    assert main([str(root), "--no-open", "-o", str(out)]) == 0
    page = out.read_text()
    assert "by Ben in" in page and f'href="{load.last.url}"' in page and "2 lines changed since the last commit" in page
    # the code's panel says beside each line who changed it, and in its last row what git says about all of it
    assert '<pre class="csc blame">' in page and ">Ben · " in page and '<span class="sb au" data-k="u"' in page
    assert "commits by 2 people" in page and 'class="csg" checked' in page
    assert handler.lines and None in handler.lines.values() and load.lines[min(load.lines)] is not None
    assert main([str(root), "--no-open", "--no-git", "-o", str(out)]) == 0
    assert "Last changed" not in out.read_text() and 'class="csg"' not in out.read_text()
    # a folder not in git, or whose own config would have git run a filter, has no history
    assert read_history(write(tmp_path / "plain", {"app.py": HANDLER}), cmap.functions[:1]) == 0
    subprocess.run(["git", "-C", str(root), "config", "filter.x.clean", "touch ran"], check=True)
    assert read_history(root, cmap.functions) == 0
