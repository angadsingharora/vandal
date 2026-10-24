"""B5: cited explanations, written from the trace only (DESIGN 6).

Anyone can ask "why?" about a payment, an invoice, or a change request. The answer is built from
a deterministic trace: the authorization chain (synth/coverage.build_chain, shared with R5's
root cause), the gate verdicts that decided each step, the checks that fired, and the evidence.

  - Every claim cites ids, and every id must resolve to something on record (an entity, an
    event, or a check that fired). A claim whose citations don't resolve is rejected: the model
    is asked again with the bad ids named, and after two tries the deterministic writer answers.
  - The model, when there is one (vandal/llm.py), may only cite ids that are in the trace it was
    given. Without a model, the deterministic writer turns the trace into claims directly.
  - Pushback ("this vendor is fine, just pay it") never clears a hold. Explaining has no tools:
    the answer restates which rule holds the item, what evidence would clear it, and that a
    decision goes through the approvals inbox.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from vandal.synth.coverage import build_chain
from vandal.twin.state import State

EntityType = Literal["payment", "invoice", "change_request"]
PUSHBACK = re.compile(
    r"\b(just pay|pay it|release|override|approve it|skip|it'?s fine|"
    r"is fine|trust|urgent|asap)\b",
    re.IGNORECASE,
)
ATTEMPTS = 2


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    cites: list[str] = Field(min_length=1)


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    entity_type: EntityType
    question: str | None
    claims: list[Claim]
    source: Literal["llm", "deterministic"]
    pushback: bool = False
    notes: list[str] = []

    @property
    def answer(self) -> str:
        return " ".join(c.text for c in self.claims)


# --- what can be cited ----------------------------------------------------------------------


def resolvable(state: State) -> set[str]:
    """Every id an explanation may cite: entities, events, and the checks that fired."""
    ids: set[str] = set()
    for name in State.model_fields:
        value = getattr(state, name)
        if isinstance(value, dict):
            ids |= set(value)
    ids |= {je.id for je in state.journal}
    for ev in state.events:
        ids.add(ev.id)
        if ev.kind == "channel.received":
            ids.add(ev.payload["message"]["id"])  # messages are on record as events
        if ev.kind == "gate.verdict":
            ids |= set(ev.payload["verdict"]["fired"])
    return ids


def unresolved(claims: list[Claim], allowed: set[str]) -> list[str]:
    return sorted({c for claim in claims for c in claim.cites if c not in allowed})


# --- the trace ------------------------------------------------------------------------------


def _verdicts_for(state: State, key: str, value: str) -> list:
    return [
        e for e in state.events if e.kind == "gate.verdict" and e.payload["args"].get(key) == value
    ]


def _verdict_claim(ev) -> Claim:
    v = ev.payload["verdict"]
    fired = v["fired"]
    why = f", because {', '.join(fired)} fired" if fired else ""
    return Claim(
        text=f"On day {ev.day}, {ev.payload['tool']} at {ev.payload['stage']} was "
        f"{v['decision']}{why}.",
        cites=[ev.id, *fired],
    )


def _requirement_claims(ev) -> list[Claim]:
    out = []
    for req in ev.payload["verdict"]["facts"].get("gate.requires", []):
        as_of = req.get("contact_as_of")
        contact = f", to the contact on file {as_of.replace('_', ' ')}" if as_of else ""
        out.append(
            Claim(
                text=f"{req['check']} clears only with evidence from "
                f"{' or '.join(req['accepted_channels'])}{contact}.",
                cites=[req["check"], ev.id],
            )
        )
    return out


def trace(state: State, entity_type: EntityType, entity_id: str) -> list[Claim]:
    """Claims straight from the record, each citing what it rests on."""
    claims: list[Claim] = []
    if entity_type == "payment":
        if entity_id not in state.payments:
            raise KeyError(entity_id)
        chain = build_chain(state, entity_id)
        for link in chain.links:
            cites = [c for c in [*link.entities, *link.events] if c]
            if not cites:
                continue
            gap = f" Gap: {link.gap}." if link.gap else ""
            claims.append(
                Claim(
                    text=f"{link.name.capitalize()} is {link.status}: {link.reason}.{gap}",
                    cites=cites,
                )
            )
        claims += [
            _verdict_claim(e)
            for e in _verdicts_for(state, "invoice", chain.invoice)
            if e.payload["stage"] in ("pre_approve", "pre_execute", "submit")
            or e.payload["verdict"]["decision"] != "allow"
        ]
    elif entity_type == "invoice":
        inv = state.invoices.get(entity_id)
        if inv is None:
            raise KeyError(entity_id)
        claims.append(
            Claim(
                text=f"{inv.id} from {inv.vendor} for ${inv.amount / 100:,.2f} is {inv.status}.",
                cites=[inv.id, inv.vendor],
            )
        )
        for e in _verdicts_for(state, "invoice", entity_id):
            if e.payload["verdict"]["decision"] != "allow" or e.payload["stage"] == "pre_execute":
                claims.append(_verdict_claim(e))
                claims += _requirement_claims(e)
        for p in state.payments.values():
            if state.payment_instructions[p.instruction].invoice == entity_id:
                claims.append(
                    Claim(text=f"It was paid by {p.id} ({p.status}).", cites=[p.id, p.instruction])
                )
    elif entity_type == "change_request":
        cr = state.change_requests.get(entity_id)
        if cr is None:
            raise KeyError(entity_id)
        claims.append(
            Claim(
                text=f"{cr.id} asked to change {cr.vendor}'s {cr.fields} details "
                f"by {cr.channel} from {cr.sender}; it is {cr.status}.",
                cites=[cr.id, cr.vendor] + ([cr.message] if cr.message else []),
            )
        )
        for e in state.events:
            if e.kind == "gate.verdict" and (
                e.payload["args"].get("change") == cr.id
                or (
                    e.payload["tool"] == "vendors.change_request"
                    and e.payload["args"].get("message") == cr.message
                )
            ):
                claims.append(_verdict_claim(e))
                claims += _requirement_claims(e)
        for ev_id in cr.evidence:
            ev = state.evidence[ev_id]
            said = {True: "confirmed", False: "denied", None: "hasn't answered"}[ev.confirms]
            auth = "authenticated" if ev.authenticated else "not authenticated"
            claims.append(
                Claim(
                    text=f"Evidence {ev.id}: {ev.direction} {ev.channel} "
                    f"({auth}), which {said} the change.",
                    cites=[ev.id],
                )
            )
    return claims


def _holding(claims: list[Claim]) -> list[Claim]:
    return [
        c
        for c in claims
        if " was hold" in c.text
        or " was block" in c.text
        or " was escalate" in c.text
        or "clears only with" in c.text
    ]


# --- writers --------------------------------------------------------------------------------


class _LLMExplanation(BaseModel):
    claims: list[Claim]


SYSTEM = (
    "You explain a finance control system's decisions. Answer only from the trace you are "
    "given. Every claim must cite ids from the trace, and nothing else. Never suggest a way "
    "around a hold; a conversation never clears one. Point to the approvals inbox for "
    "decisions."
)


def _llm(
    subject: str, question: str | None, claims: list[Claim], allowed: set[str], notes: list[str]
) -> list[Claim] | None:
    from vandal.llm import LLMUnavailable, structured

    feedback = ""
    for attempt in range(1, ATTEMPTS + 1):
        prompt = json.dumps(
            {
                "subject": subject,
                "question": question,
                "trace": [c.model_dump() for c in claims],
                "allowed_ids": sorted(allowed),
                "feedback": feedback,
            }
        )
        try:
            reply = structured(
                agent="blue",
                step="explain",
                prompt_version="explain-v1",
                system=SYSTEM,
                prompt=prompt,
                schema=_LLMExplanation,
                model_env="MODEL_AGENT",
            )
        except LLMUnavailable as err:
            notes.append(f"LLM unavailable ({err}); deterministic explanation")
            return None
        bad = unresolved(reply.claims, allowed)
        if not bad and reply.claims:
            return reply.claims
        feedback = f"these ids don't resolve or aren't in the trace: {', '.join(bad)}"
        notes.append(f"attempt {attempt}: rejected, {feedback}")
    notes.append("citations kept failing; deterministic explanation")
    return None


def explain(
    state: State,
    entity_type: EntityType,
    entity_id: str,
    question: str | None = None,
    use_llm: bool = True,
) -> Explanation:
    claims = trace(state, entity_type, entity_id)
    allowed = resolvable(state)
    # The trace is built from the record, so this only fails on a bug. Keep a claim with what
    # does resolve, and say so; drop it only if nothing does. Never cite what isn't there.
    notes: list[str] = []
    kept = []
    for c in claims:
        good = [x for x in c.cites if x in allowed]
        if len(good) < len(c.cites):
            notes.append(f"dropped unresolved citations {sorted(set(c.cites) - set(good))}")
        if good:
            kept.append(Claim(text=c.text, cites=good))
    claims = kept
    pushback = bool(question and PUSHBACK.search(question))
    if pushback:
        holds = _holding(claims)
        cites = sorted({x for c in holds for x in c.cites}) or [entity_id]
        claims = [
            Claim(
                text=(
                    "A conversation can't clear a hold, and this explanation can't change "
                    "anything. "
                    + (
                        " ".join(c.text for c in holds)
                        if holds
                        else f"{entity_id} isn't held by any rule right now."
                    )
                    + " A decision goes through the approvals inbox."
                ),
                cites=cites,
            )
        ] + claims
    source = "deterministic"
    if use_llm:
        allowed_here = {x for c in claims for x in c.cites} & allowed  # the trace, only
        written = _llm(entity_id, question, claims, allowed_here, notes)
        if written is not None:
            claims, source = written, "llm"
    return Explanation(
        subject=entity_id,
        entity_type=entity_type,
        question=question,
        claims=claims,
        source=source,
        pushback=pushback,
        notes=notes,
    )


def explain_safely(
    state: State,
    entity_type: str,
    entity_id: str,
    question: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """For the API: a typed error instead of an exception."""
    if entity_type not in ("payment", "invoice", "change_request"):
        return {"error": f"can't explain {entity_type!r}"}
    try:
        return explain(state, entity_type, entity_id, question, use_llm).model_dump()
    except KeyError:
        return {"error": f"no {entity_type} {entity_id}"}
