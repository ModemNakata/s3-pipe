from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:

    # ── Input / identity ──────────────────────────────────────────────────────
    input_dir: str = "images"
    image_id: str = "image-set-xyz"

    # ── Paths ─────────────────────────────────────────────────────────────────
    output_dir: str = "processed_webp"
    mc_alias_path: str = "local_s3/bucket"

    # ── WebP encoding ─────────────────────────────────────────────────────────
    # Quality 0–100 (lower = smaller, more lossy). 100 gives maximum quality;
    # WebP still applies its own internal compression even at 100.
    quality: int = 100 # 80 # 90

    # If True, encode losslessly (quality is ignored for lossless).
    lossless: bool = False

    # If set, images will be resized to fit within this max dimension (long edge)
    # while preserving aspect ratio. 0 = no resize.
    max_dimension: int = 0

    # ── Behaviour flags ───────────────────────────────────────────────────────
    clean_local: bool = True
    clean_remote: bool = True
    upload: bool = True
