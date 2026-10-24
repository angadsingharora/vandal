"""Sim clock only: no wall-clock reads outside api/ (IMPLEMENTATION.md §0)."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.conventions import PACKAGE, modules

BANNED = {"now", "utcnow", "today"}
ALLOWED_DIRS = {PACKAGE / "api"}


def wall_clock_calls(source: str) -> list[int]:
    """Line numbers of datetime.now()/utcnow()/today() and date.today() calls."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in BANNED:
            continue
        target = node.func.value
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", None)
        if name in {"datetime", "date"}:
            lines.append(node.lineno)
    return lines


def _allowed(path: Path) -> bool:
    return any(path.is_relative_to(d) for d in ALLOWED_DIRS)


def test_no_wall_clock_outside_api() -> None:
    offenders = [
        f"{path.relative_to(PACKAGE.parent)}:{line}"
        for path in modules()
        if not _allowed(path)
        for line in wall_clock_calls(path.read_text())
    ]
    assert not offenders, "wall-clock read outside api/:\n" + "\n".join(offenders)


def test_detector_catches_common_forms() -> None:
    src = (
        "import datetime\n"
        "from datetime import date, datetime as dt\n"
        "datetime.datetime.now()\n"
        "datetime.date.today()\n"
        "date.today()\n"
    )
    assert wall_clock_calls(src) == [3, 4, 5]
