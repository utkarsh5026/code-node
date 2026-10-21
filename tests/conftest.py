"""
Marks each test by its folder, so `pytest -m unit` and `pytest -m integration` run one kind.
"""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        kind = item.path.relative_to(HERE).parts[0] if item.path.is_relative_to(HERE) else ""
        if kind in ("unit", "integration"):
            item.add_marker(kind)
