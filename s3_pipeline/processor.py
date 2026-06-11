from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from config import AppConfig, filter_profiles
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


def process_video(cfg: AppConfig, input_path: Path, content_id: str, workdir: Path) -> Path:
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
        print(f"[processor] WARNING: no profile fits source ({meta.min_dim}p), "
              f"nothing to encode")
        return output_dir

    print(f"[processor] active profiles: {[p.name for p in profiles]}")

    actual: dict[str, str] = {}
    for p in profiles:
        actual[p.name] = transcode.run(vcfg, p, meta)

    manifest.generate(str(output_dir), profiles, actual)
    print(f"[processor] H264 pipeline complete for {content_id}")
    return output_dir


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
