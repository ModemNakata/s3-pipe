#!/usr/bin/env python3
import subprocess
import sys
import tempfile
import os

FONT = "BpmfHuninn-Regular.ttf"
TEXT = "fevid.cloud/@SuperUser"
FONT_SIZE = "h*0.02"
X = 5
Y = 5
FONT_COLOR = "#7ccf00"
CRF = 17

INPUTS = [
    "video1.mp4",
    "video2.mp4",
    "image1.jpg",
    "image2.png",
]


def output_path(in_path):
    root, ext = os.path.splitext(in_path)
    return f"{root}_watermarked{ext}"


def build_cmd(in_path, out_path, textfile):
    filter_str = (
        f"drawtext="
        f"textfile={textfile}:"
        f"fontfile={FONT}:"
        f"fontcolor={FONT_COLOR}:"
        f"fontsize={FONT_SIZE}:"
        f"x={X}:"
        f"y={Y}"
    )

    ext = os.path.splitext(in_path)[1].lower()
    cmd = ["ffmpeg", "-loglevel", "repeat+verbose", "-i", in_path, "-y", "-vf", filter_str]

    if ext in (".mp4", ".mov", ".avi", ".mkv"):
        cmd += ["-c:v", "libx264", "-crf", str(CRF), "-preset", "slow", "-c:a", "copy"]
    elif ext == ".jpg":
        cmd += ["-frames:v", "1", "-update", "1", "-q:v", "2"]
    elif ext == ".png":
        cmd += ["-frames:v", "1", "-update", "1", "-compression_level", "0"]

    cmd.append(out_path)
    return cmd


def main():
    for in_path in INPUTS:
        if not os.path.exists(in_path):
            print(f"[-] Skipping (not found): {in_path}", file=sys.stderr)
            continue

        out_path = output_path(in_path)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(TEXT)
            textfile = f.name

        cmd = build_cmd(in_path, out_path, textfile)
        print(f"[+] {' '.join(cmd)}", flush=True)

        result = subprocess.run(cmd)
        os.unlink(textfile)

        if result.returncode != 0:
            print(f"[-] Failed: {in_path}", file=sys.stderr)
            sys.exit(1)

        print(f"[+] Done: {out_path}\n", flush=True)


if __name__ == "__main__":
    main()
