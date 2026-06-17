from __future__ import annotations

import json
import shutil
import time
import traceback
from pathlib import Path
from typing import Any

import log
from config import AppConfig
from . import api, download, processor as proc, upload


def process_item(cfg: AppConfig, item: dict[str, Any]) -> bool:
    content_id: str = item["content_id"]
    content_type: str = item["content_type"]
    files: list[dict] = item.get("files", [])
    title: str = item.get("title", "")
    uploader_name: str = item.get("uploader_name", "")
    is_paywalled: bool = item.get("is_paywalled", False)
    free_preview_duration_s: int = item.get("free_preview_duration_s", 0) or 0
    unblurred_count: int = item.get("unblurred_count", 0) or 0

    workdir = cfg.work_dir / content_id
    download_dir = workdir / "download"
    success = False

    print("")
    print(f"{'='*60}")
    print(f"[worker] processing: {content_id} ({content_type})")
    print(f"[worker] title: {title}")
    print(f"[worker] paywalled: {is_paywalled}")
    if is_paywalled:
        if content_type == "video":
            print(f"[worker] free_preview_duration: {free_preview_duration_s}s")
        elif content_type == "image_set":
            print(f"[worker] unblurred_count: {unblurred_count}")
    print(f"[worker] files: {[f['path'].split('/')[-1] for f in files]}")
    log.debug("worker", f"full item:\n{json.dumps(item, indent=2, default=str)}")
    log.debug("worker", f"workdir: {workdir}")
    log.debug("worker", f"download_dir: {download_dir}")
    print(f"{'='*60}")

    try:
        print(f"\n--- step 1/4: download originals from S3_ORIG_BUCKET ---")
        local_paths = download.download_item_files(cfg, files, download_dir)
        print(f"[worker] downloaded {len(local_paths)} file(s) to {download_dir}")

        print(f"\n--- step 2/4: encode ---")
        t0 = time.time()

        cfg.watermark_uploader_name = uploader_name

        duration = 0
        source_quality = ""

        if content_type == "video":
            if len(local_paths) != 1:
                raise ValueError(f"expected 1 file for video, got {len(local_paths)}")
            output_dir, duration, free_preview_output_dir, source_quality = proc.process_video(
                cfg, local_paths[0], content_id, cfg.work_dir,
                free_preview_duration=free_preview_duration_s if is_paywalled else 0)
        elif content_type == "image_set":
            output_dir = proc.process_images(cfg, download_dir, content_id, cfg.work_dir,
                                             first_image=local_paths[0],
                                             files=files if is_paywalled else None,
                                             unblurred_count=unblurred_count if is_paywalled else 0)
        else:
            raise ValueError(f"unknown content_type: {content_type}")

        elapsed = time.time() - t0
        print(f"[worker] encoding took {elapsed:.1f}s")
        log.debug("worker", f"encoding completed in {elapsed:.3f}s")

        print(f"\n--- step 3/4: upload to S3_BUCKET ---")
        free_preview_path = ""
        blurred_files: list[str] = []

        if content_type == "video":
            upload.upload_video(cfg, output_dir, content_id)
            s3_prefix = f"videos/{content_id}"
            thumbnail_url = f"{s3_prefix}/thumbnail.jpg"
            preview_path = f"{s3_prefix}/preview.webm"
            processed_files = [f"{s3_prefix}/master.m3u8"]
            if is_paywalled and free_preview_output_dir:
                upload.upload_video(cfg, free_preview_output_dir, f"{content_id}/free_preview")
                free_preview_path = f"{s3_prefix}/free_preview/master.m3u8"
        else:
            upload.upload_images(cfg, output_dir, content_id)
            s3_prefix = f"galleries/{content_id}"
            thumbnail_url = ""
            preview_path = f"{s3_prefix}/preview.webp"
            processed_files = [
                f"galleries/{content_id}/{f['path'].split('/')[-1].rsplit('.', 1)[0]}.webp"
                for f in files
            ]
            if is_paywalled:
                blurred_files = [
                    f"galleries/{content_id}/blurred_{i}.webp" if i >= unblurred_count else ""
                    for i in range(len(files))
                ]

        print(f"\n--- step 4/4: mark as ready ---")
        ok = api.mark_ready(cfg, content_id,
                            thumbnail_url=thumbnail_url,
                            preview_path=preview_path,
                            duration=duration,
                            processed_files=processed_files,
                            free_preview_path=free_preview_path,
                            blurred_files=blurred_files if is_paywalled else None,
                            source_quality=source_quality)
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
            log.debug("worker", f"cleaning up {workdir} (size before: {sum(f.stat().st_size for f in workdir.rglob('*') if f.is_file()) / (1024*1024):.1f} MB)")
            print(f"[worker] cleaning up {workdir}")
            shutil.rmtree(workdir)

    print(f"{'='*60}")
    return success
