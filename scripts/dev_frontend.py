#!/usr/bin/env python3
"""Free the Vite port, then start the frontend dev server.

Use this (or `make frontend`) so a second `npm run dev` does not bind a
surprise alternate port while the browser still hits 5173.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DEFAULT_PORT = 5173


def _port() -> int:
    raw = os.environ.get("FRONTEND_PORT", str(DEFAULT_PORT)).strip()
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _pids_listening_on(port: int) -> set[int]:
    pids: set[int] = set()
    if sys.platform == "win32":
        result = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    f"Get-NetTCPConnection -LocalPort {port} -State Listen "
                    "-ErrorAction SilentlyContinue | "
                    "Select-Object -ExpandProperty OwningProcess -Unique"
                ),
            ]
        )
    else:
        result = _run(["bash", "-lc", f"lsof -tiTCP:{port} -sTCP:LISTEN || true"])

    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(int(line))
    return pids


def _kill(pids: set[int]) -> None:
    for pid in sorted(pids):
        if pid <= 0 or pid == os.getpid():
            continue
        try:
            if sys.platform == "win32":
                _run(["taskkill", "/F", "/PID", str(pid), "/T"])
            else:
                os.kill(pid, 9)
            print(f"stopped pid {pid}", flush=True)
        except (OSError, ProcessLookupError):
            pass


def free_frontend_port(port: int) -> None:
    targets = _pids_listening_on(port)
    if not targets:
        print(f"port {port} already free", flush=True)
        return
    print(f"freeing port {port}: {sorted(targets)}", flush=True)
    _kill(targets)
    deadline = time.time() + 8
    while time.time() < deadline:
        if not _pids_listening_on(port):
            print(f"port {port} is free", flush=True)
            return
        time.sleep(0.25)


def main() -> int:
    port = _port()
    free_frontend_port(port)
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    cmd = [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    print(f"starting: {' '.join(cmd)} (cwd={FRONTEND})", flush=True)
    os.chdir(FRONTEND)
    if sys.platform == "win32":
        return subprocess.call(cmd)
    os.execvp(cmd[0], cmd)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
