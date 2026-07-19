"""De-duplication of generated test cases."""

from __future__ import annotations

import json
import re
from typing import Iterable

from .models import TestCase

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_WS_RE = re.compile(r"\s+")


def _norm_text(s: str) -> str:
    return _WS_RE.sub(" ", (s or "").lower()).strip()


def _case_tokens(case: TestCase) -> set[str]:
    """Token signature of a case, used for similarity dedup.

    The free-text ``description`` and the ``kind`` label are excluded: LLM
    wording varies most there and least indicates semantic duplication. The
    substantive part is ``(target, inputs, assertions)`` — two cases with the
    same inputs and the same assertions are the same test regardless of how
    the model phrased them.
    """
    parts = [
        case.target,
        _norm_text(json.dumps(case.inputs or {}, sort_keys=True)),
        _norm_text(" ".join(case.assertions or [])),
    ]
    text = " ".join(parts)
    return set(_TOKEN_RE.findall(text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union


def dedupe(
    cases: Iterable[TestCase],
    *,
    keep: str = "first",
) -> tuple[list[TestCase], list[TestCase]]:
    """Remove cases that share the same canonical key.

    Returns ``(unique, removed)``. ``keep`` is ``"first"`` or ``"last"``.
    """
    cases = list(cases)
    seen: dict[str, int] = {}
    unique: list[TestCase] = []
    removed: list[TestCase] = []
    for idx, case in enumerate(cases):
        key = case.canonical_key()
        if key in seen:
            if keep == "last":
                # Drop the previously kept one, keep this.
                old_idx = seen[key]
                removed.append(unique[unique.index(cases[old_idx])])
                unique.remove(cases[old_idx])
                seen[key] = idx
                unique.append(case)
            else:
                removed.append(case)
            continue
        seen[key] = idx
        unique.append(case)
    return unique, removed


def dedupe_similar(
    cases: Iterable[TestCase],
    *,
    threshold: float = 0.8,
    keep: str = "first",
) -> tuple[list[TestCase], list[TestCase]]:
    """Collapse *near-duplicate* cases using token-set Jaccard similarity.

    LLM outputs frequently vary in wording while being semantically identical
    (e.g. ``"result == 1"`` vs ``"result equals 1"``). Exact-hash ``dedupe``
    misses these; this pass merges any pair whose normalized token overlap
    meets *threshold*.

    Returns ``(unique, removed)``.
    """
    cases = list(cases)
    sigs = [_case_tokens(c) for c in cases]
    kept_idx: list[int] = []
    removed: list[TestCase] = []
    for i, case in enumerate(cases):
        dup_of = -1
        for j in kept_idx:
            if _jaccard(sigs[j], sigs[i]) >= threshold:
                dup_of = j
                break
        if dup_of == -1:
            kept_idx.append(i)
        else:
            if keep == "last":
                # swap: drop the earlier kept one in favour of this one
                removed.append(cases[dup_of])
                kept_idx[kept_idx.index(dup_of)] = i
            else:
                removed.append(case)
    unique = [cases[i] for i in kept_idx]
    return unique, removed


def unique_count(cases: Iterable[TestCase]) -> int:
    return len({c.canonical_key() for c in cases})
