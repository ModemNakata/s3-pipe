from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

import log
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
    if src_w >= src_h:
        h = short_side
        w = h * 16 // 9
    else:
        w = short_side
        h = w * 9 // 16
    w -= w % 2
    h -= h % 2
    return w, h


def _generate_thumbnail(input_path: Path, output_dir: Path,
                         src_w: int, src_h: int) -> Optional[Path]:
    tw, th = _target_16x9(src_w, src_h, 720)
    out = output_dir / "thumbnail.jpg"
    log.info("processor", f"thumbnail target: {tw}x{th}")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ss", "00:00:05",
        "-vframes", "1",
        "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
               f"crop={tw}:{th}",
        str(out),
    ]
    proc = log.run_cmd(cmd, module="processor")
    if proc.returncode != 0:
        log.info("processor", f"WARNING: thumbnail failed:\n{proc.stderr[-300:]}")
        return None
    log.info("processor", f"thumbnail: {out.name} ({out.stat().st_size / 1024:.1f} KB)")
    return out


def _generate_preview(input_path: Path, output_dir: Path,
                       src_w: int, src_h: int,
                       duration: int) -> Optional[Path]:
    tw, th = _target_16x9(src_w, src_h, 360)
    out = output_dir / "preview.webm"
    log.info("processor", f"preview target: {tw}x{th}")
    cmd = [
        "ffmpeg", "-y", "-ss", "0", "-i", str(input_path),
        "-t", str(duration), "-an",
        "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}",
        "-c:v", "libvpx-vp9", "-b:v", "500k",
        str(out),
    ]
    proc = log.run_cmd(cmd, module="processor")
    if proc.returncode != 0:
        log.info("processor", f"WARNING: preview failed:\n{proc.stderr[-300:]}")
        return None
    log.info("processor", f"preview: {out.name} ({out.stat().st_size / 1024:.1f} KB)")
    return out


def _generate_blurred_webp(input_path: Path, output_path: Path,
                            sigma: float = 20, steps: int = 3) -> Optional[Path]:
    log.info("processor", f"generating blurred webp from {input_path.name} "
             f"(sigma={sigma}, steps={steps})")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", f"gblur=sigma={sigma}:steps={steps}",
        "-c:v", "libwebp", "-quality", "50",
        str(output_path),
    ]
    proc = log.run_cmd(cmd, module="processor")
    if proc.returncode != 0:
        log.info("processor", f"WARNING: blurred webp failed:\n{proc.stderr[-300:]}")
        return None
    log.info("processor", f"blurred webp: {output_path.name} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


def _trim_video(input_path: Path, output_path: Path, duration: int) -> Optional[Path]:
    log.info("processor", f"trimming first {duration}s to {output_path.name}")
    cmd = [
        "ffmpeg", "-y", "-ss", "0", "-i", str(input_path),
        "-t", str(duration),
        "-c", "copy",
        str(output_path),
    ]
    proc = log.run_cmd(cmd, module="processor")
    if proc.returncode != 0:
        log.info("processor", f"WARNING: trim failed:\n{proc.stderr[-300:]}")
        return None
    log.info("processor", f"trimmed: {output_path.name} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


def _source_quality(min_dim: int, fps: float) -> str:
    if min_dim >= 2160:
        return "4K"
    suffix = "60" if fps >= 50 else ""
    return f"{min_dim}p{suffix}"


def process_video(cfg: AppConfig, input_path: Path, content_id: str, workdir: Path,
                  free_preview_duration: int = 0) -> tuple[Path, float, Optional[Path], str]:
    output_dir = workdir / content_id / "av1_output"
    print(f"[processor] ── AV1 pipeline for {content_id} ──")
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
            maxrate_kbps=0,
            bufsize_kbps=0,
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
                maxrate_kbps=0,
                bufsize_kbps=0,
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
    _generate_preview(input_path, output_dir, meta.width, meta.height,
                       cfg.preview_duration)

    free_preview_output_dir: Optional[Path] = None
    if free_preview_duration > 0:
        print(f"[processor] ── free preview (paywalled) ──")
        trimmed = workdir / content_id / "free_preview_trimmed.mp4"
        if _trim_video(input_path, trimmed, free_preview_duration):
            free_preview_output_dir = workdir / content_id / "av1_free_preview"
            fp_vcfg = cfg.build_video_config(str(trimmed), str(free_preview_output_dir))
            fp_meta = probe.probe(fp_vcfg)
            free_preview_output_dir.mkdir(parents=True, exist_ok=True)
            fp_profiles = filter_profiles(fp_vcfg.profiles, fp_meta.min_dim)
            if not fp_profiles:
                fp_src = Profile(
                    name=f"{fp_meta.min_dim}p",
                    bandwidth=int(fp_meta.bitrate_bps * 1.1),
                    ref_width=fp_meta.min_dim,
                    threshold=fp_meta.min_dim,
                    maxrate_kbps=0,
                    bufsize_kbps=0,
                    passthrough=True,
                )
                fp_profiles = [fp_src]
            else:
                fp_highest = max(p.threshold for p in fp_profiles)
                if fp_meta.min_dim > fp_highest:
                    fp_src_name = f"{fp_meta.min_dim}p"
                    fp_src = Profile(
                        name=fp_src_name,
                        bandwidth=int(fp_meta.bitrate_bps * 1.1),
                        ref_width=fp_meta.min_dim,
                        threshold=fp_meta.min_dim,
                        maxrate_kbps=0,
                        bufsize_kbps=0,
                        passthrough=True,
                    )
                    fp_profiles.insert(0, fp_src)
            print(f"[processor] free preview active profiles: {[p.name for p in fp_profiles]}")
            fp_actual: dict[str, str] = {}
            for p in fp_profiles:
                fp_actual[p.name] = transcode.run(fp_vcfg, p, fp_meta)
            manifest.generate(str(free_preview_output_dir), fp_profiles, fp_actual)

    sq = _source_quality(meta.min_dim, meta.fps)
    print(f"[processor] source quality: {sq}")
    print(f"[processor] AV1 pipeline complete for {content_id}")
    return output_dir, meta.duration_s, free_preview_output_dir, sq


def _generate_image_preview(input_path: Path, output_dir: Path) -> Optional[Path]:
    out = output_dir / "preview.webp"
    log.info("processor", f"generating image preview square from {input_path.name}")
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", "crop='min(iw,ih)':'min(iw,ih)',"
               "scale='min(720,iw)':'min(720,ih)'",
        "-c:v", "libwebp", "-quality", "100",
        str(out),
    ]
    proc = log.run_cmd(cmd, module="processor")
    if proc.returncode != 0:
        log.info("processor", f"WARNING: image preview failed:\n{proc.stderr[-300:]}")
        return None
    log.info("processor", f"image preview: {out.name} ({out.stat().st_size / 1024:.1f} KB)")
    return out


def process_images(cfg: AppConfig, download_dir: Path, content_id: str,
                   workdir: Path, first_image: Optional[Path] = None,
                   files: Optional[list[dict]] = None,
                   unblurred_count: int = 0) -> Path:
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

    if first_image is not None and first_image.exists():
        _generate_image_preview(first_image, output_dir)

    if files and unblurred_count > 0:
        for i, f in enumerate(files):
            if i >= unblurred_count:
                local_src = download_dir / f["path"].split("/")[-1]
                if local_src.exists():
                    blurred_name = f"blurred_{i}.webp"
                    _generate_blurred_webp(local_src, output_dir / blurred_name,
                                           sigma=cfg.blur_sigma, steps=cfg.blur_steps)

    print(f"[processor] WebP pipeline complete for {content_id}")
    return output_dir
