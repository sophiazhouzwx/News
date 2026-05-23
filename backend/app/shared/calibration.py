"""Calibration analysis + shrinkage.

A model's confidence is *calibrated* when its claimed N%-confidence calls
hit at ~N%. Most predictors are systematically overconfident. This module
surfaces the gap and gives you a shrinkage helper to pull future confidences
toward the historically-observed rate.

Pure functions throughout — pass in a list of ``{confidence_pct, outcome}``
dicts (from any source: SQLAlchemy rows, parquet, a backtest harness, etc.).
No DB / file I/O lives here.
"""

from __future__ import annotations

from typing import Iterable

# Default 10-pp buckets covering 0..100. Last bucket is inclusive of 100.
DEFAULT_BUCKETS: list[tuple[int, int]] = [
    (0, 10), (10, 20), (20, 30), (30, 40), (40, 50),
    (50, 60), (60, 70), (70, 80), (80, 90), (90, 101),
]


def bucket_for(
    confidence_pct: float,
    buckets: list[tuple[int, int]] = DEFAULT_BUCKETS,
) -> str:
    """Return the bucket label e.g. ``'50-59'`` for the given confidence."""
    c = max(0.0, min(100.0, float(confidence_pct)))
    for lo, hi in buckets:
        if lo <= c < hi:
            return f"{lo}-{hi - 1}"
    last_lo, last_hi = buckets[-1]
    return f"{last_lo}-{last_hi - 1}"


def calibration_curve(
    items: Iterable[dict],
    *,
    confidence_key: str = "confidence_pct",
    outcome_key: str = "outcome",
    hit_value: str = "hit",
    buckets: list[tuple[int, int]] = DEFAULT_BUCKETS,
) -> list[dict]:
    """Bucket items by claimed confidence and report observed hit rate.

    Returns one row per bucket:
        {bucket, lo, hi, n, hits, observed_hit_rate_pct, claimed_midpoint_pct, gap_pct}

    ``gap_pct = observed - claimed_midpoint``: negative means overconfident.
    """
    counts: dict[tuple[int, int], list[int]] = {b: [0, 0] for b in buckets}
    for it in items:
        c = it.get(confidence_key)
        o = it.get(outcome_key)
        if c is None or o is None:
            continue
        try:
            c_val = float(c)
        except (TypeError, ValueError):
            continue
        for lo, hi in buckets:
            if lo <= c_val < hi:
                counts[(lo, hi)][0] += 1
                if o == hit_value:
                    counts[(lo, hi)][1] += 1
                break

    out: list[dict] = []
    for (lo, hi), (n, hits) in counts.items():
        observed = (hits / n * 100.0) if n else None
        mid = (lo + hi - 1) / 2.0
        gap = (observed - mid) if observed is not None else None
        out.append({
            "bucket": f"{lo}-{hi - 1}",
            "lo": lo,
            "hi": hi - 1,
            "n": n,
            "hits": hits,
            "observed_hit_rate_pct": round(observed, 1) if observed is not None else None,
            "claimed_midpoint_pct": mid,
            "gap_pct": round(gap, 1) if gap is not None else None,
        })
    return out


def brier_score(
    items: Iterable[dict],
    *,
    confidence_key: str = "confidence_pct",
    outcome_key: str = "outcome",
    hit_value: str = "hit",
) -> float | None:
    """Lower is better. 0 = perfect, 0.25 = random binary at 50% base rate."""
    sq_errors: list[float] = []
    for it in items:
        c = it.get(confidence_key)
        o = it.get(outcome_key)
        if c is None or o is None:
            continue
        try:
            p = max(0.0, min(1.0, float(c) / 100.0))
        except (TypeError, ValueError):
            continue
        y = 1.0 if o == hit_value else 0.0
        sq_errors.append((p - y) ** 2)
    if not sq_errors:
        return None
    return sum(sq_errors) / len(sq_errors)


def shrunk_confidence(
    raw_confidence_pct: float,
    curve: list[dict],
    *,
    min_bucket_n: int = 10,
) -> float:
    """Bayesian-style blend: pull raw confidence toward the observed hit rate
    of its bucket. Weight is min(1, n / (3 * min_bucket_n)) so we trust the
    raw value until we have meaningful data.

    With min_bucket_n=10:
    - n < 10:           weight = 0, return raw
    - n = 10:           weight = 1/3, modest pull toward observed
    - n = 30:           weight = 1.0, return observed
    """
    raw = max(0.0, min(100.0, float(raw_confidence_pct)))
    for row in curve:
        if row["lo"] <= raw <= row["hi"]:
            n = row.get("n") or 0
            obs = row.get("observed_hit_rate_pct")
            if n < min_bucket_n or obs is None:
                return raw
            w = min(1.0, n / float(min_bucket_n * 3))
            return round(raw * (1 - w) + obs * w, 1)
    return raw
