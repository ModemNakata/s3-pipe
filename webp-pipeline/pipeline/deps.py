from __future__ import annotations

import os
import shutil
import subprocess
import sys

from config import Config


def check(config: Config) -> None:
    for tool in ("ffmpeg", "mc"):
        if not shutil.which(tool):
            print(f"[deps] ERROR: required tool '{tool}' not found in PATH")
            sys.exit(1)

    if not os.path.isdir(config.input_dir):
        print(f"[deps] ERROR: input directory '{config.input_dir}' not found")
        sys.exit(1)

    # Check for libwebp encoder in ffmpeg
    r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
    if "libwebp" not in r.stdout and "libwebp_anim" not in r.stdout:
        print("[deps] ERROR: libwebp encoder not available in ffmpeg")
        sys.exit(1)

    print("[deps] all dependencies satisfied")
