"""Guard as an API: ask what Guard would do with an action, without doing it.

An agent (or the person wiring one) posts the tool call it is about to make against a run's
books, and gets the verdict Guard's gate would give at that tool's stage: allow, hold, escalate
or block, which checks fired, what evidence would clear a hold, and what the verdict cites.
Nothing is executed and nothing is recorded on the run, so a check costs one gate evaluation.

`GET /guard/tools` lists the tools the gate rules on, with the arguments each takes, so a form
or an integration can be built from the API alone.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vandal.api import deps
from vandal.contracts.entities import Actor
from vandal.contracts.interfaces import Action
from vandal.twin.flows import TOOLS

router = APIRouter()

OPERATOR = Actor(id="OP-1", role="operator")

# What each stage means, for the listing.
STAGE_HELP: dict[str, str] = {
    "intake": "a document arrives and becomes an invoice",
    "invoice.match": "an invoice is matched to its purchase order and receipt",
    "pre_approve": "an approval is requested or decided",
    "schedule": "an approved invoice is put on a payment run",
    "pre_execute": "right before money leaves",
    "submit": "the instruction is handed to the bank",
    "retry": "a submitted payment is retried or queried",
    "journal": "cash is applied, reversed or reconciled in the books",
    "refund": "money is sent back to a payer",
    "change_request": "a vendor's bank or contact details change",
    "verification": "evidence for a change is recorded",
    "recovery": "a misdirected payment is chased",
}


class CheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str = Field(min_length=1, max_length=60)
    args: dict[str, Any] = Field(default_factory=dict)
    actor: Actor = OPERATOR


def _field_type(info: Any) -> str:
    ann = info.annotation
    name = getattr(ann, "__name__", None) or str(ann)
    return name.replace("typing.", "")


def _describe_tool(name: str) -> dict[str, Any]:
    spec = TOOLS[name]
    fields = []
    for fname, info in spec.args.model_fields.items():
        fields.append(
            {
                "name": fname,
                "type": _field_type(info),
                "required": info.is_required(),
                "default": None if info.is_required() else info.get_default(),
            }
        )
    return {
        "tool": name,
        "stage": spec.stage,
        "stage_help": STAGE_HELP.get(spec.stage, ""),
        "args": fields,
    }


def _say(verdict: dict[str, Any], tool: str) -> str:
    """One plain line a person or an agent can act on."""
    decision = verdict["decision"]
    fired = verdict["fired"]
    facts = verdict.get("facts", {})
    if decision == "allow":
        return f"Guard allows {tool}: nothing fired."
    verb = {"hold": "holds", "escalate": "escalates", "block": "blocks"}[decision]
    out = f"Guard {verb} {tool}"
    if fired:
        out += f" because {', '.join(fired)} fired"
    out += "."
    needs = facts.get("gate.requires") or []
    if needs:
        bits = []
        for req in needs:
            channels = " or ".join(req["accepted_channels"])
            line = f"{req['check']} clears with evidence from {channels}"
            if req.get("contact_as_of"):
                line += f", to the contact on file {req['contact_as_of'].replace('_', ' ')}"
            if req.get("window_days"):
                line += f", within {req['window_days']} days"
            bits.append(line)
        out += " " + "; ".join(bits) + "."
    missing = facts.get("gate.missing_facts") or []
    if missing:
        out += f" Facts Guard could not compute: {', '.join(missing)} (fail closed)."
    return out


@router.get("/guard/tools")
def guard_tools() -> list[dict[str, Any]]:
    """Every tool the gate rules on: its stage, what the stage means, and its arguments."""
    return [_describe_tool(name) for name in TOOLS]


@router.post("/runs/{run_id}/guard/check")
def guard_check(request: Request, run_id: str, body: CheckBody) -> dict[str, Any]:
    """What Guard would say to this tool call on this run's books right now. Dry: the books do
    not change and no event is recorded."""
    spec = TOOLS.get(body.tool)
    if spec is None:
        raise HTTPException(400, f"unknown tool {body.tool!r}; see GET /guard/tools")
    try:
        args = spec.args.model_validate(body.args)
    except ValidationError as err:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()
        )
        raise HTTPException(400, f"{body.tool} arguments: {problems}") from None
    handle = deps.get_run(request, run_id)
    with handle.lock:
        action = Action(actor=body.actor, name=body.tool, args=args.model_dump())
        verdict = handle.sandbox.gate.check(handle.state, action, spec.stage).model_dump(
            mode="json"
        )
    facts = verdict.get("facts", {})
    return {
        "run_id": run_id,
        "policy": handle.policy.version,
        "day": handle.state.day,
        "tool": body.tool,
        "stage": spec.stage,
        "actor": body.actor.model_dump(),
        "args": args.model_dump(),
        "decision": verdict["decision"],
        "fired": verdict["fired"],
        "cites": verdict["cites"],
        "requires": facts.get("gate.requires", []),
        "missing_facts": facts.get("gate.missing_facts", []),
        "summary": _say(verdict, body.tool),
        "facts": facts,
    }
