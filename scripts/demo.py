"""One command for the whole demo: the API, the war room, and (optionally) playback.

    python scripts/demo.py             # API :8000, war room :3000, Claude live if a key is set
    python scripts/demo.py --playback  # no network: LLM answers come from backend/llm_cache
    python scripts/demo.py --mock      # no backend at all: the war room replays recorded fixtures

Needs Python 3.12 with uv (`python -m uv`), and Node (`npm install` is run in frontend/ when
node_modules is missing). Ctrl+C stops both processes.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
# Each child gets its own process group on Windows, so the CTRL_BREAK_EVENT sent on shutdown
# reaches it (and the node/uvicorn processes under it) and not this script's console group.
GROUP = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}


def wait_for(url: str, seconds: float, label: str) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:  # noqa: S310 (localhost)
                if r.status < 500:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    print(f"!! {label} didn't answer at {url} within {seconds:.0f}s", file=sys.stderr)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--playback", action="store_true", help="serve LLM answers from the cache only")
    ap.add_argument("--mock", action="store_true", help="war room only, from recorded fixtures")
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=3000)
    ap.add_argument("--no-install", action="store_true", help="don't run npm install")
    args = ap.parse_args()

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if npm is None:
        print("npm not found on PATH", file=sys.stderr)
        return 2
    if not args.no_install and not (FRONTEND / "node_modules").exists():
        print(">> npm install (first run)")
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)

    procs: list[subprocess.Popen] = []
    try:
        if not args.mock:
            playback = "true" if args.playback else os.environ.get("DEMO_PLAYBACK", "false")
            origins = f"http://localhost:{args.web_port},http://127.0.0.1:{args.web_port}"
            env = os.environ | {"DEMO_PLAYBACK": playback, "VANDAL_CORS_ORIGINS": origins}
            mode = " (playback)" if args.playback else ""
            print(f">> API on http://localhost:{args.api_port}{mode}")
            uvicorn = ["uvicorn", "vandal.api.main:app", "--port", str(args.api_port)]
            # A standalone uv on PATH (the installer's default) first, else the pip module.
            uv = [shutil.which("uv")] if shutil.which("uv") else [sys.executable, "-m", "uv"]
            cmd = [*uv, "run", *uvicorn]
            procs.append(subprocess.Popen(cmd, cwd=BACKEND, env=env, **GROUP))
            wait_for(f"http://localhost:{args.api_port}/settings", 60, "the API")

        web_env = os.environ | {
            "NEXT_PUBLIC_VANDAL_API": f"http://localhost:{args.api_port}",
            "NEXT_PUBLIC_VANDAL_MOCK": "1" if args.mock else "0",
        }
        print(f">> war room on http://localhost:{args.web_port}{' (mock)' if args.mock else ''}")
        web = [npm, "exec", "--", "next", "dev", "-p", str(args.web_port)]
        procs.append(subprocess.Popen(web, cwd=FRONTEND, env=web_env, **GROUP))
        if wait_for(f"http://localhost:{args.web_port}/", 120, "the war room"):
            print(f"\nOpen http://localhost:{args.web_port}  (Ctrl+C stops everything)\n")
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        for p in procs:
            if p.poll() is not None:
                print(f"!! a process exited with {p.returncode}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                try:
                    p.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM)
                except Exception:  # noqa: BLE001
                    p.terminate()
        for p in procs:
            try:
                p.wait(10)
            except Exception:  # noqa: BLE001
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
