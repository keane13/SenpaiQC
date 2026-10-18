"""p-chart with 3-sigma limits, one subgroup per (day, shift). Deterministic."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Subgroup:
    key: str  # "YYYY-MM-DD/A"
    n: int  # parts inspected
    d: int  # parts with this defect


@dataclass
class PChartPoint:
    key: str
    n: int
    d: int
    p: float
    center: float
    ucl: float
    lcl: float
    out_of_control: bool


def p_chart(subgroups: list[Subgroup], baseline: int | None = None) -> list[PChartPoint]:
    """Compute p-chart points.

    The centre line comes from the first `baseline` subgroups (phase I) when given,
    otherwise from all subgroups. Using a baseline keeps a later spike from inflating
    its own control limits.
    """
    ref = subgroups[:baseline] if baseline else subgroups
    total_n = sum(s.n for s in ref)
    p_bar = (sum(s.d for s in ref) / total_n) if total_n else 0.0
    points: list[PChartPoint] = []
    for s in subgroups:
        p = s.d / s.n if s.n else 0.0
        sigma = math.sqrt(p_bar * (1 - p_bar) / s.n) if s.n else 0.0
        ucl = min(1.0, p_bar + 3 * sigma)
        lcl = max(0.0, p_bar - 3 * sigma)
        points.append(PChartPoint(s.key, s.n, s.d, p, p_bar, ucl, lcl, p > ucl))
    return points
