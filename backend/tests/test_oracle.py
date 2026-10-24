"""Oracle labels are harness-only: Tools, the gate, and Operators can never read them."""

from __future__ import annotations

import json

from tests.conventions import imported_modules, module_name, modules
from tests.test_scenario_a import TRACE
from vandal.contracts.entities import OracleLabel
from vandal.sandbox import new_sandbox
from vandal.twin.state import State
from vandal.verify.oracle import Oracle
from vandal.verify.replay import Trace, replay_detailed

BLIND = ("twin", "guard", "operator", "contracts")


def _scenario_a():
    t = Trace.load(TRACE)
    return replay_detailed(t.seed, t.moves, sandbox=lambda s: new_sandbox(seed=s), days=t.days)


def test_labels_exist_but_never_reach_state() -> None:
    _, sb, oracle = _scenario_a()
    assert oracle.labels  # the harness did label the attack
    dumped = json.dumps(sb.run.state.model_dump(mode="json"))
    for label in ("attacker_controlled", "true_sender", "deepfake", "duplicate_of"):
        assert label not in dumped


def test_state_has_no_oracle_fields() -> None:
    for name, field in State.model_fields.items():
        assert "OracleLabel" not in str(field.annotation), name


def _reachable(obj, depth: int = 0, seen=None):
    """Objects reachable through attributes and containers, without descending into State."""
    seen = seen if seen is not None else set()
    if id(obj) in seen or depth > 6 or isinstance(obj, State):
        return
    seen.add(id(obj))
    yield obj
    children = []
    if isinstance(obj, dict):
        children = list(obj.values())
    elif isinstance(obj, list | tuple | set):
        children = list(obj)
    elif hasattr(obj, "__dict__"):
        children = list(vars(obj).values())
    for child in children:
        yield from _reachable(child, depth + 1, seen)


def test_tools_gate_and_operators_hold_no_oracle() -> None:
    _, sb, _ = _scenario_a()
    for root in (sb.tools, sb.gate, sb.operator, sb.approver):
        for obj in _reachable(root):
            assert not isinstance(obj, Oracle | OracleLabel), (type(root).__name__, obj)


def test_blind_packages_never_import_the_oracle() -> None:
    offenders = [
        f"{module_name(path)}:{line} imports {name}"
        for path in modules(*BLIND)
        for line, name in imported_modules(path)
        if name == "vandal.verify" or name.startswith("vandal.verify.")
    ]
    assert not offenders, "\n".join(offenders)
