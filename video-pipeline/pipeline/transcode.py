from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from config import VideoConfig, Profile, calc_maxrate, calc_bufsize, build_scale
from pipeline.probe import VideoMeta


def run(cfg: VideoConfig, profile: Profile, meta: VideoMeta) -> str:
    source_kbps = meta.bitrate_bps // 1000
    maxrate = calc_maxrate(profile.ceiling_kbps, source_kbps, cfg.cap_scale)
    bufsize = calc_bufsize(maxrate, cfg.buf_factor)
    scale_filter, actual_res = build_scale(profile, meta.width, meta.height)

    print(f"[transcode] {profile.name} ({actual_res})  "
          f"crf={cfg.crf}  maxrate={maxrate}k  bufsize={bufsize}k"
          f"{'  (passthrough)' if profile.passthrough else ''}")

    playlist = os.path.join(cfg.output_dir, f"{profile.name}.m3u8")
    seg_pattern = os.path.join(cfg.output_dir, f"{profile.name}_%03d.m4s")

    cmd = ["ffmpeg", "-y", "-i", cfg.input_video]
    if scale_filter:
        cmd += ["-vf", scale_filter]
    cmd += ["-c:v", cfg.video_codec]
    cmd += ["-crf", str(cfg.crf)]
    cmd += ["-maxrate", f"{maxrate}k"]
    cmd += ["-bufsize", f"{bufsize}k"]
    cmd += ["-preset", cfg.preset]
    cmd += ["-pix_fmt", cfg.pixel_format]

    if cfg.video_codec_tag:
        cmd += ["-vtag", cfg.video_codec_tag]
    if cfg.codec_params:
        param_flag = "-x265-params" if cfg.video_codec == "libx265" else "-x264-params"
        cmd += [param_flag, cfg.codec_params]

    cmd += ["-g", str(cfg.hls.keyframe_interval)]
    cmd += ["-sc_threshold", "0"]

    MIN_AUDIO_KBPS = 64
    DEFAULT_AUDIO_KBPS = 128
    if meta.audio_bitrate_bps:
        ab_kbps = max(MIN_AUDIO_KBPS, meta.audio_bitrate_bps // 1000)
    else:
        ab_kbps = DEFAULT_AUDIO_KBPS
    cmd += ["-c:a", "aac", "-b:a", f"{ab_kbps}k"]

    cmd += ["-hls_time", str(cfg.hls.segment_duration)]
    cmd += ["-hls_playlist_type", cfg.hls.playlist_type]
    cmd += ["-hls_segment_type", cfg.hls.segment_type]
    cmd += ["-hls_fmp4_init_filename", f"{profile.name}_init.mp4"]
    cmd += ["-hls_segment_filename", seg_pattern]
    cmd += ["-hls_flags", "independent_segments"]
    cmd += ["-start_number", "0"]
    cmd.append(playlist)

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[transcode] ERROR: {profile.name} failed:\n{proc.stderr[-500:]}")
        sys.exit(1)

    segs = list(Path(cfg.output_dir).glob(f"{profile.name}_*.m4s"))
    init = Path(cfg.output_dir) / f"{profile.name}_init.mp4"
    total_bytes = sum(f.stat().st_size for f in segs)
    if init.exists():
        total_bytes += init.stat().st_size
    total_mb = total_bytes / (1024 * 1024)

    reduction_bytes = meta.source_size_bytes - total_bytes
    reduction_pct = (reduction_bytes / meta.source_size_bytes * 100) if meta.source_size_bytes > 0 else 0
    sign = "-" if reduction_bytes >= 0 else "+"

    print(f"[transcode] {profile.name}: {len(segs)} segments, {total_mb:.1f} MB"
          f"  ({sign}{abs(reduction_bytes) / (1024*1024):.1f} MB,"
          f" {sign}{abs(reduction_pct):.1f}%)")

    return actual_res
