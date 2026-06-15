from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from config import ImageConfig


def _write_textfile(text: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write(text)
    f.close()
    return f.name


def _cleanup_textfile(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def run(cfg: ImageConfig) -> int:
    parts = []
    if cfg.max_dimension > 0:
        parts.append(
            f"scale='if(gt(iw,ih),{cfg.max_dimension},-2)':"
            f"'if(gt(iw,ih),-2,{cfg.max_dimension})'"
        )

    textfile = None
    if cfg.watermark.enabled:
        w = cfg.watermark
        full_text = f"{w.text}@{w.uploader_name}" if w.uploader_name else w.text
        textfile = _write_textfile(full_text)
        wt_parts = [
            f"textfile={textfile}",
            f"fontfile={w.font}",
            f"fontcolor={w.color}",
            f"fontsize={w.font_size_expr}",
            f"x={w.x}",
            f"y={w.y}",
        ]
        if w.box:
            wt_parts += ["box=1", f"boxcolor={w.boxcolor}", f"boxborderw={w.boxborderw}"]
        if w.borderw > 0:
            wt_parts += [f"bordercolor={w.bordercolor}", f"borderw={w.borderw}"]
        parts.append("drawtext=" + ":".join(wt_parts))

    filter_string = ",".join(parts) if parts else None

    wm_label = " +wm" if cfg.watermark.enabled else ""
    print(f"[process] watermark={'on' if cfg.watermark.enabled else 'off'}")

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

    if textfile is not None:
        _cleanup_textfile(textfile)

    if count == 0:
        print(f"[process] ERROR: no convertible image files found in '{cfg.input_dir}'")
        sys.exit(1)

    skip_msg = f", {skipped} skipped" if skipped else ""
    print(f"[process] converted {count} image(s): "
          f"{total_in / (1024*1024):.1f} MB -> {total_out / (1024*1024):.1f} MB "
          f"({(1 - total_out / total_in) * 100:.1f}% reduction{skip_msg})")

    return count
