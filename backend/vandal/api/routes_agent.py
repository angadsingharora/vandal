"""Connect your own agent: Guard in the live path of an agent Vandal didn't write.

A connection binds one agent to one run's books. Its token is the agent's credential: every
call made with it goes through the same gated Tools layer the built-in Operator uses, so Guard
rules on it, the run records it, and the war room's verdict feed shows it as it happens.

Three ways in, one rulebook:

  - REST:  `GET /agent/v1/books`, `GET /agent/v1/tools` and `POST /agent/v1/call`, with
           `Authorization: Bearer <token>`.
  - MCP:   `POST /mcp/<token>` speaks MCP's streamable-HTTP transport in JSON-response mode, so
           Claude Desktop, Claude Code, or any MCP client can add Vandal as a server.
  - Claude: `POST /runs/{id}/connections/{cid}/claude` runs a Claude agent server-side with the
           same tools as that connection. It needs ANTHROPIC_API_KEY on the host.

Connections live in memory with their run; a restart or the run's eviction ends them.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vandal.api import deps
from vandal.api.registry import RunHandle
from vandal.api.routes_guard import _say
from vandal.contracts.entities import Actor
from vandal.contracts.interfaces import Action
from vandal.llm import DEFAULT_MODELS, FALLBACK_BETA, LLMUnavailable, _client, load_env
from vandal.twin.flows import TOOLS

router = APIRouter()

MCP_PROTOCOL = "2025-06-18"
MAX_CALLS_PER_CONNECTION = 2000
MAX_CONNECTIONS_PER_RUN = 12
AGENT_TURNS = 24


# --- connections ----------------------------------------------------------------------------


@dataclass
class Connection:
    id: str
    token: str
    name: str
    run_id: str
    owner: str | None
    created: float = field(default_factory=time.time)
    calls: deque = field(default_factory=lambda: deque(maxlen=200))
    total: int = 0
    last_seen: float | None = None
    clients: set[str] = field(default_factory=set)  # rest, mcp, claude
    busy: threading.Lock = field(default_factory=threading.Lock)  # one Claude run at a time

    @property
    def actor(self) -> Actor:
        return Actor(id=f"agent:{_slug(self.name)}", role="operator")

    def public(self, *, with_token: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "name": self.name,
            "run_id": self.run_id,
            "actor": self.actor.id,
            "created": self.created,
            "last_seen": self.last_seen,
            "total_calls": self.total,
            "clients": sorted(self.clients),
            "calls": list(self.calls)[-50:],
            "token_hint": f"{self.token[:8]}…",
        }
        if with_token:
            out["token"] = self.token
        return out


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "agent"


_LOCK = threading.Lock()


def _store(request: Request) -> dict[str, Connection]:
    app = request.app
    with _LOCK:
        if not hasattr(app.state, "connections"):
            app.state.connections = {}
        return app.state.connections


def _by_token(request: Request, token: str | None) -> Connection:
    if not token:
        raise HTTPException(401, "missing token: send Authorization: Bearer <token>")
    conn = _store(request).get(token.strip())
    if conn is None:
        raise HTTPException(401, "unknown or revoked token; make a new connection in the workspace")
    return conn


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else None


def _current_run(request: Request, owner: str | None) -> RunHandle | None:
    """The owner's newest live run: where a connection goes when its run was replaced."""
    if owner is None:
        return None
    live = [h for h in deps.registry(request).runs_of(owner) if h.kind == "operate"]
    return live[-1] if live else None


def _run_of(request: Request, conn: Connection) -> RunHandle:
    """The connection's run. A New run (say, under another policy) replaces the owner's run;
    the agent follows to the new one, so its MCP URL and token keep working."""
    try:
        return deps.registry(request).run(conn.run_id)
    except KeyError:
        handle = _current_run(request, conn.owner)
        if handle is None:
            raise HTTPException(
                410, f"run {conn.run_id} is gone (the server restarted); make a new connection"
            ) from None
        conn.run_id = handle.id
        return handle


# --- what the agent sees --------------------------------------------------------------------


