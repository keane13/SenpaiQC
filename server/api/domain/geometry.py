"""Coordinate conversion. ER 2 returns [y, x] normalised to 0-1000; we store pixel [x, y]."""
from __future__ import annotations


def yx1000_to_px(point_yx: list[float], width: int, height: int) -> list[int]:
    y, x = point_yx
    return [_clamp(round(x / 1000 * width), width), _clamp(round(y / 1000 * height), height)]


def box1000_to_px(box: list[float], width: int, height: int) -> list[int]:
    """[ymin, xmin, ymax, xmax] in 0-1000 -> pixel [x1, y1, x2, y2]."""
    ymin, xmin, ymax, xmax = box
    return [
        _clamp(round(xmin / 1000 * width), width),
        _clamp(round(ymin / 1000 * height), height),
        _clamp(round(xmax / 1000 * width), width),
        _clamp(round(ymax / 1000 * height), height),
    ]


def _clamp(v: int, hi: int) -> int:
    return max(0, min(hi, v))
