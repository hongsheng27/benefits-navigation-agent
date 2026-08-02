#!/usr/bin/env python3
"""Free the backend port, then start uvicorn with --reload.

Use this (or `make backend`) instead of starting another raw uvicorn.
On Windows, orphaned `--reload` workers often keep serving old code on the port.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEFAULT_PORT = 8000


def _port() -> int:
    raw = os.environ.get("BACKEND_PORT", str(DEFAULT_PORT)).strip()
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


def _uvicorn_pids() -> set[int]:
    """Best-effort: any local uvicorn serving app.main:app."""
    pids: set[int] = set()
    if sys.platform == "win32":
        result = _run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { "
                    "$_.CommandLine -and "
                    "$_.CommandLine -match 'uvicorn\\s+app\\.main:app' "
                    "} | Select-Object -ExpandProperty ProcessId"
                ),
            ]
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
        return pids

    result = _run(
        [
            "bash",
            "-lc",
            "ps -ao pid=,args= | grep -F 'uvicorn app.main:app' | grep -v grep || true",
        ]
    )
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if parts and parts[0].isdigit():
            pids.add(int(parts[0]))
    return pids


def _kill(pids: set[int]) -> None:
    for pid in sorted(pids):
        if pid <= 0:
            continue
        try:
            if sys.platform == "win32":
                _run(["taskkill", "/F", "/PID", str(pid), "/T"])
            else:
                os.kill(pid, 9)
            print(f"stopped pid {pid}", flush=True)
        except (OSError, ProcessLookupError):
            pass


def free_backend_port(port: int) -> None:
    """Kill listeners on port and leftover uvicorn app.main workers."""
    targets = _pids_listening_on(port) | _uvicorn_pids()
    # Never kill ourselves.
    targets.discard(os.getpid())
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
    left = _pids_listening_on(port)
    if left:
        print(
            f"warning: port {port} still held by {sorted(left)}; starting anyway",
            flush=True,
        )


def main() -> int:
    port = _port()
    free_backend_port(port)
    cmd = [
        "uv",
        "run",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--reload",
    ]
    print(f"starting: {' '.join(cmd)} (cwd={BACKEND})", flush=True)
    os.chdir(BACKEND)
    if sys.platform == "win32":
        return subprocess.call(cmd)
    os.execvp(cmd[0], cmd)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
