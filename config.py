from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Video pipeline types
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Profile:
    name: str
    bandwidth: int
    ref_width: int
    threshold: int
    ceiling_kbps: int


@dataclass
class HlsConfig:
    segment_duration: int = 4
    segment_type: str = "fmp4"
    playlist_type: str = "vod"
    keyframe_interval: int = 60


@dataclass
class VideoConfig:
    input_video: str = ""
    output_dir: str = ""

    video_codec: str = "libx264"
    video_codec_tag: Optional[str] = "avc1"
    codec_params: Optional[str] = "keyint=60:min-keyint=60:scenecut=0"
    preset: str = "slow"
    crf: int = 23
    cap_scale: float = 0.9
    buf_factor: float = 2
    pixel_format: str = "yuv420p"

    hls: HlsConfig = field(default_factory=HlsConfig)

    profiles: List[Profile] = field(default_factory=lambda: [
        Profile("1440p", 12000000, 2560, 1440, 12000),
        Profile("1080p", 6000000, 1920, 1080, 6000),
        Profile("720p",  3000000, 1280, 720,  3000),
        Profile("480p",  1200000, 854,  480,  1200),
    ])
    fallback_profile: Profile = field(default_factory=lambda: Profile(
        "source", 1600000, 1920, 0, 1600,
    ))


# ═══════════════════════════════════════════════════════════════════════
# Image pipeline types
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ImageConfig:
    input_dir: str = ""
    output_dir: str = ""
    quality: int = 100
    lossless: bool = False
    max_dimension: int = 0


# ═══════════════════════════════════════════════════════════════════════
# App / S3 settings
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class AppConfig:
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = "fevid"
    s3_bucket_origin: str = "fevid-orig"
    api_base_url: str = "http://app:8080"
    poll_interval_sec: int = 30
    work_dir: Path = Path("/tmp/pipeline-work")
    mc_alias: str = "fevid"

    @classmethod
    def from_env(cls) -> AppConfig:
        env_path = Path(__file__).resolve().parent / ".env"
        if not env_path.exists():
            print("[config] ERROR: .env not found at", env_path)
            sys.exit(1)

        env: dict[str, str] = {}
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()

        return cls(
            s3_endpoint=env.get("S3_ENDPOINT", ""),
            s3_access_key=env.get("S3_ACCESS_KEY", ""),
            s3_secret_key=env.get("S3_SECRET_KEY", ""),
            s3_region=env.get("S3_REGION", "us-east-1"),
            s3_bucket=env.get("S3_BUCKET", "fevid"),
            s3_bucket_origin=env.get("S3_BUCKET_ORIGIN", "fevid-orig"),
            api_base_url=os.environ.get("PIPELINE_API_URL", "http://app:8080").rstrip("/"),
            poll_interval_sec=int(os.environ.get("POLL_INTERVAL", "30")),
            work_dir=Path(os.environ.get("PIPELINE_WORK_DIR", "/tmp/pipeline-work")),
        )

    def setup_mc(self) -> None:
        print(f"[config] configuring mc alias '{self.mc_alias}' -> {self.s3_endpoint}")
        proc = subprocess.run(
            ["mc", "alias", "set", self.mc_alias,
             self.s3_endpoint, self.s3_access_key, self.s3_secret_key],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(f"[config] ERROR setting mc alias:\n{proc.stderr}")
            sys.exit(1)
        print(f"[config] mc alias '{self.mc_alias}' ready")

    @property
    def orig_bucket_path(self) -> str:
        return f"{self.mc_alias}/{self.s3_bucket_origin}"

    @property
    def dest_bucket_path(self) -> str:
        return f"{self.mc_alias}/{self.s3_bucket}"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def filter_profiles(profiles: List[Profile], source_min_dim: int) -> List[Profile]:
    return [p for p in profiles if source_min_dim >= p.threshold]


def build_fallback(source_min_dim: int, fallback: Profile) -> Profile:
    bw = max(200000, fallback.bandwidth)
    return Profile(
        name=fallback.name,
        bandwidth=bw,
        ref_width=fallback.ref_width,
        threshold=0,
        ceiling_kbps=fallback.ceiling_kbps,
    )


def calc_maxrate(ceiling_kbps: int, source_kbps: int, cap_scale: float) -> int:
    return min(ceiling_kbps, int(source_kbps * cap_scale))


def calc_bufsize(maxrate_kbps: int, buf_factor: float) -> int:
    return int(maxrate_kbps * buf_factor)


def build_scale(profile: Profile, src_w: int, src_h: int) -> Tuple[str, str]:
    if src_w >= src_h:
        w = profile.ref_width
        h = int(w * src_h / src_w / 2) * 2
        return f"scale={w}:-2", f"{w}x{h}"
    else:
        h = profile.ref_width
        w = int(h * src_w / src_h / 2) * 2
        return f"scale=-2:{h}", f"{w}x{h}"