def books(handle: RunHandle) -> dict[str, Any]:
    """The books in the shape an agent reads: who is owed what, where money would go, what is
    waiting. Amounts are cents."""
    with handle.lock:
        s = handle.state
        current: dict[str, Any] = {}
        for a in s.vendor_bank_accounts.values():
            if a.status in ("verified", "unverified"):
                current[a.vendor] = a
        contacts = {c.vendor: c for c in s.vendor_contacts.values() if c.valid_to is None}
        vendors = []
        for v in s.vendors.values():
            acct = current.get(v.id)
            c = contacts.get(v.id)
            vendors.append(
                {
                    "id": v.id,
                    "name": v.name,
                    "domain": v.domain,
                    "status": v.status,
                    "bank_account": None
                    if acct is None
                    else {
                        "id": acct.id,
                        "routing": acct.routing,
                        "account_last4": acct.account[-4:],
                        "status": acct.status,
                    },
                    "contact": None if c is None else {"name": c.name, "email": c.email},
                }
            )
        open_statuses = ("received", "validated", "approved", "scheduled", "held")
        invoices = [
            {
                "id": i.id,
                "vendor": i.vendor,
                "vendor_name": s.vendors[i.vendor].name if i.vendor in s.vendors else i.vendor,
                "number": i.number,
                "amount_cents": i.amount,
                "status": i.status,
                "due_day": i.due_date,
                "po": i.po,
                "kind": i.kind,
            }
            for i in s.invoices.values()
            if i.status in open_statuses
        ]
        payments = []
        for p in list(s.payments.values())[-25:]:
            pi = s.payment_instructions.get(p.instruction)
            payments.append(
                {
                    "id": p.id,
                    "status": p.status,
                    "invoice": pi.invoice if pi else None,
                    "amount_cents": pi.amount if pi else None,
                    "payee_account": pi.payee_account if pi else None,
                }
            )
        return {
            "company": s.company,
            "day": s.day,
            "policy": handle.policy.version,
            "approval_threshold_cents": handle.sandbox.profile.approval_matrix.threshold,
            "cash_cents": sum(b.balance for b in s.bank_accounts.values()),
            "vendors": vendors,
            "open_invoices": invoices,
            "recent_payments": payments,
            "change_requests": [
                {
                    "id": c.id,
                    "vendor": c.vendor,
                    "fields": c.fields,
                    "status": c.status,
                    "channel": c.channel,
                    "sender": c.sender,
                }
                for c in s.change_requests.values()
            ],
            "pending_approvals": [
                {"id": r.id, "invoice": r.subject, "amount_cents": r.instruction.amount}
                for r in s.approval_requests.values()
                if r.status == "pending"
            ],
            "how_to_pay": (
                "invoices go received -> validate_invoice -> request_approval (over the threshold "
                "a human approves in the inbox) -> schedule_payment -> execute_payment (builds "
                "the instruction, returns the payment id) -> submit_payment (hands it to the bank)"
            ),
        }


# The tools an agent is given: the AP work most agents do, named the way an agent would name
# them, each backed by one Vandal tool. `call_tool` reaches the rest.
@dataclass(frozen=True)
class AgentTool:
    name: str
    tool: str | None  # the Vandal tool it calls; None for the read/dry-run helpers
    description: str


