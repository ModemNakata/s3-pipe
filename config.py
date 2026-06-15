from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════
# Watermark types
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class WatermarkConfig:
    enabled: bool = True
    text: str = "fevid.cloud"
    font: str = ""
    font_size: int = 0
    color: str = "#7ccf00"
    x: int = 5
    y: int = 5
    box: bool = False
    boxcolor: str = "black@0.5"
    boxborderw: int = 6
    bordercolor: str = "black"
    borderw: int = 1
    uploader_name: str = ""


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
    passthrough: bool = False


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
    watermark: WatermarkConfig = field(default_factory=WatermarkConfig)


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
    watermark: WatermarkConfig = field(default_factory=WatermarkConfig)


# ═══════════════════════════════════════════════════════════════════════
# App / S3 settings
# ═══════════════════════════════════════════════════════════════════════

_DEFAULT_PROFILES_JSON = json.dumps([
    {"name": "1440p", "bandwidth": 12000000, "ref_width": 2560,
     "threshold": 1440, "ceiling_kbps": 12000},
    {"name": "1080p", "bandwidth": 6000000, "ref_width": 1920,
     "threshold": 1080, "ceiling_kbps": 6000},
    {"name": "720p",  "bandwidth": 3000000, "ref_width": 1280,
     "threshold": 720,  "ceiling_kbps": 3000},
    {"name": "480p",  "bandwidth": 1200000, "ref_width": 854,
     "threshold": 480,  "ceiling_kbps": 1200},
])


@dataclass
class AppConfig:
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = "fevid"
    s3_bucket_origin: str = "fevid-orig"

    api_base_url: str = "http://app:8080"
    api_verify_ssl: bool = True
    poll_interval_sec: int = 30
    work_dir: Path = Path("/tmp/pipeline-work")
    mc_alias: str = "fevid"

    # Video defaults
    video_codec: str = "libx264"
    video_codec_tag: Optional[str] = "avc1"
    video_codec_params: Optional[str] = "keyint=60:min-keyint=60:scenecut=0"
    video_preset: str = "slow"
    video_crf: int = 23
    video_cap_scale: float = 0.9
    video_buf_factor: float = 2
    video_pix_fmt: str = "yuv420p"

    hls_segment_duration: int = 4
    hls_segment_type: str = "fmp4"
    hls_playlist_type: str = "vod"
    hls_keyframe_interval: int = 60

    profiles: List[Profile] = field(default_factory=list)

    # Preview defaults
    preview_duration: int = 5

    # Image defaults
    image_quality: int = 100
    image_lossless: bool = False
    image_max_dimension: int = 0

    # Watermark defaults
    watermark_enabled: bool = False
    watermark_text: str = "fevid.cloud/@SuperUser"
    watermark_font: str = ""
    watermark_font_size: int = 0
    watermark_color: str = "#7ccf00"
    watermark_x: int = 5
    watermark_y: int = 5
    watermark_box: bool = False
    watermark_boxcolor: str = "black@0.5"
    watermark_boxborderw: int = 6
    watermark_bordercolor: str = "black"
    watermark_borderw: int = 1
    watermark_uploader_name: str = ""

    # Dev mode — re-process already-ready content (set via --test CLI flag)
    dev_mode: bool = False

    # ── helpers ────────────────────────────────────────────────────────

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

        profiles = cls._load_profiles(
            env.get("VIDEO_PROFILES", ""),
        )

        return cls(
            s3_endpoint=env.get("S3_ENDPOINT", ""),
            s3_access_key=env.get("S3_ACCESS_KEY", ""),
            s3_secret_key=env.get("S3_SECRET_KEY", ""),
            s3_region=env.get("S3_REGION", "us-east-1"),
            s3_bucket=env.get("S3_BUCKET", "fevid"),
            s3_bucket_origin=env.get("S3_BUCKET_ORIGIN", "fevid-orig"),
            api_base_url=os.environ.get(
                "PIPELINE_API_URL", env.get("PIPELINE_API_URL", "http://app:8080"),
            ).rstrip("/"),
            api_verify_ssl=(os.environ.get("PIPELINE_API_VERIFY_SSL",
                                           env.get("PIPELINE_API_VERIFY_SSL", "true"))
                            .lower() not in ("false", "0", "no")),
            poll_interval_sec=int(os.environ.get(
                "POLL_INTERVAL", env.get("POLL_INTERVAL", "30"),
            )),
            work_dir=Path(os.environ.get(
                "PIPELINE_WORK_DIR", env.get("PIPELINE_WORK_DIR", "/tmp/pipeline-work"),
            )),
            video_codec=env.get("VIDEO_CODEC", "libx264"),
            video_codec_tag=env.get("VIDEO_CODEC_TAG") or None,
            video_codec_params=env.get("VIDEO_CODEC_PARAMS") or None,
            video_preset=env.get("VIDEO_PRESET", "slow"),
            video_crf=int(env.get("VIDEO_CRF", "23")),
            video_cap_scale=float(env.get("VIDEO_CAP_SCALE", "0.9")),
            video_buf_factor=float(env.get("VIDEO_BUF_FACTOR", "2")),
            video_pix_fmt=env.get("VIDEO_PIX_FMT", "yuv420p"),
            hls_segment_duration=int(env.get("HLS_SEGMENT_DURATION", "4")),
            hls_segment_type=env.get("HLS_SEGMENT_TYPE", "fmp4"),
            hls_playlist_type=env.get("HLS_PLAYLIST_TYPE", "vod"),
            hls_keyframe_interval=int(env.get("HLS_KEYFRAME_INTERVAL", "60")),
            profiles=profiles,
            preview_duration=int(env.get("PREVIEW_DURATION", "5")),
            image_quality=int(env.get("WEBP_QUALITY", "100")),
            image_lossless=(env.get("WEBP_LOSSLESS", "false").lower()
                            in ("true", "1", "yes")),
            image_max_dimension=int(env.get("WEBP_MAX_DIMENSION", "0")),

            watermark_enabled=(env.get("WATERMARK_ENABLED", "false").lower()
                               in ("true", "1", "yes")),
            watermark_text=env.get("WATERMARK_TEXT", "fevid.cloud/"),
            watermark_font=env.get("WATERMARK_FONT", ""),
            watermark_color=env.get("WATERMARK_COLOR", "#7ccf00"),
            watermark_x=int(env.get("WATERMARK_X", "5")),
            watermark_y=int(env.get("WATERMARK_Y", "5")),
            watermark_box=(env.get("WATERMARK_BOX", "false").lower()
                           in ("true", "1", "yes")),
            watermark_boxcolor=env.get("WATERMARK_BOXCOLOR", "black@0.5"),
            watermark_boxborderw=int(env.get("WATERMARK_BOXBORDERW", "6")),
            watermark_bordercolor=env.get("WATERMARK_BORDERCOLOR", "black"),
            watermark_borderw=int(env.get("WATERMARK_BORDERW", "1")),
        )

    @staticmethod
    def _load_profiles(raw: str) -> List[Profile]:
        if not raw:
            return [
                Profile("1440p", 12000000, 2560, 1440, 12000),
                Profile("1080p", 6000000, 1920, 1080, 6000),
                Profile("720p",  3000000, 1280, 720,  3000),
                Profile("480p",  1200000, 854,  480,  1200),
            ]
        try:
            data = json.loads(raw)
            return [Profile(**d) for d in data]
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"[config] WARNING: invalid VIDEO_PROFILES JSON ({e}), using defaults")
            return []

    def build_video_config(self, input_video: str, output_dir: str) -> VideoConfig:
        return VideoConfig(
            input_video=input_video,
            output_dir=output_dir,
            video_codec=self.video_codec,
            video_codec_tag=self.video_codec_tag,
            codec_params=self.video_codec_params,
            preset=self.video_preset,
            crf=self.video_crf,
            cap_scale=self.video_cap_scale,
            buf_factor=self.video_buf_factor,
            pixel_format=self.video_pix_fmt,
            hls=HlsConfig(
                segment_duration=self.hls_segment_duration,
                segment_type=self.hls_segment_type,
                playlist_type=self.hls_playlist_type,
                keyframe_interval=self.hls_keyframe_interval,
            ),
            profiles=list(self.profiles),
            watermark=WatermarkConfig(
                enabled=self.watermark_enabled,
                text=self.watermark_text,
                font=self.watermark_font,
                font_size=self.watermark_font_size,
                color=self.watermark_color,
                x=self.watermark_x,
                y=self.watermark_y,
                box=self.watermark_box,
                boxcolor=self.watermark_boxcolor,
                boxborderw=self.watermark_boxborderw,
                bordercolor=self.watermark_bordercolor,
                borderw=self.watermark_borderw,
                uploader_name=self.watermark_uploader_name,
            ),
        )

    def build_image_config(self, input_dir: str, output_dir: str) -> ImageConfig:
        return ImageConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            quality=self.image_quality,
            lossless=self.image_lossless,
            max_dimension=self.image_max_dimension,
            watermark=WatermarkConfig(
                enabled=self.watermark_enabled,
                text=self.watermark_text,
                font=self.watermark_font,
                font_size=self.watermark_font_size,
                color=self.watermark_color,
                x=self.watermark_x,
                y=self.watermark_y,
                box=self.watermark_box,
                boxcolor=self.watermark_boxcolor,
                boxborderw=self.watermark_boxborderw,
                bordercolor=self.watermark_bordercolor,
                borderw=self.watermark_borderw,
                uploader_name=self.watermark_uploader_name,
            ),
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

