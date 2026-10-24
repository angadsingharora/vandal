"""twin/ search/ synth/ verify/ guard/ never import from operator/ (IMPLEMENTATION.md §0)."""

from __future__ import annotations

from tests.conventions import imported_modules, module_name, modules

BOUNDED = ("twin", "search", "synth", "verify", "guard", "contracts")


def test_core_never_imports_operator() -> None:
    offenders = [
        f"{module_name(path)}:{line} imports {name}"
        for path in modules(*BOUNDED)
        for line, name in imported_modules(path)
        if name == "vandal.operator" or name.startswith("vandal.operator.")
    ]
    assert not offenders, "\n".join(offenders)


def test_boundary_check_resolves_relative_imports(tmp_path) -> None:
    from tests import conventions

    pkg = tmp_path / "vandal" / "twin"
    pkg.mkdir(parents=True)
    bad = pkg / "bad.py"
    bad.write_text("from ..operator import reference\n")
    original = conventions.PACKAGE
    conventions.PACKAGE = tmp_path / "vandal"
    try:
        names = [n for _, n in conventions.imported_modules(bad)]
    finally:
        conventions.PACKAGE = original
    assert "vandal.operator.reference" in names
