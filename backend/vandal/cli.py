"""vandal seed | run | attack | search | synth | verify | inject"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

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
    from vandal.sandbox import replay_with_reference
    from vandal.verify.replay import Trace

    trace = Trace.load(args.trace)
    result = replay_with_reference(trace, args.profile)
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
    return 0


IMPLEMENTED: dict[str, Callable[[argparse.Namespace], int]] = {
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
        if name in ("seed", "run", "attack"):
            cmd.add_argument("--profile", default="bayline", help="profile name or YAML path")
            cmd.add_argument("--seed", type=int, default=DEFAULT_SEED)
        if name == "run":
            cmd.add_argument("--days", type=int, default=5)
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
