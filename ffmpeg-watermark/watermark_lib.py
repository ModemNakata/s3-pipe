from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional


from config import calc_font_size as _calc_font_size


@dataclass
class WatermarkConfig:
    enabled: bool = False
    text: str = "fevid.cloud/@SuperUser"
    font: str = ""
    font_size: int = 0
    color: str = "#7ccf00"
    x: int = 5
    y: int = 5
    box: bool = False
    boxcolor: str = "black@0.5"
    boxborderw: int = 6
    bordercolor: str = "black"
    borderw: int = 1
    uploader_name: str = ""


def _watermark_text(cfg: WatermarkConfig) -> str:
    if cfg.uploader_name:
        return f"{cfg.text}@{cfg.uploader_name}"
    return cfg.text


def _build_common(cfg: WatermarkConfig, textfile: str, font_size: int) -> list[str]:
    parts = [
        f"textfile={textfile}",
        f"fontfile={cfg.font}",
        f"fontcolor={cfg.color}",
        f"fontsize={font_size}",
        f"x={cfg.x}",
        f"y={cfg.y}",
    ]
    if cfg.box:
        parts.append("box=1")
        parts.append(f"boxcolor={cfg.boxcolor}")
        parts.append(f"boxborderw={cfg.boxborderw}")
    if cfg.borderw > 0:
        parts.append(f"bordercolor={cfg.bordercolor}")
        parts.append(f"borderw={cfg.borderw}")
    return parts


def build_drawtext_filter(cfg: WatermarkConfig, textfile: str, font_size: int) -> str:
    return "drawtext=" + ":".join(_build_common(cfg, textfile, font_size))


def write_textfile(text: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    f.write(text)
    f.close()
    return f.name


def cleanup_textfile(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
