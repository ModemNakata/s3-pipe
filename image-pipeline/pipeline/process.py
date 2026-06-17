from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import log
from config import ImageConfig, calc_font_size


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


def _probe_dimensions(path: str) -> tuple[int, int]:
    result = log.run_cmd(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", path],
        module="process",
    )
    if result.returncode != 0:
        return 0, 0
    import json as _json
    data = _json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        return 0, 0
    s = streams[0]
    return int(s.get("width", 0)), int(s.get("height", 0))


def run(cfg: ImageConfig) -> int:
    parts = []
    if cfg.max_dimension > 0:
        parts.append(
            f"scale='if(gt(iw,ih),{cfg.max_dimension},-2)':"
            f"'if(gt(iw,ih),-2,{cfg.max_dimension})'"
        )

    textfile = None
    _drawtext_template: str | None = None
    if cfg.watermark.enabled:
        w = cfg.watermark
        full_text = f"{w.text}@{w.uploader_name}" if w.uploader_name else w.text
        textfile = _write_textfile(full_text)
        wt_parts = [
            f"textfile={textfile}",
            f"fontfile={w.font}",
            f"fontcolor={w.color}",
            f"x={w.x}",
            f"y={w.y}",
        ]
        if w.borderw > 0:
            wt_parts += [f"bordercolor={w.bordercolor}", f"borderw={w.borderw}"]
        _drawtext_template = "drawtext=" + ":".join(wt_parts)

    filter_string = ",".join(parts) if parts else None

    log.info("process", f"watermark={'on' if cfg.watermark.enabled else 'off'}")

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

        if _drawtext_template is not None:
            iw, ih = _probe_dimensions(str(src_path))
            fs = calc_font_size(iw, ih, cfg.watermark)
            vf_parts = list(parts)
            vf_parts.append(f"{_drawtext_template}:fontsize={fs}")
            cmd += ["-vf", ",".join(vf_parts)]
        elif filter_string:
            cmd += ["-vf", filter_string]

        if cfg.lossless:
            cmd += ["-lossless", "1"]
        else:
            cmd += ["-quality", str(cfg.quality)]
        cmd += ["-c:v", "libwebp", out_path]

        proc = log.run_cmd(cmd, module="process")
        if proc.returncode != 0:
            log.info("process", f"SKIP: {src_path.name} is not a supported image format")
            skipped += 1
            continue

        out_bytes = os.path.getsize(out_path)
        total_in += in_bytes
        total_out += out_bytes
        count += 1
        reduction = (1 - out_bytes / in_bytes) * 100 if in_bytes > 0 else 0
        log.info("process", f"{src_path.name} -> {out_name}  "
                 f"{in_bytes / 1024:.1f}K -> {out_bytes / 1024:.1f}K  ({reduction:.1f}%)")

    if textfile is not None:
        _cleanup_textfile(textfile)

    if count == 0:
        log.info("process", f"ERROR: no convertible image files found in '{cfg.input_dir}'")
        sys.exit(1)

    skip_msg = f", {skipped} skipped" if skipped else ""
    log.info("process", f"converted {count} image(s): "
             f"{total_in / (1024*1024):.1f} MB -> {total_out / (1024*1024):.1f} MB "
             f"({(1 - total_out / total_in) * 100:.1f}% reduction{skip_msg})")

    return count