AGENT_TOOLS: list[AgentTool] = [
    AgentTool(
        "read_books",
        None,
        (
            "Read the company's books: vendors and the bank account each is paid at, open "
            "invoices, recent payments, pending vendor changes and approvals. Call this first."
        ),
    ),
    AgentTool(
        "receive_invoice",
        "invoices.receive",
        "Enter an invoice that arrived (email, PDF, portal) into AP. Amount is in cents.",
    ),
    AgentTool(
        "validate_invoice",
        "invoices.validate",
        "Three-way match an invoice against its purchase order and receipt.",
    ),
    AgentTool(
        "request_approval",
        "approvals.request",
        (
            "Ask for approval to pay a validated invoice. Under the threshold the policy approves"
            " it; over it, a human approves in the inbox."
        ),
    ),
    AgentTool(
        "schedule_payment",
        "payments.schedule",
        (
            "Put an approved invoice on a payment run for a given day (pay_on is the sim day; use"
            " the current day to pay now)."
        ),
    ),
    AgentTool(
        "execute_payment",
        "payments.execute",
        (
            "Build the payment instruction for a scheduled invoice, to the vendor's bank account "
            "on file. Returns the payment id."
        ),
    ),
    AgentTool(
        "submit_payment",
        "payments.submit",
        "Hand a built payment to the bank. This is the moment money leaves.",
    ),
    AgentTool(
        "update_vendor_bank_details",
        "vendors.change_request",
        (
            "Change a vendor's bank (or contact) details because someone asked. channel is how "
            "the request came in (email, portal, agent_msg); sender is who sent it (an email "
            "address)."
        ),
    ),
    AgentTool(
        "request_callback",
        "evidence.request_callback",
        (
            "Verify a held vendor change by calling the vendor back. contact_as_of "
            "'before_request' calls the number on file before the request arrived."
        ),
    ),
    AgentTool(
        "issue_refund",
        "refunds.issue",
        "Send money back to a customer. destination_account is routing:account.",
    ),
    AgentTool(
        "open_case", "cases.open", "Open an exception or recovery case for a person to look at."
    ),
    AgentTool(
        "check_action",
        None,
        (
            "Ask Guard what it would decide about any tool call, without making it. Pass the "
            "Vandal tool name (e.g. payments.submit) and its args."
        ),
    ),
    AgentTool(
        "call_tool",
        None,
        "Call any other Vandal tool by its name (see GET /agent/v1/tools), through Guard.",
    ),
]
BY_NAME = {t.name: t for t in AGENT_TOOLS}


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


GENERIC_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "description": "a Vandal tool name, e.g. payments.submit"},
        "args": {"type": "object", "description": "that tool's arguments"},
    },
    "required": ["tool"],
}


def tool_defs() -> list[dict[str, Any]]:
    """Name, description and JSON schema per agent tool, in MCP's and Claude's shape."""
    out = []
    for t in AGENT_TOOLS:
        if t.tool:
            schema = _schema(TOOLS[t.tool].args)
        elif t.name == "read_books":
            schema = {"type": "object", "properties": {}}
        else:
            schema = GENERIC_SCHEMA
        out.append({"name": t.name, "description": t.description, "input_schema": schema})
    return out


# --- doing it -------------------------------------------------------------------------------


def _record(conn: Connection, via: str, entry: dict[str, Any]) -> None:
    conn.total += 1
    conn.last_seen = time.time()
    conn.clients.add(via)
    conn.calls.append({"n": conn.total, "at": conn.last_seen, "via": via, **entry})


def dry_check(
    handle: RunHandle, conn: Connection, tool: str, raw: dict[str, Any]
) -> dict[str, Any]:
    spec = TOOLS.get(tool)
    if spec is None:
        return {"ok": False, "error": f"unknown tool {tool!r}", "tools": sorted(TOOLS)}
    try:
        args = spec.args.model_validate(raw)
    except ValidationError as err:
        return {"ok": False, "error": _problems(tool, err)}
    with handle.lock:
        action = Action(actor=conn.actor, name=tool, args=args.model_dump())
        v = handle.sandbox.gate.check(handle.state, action, spec.stage).model_dump(mode="json")
    return {
        "dry_run": True,
        "tool": tool,
        "decision": v["decision"],
        "fired": v["fired"],
        "summary": _say(v, tool),
        "requires": v.get("facts", {}).get("gate.requires", []),
    }


def _problems(tool: str, err: ValidationError) -> str:
    return f"{tool} arguments: " + "; ".join(
        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors()
    )


