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


IMPLEMENTED: dict[str, Callable[[argparse.Namespace], int]] = {"seed": cmd_seed}


def build_parser() -> argparse.ArgumentParser:
    from vandal.twin.seed import DEFAULT_SEED

    parser = argparse.ArgumentParser(prog="vandal", description="Vandal Sandbox CLI")
    sub = parser.add_subparsers(dest="command", metavar="command", required=True)
    for name, (help_text, _slice) in COMMANDS.items():
        cmd = sub.add_parser(name, help=help_text)
        if name == "seed":
            cmd.add_argument("--profile", default="bayline", help="profile name or YAML path")
            cmd.add_argument("--seed", type=int, default=DEFAULT_SEED)
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
