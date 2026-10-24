"""R3: harness-only ground truth (the answer key, DESIGN 10.1).

Labels are written by the harness when it applies an adversary move, and read only by
invariants and the scorecard. They never enter State, so Tools, the gate, and every Operator
are blind to them. tests/test_oracle.py enforces this.
"""

from __future__ import annotations

from typing import Literal

from vandal.contracts.entities import OracleLabel

LabelKind = Literal["attacker_controlled", "true_sender", "deepfake", "duplicate_of"]


def account_key(routing: str, account: str) -> str:
    """Labels name bank accounts by their numbers: the twin's BA- id doesn't exist yet when the
    attacker sends the request."""
    return f"acct:{routing}:{account}"


class Oracle:
    def __init__(self) -> None:
        self.labels: list[OracleLabel] = []

    def add(self, subject: str, label: LabelKind, value: str | bool = True) -> None:
        self.labels.append(OracleLabel(subject=subject, label=label, value=value))

    def has(self, subject: str, label: str) -> bool:
        return any(lb.subject == subject and lb.label == label for lb in self.labels)

    def attacker_controlled(self, routing: str, account: str) -> bool:
        return self.has(account_key(routing, account), "attacker_controlled")

    def duplicates(self) -> list[tuple[str, str]]:
        """(invoice, original) pairs labeled duplicate_of."""
        return [(lb.subject, str(lb.value)) for lb in self.labels if lb.label == "duplicate_of"]
