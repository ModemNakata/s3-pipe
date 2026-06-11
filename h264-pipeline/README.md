# H264 Pipeline

Transcodes a source video into an adaptive-bitrate HLS stream (fMP4 segments + master manifest). Designed to avoid wasting bits — audio re-encodes at source rate, video bitrate is capped relative to the original.

## Pipeline steps

1. **deps** — verify `ffmpeg`, `ffprobe`, `mc` are in PATH and the chosen encoder is available.
2. **probe** — extract resolution, bitrate, fps, duration, audio bitrate/codec from source with `ffprobe`.
3. **workspace** — clean local staging dir (and optionally remote S3 path).
4. **ladder** — filter the quality-ladder profiles to only those whose short-edge threshold fits the source. If none match, a fallback profile is used.
5. **transcode** — for each active profile:
   - Scale to target resolution (handles portrait/landscape).
   - CRF-based encoding with capped maxrate: `min(profile_ceiling, source_kbps * 0.9)`.
   - Audio re-encoded to AAC at the **source's own audio bitrate** (floor 64 kbps, fallback 128 kbps) to avoid wasting bits on audio across multiple variants.
   - Package as HLS fMP4 with independent keyframes.
6. **manifest** — generate `master.m3u8`.
7. **upload** — sync the staging dir to S3 via `mc`.

## Configuration

All settings live in `config.py` as a `Config` dataclass. Key knobs:

| Field | Default | What it does |
|---|---|---|
| `input_video` | `"video_output.mp4"` | Source file |
| `video_codec` | `"libx264"` | Encoder (libx264/libx265) |
| `crf` | `23` | Quality (lower = better) |
| `cap_scale` | `0.9` | Maxrate = `min(ceiling, source_kbps * cap_scale)` |
| `preset` | `"slow"` | Speed/compression trade-off |

## Optional features (not yet implemented)

### Watermark

Add a logo overlay to every variant. In `config.py`, add:

```python
watermark_path: Optional[str] = None
watermark_position: str = "top-left"  # top-left/right, bottom-left/right
```

In `transcode.py`, replace the simple `-vf` with a filter_complex when watermark_path is set:

```python
if config.watermark_path:
    cmd += ["-i", config.watermark_path]

    out_w, out_h = map(int, actual_res.split("x"))
    wm_h = max(30, int(out_h * 0.1))                     # 10% of output height

    positions = {
        "top-left":       "10:10",
        "top-right":      "main_w-overlay_w-10:10",
        "bottom-left":    "10:main_h-overlay_h-10",
        "bottom-right":   "main_w-overlay_w-10:main_h-overlay_h-10",
    }
    pos = positions.get(config.watermark_position, positions["bottom-right"])

    filter_complex = (
        f"[0:v]{scale_filter}[vid];"
        f"[1:v]scale=-2:{wm_h}:flags=lanczos[wm];"
        f"[vid][wm]overlay={pos}:format=auto[outv]"
    )
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", "[outv]"]
    cmd += ["-map", "0:a"]
else:
    cmd += ["-vf", scale_filter]
```

The watermark is scaled proportionally per variant (10% of output height) so it stays the same relative size across all ladder rungs.

### Intro / splash screen

Prepend a short branded clip (animation + jingle) to every variant using ffmpeg's `concat` filter:

```python
cmd = ["ffmpeg", "-y", "-i", "intro.mp4", "-i", config.input_video]

filter_complex = (
    "[0:v]scale=W:H:flags=bicubic[intro_v];"
    "[0:a]adelay=0[intro_a];"
    "[intro_v][1:v][intro_a][1:a]concat=n=2:v=1:a=1[outv][outa]"
)
cmd += ["-filter_complex", filter_complex]
cmd += ["-map", "[outv]"]
cmd += ["-map", "[outa]"]
```

The intro clip would need to be pre-rendered (e.g. `ffmpeg -f lavfi -i color=c=black:s=1920x1080:d=3 -vf "drawtext=text='My Brand':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" -f lavfi -i anullsrc=r=48000 -shortest intro.mp4` for a basic text splash + silence).
