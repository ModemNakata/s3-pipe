#!/usr/bin/env python3
"""
WebP image conversion pipeline.

Steps:
  1. Check system dependencies (ffmpeg, mc, libwebp).
  2. Create a clean local staging directory.
  3. Optionally purge the remote S3 bucket path for this image_id.
  4. Convert every supported image in input_dir to .webp using ffmpeg's libwebp.
  5. Upload the staging directory to S3 via mc.
"""

from config import Config
from pipeline import deps, workspace, process as proc, upload


def main() -> None:
    cfg = Config()

    print("=== WEBP IMAGE PIPELINE ===\n")

    # ── 1. Verify tooling ─────────────────────────────────────────────────
    deps.check(cfg)

    # ── 2. Prepare local workspace ────────────────────────────────────────
    workspace.clean_local(cfg)

    # ── 3. Clear remote bucket ────────────────────────────────────────────
    if cfg.clean_remote:
        workspace.clean_remote(cfg)

    # ── 4. Convert images to WebP ─────────────────────────────────────────
    count = proc.run(cfg)

    # ── 5. Upload to S3 ───────────────────────────────────────────────────
    upload.run(cfg)

    print(f"\n=== PIPELINE COMPLETE ===")
    print(f"Converted {count} image(s) to WebP")
    print(f"Location: {cfg.mc_alias_path}/{cfg.image_id}/")


if __name__ == "__main__":
    main()
