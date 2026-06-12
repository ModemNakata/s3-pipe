#!/usr/bin/env python3
"""
S3 Pipeline Runner

Usage:
  python main.py                          # Polling loop
  python main.py --uuid <id>              # Process one video by UUID (fetches file info from API)
  python main.py --uuid <id> --file <p>   # Process one video with explicit S3 key (no API)
"""

import argparse
import sys

from config import AppConfig
from s3_pipeline import api
from s3_pipeline.runner import run as run_poll_loop, _print_banner
from s3_pipeline.worker import process_item


def main() -> None:
    parser = argparse.ArgumentParser(description="S3 Pipeline Runner")
    parser.add_argument("--uuid", "-u", metavar="UUID",
                        help="Process a specific content UUID once")
    parser.add_argument("--file", "-f", metavar="S3_KEY",
                        help="S3 key in S3_ORIG_BUCKET "
                             "(default: fetched from GET /api/content/{uuid})")
    args = parser.parse_args()

    cfg = AppConfig.from_env()
    cfg.setup_mc()

    if args.uuid:
        _print_banner(cfg)

        if args.file:
            # Explicit file path — no API call
            item = {
                "content_id": args.uuid,
                "content_type": "video",
                "title": args.uuid,
                "files": [{"path": args.file}],
            }
            print(f"[main] direct mode: content={args.uuid}, file={args.file}")
        else:
            # Look up content info from API
            info = api.get_content(cfg, args.uuid)
            if info and info.get("files"):
                item = info
                print(f"[main] direct mode: content={args.uuid}, "
                      f"file={info['files'][0]['path']}")
            else:
                print(f"[main] ERROR: content '{args.uuid}' not found via API "
                      f"and no --file provided")
                sys.exit(1)

        process_item(cfg, item)
    else:
        run_poll_loop()


if __name__ == "__main__":
    main()
