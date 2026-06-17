from __future__ import annotations

import time
from typing import Optional

import log
from config import AppConfig
from . import api
from .worker import process_item


def run(cfg: Optional[AppConfig] = None) -> None:
    if cfg is None:
        cfg = AppConfig.from_env()
        cfg.setup_mc()
    _print_banner(cfg)
    run_loop(cfg)


def run_once(cfg: AppConfig) -> None:
    cfg.dev_mode = True
    items = api.get_pending_items(cfg)
    for item in items:
        process_item(cfg, item)


def run_loop(cfg: AppConfig) -> None:
    while True:
        try:
            items = api.get_pending_items(cfg)
            if not items:
                log.debug("runner", "no pending items, entering sleep")
                print(f"[runner] no pending items, sleeping {cfg.poll_interval_sec}s")
                time.sleep(cfg.poll_interval_sec)
                continue

            log.debug("runner", f"processing {len(items)} pending item(s)")
            for item in items:
                process_item(cfg, item)

        except KeyboardInterrupt:
            print("\n[runner] interrupted, shutting down")
            break
        except Exception as exc:
            print(f"[runner] unexpected error in poll loop: {exc}")
            import traceback
            traceback.print_exc()
            print(f"[runner] sleeping {cfg.poll_interval_sec}s before retry")
            time.sleep(cfg.poll_interval_sec)


def _print_banner(cfg: AppConfig) -> None:
    print("")
    print("╔══════════════════════════════════════════════╗")
    print("║      S3 Pipeline Runner — starting up       ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"  API:            {cfg.api_base_url}")
    print(f"  S3 endpoint:    {cfg.s3_endpoint}")
    print(f"  S3 orig bucket: {cfg.s3_bucket_origin}")
    print(f"  S3 dest bucket: {cfg.s3_bucket}")
    print(f"  Poll interval:  {cfg.poll_interval_sec}s")
    print(f"  Work dir:       {cfg.work_dir}")
    if cfg.dev_mode:
        print(f"  Mode:           DEV (all=true)")
    print("")
