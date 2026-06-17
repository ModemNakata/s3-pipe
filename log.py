from __future__ import annotations

import os
import subprocess
import sys
import threading
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


def _load_stream_output() -> bool:
    val = os.environ.get("STREAM_CMD_OUTPUT")
    if val:
        return val.lower() in ("true", "1", "yes")
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("STREAM_CMD_OUTPUT="):
                return line.split("=", 1)[1].strip().lower() in ("true", "1", "yes")
    return False


STREAM_CMD_OUTPUT = _load_stream_output()


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
    if is_debug():
        debug(module, f"$ {' '.join(cmd)}")

    t0 = time.time()

    if STREAM_CMD_OUTPUT:
        kwargs.pop("capture_output", None)
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True
        kwargs["bufsize"] = 1

        proc = subprocess.Popen(cmd, **kwargs)
        out_lines: list[str] = []
        err_lines: list[str] = []

        def _pipe(stream: Any, lines: list[str], dest: Any) -> None:
            for line in iter(stream.readline, ""):
                lines.append(line)
                dest.write(line)
                dest.flush()

        threads = [
            threading.Thread(target=_pipe, args=(proc.stdout, out_lines, sys.stdout)),
            threading.Thread(target=_pipe, args=(proc.stderr, err_lines, sys.stderr)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        proc.wait()

        elapsed = time.time() - t0
        if is_debug():
            debug(module, f"returncode: {proc.returncode}  ({elapsed:.2f}s)")

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout="".join(out_lines),
            stderr="".join(err_lines),
        )

    kwargs["capture_output"] = True
    kwargs["text"] = True
    proc = subprocess.run(cmd, **kwargs)
    elapsed = time.time() - t0
    if is_debug():
        debug(module, f"returncode: {proc.returncode}  ({elapsed:.2f}s)")

    return proc
