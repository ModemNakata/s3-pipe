from __future__ import annotations

import subprocess
from pathlib import Path

from config import AppConfig


def upload_dir(cfg: AppConfig, local_dir: Path, s3_dest: str) -> None:
    src = f"{local_dir}/"
    print(f"[upload] mc cp --recursive {src} -> {s3_dest}")
    proc = subprocess.run(
        ["mc", "cp", "--recursive", src, s3_dest],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"[upload] ERROR:\n{proc.stderr}")
        raise RuntimeError(f"mc upload failed for {local_dir}")

    total = sum(f.stat().st_size for f in local_dir.rglob("*") if f.is_file())
    print(f"[upload] done ({total / (1024*1024):.1f} MB uploaded)")


def upload_video(cfg: AppConfig, output_dir: Path, content_id: str) -> None:
    dest = f"{cfg.mc_alias}/{cfg.s3_bucket}/videos/{content_id}/"
    upload_dir(cfg, output_dir, dest)


def upload_images(cfg: AppConfig, output_dir: Path, content_id: str) -> None:
    dest = f"{cfg.mc_alias}/{cfg.s3_bucket}/galleries/{content_id}/"
    upload_dir(cfg, output_dir, dest)
