from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WatermarkConfig:
    enabled: bool = False
    text: str = "fevid.cloud/@SuperUser"
    font: str = ""
    font_size_expr: str = "h*0.02"
    color: str = "#7ccf00"
    x: int = 5
    y: int = 5


def build_drawtext_filter(cfg: WatermarkConfig, textfile: str) -> str:
    return (
        f"drawtext="
        f"textfile={textfile}:"
        f"fontfile={cfg.font}:"
        f"fontcolor={cfg.color}:"
        f"fontsize={cfg.font_size_expr}:"
        f"x={cfg.x}:"
        f"y={cfg.y}"
    )


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
