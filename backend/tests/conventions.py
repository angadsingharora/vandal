"""Shared helpers for the lint tests that enforce IMPLEMENTATION.md §0."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "vandal"


def modules(*subpackages: str) -> list[Path]:
    roots = [PACKAGE / s for s in subpackages] if subpackages else [PACKAGE]
    return sorted(p for root in roots for p in root.rglob("*.py"))


def module_name(path: Path) -> str:
    rel = path.relative_to(PACKAGE.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(path: Path) -> list[tuple[int, str]]:
    """Absolute names of every module imported by `path`, relative imports resolved."""
    tree = ast.parse(path.read_text(), filename=str(path))
    package = module_name(path).split(".")
    if path.name != "__init__.py":
        package = package[:-1]
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - node.level + 1]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            found.append((node.lineno, mod))
            found += [(node.lineno, f"{mod}.{a.name}") for a in node.names]
    return found