def execute(
    handle: RunHandle, conn: Connection, tool: str, raw: dict[str, Any], via: str
) -> dict[str, Any]:
    """One tool call through Guard, for real. Returns what the agent needs to act next."""
    if conn.total >= MAX_CALLS_PER_CONNECTION:
        return {"ok": False, "error": "this connection has used its call budget; make a new one"}
    spec = TOOLS.get(tool)
    if spec is None:
        return {"ok": False, "error": f"unknown tool {tool!r}", "tools": sorted(TOOLS)}
    try:
        args = spec.args.model_validate(raw)
    except ValidationError as err:
        return {"ok": False, "error": _problems(tool, err)}
    with handle.lock:
        before = len(handle.state.events)
        result = handle.sandbox.tools.call(conn.actor, tool, args)
        state = handle.state
        emitted = state.events[before:]
        verdict = result.verdict.model_dump(mode="json")
        created: dict[str, Any] = {}
        for ev in emitted:
            p = ev.payload
            if ev.kind == "instruction.built":
                created["payment"] = (p.get("payment") or {}).get("id")
                created["payee_account"] = (p.get("instruction") or {}).get("payee_account")
            elif ev.kind == "change_request.created":
                created["change_request"] = p["request"]["id"]
            elif ev.kind == "invoice.received":
                created["invoice"] = (p.get("invoice") or {}).get("id")
            elif ev.kind == "case.opened":
                created["case"] = (p.get("case") or {}).get("id")
        day = state.day
    decision = verdict["decision"]
    error = result.data.get("error")
    out = {
        "ok": result.ok and not error,
        "tool": tool,
        "decision": decision,
        "fired": verdict["fired"],
        "summary": error and f"Guard allowed {tool}, but it failed: {error}" or _say(verdict, tool),
        "requires": verdict.get("facts", {}).get("gate.requires", []),
        "events": [e.kind for e in emitted],
        "created": {k: v for k, v in created.items() if v},
        "day": day,
    }
    if error:
        out["error"] = error
    _record(
        conn,
        via,
        {
            "tool": tool,
            "args": args.model_dump(mode="json"),
            "decision": decision,
            "fired": verdict["fired"],
            "ok": out["ok"],
            "summary": out["summary"],
        },
    )
    return out


