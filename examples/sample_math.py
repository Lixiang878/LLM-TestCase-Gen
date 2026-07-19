"""Sample module used by the offline demo and the README examples.

These are deliberately small, well-documented functions so the LLM (or the
offline MockProvider) can produce meaningful test cases. Use it as a template
for your own modules.
"""

from typing import Sequence


def divide(a: float, b: float) -> float:
    """Divide ``a`` by ``b``.

    Raises:
        ZeroDivisionError: if ``b`` is exactly zero.
    """
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a / b


def clamp(x: int, lo: int, hi: int) -> int:
    """Clamp ``x`` into the closed interval ``[lo, hi]``."""
    if lo > hi:
        raise ValueError("lo must be <= hi")
    return max(lo, min(hi, x))


def first(items: Sequence) -> object:
    """Return the first element of a non-empty sequence."""
    if not items:
        raise ValueError("items must be non-empty")
    return items[0]


def normalize(values: list[float]) -> list[float]:
    """Scale a list of values to the unit interval ``[0, 1]``.

    Returns an empty list when ``values`` is empty or all equal.
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]
