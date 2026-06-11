from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from config import ImageConfig


def run(cfg: ImageConfig) -> int:
    filter_string = None
    parts = []
    if cfg.max_dimension > 0:
        parts.append(
            f"scale='if(gt(iw,ih),{cfg.max_dimension},-2)':"
            f"'if(gt(iw,ih),-2,{cfg.max_dimension})'"
        )
    if parts:
        filter_string = ",".join(parts)

    total_in = 0
    total_out = 0
    count = 0
    skipped = 0

    for src_path in sorted(Path(cfg.input_dir).iterdir()):
        if not src_path.is_file():
            continue

        stem = src_path.stem
        out_name = f"{stem}.webp"
        out_path = os.path.join(cfg.output_dir, out_name)
        in_bytes = src_path.stat().st_size

        cmd = ["ffmpeg", "-y", "-i", str(src_path)]
        if filter_string:
            cmd += ["-vf", filter_string]
        if cfg.lossless:
            cmd += ["-lossless", "1"]
        else:
            cmd += ["-quality", str(cfg.quality)]
        cmd += ["-c:v", "libwebp", out_path]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"[process] SKIP: {src_path.name} is not a supported image format")
            skipped += 1
            continue

        out_bytes = os.path.getsize(out_path)
        total_in += in_bytes
        total_out += out_bytes
        count += 1
        reduction = (1 - out_bytes / in_bytes) * 100 if in_bytes > 0 else 0
        print(f"[process] {src_path.name} -> {out_name}  "
              f"{in_bytes / 1024:.1f}K -> {out_bytes / 1024:.1f}K  ({reduction:.1f}%)")

    if count == 0:
        print(f"[process] ERROR: no convertible image files found in '{cfg.input_dir}'")
        sys.exit(1)

    skip_msg = f", {skipped} skipped" if skipped else ""
    print(f"[process] converted {count} image(s): "
          f"{total_in / (1024*1024):.1f} MB -> {total_out / (1024*1024):.1f} MB "
          f"({(1 - total_out / total_in) * 100:.1f}% reduction{skip_msg})")

    return count