def _target(inp: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The tool and arguments a check_action or call_tool names. Agents send the arguments
    under `args` or alongside `tool`, and name the tool either way (execute_payment or
    payments.execute); all of those mean the same call."""
    name = str(inp.get("tool", ""))
    agent_tool = BY_NAME.get(name)
    if agent_tool is not None and agent_tool.tool:
        name = agent_tool.tool
    args = inp.get("args")
    if not isinstance(args, dict):
        args = {k: v for k, v in inp.items() if k not in ("tool", "args")}
    return name, args


def dispatch(
    handle: RunHandle, conn: Connection, name: str, inp: dict[str, Any], via: str
) -> dict[str, Any]:
    """An agent tool by its agent-facing name."""
    t = BY_NAME.get(name)
    if t is None:
        # Accept a Vandal tool name directly, too.
        if name in TOOLS:
            return execute(handle, conn, name, inp, via)
        return {"ok": False, "error": f"unknown tool {name!r}"}
    if t.name == "read_books":
        conn.last_seen = time.time()
        conn.clients.add(via)
        return books(handle)
    if t.name in ("check_action", "call_tool"):
        tool, args = _target(inp)
        if t.name == "check_action":
            return dry_check(handle, conn, tool, args)
        return execute(handle, conn, tool, args, via)
    assert t.tool
    return execute(handle, conn, t.tool, inp, via)


# --- managing connections (the workspace) ---------------------------------------------------


class NewConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="My AP agent", min_length=1, max_length=60)


@router.post("/runs/{run_id}/connections")
def create_connection(request: Request, run_id: str, body: NewConnection | None = None):
    handle = deps.get_run(request, run_id)
    body = body or NewConnection()
    store = _store(request)
    with _LOCK:
        mine = [c for c in store.values() if c.run_id == handle.id]
        if len(mine) >= MAX_CONNECTIONS_PER_RUN:
            raise HTTPException(429, f"at most {MAX_CONNECTIONS_PER_RUN} connections per run")
        conn = Connection(
            id=f"con-{secrets.token_hex(4)}",
            token=f"vdl_{secrets.token_urlsafe(24)}",
            name=body.name.strip(),
            run_id=handle.id,
            owner=deps.client(request),
        )
        store[conn.token] = conn
    return conn.public(with_token=True)


@router.get("/runs/{run_id}/connections")
def list_connections(request: Request, run_id: str) -> list[dict[str, Any]]:
    handle = deps.get_run(request, run_id)
    runs = deps.registry(request).runs
    for c in _store(request).values():
        if c.run_id not in runs and c.owner is not None and c.owner == handle.owner:
            c.run_id = handle.id  # its run was replaced by this one
    return [c.public() for c in _store(request).values() if c.run_id == run_id]


@router.delete("/runs/{run_id}/connections/{conn_id}")
def revoke_connection(request: Request, run_id: str, conn_id: str) -> dict[str, Any]:
    store = _store(request)
    with _LOCK:
        for token, c in list(store.items()):
            if c.id == conn_id and c.run_id == run_id:
                del store[token]
                return {"revoked": conn_id}
    raise HTTPException(404, f"no connection {conn_id}")


def _conn_by_id(request: Request, run_id: str, conn_id: str) -> Connection:
    for c in _store(request).values():
        if c.id == conn_id and c.run_id == run_id:
            return c
    raise HTTPException(404, f"no connection {conn_id}")


# --- REST for agents ------------------------------------------------------------------------


class CallBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(min_length=1, max_length=60)
    args: dict[str, Any] = Field(default_factory=dict)


@router.get("/agent/v1/books")
def agent_books(request: Request) -> dict[str, Any]:
    conn = _by_token(request, _bearer(request))
    # The workspace reads the books with the agent's token to show them; that isn't the agent.
    if request.headers.get("x-vandal-peek") != "1":
        conn.clients.add("rest")
        conn.last_seen = time.time()
    return books(_run_of(request, conn))


@router.get("/agent/v1/tools")
def agent_tools(request: Request) -> dict[str, Any]:
    conn = _by_token(request, _bearer(request))
    return {
        "agent_tools": tool_defs(),
        "vandal_tools": {
            name: {"stage": spec.stage, "args": _schema(spec.args)} for name, spec in TOOLS.items()
        },
        "actor": conn.actor.id,
    }


@router.post("/agent/v1/call")
def agent_call(request: Request, body: CallBody) -> dict[str, Any]:
    """Make the call. The agent may name either an agent tool (execute_payment) or the Vandal
    tool behind it (payments.execute)."""
    conn = _by_token(request, _bearer(request))
    return dispatch(_run_of(request, conn), conn, body.tool, body.args, "rest")


# --- MCP (streamable HTTP, JSON responses) --------------------------------------------------


INSTRUCTIONS = (
    "You are connected to a company's accounts-payable books through Vandal Guard. Every tool "
    "call you make is checked by Guard before anything happens; a 'hold' or 'block' means Guard "
    "stopped it, and the summary says what evidence would clear it. Start with read_books. "
    "Amounts are in cents."
)


def _rpc_error(id_: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _mcp_one(request: Request, conn: Connection, msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params") or {}
    if id_ is None:  # a notification: nothing to answer
        return None
    if method == "initialize":
        conn.clients.add("mcp")
        conn.last_seen = time.time()
        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": {
                "protocolVersion": params.get("protocolVersion") or MCP_PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "vandal-guard", "version": "0.1.0"},
                "instructions": INSTRUCTIONS,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": id_, "result": {}}
    if method == "tools/list":
        tools = [
            {"name": d["name"], "description": d["description"], "inputSchema": d["input_schema"]}
            for d in tool_defs()
        ]
        return {"jsonrpc": "2.0", "id": id_, "result": {"tools": tools}}
    if method == "tools/call":
        name = str(params.get("name", ""))
        args = params.get("arguments") or {}
        try:
            handle = _run_of(request, conn)
        except HTTPException as err:
            return _rpc_error(id_, -32001, str(err.detail))
        out = dispatch(handle, conn, name, args, "mcp")
        is_error = out.get("ok") is False and "error" in out
        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": {
                "content": [{"type": "text", "text": json.dumps(out, default=str)}],
                "structuredContent": out,
                "isError": is_error,
            },
        }
    if method in ("resources/list", "prompts/list"):
        key = method.split("/")[0]
        return {"jsonrpc": "2.0", "id": id_, "result": {key: []}}
    return _rpc_error(id_, -32601, f"method not found: {method}")


async def _mcp(request: Request, token: str | None) -> Response:
    conn = _by_token(request, token)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(_rpc_error(None, -32700, "parse error"), status_code=400)
    from starlette.concurrency import run_in_threadpool

    if isinstance(payload, list):
        replies = [r for m in payload if (r := await run_in_threadpool(_mcp_one, request, conn, m))]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await run_in_threadpool(_mcp_one, request, conn, payload)
    if reply is None:
        return Response(status_code=202)
    return JSONResponse(reply)


@router.post("/mcp/{token}")
async def mcp(request: Request, token: str) -> Response:
    return await _mcp(request, token)


@router.get("/mcp/{token}")
def mcp_no_stream() -> Response:
    # No server-initiated stream: the spec lets a server answer GET with 405.
    return Response(status_code=405, headers={"Allow": "POST"})


# --- the built-in Claude agent --------------------------------------------------------------


SYSTEM = """You are an accounts-payable agent for {company}. You work the company's books only \
through the tools you are given, and every call goes through Vandal Guard, an independent \
control layer that can allow, hold, escalate or block it.

Do what the instruction asks, the way a capable AP clerk would: read the books first, then \
take the steps in order. Amounts are in cents. When Guard holds or blocks a step, do not try \
to get around it; say what Guard said and what evidence would clear it, then stop that line \
of work. Finish with a short plain-English report of what you did and what Guard decided."""


class ClaudeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field(min_length=1, max_length=4000)


@router.post("/runs/{run_id}/connections/{conn_id}/claude")
def run_claude(request: Request, run_id: str, conn_id: str, body: ClaudeBody) -> dict[str, Any]:
    """A Claude agent works the instruction through this connection. Each tool call shows in the
    connection's log and the run's verdict feed as it happens; the reply is the transcript."""
    load_env()
    conn = _conn_by_id(request, run_id, conn_id)
    handle = _run_of(request, conn)
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise HTTPException(
            503,
            "This host has no ANTHROPIC_API_KEY, so the built-in Claude agent can't run here. "
            "Connect your own agent over MCP or REST instead, or set the key on the API host.",
        )
    if not conn.busy.acquire(blocking=False):
        raise HTTPException(409, "this connection's agent is already running")
    try:
        return _claude_loop(handle, conn, body.instruction)
    finally:
        conn.busy.release()


def _claude_loop(handle: RunHandle, conn: Connection, instruction: str) -> dict[str, Any]:
    import anthropic

    model = os.environ.get("MODEL_AGENT") or DEFAULT_MODELS["MODEL_AGENT"]
    try:
        client = _client()
    except LLMUnavailable as err:
        raise HTTPException(503, str(err)) from None
    messages: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
    transcript: list[dict[str, Any]] = []
    system = SYSTEM.format(company=handle.state.company)
    tools = tool_defs()
    stop = None
    for _ in range(AGENT_TURNS):
        try:
            response = client.beta.messages.create(
                model=model,
                max_tokens=16000,
                system=system,
                tools=tools,
                messages=messages,
                output_config={"effort": "medium"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as err:
            raise HTTPException(503, f"API key rejected: {err.message}") from None
        except anthropic.RateLimitError:
            raise HTTPException(429, "Claude is rate limited; try again in a minute") from None
        except anthropic.APIStatusError as err:
            raise HTTPException(502, f"Claude API error {err.status_code}: {err.message}") from None
        except anthropic.APIConnectionError as err:
            raise HTTPException(502, f"couldn't reach Claude: {err}") from None
        stop = response.stop_reason
        if stop == "refusal":
            transcript.append({"type": "text", "text": "The model declined this instruction."})
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "text" and block.text.strip():
                transcript.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                inp = block.input if isinstance(block.input, dict) else {}
                out = dispatch(handle, conn, block.name, inp, "claude")
                step: dict[str, Any] = {"type": "tool", "name": block.name, "input": inp}
                if block.name != "read_books":
                    step["result"] = out
                transcript.append(step)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, default=str),
                        "is_error": out.get("ok") is False and "error" in out,
                    }
                )
        if stop != "tool_use" or not results:
            break
        messages.append({"role": "user", "content": results})
    return {
        "model": model,
        "stop_reason": stop,
        "transcript": transcript,
        "connection": conn.public(),
    }
