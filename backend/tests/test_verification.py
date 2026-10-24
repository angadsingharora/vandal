"""R7 done-when: `vandal verify --policy v1` passes all six checks of DESIGN 10 and writes
evidence/v1.json, and the same command reports the failures under v0. The suite runs at depth 1
here to stay fast; the CLI defaults to depth 3."""

from __future__ import annotations

import json
from functools import partial

import pytest

from vandal.cli import load_policy, main
from vandal.contracts.entities import Actor
from vandal.sandbox import new_sandbox
from vandal.synth.templates import V0
from vandal.twin.flows import InvoiceArgs
from vandal.twin.profile import load_profile
from vandal.twin.seed import seed_state
from vandal.verify.regression import CASES, run_suite
from vandal.verify.suite import legit_ops, verify
from vandal.verify.variants import THREAT_CLASSES, grid, sample

V1 = load_policy("v1")


def factory_for(policy):
    return partial(new_sandbox, "bayline", policy=policy)


@pytest.fixture(scope="module")
def pack_v1():
    return verify(V1, V0, factory_for, profile="bayline", depth=1)


@pytest.fixture(scope="module")
def pack_v0():
    return verify(V0, V0, factory_for, profile="bayline", depth=1)


@pytest.mark.slow
def test_v1_passes_all_six_checks(pack_v1) -> None:
    assert [c.name for c in pack_v1.checks] == [
        "replay",
        "re-search",
        "variants",
        "regression",
        "legit ops",
        "invariants",
    ]
    assert all(c.passed for c in pack_v1.checks), [c.detail for c in pack_v1.checks]
    assert pack_v1.approvable
    assert pack_v1.counterexample.found_under == "v0"
    assert pack_v1.diagnosis["gap"] == "approval_binding"
    assert pack_v1.diff == V1.diff and len(pack_v1.chosen) == 2


@pytest.mark.slow
def test_v0_reports_its_failures(pack_v0) -> None:
    failed = {c.name for c in pack_v0.checks if not c.passed}
    assert failed == {"replay", "re-search", "variants", "regression", "invariants"}
    assert not pack_v0.approvable


@pytest.mark.slow
def test_scorecard_before_and_after(pack_v1) -> None:
    before, after = pack_v1.metrics["before"], pack_v1.metrics["after"]
    assert (before.policy, after.policy) == ("v0", "v1")
    assert before.attack_success_rate == 1.0 and after.attack_success_rate == 0.0
    assert before.exposure > 0 and after.exposure == 0
    assert after.false_positive_rate == 0.0 < before.false_positive_rate
    assert after.violations_found == 0 < before.violations_found
    assert set(after.attack_success) == set(THREAT_CLASSES.values())
    assert after.extraction_accuracy is None and after.notes  # honest about what isn't measured


@pytest.mark.slow
def test_evidence_pack_is_written(pack_v1, tmp_path) -> None:
    path = pack_v1.write(tmp_path)
    assert path.name == "v1.json"
    data = json.loads(path.read_text())
    assert {
        "counterexample",
        "diagnosis",
        "candidates",
        "chosen",
        "diff",
        "checks",
        "metrics",
    } <= set(data)


def test_variants_are_held_out_and_stratified() -> None:
    state, profile = seed_state(), load_profile()
    picked = sample(state, profile)
    assert len(picked) == 40
    by_class = {}
    for v in picked:
        by_class[v.threat_class] = by_class.get(v.threat_class, 0) + 1
    assert set(by_class.values()) == {8}
    vendors = {m.params["vendor"] for v in picked for m in v.moves}
    assert len(vendors) > 2  # beyond search's two representatives
    assert picked == sample(state, profile)  # reproducible
    assert len(grid(state, profile)) > len(picked)


def test_regression_suite() -> None:
    assert len(CASES) >= 18
    v1 = run_suite(factory_for(V1))
    assert v1.passed, [(c.name, c.problems) for c in v1.cases if c.status == "failed"]
    v0 = run_suite(factory_for(V0))
    failed = {c.name for c in v0.cases if c.status == "failed"}
    assert "bank_change_email_callback" in failed and "baseline" not in failed
    assert not [c for c in v0.cases if c.status == "skipped"]


def test_every_seeded_invoice_replays_on_its_own() -> None:
    ops = legit_ops(factory_for(V1))
    assert len(ops) == 80
    assert all(op.paid and not op.holds and not op.blocks and not op.violations for op in ops)


def test_credit_memo_cancels_only_unpaid_invoices() -> None:
    sb = new_sandbox()
    op = Actor(id="OP-1", role="operator")
    paid = next(i for i in sb.run.state.invoices.values() if i.status == "paid")
    r = sb.tools.call(
        op,
        "invoices.receive",
        InvoiceArgs(
            vendor=paid.vendor,
            number="CM-1",
            amount=100,
            dimension="P-01",
            kind="credit_memo",
            supersedes=paid.id,
        ),
    )
    assert not r.ok and "paid" in r.data["error"]


@pytest.mark.slow
def test_vandal_verify_cli(tmp_path, capsys) -> None:
    args = ["verify", "--depth", "1", "--workers", "1", "--out", str(tmp_path)]
    assert main([*args, "--policy", "v1"]) == 0
    out = capsys.readouterr().out
    assert out.count("PASS") == 6 and "approvable: wrote" in out
    assert (tmp_path / "v1.json").exists()
    assert main([*args, "--policy", "v0"]) == 1
    out = capsys.readouterr().out
    assert "FAIL  1 replay" in out and "NOT approvable" in out
