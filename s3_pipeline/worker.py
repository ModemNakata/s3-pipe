from __future__ import annotations

import shutil
import time
import traceback
from pathlib import Path
from typing import Any

from config import AppConfig
from . import api, download, processor as proc, upload


def process_item(cfg: AppConfig, item: dict[str, Any]) -> bool:
    content_id: str = item["content_id"]
    content_type: str = item["content_type"]
    files: list[dict] = item.get("files", [])
    title: str = item.get("title", "")

    workdir = cfg.work_dir / content_id
    download_dir = workdir / "download"
    success = False

    print("")
    print(f"{'='*60}")
    print(f"[worker] processing: {content_id} ({content_type})")
    print(f"[worker] title: {title}")
    print(f"[worker] files: {[f['original_name'] for f in files]}")
    print(f"{'='*60}")

    try:
        print(f"\n--- step 1/4: download originals from S3_ORIG_BUCKET ---")
        local_paths = download.download_item_files(cfg, files, download_dir)
        print(f"[worker] downloaded {len(local_paths)} file(s) to {download_dir}")

        print(f"\n--- step 2/4: encode ---")
        t0 = time.time()

        duration = 0

        if content_type == "video":
            if len(local_paths) != 1:
                raise ValueError(f"expected 1 file for video, got {len(local_paths)}")
            output_dir, duration = proc.process_video(cfg, local_paths[0], content_id, cfg.work_dir)
        elif content_type == "image_set":
            output_dir = proc.process_images(cfg, download_dir, content_id, cfg.work_dir)
        else:
            raise ValueError(f"unknown content_type: {content_type}")

        elapsed = time.time() - t0
        print(f"[worker] encoding took {elapsed:.1f}s")

        print(f"\n--- step 3/4: upload to S3_BUCKET ---")
        if content_type == "video":
            upload.upload_video(cfg, output_dir, content_id)
            s3_prefix = f"videos/{content_id}"
            thumbnail_url = f"{s3_prefix}/thumbnail.jpg"
            preview_path = f"{s3_prefix}/preview.webm"
        else:
            upload.upload_images(cfg, output_dir, content_id)
            thumbnail_url = ""
            preview_path = ""

        print(f"\n--- step 4/4: mark as ready ---")
        ok = api.mark_ready(cfg, content_id,
                            thumbnail_url=thumbnail_url,
                            preview_path=preview_path,
                            duration=duration)
        if not ok:
            print(f"[worker] WARNING: API returned error for mark_ready, "
                  f"content may remain in 'processing' state")

        success = True

    except Exception as exc:
        print(f"[worker] ERROR processing {content_id}: {exc}")
        traceback.print_exc()
        print(f"\n--- marking as failed ---")
        try:
            api.mark_failed(cfg, content_id)
        except Exception:
            print(f"[worker] WARNING: could not mark {content_id} as failed")

    finally:
        if workdir.exists():
            print(f"[worker] cleaning up {workdir}")
            shutil.rmtree(workdir)

    print(f"{'='*60}")
    return success
