from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from config import Config


def _build_filter(config: Config) -> str | None:
    """Build the ffmpeg -vf string. Returns None if no filter needed."""
    parts = []
    if config.max_dimension > 0:
        parts.append(f"scale='if(gt(iw,ih),{config.max_dimension},-2)':'if(gt(iw,ih),-2,{config.max_dimension})'")
    return ",".join(parts) if parts else None


def run(config: Config) -> int:
    """Convert all images in input_dir to WebP. Returns count of processed files."""
    filter_string = _build_filter(config)
    total_in = 0
    total_out = 0
    count = 0

    allowed = set(config.input_extensions)

    for src_path in sorted(Path(config.input_dir).iterdir()):
        if not src_path.is_file():
            continue
        ext = src_path.suffix.lower()
        if ext not in allowed:
            continue

        stem = src_path.stem
        out_name = f"{stem}.webp"
        out_path = os.path.join(config.output_dir, out_name)

        in_bytes = src_path.stat().st_size

        cmd = ["ffmpeg", "-y", "-i", str(src_path)]

        if filter_string:
            cmd += ["-vf", filter_string]

        if config.lossless:
            cmd += ["-lossless", "1"]
        else:
            cmd += ["-quality", str(config.quality)]

        cmd += ["-c:v", "libwebp"]
        cmd.append(out_path)

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"[process] ERROR: {src_path.name} -> {out_name} failed:\n{proc.stderr[-300:]}")
            sys.exit(1)

        out_bytes = os.path.getsize(out_path)
        total_in += in_bytes
        total_out += out_bytes
        count += 1

        reduction_pct = (1 - out_bytes / in_bytes) * 100 if in_bytes > 0 else 0
        print(f"[process] {src_path.name} -> {out_name}  "
              f"{in_bytes / 1024:.1f}K -> {out_bytes / 1024:.1f}K  "
              f"({reduction_pct:.1f}%)")

    if count == 0:
        exts = ", ".join(sorted(config.input_extensions))
        print(f"[process] ERROR: no {exts} files found in '{config.input_dir}'")
        sys.exit(1)

    print(f"[process] converted {count} image(s): "
          f"{total_in / (1024*1024):.1f} MB -> {total_out / (1024*1024):.1f} MB "
          f"({(1 - total_out / total_in) * 100:.1f}% reduction)")

    return count
