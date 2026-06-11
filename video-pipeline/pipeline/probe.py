from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from config import VideoConfig


@dataclass
class VideoMeta:
    width: int
    height: int
    bitrate_bps: int
    codec: str
    fps: float
    duration_s: float
    audio_bitrate_bps: int = 0
    audio_codec: str = ""
    source_size_bytes: int = 0

    @property
    def min_dim(self) -> int:
        return min(self.width, self.height)

    @property
    def is_portrait(self) -> bool:
        return self.height > self.width

    @property
    def source_size_mb(self) -> float:
        return self.source_size_bytes / (1024 * 1024)


def probe(cfg: VideoConfig) -> VideoMeta:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,bit_rate,codec_name,r_frame_rate",
        "-show_entries", "format=bit_rate,duration",
        "-of", "json",
        cfg.input_video,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[probe] ffprobe failed:\n{proc.stderr}")
        sys.exit(1)

    try:
        data = json.loads(proc.stdout)
        s = data["streams"][0]
        fmt = data["format"]
        w = int(s["width"])
        h = int(s["height"])
        codec = s.get("codec_name", "unknown")
        num, den = str(s.get("r_frame_rate", "30/1")).split("/")
        fps = int(num) / int(den)
        br = s.get("bit_rate") or fmt.get("bit_rate", "0")
        br = int(br) if br not in ("N/A", "0") else 0
        dur = float(fmt.get("duration", 0))
    except (KeyError, IndexError, ValueError) as e:
        print(f"[probe] failed to parse ffprobe output: {e}")
        sys.exit(1)

    audio_br = 0
    audio_codec = ""
    acmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=bit_rate,codec_name",
        "-of", "json",
        cfg.input_video,
    ]
    ap = subprocess.run(acmd, capture_output=True, text=True)
    if ap.returncode == 0:
        try:
            adata = json.loads(ap.stdout)
            if adata.get("streams"):
                s2 = adata["streams"][0]
                abr = s2.get("bit_rate", "0")
                audio_br = int(abr) if abr not in ("N/A", "0") else 0
                audio_codec = s2.get("codec_name", "")
        except (KeyError, IndexError, ValueError):
            pass

    source_bytes = os.path.getsize(cfg.input_video)

    meta = VideoMeta(
        width=w, height=h, bitrate_bps=br, codec=codec,
        fps=fps, duration_s=dur,
        audio_bitrate_bps=audio_br, audio_codec=audio_codec,
        source_size_bytes=source_bytes,
    )
    print(f"[probe] {meta.width}x{meta.height} ({meta.min_dim}p)  {meta.codec}"
          f"  {meta.bitrate_bps // 1000} kbps  {meta.fps:.2f} fps"
          f"  {meta.duration_s:.1f}s"
          f"  audio: {meta.audio_codec} {meta.audio_bitrate_bps // 1000}k"
          f"  source: {meta.source_size_mb:.1f} MB")
    return meta
