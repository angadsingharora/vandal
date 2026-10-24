"""R6: lints that reject a candidate control before search spends time on it (DESIGN 9.2).

overfit                 equality on amounts, entity keys, or invoice numbers: it fixes the one
                        trace, not the gap
spoofable               clears a hold with evidence the attacker can forge, given the profile's
                        attacker capabilities (e.g. T1 accepting phone_in when caller ID can be
                        spoofed)
block_where_hold_works  blocks outright where the template offers a hold that evidence or a
                        human can clear
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vandal.contracts.controls import Control
from vandal.synth.templates import T1Params, params_of
from vandal.twin.profile import AttackerCapabilities

LintName = Literal["overfit", "spoofable", "block_where_hold_works"]

ENTITY_KEY = re.compile(r"^[A-Z]{1,4}-\d+[A-Z]?$")
EXACT_FACTS = (".amount", ".id", ".number", "payee_account")
# Templates whose action could be a hold. T3 blocks a second execution of the same obligation;
# there is nothing a hold would wait for.
HOLDABLE = ("T1", "T2", "T4", "T5", "T6")


class LintFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lint: LintName
    template: str
    message: str


def forgeable_channels(caps: AttackerCapabilities) -> set[str]:
    """Evidence channels the attacker can produce on their own."""
    out = {"email", "agent_msg"}  # lookalike domains and compromised mailboxes
    if caps.spoof_caller_id:
        out.add("phone_in")
    if caps.clone_voice:
        out |= {"phone_in", "video"}
    if caps.portal_takeover:
        out.add("portal")
    return out


def lint(
    control: Control, caps: AttackerCapabilities, counterexample_amounts: Iterable[int] = ()
) -> list[LintFinding]:
    """`counterexample_amounts` are the payment amounts in the trace being repaired: a numeric
    parameter within 1% of one is tuned to that trace, not to the gap."""
    findings: list[LintFinding] = []
    params = params_of(control)

    def add(name: LintName, message: str) -> None:
        findings.append(LintFinding(lint=name, template=control.template, message=message))

    for check in control.compile():
        for cond in check.when.all:
            values = cond.value if isinstance(cond.value, list) else [cond.value]
            keyed = [v for v in values if isinstance(v, str) and ENTITY_KEY.match(v)]
            if keyed:
                add("overfit", f"{check.id} matches specific records {keyed}")
            elif (
                cond.op in ("eq", "ne", "in")
                and cond.fact.endswith(EXACT_FACTS)
                and not isinstance(cond.value, bool)
            ):
                add("overfit", f"{check.id} compares {cond.fact} to an exact value")

    blocks = [c.id for c in control.compile() if c.action == "block"]
    if blocks and control.template in HOLDABLE:
        add(
            "block_where_hold_works",
            f"{', '.join(blocks)} block; a hold would let a "
            "legitimate case through once verified or approved",
        )

    amounts = [a for a in counterexample_amounts if a > 0]
    for name, value in params.model_dump().items():
        if isinstance(value, int) and not isinstance(value, bool) and value >= 100:
            near = [a for a in amounts if abs(value - a) * 100 <= a]
            if near:
                add("overfit", f"{name}={value} sits on the counterexample's amount {near[0]}")

    if isinstance(params, T1Params):
        forged = sorted(set(params.accepted_channels) & forgeable_channels(caps))
        if forged:
            add(
                "spoofable",
                f"T1 accepts {', '.join(forged)}, which this attacker can forge "
                f"(spoof_caller_id={caps.spoof_caller_id}, "
                f"clone_voice={caps.clone_voice})",
            )
    return findings
