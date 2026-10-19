"""
Links that open a line of the code in an editor: VS Code's and Cursor's vscode:// and cursor:// links, with the
remote form inside WSL, where the editor runs on Windows and the code is in the Linux distro.
"""

from __future__ import annotations

from urllib.parse import quote

EDITORS = {"vscode": "VS Code", "cursor": "Cursor"}  # --editor's choices besides none, and the name each link says


def editor_link(editor: str, root: str, wsl: str = "") -> str:
    """
    A link to a line of a file under root in the editor, with {file} and {line} left to fill in (open_at fills them),
    or '' for none. wsl is the WSL distro the code is in ('Ubuntu'), when it is.
    """
    if editor not in EDITORS:
        return ""
    path = root.replace("\\", "/").rstrip("/")
    path = quote(path if path.startswith("/") else "/" + path, safe="/:")  # C:/code -> /C:/code
    if wsl:
        return f"{editor}://vscode-remote/wsl+{quote(wsl)}{path}/{{file}}:{{line}}"
    return f"{editor}://file{path}/{{file}}:{{line}}"


def open_at(link: str, file: str, line: int) -> str:
    """
    The link for one line of a file (its path from the folder read), or '' with no link.
    """
    if not link:
        return ""
    return link.replace("{file}", quote(file)).replace("{line}", str(max(1, line)))


def editor_name(link: str) -> str:
    """
    The editor a link opens, by name: 'VS Code'.
    """
    return EDITORS.get(link.partition("://")[0], "your editor")
