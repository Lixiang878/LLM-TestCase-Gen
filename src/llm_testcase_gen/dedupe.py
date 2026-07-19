"""De-duplication of generated test cases."""

from __future__ import annotations

from typing import Iterable

from .models import TestCase


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


def unique_count(cases: Iterable[TestCase]) -> int:
    return len({c.canonical_key() for c in cases})
