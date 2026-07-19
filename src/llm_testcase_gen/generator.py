"""Generation orchestration: call a provider, parse, and assemble cases."""

from __future__ import annotations

import json
import re
from typing import Iterable, Sequence

from .models import FunctionSpec, TestCase
from .provider import BaseProvider
from .prompt_builder import build_generation_messages

_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_llm_output(text: str, target: str = "unknown") -> list[TestCase]:
    """Robustly extract a ``{"cases": [...]}`` list from an LLM reply.

    Tolerates markdown code fences and surrounding prose.
    """
    if not text:
        return []
    candidate = text.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.S)
    if fence:
        candidate = fence.group(1)
    # Fallback: grab the outermost {...} block.
    if not candidate.lstrip().startswith("{"):
        m = _JSON_RE.search(candidate)
        candidate = m.group(0) if m else candidate
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # Last resort: try to locate a "cases" array anywhere.
        m = re.search(r'"cases"\s*:\s*(\[.*?\])\s*}', candidate, re.S)
        if not m:
            return []
        try:
            data = {"cases": json.loads(m.group(1))}
        except json.JSONDecodeError:
            return []
    raw_cases = data.get("cases", []) if isinstance(data, dict) else []
    out: list[TestCase] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        item["target"] = item.get("target") or target
        out.append(TestCase.from_dict(item))
    return out


def generate_cases(
    func: FunctionSpec,
    provider: BaseProvider,
    strategies: Sequence[str] | None = None,
    *,
    cases_per_strategy: int = 3,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    extra_instructions: str | None = None,
    provider_name: str | None = None,
) -> list[TestCase]:
    """Generate test cases for *func* across the given *strategies*.

    Each strategy is one provider call; results are concatenated. The
    ``MockProvider`` ignores ``cases_per_strategy`` and emits its own fixed set.
    """
    strategies = list(strategies or ["normal", "boundary", "exception"])
    pname = provider_name or getattr(provider, "name", "unknown")
    collected: list[TestCase] = []
    for strategy in strategies:
        messages = build_generation_messages(
            func, strategy, extra_instructions=extra_instructions
        )
        text = provider.complete(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        for case in parse_llm_output(text, target=func.name):
            case.provider = pname
            case.raw = text
            collected.append(case)
    return collected
