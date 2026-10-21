"""
The terminal: rich consoles for what the command says, and keys read one at a time for the file browser.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager

from rich.console import Console

console = Console(highlight=False)
errors = Console(stderr=True, highlight=False)

# what a key's escape sequence (after ESC) means, on Linux and macOS terminals
_ESCAPES = {
    "[A": "up",
    "[B": "down",
    "[C": "right",
    "[D": "left",
    "OA": "up",
    "OB": "down",
    "OC": "right",
    "OD": "left",
    "[H": "home",
    "[F": "end",
    "OH": "home",
    "OF": "end",
    "[1~": "home",
    "[4~": "end",
    "[7~": "home",
    "[8~": "end",
    "[5~": "pageup",
    "[6~": "pagedown",
    "[3~": "delete",
    "[Z": "shift-tab",
}

# what the second half of a Windows console's two-part key means
_WINDOWS_KEYS = {
    "H": "up",
    "P": "down",
    "M": "right",
    "K": "left",
    "G": "home",
    "O": "end",
    "I": "pageup",
    "Q": "pagedown",
    "S": "delete",
}

# the plain keys, by the character the terminal sends
_PLAIN = {
    "\r": "enter",
    "\n": "enter",
    "\t": "tab",
    "\x7f": "backspace",
    "\x08": "backspace",
    "\x1b": "esc",
    "\x03": "ctrl-c",
}


def can_ask() -> bool:
    """
    Whether someone is at a terminal to ask: stdin and stdout are both one.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


@contextmanager
def keys() -> Generator[Callable[[], str], None, None]:
    """
    A function that waits for the next key and names it: 'up', 'enter', 'esc', 'ctrl-c', or the character typed.
    The terminal stops echoing what's typed until the block ends (Ctrl-C still raises KeyboardInterrupt).
    """
    if os.name == "nt":
        yield _windows_key
        return
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)  # not raw: rich's newlines still go back to the line's start
        yield lambda: _unix_key(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def _unix_key(fd: int) -> str:
    import select

    first = os.read(fd, 1)
    if first == b"\x1b":
        sequence = ""
        while select.select([fd], [], [], 0.03)[0]:  # the rest of an escape sequence comes at once; Esc alone doesn't
            sequence += os.read(fd, 1).decode("ascii", "replace")
            if sequence[-1].isalpha() or sequence[-1] == "~":
                break
        return _ESCAPES.get(sequence, "esc" if not sequence else "")
    if first[0] >= 0xC0:  # the first byte of a character UTF-8 spends several on
        more = 3 if first[0] >= 0xF0 else 2 if first[0] >= 0xE0 else 1
        first += os.read(fd, more)
    text = first.decode("utf-8", "replace")
    return _PLAIN.get(text, text)


def _windows_key() -> str:
    import msvcrt

    first = msvcrt.getwch()
    if first in ("\x00", "\xe0"):
        return _WINDOWS_KEYS.get(msvcrt.getwch(), "")
    return _PLAIN.get(first, first)
