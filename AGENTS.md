# HLS-webp-pipeline-S3 — Agent Guide

## Project Overview

A media processing pipeline that downloads source files from S3 (MinIO), transcodes them, and uploads results back to S3 with an API status callback. Supports two content types:

- **Video**: HLS (fMP4 segments) via ffmpeg + libx264, with multi-profile ABR ladder
- **Image set**: WebP via ffmpeg's libwebp encoder

Used by a parent platform at `fevid.cloud` — the API at `PIPELINE_API_URL` serves pending items and receives status updates.

## Quick Start

```bash
# Copy and edit config
cp .env_example .env

# Run main polling loop (fetches pending items from API every N seconds)
python main.py

# Process one specific video by UUID
python main.py --uuid <id>

# Process one video with explicit S3 key (no API call)
python main.py --uuid <id> --file <s3_key>

# Dev/test mode — single pass, re-process already-ready items (?all=true)
python main.py --test
```

There are **no Python dependencies** beyond stdlib. External tools required: `ffmpeg`, `ffprobe`, `mc` (MinIO Client).

## Architecture

### Code Layout

```
.
├── main.py                       # CLI entrypoint (argparse)
├── config.py                     # AppConfig, VideoConfig, ImageConfig, Profile, WatermarkConfig dataclasses
├── log.py                        # Logging helpers + subprocess runner (run_cmd)
├── deps.py                       # Dependency checks (ffmpeg encoder avail, mc in PATH)
├── s3_pipeline/                  # Orchestration layer
│   ├── runner.py                 # Poll loop & run-once logic
│   ├── worker.py                 # process_item() — the main 4-step pipeline
│   ├── processor.py              # Video/Image processing orchestration (calls sub-pipelines)
│   ├── download.py               # S3 download via `mc cp`
│   ├── upload.py                 # S3 upload via `mc cp --recursive`
│   ├── api.py                    # HTTP client for PATCH callbacks (GET pending, PATCH status)
│   └── __init__.py               # empty
├── video-pipeline/pipeline/      # Video sub-pipeline (importlib-loaded at runtime)
│   ├── probe.py                  # ffprobe → VideoMeta dataclass
│   ├── transcode.py              # ffmpeg → HLS segments per profile
│   └── manifest.py               # Generate master.m3u8
├── image-pipeline/pipeline/      # Image sub-pipeline (importlib-loaded at runtime)
│   └── process.py                # ffmpeg → WebP per source image
├── .env_example                  # Required config template
├── BpmfHuninn-Regular.ttf        # Watermark font file
└── AGENTS.md                     # This file
```

### Control Flow

```
main.py
  └─> s3_pipeline/runner.run() ──> poll loop: GET /api/pending-processing
        └─> worker.process_item()
              ├── step 1: download.download_item_files()   [mc cp from S3_ORIG_BUCKET]
              ├── step 2: processor.process_video() or process_images()
              │            ├── _load_pipeline() [importlib] ──> probe/transcode/manifest or process
              │            ├── deps.check_video() or check_image()
              │            └── ffmpeg subprocess calls
              ├── step 3: upload.upload_video() or upload_images()  [mc cp to S3_BUCKET]
              └── step 4: api.mark_ready() or mark_failed()  [PATCH /api/content/{id}/status]
```

### Key Design Details

- **Dynamic pipeline loading**: `processor._load_pipeline()` uses `importlib` to load `video-pipeline/` or `image-pipeline/` modules at runtime. This avoids hard import paths. The modules are loaded fresh each time via `_clear()` (deletes from `sys.modules`).
- **S3 operations**: All S3 I/O uses the `mc` CLI tool, not boto3. The `mc` alias is configured at startup via `AppConfig.setup_mc()`.
- **API communication**: Pure stdlib (`urllib.request`), no requests library. Uses `urllib.request.urlopen` with configurable SSL verification. PATCH requests use `X-Api-Key` header (value = S3 access key).
- **Logging**: Custom `log.py` with `info()` and `debug()` print-based logging. `run_cmd()` is the standard subprocess runner — it captures output by default, or streams to terminal when `STREAM_CMD_OUTPUT=true`.
- **Work directory**: Content is processed in `PIPELINE_WORK_DIR/{content_id}/` and cleaned up via `shutil.rmtree()` in the `finally` block.

### Content Types & Paywalled Content

