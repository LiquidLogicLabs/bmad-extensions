"""pm_status.metrics.spend -- summing and printing metric blocks for `report`.

A leaf: it reads `core` and nothing else in `metrics`. `report` consumes it, not the other
way round.
"""

from __future__ import annotations

from ..core import (
    METRIC_FIELDS,
    _actual_metric,
)


def _block_totals(node, block: str = "actual") -> dict:
    """One metric block's numeric values. Absent and `N/A` entries are omitted
    rather than coerced to zero — a missing measurement is not a measured zero."""
    b = (node or {}).get(block) or {}
    out = {}
    for m in METRIC_FIELDS:
        v = _actual_metric(b, m)
        if v is not None:
            out[m] = v
    return out


def _add_totals(dst: dict, src: dict) -> None:
    for k, v in (src or {}).items():
        dst[k] = dst.get(k, 0.0) + v


def _fmt_actuals(totals: dict) -> str:
    """Render an actuals dict in stable METRIC_FIELDS order."""
    return "  ".join(f"{m}={_norm_spend(totals.get(m))}" for m in METRIC_FIELDS)


def _norm_spend(v):
    """Display form for a summed metric: 0 when absent, trimmed of float noise.

    Summing floats produces 3.9000000000000004; a report that prints that is
    reporting its own arithmetic rather than the number. Rounded to 4 places
    (well past any metric's real precision) and shown as an int when integral.
    """
    if v is None:
        return 0
    try:
        f = round(float(v), 4)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() else f
