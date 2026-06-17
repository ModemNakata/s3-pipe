from __future__ import annotations

import os
import shutil
import sys

import log
from config import VideoConfig, ImageConfig


def check_video(cfg: VideoConfig) -> None:
    for tool in ("ffmpeg", "ffprobe", "mc"):
        if not shutil.which(tool):
            print(f"[deps] ERROR: required tool '{tool}' not found in PATH")
            sys.exit(1)

    if not os.path.exists(cfg.input_video):
        print(f"[deps] ERROR: input file '{cfg.input_video}' not found")
        sys.exit(1)

    r = log.run_cmd(["ffmpeg", "-encoders"], module="deps")
    if cfg.video_codec not in r.stdout:
        log.info("deps", f"ERROR: encoder '{cfg.video_codec}' not available in ffmpeg")
        sys.exit(1)

    log.info("deps", "video dependencies satisfied")


def check_image(cfg: ImageConfig) -> None:
    for tool in ("ffmpeg", "mc"):
        if not shutil.which(tool):
            print(f"[deps] ERROR: required tool '{tool}' not found in PATH")
            sys.exit(1)

    if not os.path.isdir(cfg.input_dir):
        print(f"[deps] ERROR: input directory '{cfg.input_dir}' not found")
        sys.exit(1)

    r = log.run_cmd(["ffmpeg", "-encoders"], module="deps")
    if "libsvtav1" not in r.stdout:
        log.info("deps", "ERROR: libsvtav1 encoder not available in ffmpeg")
        sys.exit(1)

    log.info("deps", "image dependencies satisfied")
