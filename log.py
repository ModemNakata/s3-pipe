from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any


def _load_log_level() -> str:
    level = os.environ.get("LOG_LEVEL")
    if level:
        return level.upper()
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("LOG_LEVEL="):
                return line.split("=", 1)[1].strip().upper()
    return "INFO"


LOG_LEVEL = _load_log_level()


def is_debug() -> bool:
    return LOG_LEVEL == "DEBUG"


def info(module: str, msg: str) -> None:
    print(f"[{module}] {msg}")


def debug(module: str, msg: str) -> None:
    if is_debug():
        print(f"[{module}] [DEBUG] {msg}")


def run_cmd(
    cmd: list[str],
    module: str = "cmd",
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    kwargs["capture_output"] = True
    kwargs["text"] = True

    if is_debug():
        debug(module, f"$ {' '.join(cmd)}")

    t0 = time.time()
    proc = subprocess.run(cmd, **kwargs)
    elapsed = time.time() - t0

    if is_debug():
        debug(module, f"returncode: {proc.returncode}  ({elapsed:.2f}s)")
        if proc.stdout:
            out = proc.stdout
            if len(out) > 2000:
                out = out[:2000] + f"\n[DEBUG] (... {len(proc.stdout)} total chars)"
            debug(module, f"stdout:\n{out}")
        if proc.stderr:
            err = proc.stderr
            if len(err) > 2000:
                err = err[:2000] + f"\n[DEBUG] (... {len(proc.stderr)} total chars)"
            debug(module, f"stderr:\n{err}")

    return proc