def calc_font_size(w: int, h: int, font_size_override: int) -> int:
    if font_size_override > 0:
        print(f"[watermark] font_size: fixed {font_size_override}px (config override)")
        return font_size_override
    ratio = 0.03 if h > w else 0.02
    base = w if h > w else h
    fs = int(base * ratio)
    orientation = "portrait" if h > w else "landscape"
    print(f"[watermark] font_size: {w}x{h} {orientation}  "
          f"{'w' if h>w else 'h'}*{ratio} = {base}*{ratio} = {fs}px")
    return fs


def filter_profiles(profiles: List[Profile], source_min_dim: int) -> List[Profile]:
    return [p for p in profiles if source_min_dim >= p.threshold]


def calc_maxrate(ceiling_kbps: int, source_kbps: int, cap_scale: float) -> int:
    return min(ceiling_kbps, int(source_kbps * cap_scale))


def calc_bufsize(maxrate_kbps: int, buf_factor: float) -> int:
    return int(maxrate_kbps * buf_factor)


def build_scale(profile: Profile, src_w: int, src_h: int) -> Tuple[Optional[str], str]:
    if profile.passthrough:
        return None, f"{src_w}x{src_h}"
    if src_w >= src_h:
        w = profile.ref_width
        h = int(w * src_h / src_w / 2) * 2
        return f"scale={w}:-2", f"{w}x{h}"
    else:
        h = profile.ref_width
        w = int(h * src_w / src_h / 2) * 2
        return f"scale=-2:{h}", f"{w}x{h}"
