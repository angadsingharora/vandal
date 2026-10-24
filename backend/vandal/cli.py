"""vandal seed | run | attack | search | synth | verify | inject"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable

# Exhaustive depth 4 takes ~75s even with partial-order reduction and 8-10 workers, so the
# default is 3 (IMPLEMENTATION R4, step 5). --depth 4 still works.
DEFAULT_DEPTH = 3

COMMANDS: dict[str, tuple[str, str]] = {
    "seed": ("Print the seeded company summary", "R1"),
    "run": ("Run legitimate operations for N business days", "R2"),
    "attack": ("Replay a hand-written adversary trace", "R3"),
    "search": ("Bounded adversarial search for violations", "R4"),
    "synth": ("Diagnose and synthesize a control (CEGIS)", "R8"),
    "verify": ("Run the verification suite against a policy", "R7"),
    "inject": ("Run a user-authored threat in plain language", "R9"),
}


def cmd_seed(args: argparse.Namespace) -> int:
    from vandal.twin.profile import load_profile
    from vandal.twin.seed import seed_state, summary

    profile = load_profile(args.profile)
    print(summary(seed_state(profile, seed=args.seed), profile))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from collections import Counter

    from vandal.sandbox import new_sandbox
    from vandal.verify.invariants import check

    sb = new_sandbox(args.profile, seed=args.seed).operate(args.days)
    state = sb.run.state
    verdicts = Counter(
        e.payload["verdict"]["decision"] for e in state.events if e.kind == "gate.verdict"
    )
    statuses = Counter(i.status for i in state.invoices.values())
    pays = Counter(p.status for p in state.payments.values())
    violations = check(state)
    print(f"{state.company}: ran {args.days} business days (now day {state.day})")
    print(f"  tool calls       {sb.tools.calls}  verdicts {dict(sorted(verdicts.items()))}")
    print(f"  invoices         {dict(sorted(statuses.items()))}")
    print(f"  payments         {dict(sorted(pays.items()))}")
    for ba in state.bank_accounts.values():
        print(f"  bank {ba.name:<11} ${ba.balance / 100:,.2f}")
    print(f"  invariants       {'all hold' if not violations else ''}")
    for v in violations:
        print(f"    {v.invariant}: {v.message}")
    print(f"  events           {len(state.events)}")
    print(f"  state_hash       {state.state_hash()}")
    return 1 if violations else 0


def cmd_attack(args: argparse.Namespace) -> int:
    from functools import partial

    from vandal.sandbox import new_sandbox
    from vandal.verify.replay import Trace, replay_detailed

    trace = Trace.load(args.trace)
    result, sb, _ = replay_detailed(
        trace.seed, trace.moves, days=trace.days, sandbox=partial(new_sandbox, args.profile)
    )
    print(f"trace {trace.name}: {len(trace.moves)} moves, seed {trace.seed}, {trace.days} days")
    for m in trace.moves:
        params = " ".join(f"{k}={v}" for k, v in m.params.items())
        print(f"  @{m.at:<3} {m.kind} {params}".rstrip())
    if not result.violations:
        print("no violations: the controls held")
    else:
        print(f"VIOLATED {', '.join(result.violated)}")
        for v in result.violations:
            print(f"  {v.invariant}  {v.message}")
    print(f"exposure    ${result.exposure / 100:,.2f}  ({result.exposure} cents)")
    print(f"state_hash  {result.state_hash}")
    _print_diagnosis(sb, result.violations)
    return 0


def _timeline(state, subjects: set[str]) -> list[str]:
    """The events behind the violating payments: approval, change, execution, settlement."""
    pays = {s for s in subjects if s in state.payments}
    invoices = {state.payment_instructions[state.payments[p].instruction].invoice for p in pays}
    accounts = {
        state.payment_instructions[state.payments[p].instruction].payee_account for p in pays
    }
    keep = (
        "approval.requested",
        "approval.granted",
        "channel.received",
        "change_request.created",
        "vendor.bank_changed",
        "instruction.built",
        "payment.submitted",
        "bank.settled",
    )
    lines = []
    for e in state.events:
        if e.kind not in keep:
            continue
        blob = str(e.payload)
        if any(x in blob for x in invoices | pays | accounts) or e.kind == "channel.received":
            what = {
                "approval.requested": lambda p: f"{p['request']['subject']} waits in the inbox",
                "approval.granted": lambda p: (
                    f"{p['approval']['subject']} approved by {p['approval']['approver']} to "
                    f"{p['approval']['approved_instruction']['payee_account']}"
                ),
                "channel.received": lambda p: (
                    f"{p['message']['channel']} from {p['message']['sender']}: "
                    f"{p['message']['subject']}"
                ),
                "change_request.created": lambda p: (
                    f"{p['request']['id']} {p['request']['status']} for {p['request']['vendor']}"
                ),
                "vendor.bank_changed": lambda p: f"vendor master now pays {p['account']['id']}",
                "instruction.built": lambda p: (
                    f"{p['payment']['id']} built to {p['instruction']['payee_account']} "
                    f"for {p['instruction']['amount']}"
                ),
                "payment.submitted": lambda p: f"{p['payment']} submitted",
                "bank.settled": lambda p: f"{p['transaction']['payment']} settled",
            }[e.kind](e.payload)
            lines.append(f"  day {e.day}  {e.id}  {e.kind:<23} {what}")
    return lines


def _print_diagnosis(sb, violations) -> None:
    from vandal.synth.coverage import diagnose
    from vandal.verify.invariants import Limits

    d = diagnose(sb.run.state, violations, Limits.from_profile(sb.profile))
    if d is None:
        return
    also = f" (also: {', '.join(d.also)})" if d.also else ""
    print(f"diagnosis: {d.gap} at the {d.link} link of {d.payment}{also}")
    print(f"  {d.reason}")
    for ln in d.chain.links:
        print(f"  {ln.name:<10} {ln.status:<9} {ln.gap or '':<22} {ln.reason}")
    print(f"  cites {', '.join(d.cites)}")


def cmd_search(args: argparse.Namespace) -> int:
    from functools import partial

    from vandal.sandbox import new_sandbox
    from vandal.search.alphabet import SCENARIOS
    from vandal.search.bfs import search
    from vandal.search.minimize import minimize_trace
    from vandal.verify.replay import replay, replay_detailed

    scenario = SCENARIOS[args.scenario]
    factory = partial(new_sandbox, args.profile)
    result = search(
        factory,
        scenario,
        seed=args.seed,
        depth=args.depth,
        workers=args.workers,
        exhaustive=args.exhaustive,
    )
    print(f"scenario {scenario.name}: {scenario.description}")
    print(
        f"  alphabet          {result.alphabet} moves, depth <= {result.depth}, "
        f"{scenario.days} days, workers {result.workers}"
    )
    print(f"  explored          {result.explored} sequences (per depth: {result.levels})")
    print(
        f"  deduped           {result.deduped} by state hash, {result.pruned} skipped by "
        "partial-order reduction"
    )
    print(
        f"  throughput        {result.runs_per_second:,.0f} runs/s, "
        f"{result.ms_per_run:.2f} ms/run, {result.seconds:.2f}s"
    )
    if result.best is None:
        print(f"no violations within depth {result.depth}")
        return 0
    n, shortest = len(result.findings), len(result.best.moves)
    print(f"  violating         {n} sequences (shortest: {shortest} moves)")

    def violated(moves):
        return set(replay(args.seed, moves, sandbox=factory, days=scenario.days).violated)

    minimal = minimize_trace(result.best.moves, violated)
    final, sb, _ = replay_detailed(args.seed, minimal, sandbox=factory, days=scenario.days)
    print(f"minimal counterexample ({len(minimal)} move{'s' if len(minimal) != 1 else ''}):")
    for m in minimal:
        params = " ".join(f"{k}={v}" for k, v in m.params.items())
        print(f"  @{m.at:<3} {m.kind} {params}".rstrip())
    print(f"VIOLATED {', '.join(final.violated)}  exposure ${final.exposure / 100:,.2f}")
    for v in final.violations:
        print(f"  {v.invariant}  {v.message}")
    print("timeline:")
    for line in _timeline(sb.run.state, {v.subject for v in final.violations}):
        print(line)
    _print_diagnosis(sb, final.violations)
    return 0


IMPLEMENTED: dict[str, Callable[[argparse.Namespace], int]] = {
    "search": cmd_search,
    "seed": cmd_seed,
    "run": cmd_run,
    "attack": cmd_attack,
}


def build_parser() -> argparse.ArgumentParser:
    from vandal.twin.seed import DEFAULT_SEED

    parser = argparse.ArgumentParser(prog="vandal", description="Vandal Sandbox CLI")
    sub = parser.add_subparsers(dest="command", metavar="command", required=True)
    for name, (help_text, _slice) in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text)
        if name in ("seed", "run", "attack", "search"):
            cmd.add_argument("--profile", default="bayline", help="profile name or YAML path")
            cmd.add_argument("--seed", type=int, default=DEFAULT_SEED)
        if name == "run":
            cmd.add_argument("--days", type=int, default=5)
        if name == "search":
            cmd.add_argument("--scenario", default="a", help="scenario name (search/alphabet.py)")
            cmd.add_argument(
                "--depth", type=int, default=int(os.environ.get("SEARCH_DEPTH", DEFAULT_DEPTH))
            )
            cmd.add_argument(
                "--workers", type=int, default=int(os.environ.get("SEARCH_WORKERS", 1))
            )
            cmd.add_argument(
                "--exhaustive",
                action="store_true",
                help="explore every depth, not just up to the first violations",
            )
        if name == "attack":
            cmd.add_argument("--trace", required=True, help="path to a trace JSON file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args, _rest = build_parser().parse_known_args(argv)
    if args.command in IMPLEMENTED:
        return IMPLEMENTED[args.command](args)
    _help, slice_id = COMMANDS[args.command]
    print(f"vandal {args.command}: not implemented yet (lands in {slice_id})", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
