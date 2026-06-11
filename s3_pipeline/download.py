from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from config import AppConfig


def download_file(cfg: AppConfig, s3_key: str, local_path: Path) -> Path:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    src = f"{cfg.orig_bucket_path}/{s3_key}"

    print(f"[download] mc cp {src} -> {local_path}")
    proc = subprocess.run(
        ["mc", "cp", src, str(local_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"[download] ERROR:\n{proc.stderr}")
        sys.exit(1)

    size = local_path.stat().st_size
    print(f"[download] done ({size / 1024:.1f} KB)")
    return local_path


def download_item_files(
    cfg: AppConfig, files: list[dict], dest_dir: Path,
) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for f in files:
        original_name = f.get("original_name", f["path"].split("/")[-1])
        local_path = dest_dir / original_name
        download_file(cfg, f["path"], local_path)
        paths.append(local_path)
    return paths
