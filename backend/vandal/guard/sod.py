"""B3: roles and segregation of duties (DESIGN 6.1), enforced by Blue's gate on every call.

These checks are Blue's own, always on, under every policy: a policy patch can add controls but
can't take these away. No actor both requests and approves the same action, and each role may
call only its own tools:

  operator   intake, approval *requests*, scheduling, execution, retries, reconciliation,
             vendor-master changes, gathering evidence, cash application, refund requests
  approver   deciding approval requests (a human, through the inbox)

A tool missing from this table is blocked for everyone (tests/test_gate.py checks that every
tool has a role). Nobody else calls tools: the gate, the synthesizer, and external parties have
none. Policy patches never go through Tools; they're decided in the policy inbox
(guard/approvals.py), with the same rule that the submitter can't approve.
"""

from __future__ import annotations

from vandal.contracts.controls import Check, Condition, Predicate

ROLE_TOOLS: dict[str, tuple[str, ...]] = {
    "operator": (
        "invoices.receive",
        "invoices.validate",
        "approvals.request",
        "payments.schedule",
        "payments.execute",
        "payments.submit",
        "payments.retry",
        "payments.query_status",
        "ledger.reconcile",
        "vendors.change_request",
        "vendors.apply_change",
        "evidence.request_callback",
        "evidence.record_portal",
        "evidence.record_inbound",
        "cash.apply",
        "cash.reverse",
        "refunds.issue",
    ),
    "approver": ("approvals.decide",),
}


def _when(*conditions: tuple[str, str, object]) -> Predicate:
    return Predicate(all=[Condition(fact=f, op=op, value=v) for f, op, v in conditions])


def allowed_roles(tool: str) -> list[str]:
    return sorted(role for role, tools in ROLE_TOOLS.items() if tool in tools)


def sod_checks(tool_stages: dict[str, str]) -> list[Check]:
    """One role check per tool, plus no self-approval. `tool_stages` maps each tool to the
    gate stage it runs at (twin/flows.TOOLS)."""
    checks = []
    for tool, stage in sorted(tool_stages.items()):
        checks.append(
            Check(
                id=f"sod.role.{tool}",
                stage=stage,
                when=_when(("tool", "eq", tool), ("actor.role", "not_in", allowed_roles(tool))),
                action="block",
            )
        )
    checks.append(
        Check(
            id="sod.self_approval",
            stage="pre_approve",
            when=_when(("tool", "eq", "approvals.decide"), ("sod.requester_is_actor", "eq", True)),
            action="block",
        )
    )
    return checks
