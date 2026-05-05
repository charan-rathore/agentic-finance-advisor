"""
run.py

Single-command launcher for Paisa Pal. Spawns the multi-agent backend and the
Streamlit UI in one process group so a developer can clone the repo, set the
GEMINI_API_KEY in .env, and run

    python run.py

without needing two terminals. Both children inherit the parent's stdout, so
their logs interleave in one window.

The launcher handles SIGINT and SIGTERM cleanly: it sends the signal to both
children, waits up to 5 seconds, and then escalates to terminate.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _launch(cmd: list[str], name: str) -> subprocess.Popen[bytes]:
    print(f"[run.py] starting {name}: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=ROOT)


def _shutdown(procs: dict[str, subprocess.Popen[bytes]]) -> None:
    print("\n[run.py] shutting down children...")
    for name, p in procs.items():
        if p.poll() is None:
            try:
                p.send_signal(signal.SIGINT)
            except Exception as exc:
                print(f"[run.py] signal to {name} failed: {exc}")
    deadline = time.monotonic() + 5.0
    for name, p in procs.items():
        timeout = max(0.1, deadline - time.monotonic())
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"[run.py] {name} did not stop in time, terminating")
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()


def main() -> int:
    python = sys.executable

    procs: dict[str, subprocess.Popen[bytes]] = {}
    skip_agents = os.environ.get("PAISA_SKIP_AGENTS") == "1"

    if not skip_agents:
        procs["agents"] = _launch([python, str(ROOT / "main.py")], "agents (main.py)")
    else:
        print("[run.py] PAISA_SKIP_AGENTS=1 set, only launching the UI")

    procs["ui"] = _launch(
        [python, "-m", "streamlit", "run", str(ROOT / "ui" / "app.py")],
        "Streamlit UI (ui/app.py)",
    )

    try:
        while True:
            time.sleep(1)
            for name, p in procs.items():
                if p.poll() is not None:
                    print(f"[run.py] child '{name}' exited with code {p.returncode}")
                    _shutdown(procs)
                    return p.returncode or 1
    except KeyboardInterrupt:
        _shutdown(procs)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
