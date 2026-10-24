"""R1 done-when: deterministic seed, independent clones, `vandal seed` prints the summary."""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest
from pydantic import ValidationError

from vandal.cli import main
from vandal.twin.profile import load_profile
from vandal.twin.seed import seed_state


@pytest.fixture(scope="module")
def profile():
    return load_profile("bayline")


def test_five_seeds_in_a_row_give_the_same_hash(profile) -> None:
    hashes = {seed_state(profile, seed=7).state_hash() for _ in range(5)}
    assert len(hashes) == 1


def test_different_seeds_differ(profile) -> None:
    assert seed_state(profile, seed=7).state_hash() != seed_state(profile, seed=8).state_hash()


def test_hash_is_stable_across_processes() -> None:
    def run(hashseed: str) -> str:
        env = {**os.environ, "PYTHONHASHSEED": hashseed}
        out = subprocess.run(
            [sys.executable, "-m", "vandal.cli", "seed"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return re.search(r"state_hash\s+(\w+)", out).group(1)

    assert run("1") == run("2")


def test_clone_is_independent(profile) -> None:
    original = seed_state(profile)
    before = original.state_hash()
    clone = original.clone()
    clone.update("vendors", "V-007", status="blocked")
    clone.update("invoices", "INV-1042", amount=clone.invoices["INV-1042"].amount + 1)
    clone.update("bank_accounts", "CB-OPER", balance=0)
    clone.journal.pop()
    assert original.state_hash() == before
    assert original.vendors["V-007"].status == "active"
    assert clone.state_hash() != before


def test_entities_cannot_be_edited_in_place(profile) -> None:
    # Clones share entity objects, so an in-place edit would leak into every state.
    state = seed_state(profile)
    with pytest.raises(ValidationError):
        state.vendors["V-007"].status = "blocked"
    with pytest.raises(ValidationError):
        state.journal[0].memo = "tampered"


def test_company_shape(profile) -> None:
    s = seed_state(profile)
    assert len(s.vendors) == 25
    assert 55 <= len(s.purchase_orders) <= 65
    assert len(s.receipts) == len(s.purchase_orders)
    assert len(s.invoices) == 80
    assert s.bank_accounts["CB-OPER"].balance == 180_000_000
    assert s.bank_accounts["CB-RSRV"].balance == 20_000_000
    for vid in s.vendors:
        assert any(
            a.vendor == vid and a.status == "verified" for a in s.vendor_bank_accounts.values()
        ), vid
        current = [c for c in s.vendor_contacts.values() if c.vendor == vid and c.valid_to is None]
        assert len(current) == 1, vid


def test_scenario_a_invoice(profile) -> None:
    s = seed_state(profile)
    inv = s.invoices["INV-1042"]
    assert (inv.vendor, inv.amount, inv.status) == ("V-007", 4_000_000, "received")
    assert s.purchase_orders[inv.po].amount == 4_000_000
    assert any(r.po == inv.po for r in s.receipts.values())
    prior = [
        p
        for p in s.payments.values()
        if s.invoices[s.payment_instructions[p.instruction].invoice].vendor == "V-007"
    ]
    assert len(prior) >= profile.approval_matrix.min_prior_payments


def test_pending_invoices_pass_v0_match(profile) -> None:
    s = seed_state(profile)
    tol = profile.approval_matrix.match_tolerance_pct
    threshold = profile.approval_matrix.threshold
    for inv in s.invoices.values():
        if inv.status != "received":
            continue
        if inv.id != "INV-1042":
            assert inv.amount < threshold, inv.id
        if inv.po:
            po = s.purchase_orders[inv.po].amount
            assert abs(inv.amount - po) * 100 <= po * tol, inv.id


def test_invoice_numbers_unique_per_vendor(profile) -> None:
    s = seed_state(profile)
    keys = [(i.vendor, i.number) for i in s.invoices.values()]
    assert len(keys) == len(set(keys))


def test_opening_entry_balances(profile) -> None:
    (entry,) = seed_state(profile).journal
    assert sum(line.debit for line in entry.lines) == sum(line.credit for line in entry.lines)


def test_vandal_seed_prints_summary(capsys) -> None:
    assert main(["seed"]) == 0
    out = capsys.readouterr().out
    assert "Bayline Property Group" in out
    assert "vendors           25" in out
    assert "state_hash" in out