- **`video`**: Expects exactly 1 source file. Generates HLS output, thumbnail (JPG, 16:9 crop at 5s), preview (WebM/VP9). For paywalled videos, also generates a separate HLS free-preview subdirectory (trimmed to `free_preview_duration_s`).
- **`image_set`**: Generates WebP from each file in the download directory. First-image preview (720px square crop). For paywalled image sets, generates blurred WebP variants (`blurred_{i}.webp`) via ffmpeg `gblur` filter for images beyond `unblurred_count`.
- S3 paths: `videos/{content_id}/` and `galleries/{content_id}/` respectively.

## Configuration

All config is via `.env` file (loaded in `AppConfig.from_env()`). Environment variables override `.env` values for: `PIPELINE_API_URL`, `PIPELINE_API_VERIFY_SSL`, `POLL_INTERVAL`, `PIPELINE_WORK_DIR`, `LOG_LEVEL`. See `.env_example` for all options.

Key config groups:
- **S3**: endpoint, credentials, region, buckets (origin + destination)
- **Video**: codec, CRF, preset, pixel format, HLS params, rate control toggle/overrides
- **Profiles**: ABR ladder (1440p/1080p/720p/480p) with bandwidth/ref_width/threshold/maxrate/bufsize
- **Image**: WebP quality, lossless, max dimension constraint
- **Watermark**: drawtext filter params, diagonal-responsive font sizing, optional font file
- **Blur**: sigma + steps for paywalled gallery blur
- **Logging**: LOG_LEVEL (INFO/DEBUG), STREAM_CMD_OUTPUT for live ffmpeg output

## Code Patterns & Gotchas

### Gotchas

- **Profile dataclass has mismatched fields**: The `Profile` dataclass requires `maxrate_kbps` and `bufsize_kbps` as constructor args, but code in `processor.py` constructs them without these fields (using `ceiling_kbps` which doesn't exist on the dataclass). The `transcode.py` also accesses `profile.ceiling_kbps`. This is a known work-in-progress refactoring state — the defaults in `_load_profiles()` also omit `bufsize_kbps`. Pyright reports several type errors for this.
- **`_load_profiles()` hardcodes maxrate defaults**: The fallback profiles in lines 269-273 pass only 5 args (name, bandwidth, ref_width, threshold, maxrate_kbps) but miss `bufsize_kbps`. These are treated as positional matching old signature before `maxrate_kbps` and `bufsize_kbps` fields were added.
- **`download.py` calls `sys.exit(1)`** on error instead of raising. This kills the entire process, not just the current item.
- **No retry logic**: The poll loop catches exceptions broadly and retries, but individual item failures within `process_item` go through a try/except that marks the content as failed via API then continues.
- **Work dir cleanup**: `shutil.rmtree(workdir)` runs in `finally` block of `process_item()` — log.debug shows size before deletion. If something goes wrong, the workdir is removed regardless.
- **Imports use `from __future__ import annotations`** in all modules.
- **`log.py`** reads `.env` directly (not through `AppConfig`) for `LOG_LEVEL` and `STREAM_CMD_OUTPUT` — these configs are read in two places.
- **Watermark font**: The `BpmfHuninn-Regular.ttf` font file sits at the project root. Set `WATERMARK_FONT` in `.env` to its absolute path to enable watermark text rendering.
- **Rate control toggle**: `RATE_CONTROL_ENABLED=false` disables `-maxrate`/`-bufsize` entirely in ffmpeg. `RATE_CONTROL_MAXRATE`/`RATE_CONTROL_BUFSIZE` override per-profile calculations.

### Naming & Style

- Python 3.10+ (uses `str | None` syntax)
- No type checking or linting configured (pyright errors exist)
- Print-based logging (`[module] message`) with custom `log.py`
- Config dataclasses in `config.py` hold both defaults and env-loaded values
- Private module functions prefixed with `_`
- `run_cmd(cmd, module=...)` for all subprocess calls — always returns `subprocess.CompletedProcess`

### Testing

There are no tests, no test framework, no CI configuration. The project is in active development.

## Commands

```bash
# Run pipeline (polling mode)
python main.py

# Process specific content
python main.py --uuid <uuid>
python main.py --uuid <uuid> --file <s3_key>

# Dev single-pass (re-process ready items too)
python main.py --test

# Check dependencies manually
python -c "from deps import check_video; from config import VideoConfig; check_video(VideoConfig(input_video='/path/to/file'))"

# Set streaming output for live ffmpeg progress
STREAM_CMD_OUTPUT=true python main.py

# Debug mode (verbose command logging)
LOG_LEVEL=DEBUG python main.py
```

No build, test, lint, or typecheck commands exist. Run directly with `python main.py`.
