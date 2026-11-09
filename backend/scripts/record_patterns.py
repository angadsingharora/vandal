"""Record Moss pattern recalls for the demo's messages, so playback shows Moss answers offline.

Replays every trace in scenarios/, five days of legitimate operations, and every held-out
variant verification draws from (verify/variants.grid), then asks Moss about each inbound message
with text. Recordings are keyed with digits masked, so they cover the fresh account numbers
Strike writes into each attack. Recordings land in PATTERN_CACHE_DIR (default
backend/pattern_cache/) and are safe to commit: each holds the message text and the pattern ids.

    uv run python scripts/record_patterns.py          # needs MOSS_PROJECT_ID / MOSS_PROJECT_KEY
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path

from vandal.guard import patterns
from vandal.llm import load_env
from vandal.sandbox import new_sandbox
from vandal.twin.profile import load_profile
from vandal.verify.replay import Trace, replay_detailed
from vandal.verify.variants import grid

BACKEND = Path(__file__).resolve().parents[1]


def messages(state) -> list[str]:
    out = []
    for e in state.events:
        msg = e.payload.get("message") or {} if e.kind == "channel.received" else {}
        if msg and msg.get("channel") not in ("system", "bank_feed"):
            text = patterns.message_text(msg)
            if text:
                out.append(text)
    return out


def main() -> int:
    load_env()
    if not patterns.configured():
        print("set MOSS_PROJECT_ID and MOSS_PROJECT_KEY (backend/.env)", file=sys.stderr)
        return 1
    texts: list[str] = []
    for path in sorted((BACKEND / "scenarios").glob("*.json")):
        _, sb, _ = replay_detailed(
            7, Trace.load(path).moves, sandbox=partial(new_sandbox, "bayline")
        )
        texts += messages(sb.run.state)
    texts += messages(new_sandbox("bayline").operate(5).run.state)
    for variant in grid(new_sandbox("bayline").run.state, load_profile("bayline")):
        _, sb, _ = replay_detailed(7, variant.moves, sandbox=partial(new_sandbox, "bayline"))
        texts += messages(sb.run.state)
    sources: dict[str, int] = {}
    unique = {patterns._key(t): t for t in texts}
    for text in unique.values():
        r = patterns.recall(text)
        sources[r.source] = sources.get(r.source, 0) + 1
        if r.source == "lexical":
            print(f"not recorded: {r.note}", file=sys.stderr)
            return 1
    print(f"{len(unique)} messages: {sources} -> {patterns.cache_dir()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
