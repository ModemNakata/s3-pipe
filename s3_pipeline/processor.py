from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from config import AppConfig, Profile, filter_profiles
from deps import check_video, check_image

ROOT = Path(__file__).resolve().parent.parent


def _load_pipeline(base: Path) -> dict[str, Any]:
    modules: dict[str, Any] = {}
    entries = [
        ("config",                base / "config.py"),
        ("pipeline",              base / "pipeline" / "__init__.py"),
        ("pipeline.probe",        base / "pipeline" / "probe.py"),
        ("pipeline.transcode",    base / "pipeline" / "transcode.py"),
        ("pipeline.manifest",     base / "pipeline" / "manifest.py"),
        ("pipeline.process",      base / "pipeline" / "process.py"),
    ]
    for mod_name, file_path in entries:
        if not file_path.exists():
            continue
        spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        modules[mod_name.split(".")[-1]] = mod
    return modules


def _clear() -> None:
    keys = [k for k in sys.modules if k in (
        "config", "pipeline", "pipeline.probe",
        "pipeline.transcode", "pipeline.manifest",
        "pipeline.process",
    )]
    for k in keys:
        del sys.modules[k]


def _target_16x9(src_w: int, src_h: int, max_short: int) -> tuple[int, int]:
    min_dim = min(src_w, src_h)
    short_side = min(min_dim, max_short)
    if src_w >= src_h:  # landscape — short side is height
        h = short_side
        w = h * 16 // 9
    else:  # portrait — short side is width
        w = short_side
        h = w * 9 // 16
    w -= w % 2
    h -= h % 2
    return w, h


def _generate_thumbnail(input_path: Path, output_dir: Path, src_w: int, src_h: int) -> Optional[Path]:
    tw, th = _target_16x9(src_w, src_h, 720)
    out = output_dir / "thumbnail.jpg"
    print(f"[processor] thumbnail target: {tw}x{th}")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ss", "00:00:05",
        "-vframes", "1",
        "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
               f"crop={tw}:{th}",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[processor] WARNING: thumbnail failed:\n{proc.stderr[-300:]}")
        return None
    print(f"[processor] thumbnail: {out.name} ({out.stat().st_size / 1024:.1f} KB)")
    return out


def _generate_preview(input_path: Path, output_dir: Path, src_w: int, src_h: int) -> Optional[Path]:
    tw, th = _target_16x9(src_w, src_h, 360)
    out = output_dir / "preview.webm"
    print(f"[processor] preview target: {tw}x{th}")
    cmd = [
        "ffmpeg", "-y", "-ss", "0", "-i", str(input_path),
        "-t", "5", "-an",
        "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}",
        "-c:v", "libvpx-vp9", "-b:v", "500k",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[processor] WARNING: preview failed:\n{proc.stderr[-300:]}")
        return None
    print(f"[processor] preview: {out.name} ({out.stat().st_size / 1024:.1f} KB)")
    return out


def process_video(cfg: AppConfig, input_path: Path, content_id: str, workdir: Path) -> tuple[Path, float]:
    output_dir = workdir / content_id / "h264_output"
    print(f"[processor] ── H264 pipeline for {content_id} ──")
    print(f"[processor] input:  {input_path}")
    print(f"[processor] output: {output_dir}")

    vcfg = cfg.build_video_config(str(input_path), str(output_dir))
    check_video(vcfg)

    _clear()
    mods = _load_pipeline(ROOT / "video-pipeline")
    probe = mods["probe"]
    transcode = mods["transcode"]
    manifest = mods["manifest"]
    meta = probe.probe(vcfg)

    output_dir.mkdir(parents=True, exist_ok=True)

    profiles = filter_profiles(vcfg.profiles, meta.min_dim)

    if not profiles:
        src_profile = Profile(
            name=f"{meta.min_dim}p",
            bandwidth=int(meta.bitrate_bps * 1.1),
            ref_width=meta.min_dim,
            threshold=meta.min_dim,
            ceiling_kbps=meta.bitrate_bps // 1000,
            passthrough=True,
        )
        profiles = [src_profile]
        print(f"[processor] source below any profile, using passthrough: "
              f"{src_profile.name} ({meta.width}x{meta.height})")
    else:
        highest = max(p.threshold for p in profiles)
        if meta.min_dim > highest:
            src_name = f"{meta.min_dim}p"
            src_profile = Profile(
                name=src_name,
                bandwidth=int(meta.bitrate_bps * 1.1),
                ref_width=meta.min_dim,
                threshold=meta.min_dim,
                ceiling_kbps=meta.bitrate_bps // 1000,
                passthrough=True,
            )
            profiles.insert(0, src_profile)
            print(f"[processor] added source profile: {src_name} "
                  f"({meta.width}x{meta.height})")

    print(f"[processor] active profiles: {[p.name for p in profiles]}")

    actual: dict[str, str] = {}
    for p in profiles:
        actual[p.name] = transcode.run(vcfg, p, meta)

    manifest.generate(str(output_dir), profiles, actual)

    _generate_thumbnail(input_path, output_dir, meta.width, meta.height)
    _generate_preview(input_path, output_dir, meta.width, meta.height)

    print(f"[processor] H264 pipeline complete for {content_id}")
    return output_dir, meta.duration_s


def process_images(cfg: AppConfig, download_dir: Path, content_id: str, workdir: Path) -> Path:
    output_dir = workdir / content_id / "webp_output"
    print(f"[processor] ── WebP pipeline for {content_id} ──")
    print(f"[processor] input:  {download_dir}")
    print(f"[processor] output: {output_dir}")

    icfg = cfg.build_image_config(str(download_dir), str(output_dir))
    check_image(icfg)

    _clear()
    mods = _load_pipeline(ROOT / "image-pipeline")
    process_mod = mods["process"]

    output_dir.mkdir(parents=True, exist_ok=True)
    process_mod.run(icfg)

    print(f"[processor] WebP pipeline complete for {content_id}")
    return output_dir
