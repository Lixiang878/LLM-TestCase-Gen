"""Prompt construction for the test-case generation LLM call."""

from __future__ import annotations

import json
from typing import Iterable

from .models import FunctionSpec

SYSTEM_PROMPT = (
    "You are a senior software engineer specializing in unit testing. "
    "Given a function's signature, parameters, docstring and source, you "
    "propose concrete unit-test cases. Each case must be specific, runnable "
    "in spirit, and cover one of three dimensions: normal (happy path), "
    "boundary (edge values: 0, empty, None, max, min), or exception "
    "(invalid input that should raise). "
    "Respond ONLY with a JSON object of the form "
    '{"cases": [{"kind": "normal|boundary|exception", "description": str, '
    '"inputs": {arg: value, ...}, "expected": str, "assertions": [str, ...]}, ...]}. '
    "Keep assertions as short Python expressions. Do not wrap the JSON in "
    "markdown fences."
)

_STRATEGY_HINTS = {
    "normal": (
        "Focus on the happy path with representative, valid inputs. "
        "Produce cases that exercise typical usage and a few meaningful variants."
    ),
    "boundary": (
        "Focus on boundary and edge conditions: empty collections, zero, None, "
        "negative numbers, maximum/minimum representable values, single-element "
        "inputs, and off-by-one cases."
    ),
    "exception": (
        "Focus on invalid or malformed inputs that should be rejected: wrong "
        "types, None where disallowed, out-of-range values, missing required "
        "arguments, and empty/garbage payloads. The case should assert that an "
        "appropriate exception is raised."
    ),
}


def build_generation_messages(
    func: FunctionSpec,
    strategy: str = "normal",
    *,
    extra_instructions: str | None = None,
) -> list[dict[str, str]]:
    """Return ``[system, user]`` chat messages for one generation pass."""
    hint = _STRATEGY_HINTS.get(strategy, _STRATEGY_HINTS["normal"])
    params_desc = ", ".join(
        f"{p.name}:{p.annotation or 'Any'}" + (f"={p.default}" if p.default else "")
        for p in func.params
    )
    user = (
        f"Please generate unit-test cases for the following function.\n\n"
        f"Function name: {func.name}\n"
        f"Signature: {func.signature}\n"
        f"Parameters: {params_desc or '(none)'}\n"
        f"Returns: {func.returns or '(unspecified)'}\n"
        f"Docstring:\n{func.docstring or '(none)'}\n\n"
        f"Source:\n{func.source or '(not provided)'}\n\n"
        f"Strategy: {strategy}. {hint}\n"
    )
    if extra_instructions:
        user += f"\nAdditional instructions: {extra_instructions}\n"
    user += (
        "\nReturn the JSON now.\n"
        f"<<FUNC_JSON>>{json.dumps(func.to_dict(), ensure_ascii=False)}<</FUNC_JSON>>"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_all_messages(
    func: FunctionSpec,
    strategies: Iterable[str],
    extra_instructions: str | None = None,
) -> list[list[dict[str, str]]]:
    """Build one message pair per requested strategy."""
    return [
        build_generation_messages(func, s, extra_instructions=extra_instructions)
        for s in strategies
    ]
