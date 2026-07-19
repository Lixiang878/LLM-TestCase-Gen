"""Coverage analysis across test dimensions."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .models import TestCase

VALID_DIMENSIONS = ("normal", "boundary", "exception")


def _norm_kind(kind: str) -> str:
    k = (kind or "").lower()
    if k in VALID_DIMENSIONS:
        return k
    # Heuristic re-classification from the kind string.
    if any(t in k for t in ("edge", "limit", "zero", "empty", "min", "max")):
        return "boundary"
    if any(t in k for t in ("error", "invalid", "raise", "fail", "except")):
        return "exception"
    return "normal"


def coverage_report(cases: Iterable[TestCase]) -> dict:
    """Aggregate coverage statistics for a set of cases."""
    cases = list(cases)
    by_dimension = Counter()
    by_function = defaultdict(Counter)
    by_function_total = Counter()
    kinds_seen = set()

    for c in cases:
        k = _norm_kind(c.kind)
        kinds_seen.add(k)
        by_dimension[k] += 1
        by_function[c.target][k] += 1
        by_function_total[c.target] += 1

    total = len(cases)
    missing_dims = [d for d in VALID_DIMENSIONS if by_dimension.get(d, 0) == 0]

    per_function = {}
    for fn, total_cnt in by_function_total.items():
        dims = dict(by_function[fn])
        per_function[fn] = {
            "total": total_cnt,
            "normal": dims.get("normal", 0),
            "boundary": dims.get("boundary", 0),
            "exception": dims.get("exception", 0),
            "missing_dimensions": [
                d for d in VALID_DIMENSIONS if dims.get(d, 0) == 0
            ],
        }

    # Simple coverage score: fraction of (function × dimension) cells filled.
    cells_total = len(by_function_total) * len(VALID_DIMENSIONS)
    cells_filled = sum(
        sum(1 for d in VALID_DIMENSIONS if by_function[fn].get(d, 0) > 0)
        for fn in by_function_total
    )
    score = (cells_filled / cells_total) if cells_total else 0.0

    return {
        "total_cases": total,
        "dimensions": {
            "normal": by_dimension.get("normal", 0),
            "boundary": by_dimension.get("boundary", 0),
            "exception": by_dimension.get("exception", 0),
        },
        "kinds_seen": sorted(kinds_seen),
        "missing_dimensions": missing_dims,
        "functions": per_function,
        "function_count": len(by_function_total),
        "coverage_score": round(score, 4),
        "cells_filled": cells_filled,
        "cells_total": cells_total,
    }


def format_report(report: dict) -> str:
    """Render a human-readable coverage report."""
    lines: list[str] = []
    lines.append("=" * 52)
    lines.append("  LLM Test-Case Generation — Coverage Report")
    lines.append("=" * 52)
    lines.append(f"  Total cases      : {report['total_cases']}")
    lines.append(f"  Functions covered : {report['function_count']}")
    d = report["dimensions"]
    lines.append(f"  Normal            : {d['normal']}")
    lines.append(f"  Boundary          : {d['boundary']}")
    lines.append(f"  Exception         : {d['exception']}")
    lines.append(f"  Coverage score    : {report['coverage_score']:.0%}")
    if report["missing_dimensions"]:
        lines.append(f"  Missing dims      : {', '.join(report['missing_dimensions'])}")
    lines.append("-" * 52)
    lines.append("  Per function:")
    for fn, info in report["functions"].items():
        miss = ",".join(info["missing_dimensions"]) or "none"
        lines.append(
            f"    {fn:<24} n={info['normal']:>2} b={info['boundary']:>2} "
            f"e={info['exception']:>2}  missing={miss}"
        )
    lines.append("=" * 52)
    return "\n".join(lines)
