from __future__ import annotations

import os
import shutil
import subprocess
import sys

from config import VideoConfig, ImageConfig


def check_video(cfg: VideoConfig) -> None:
    for tool in ("ffmpeg", "ffprobe", "mc"):
        if not shutil.which(tool):
            print(f"[deps] ERROR: required tool '{tool}' not found in PATH")
            sys.exit(1)

    if not os.path.exists(cfg.input_video):
        print(f"[deps] ERROR: input file '{cfg.input_video}' not found")
        sys.exit(1)

    r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
    if cfg.video_codec not in r.stdout:
        print(f"[deps] ERROR: encoder '{cfg.video_codec}' not available in ffmpeg")
        sys.exit(1)

    print("[deps] video dependencies satisfied")


def check_image(cfg: ImageConfig) -> None:
    for tool in ("ffmpeg", "mc"):
        if not shutil.which(tool):
            print(f"[deps] ERROR: required tool '{tool}' not found in PATH")
            sys.exit(1)

    if not os.path.isdir(cfg.input_dir):
        print(f"[deps] ERROR: input directory '{cfg.input_dir}' not found")
        sys.exit(1)

    r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
    if "libwebp" not in r.stdout and "libwebp_anim" not in r.stdout:
        print("[deps] ERROR: libwebp encoder not available in ffmpeg")
        sys.exit(1)

    print("[deps] image dependencies satisfied")
