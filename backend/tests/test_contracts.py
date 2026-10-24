from __future__ import annotations

import pytest
from pydantic import ValidationError

from vandal.contracts.controls import Check, Control, Predicate
from vandal.contracts.entities import Actor, Invoice
from vandal.contracts.moves import Move
from vandal.contracts.verdicts import Verdict


def test_contract_models_construct() -> None:
    Move(kind="change_request", params={"vendor": "V-007", "sender": "lookalike"}, at=3)
    Check(id="v0.threshold", stage="pre_approve", when=Predicate(), action="escalate")
    Verdict(decision="hold", fired=["v0.threshold"], facts={"amount": 4_000_000}, cites=[])
    Actor(id="op", role="operator")


def test_money_is_integer_cents() -> None:
    inv = Invoice(
        id="INV-1042",
        vendor="V-007",
        number="1042",
        amount=4_000_000,
        dimension="P-01",
        due_date=10,
    )
    assert inv.amount == 4_000_000
    with pytest.raises(ValidationError):
        Invoice(id="INV-1", vendor="V-1", number="1", amount=12.5, dimension="P", due_date=1)


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Move(kind="tick", params={}, at=0, extra=1)


def test_control_compile_is_not_yet_implemented() -> None:
    with pytest.raises(NotImplementedError):
        Control(template="T1", params={}).compile()
