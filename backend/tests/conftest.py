"""Slow tests (full searches, CEGIS, verification packs) are skipped by default so the everyday
suite stays fast. Run everything with `uv run pytest --slow` (or VANDAL_SLOW=1)."""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow",
        action="store_true",
        help="also run slow tests: full searches, CEGIS, verification packs",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: takes seconds; skipped unless --slow")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--slow") or os.environ.get("VANDAL_SLOW"):
        return
    skip = pytest.mark.skip(reason="slow: run with --slow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
