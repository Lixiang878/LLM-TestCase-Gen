"""LLM provider abstraction.

Two providers ship with the toolkit:

* :class:`MockProvider` — deterministic, offline. Returns plausible test cases
  derived from the function name so the whole pipeline can be exercised and
  tested without a network or an API key.
* :class:`OpenAIProvider` — talks to any OpenAI-compatible Chat Completions
  endpoint (OpenAI, Wenxin ``/v1`` proxy, Qwen, local vLLM, ...). The ``openai``
  package is imported lazily; if it is unavailable we fall back to a raw
  ``requests`` call, and if that is also missing we raise a clear error.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Sequence

from .models import FunctionSpec


class BaseProvider:
    """Minimal chat interface: ``complete(messages) -> str``."""

    name = "base"

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        raise NotImplementedError

    def generate_cases(
        self,
        func: FunctionSpec,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        return self.complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )


class MockProvider(BaseProvider):
    """Offline provider that returns deterministic, plausible-looking cases.

    It does not call any model. Instead it fabricates a small set of normal,
    boundary, and exception cases inferred from the function signature so the
    rest of the pipeline (parse → dedupe → coverage) can be developed and
    tested without a network. The produced cases are clearly pseudo-data and
    must be reviewed before use as real tests.
    """

    name = "mock"

    def __init__(self, seed_cases: int = 3, **kwargs: Any) -> None:
        self.seed_cases = max(1, seed_cases)

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        user = ""
        for m in messages:
            if m.get("role") == "user":
                user = m.get("content", "")
                break
        # Recover the FunctionSpec we stashed in the user message footer.
        func = self._recover_func(user)
        return self._render(func)

    # -- internals ---------------------------------------------------------
    def _recover_func(self, user: str) -> FunctionSpec:
        # The prompt builder appends a JSON footer; parse it back.
        m = re.search(r"<<FUNC_JSON>>\s*(\{.*\})\s*<</FUNC_JSON>>", user, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                return FunctionSpec(
                    name=data.get("name", "unknown"),
                    signature=data.get("signature", ""),
                    params=[
                        FunctionSpec.__dataclass_fields__  # placeholder
                        and _param_from_dict(p)
                        for p in data.get("params", [])
                    ],
                    docstring=data.get("docstring", ""),
                    returns=data.get("returns", ""),
                    source=data.get("source", ""),
                    file=data.get("file", ""),
                    lineno=data.get("lineno", 0),
                )
            except Exception:
                pass
        return FunctionSpec(name="unknown", signature="")

    def _render(self, func: FunctionSpec) -> str:
        params = [p.name for p in func.params if not p.name.startswith(("*", "**"))]
        if not params:
            params = ["x"]
        cases: list[dict[str, Any]] = []
        # normal
        cases.append(
            {
                "kind": "normal",
                "description": f"Typical call to {func.name} with nominal inputs.",
                "inputs": {p: _nominal(p) for p in params},
                "expected": "Returns the expected nominal result.",
                "assertions": [f"result == {_nominal(params[0])!r}"],
            }
        )
        # boundary
        cases.append(
            {
                "kind": "boundary",
                "description": f"Boundary input for {func.name} (zero / empty edge).",
                "inputs": {p: _boundary(p) for p in params},
                "expected": "Handles the boundary without error.",
                "assertions": ["result is not None"],
            }
        )
        # exception
        cases.append(
            {
                "kind": "exception",
                "description": f"Invalid input raises for {func.name}.",
                "inputs": {p: _invalid(p) for p in params},
                "expected": "Raises ValueError (or equivalent).",
                "assertions": ["with pytest.raises(ValueError): func(**inputs)"],
            }
        )
        # a couple of extra variants for realism
        for i in range(self.seed_cases - 1):
            cases.append(
                {
                    "kind": "normal",
                    "description": f"Variant {i + 1} of {func.name}.",
                    "inputs": {p: _nominal(p, offset=i + 1) for p in params},
                    "expected": "Returns a consistent result for the variant.",
                    "assertions": ["result is not None"],
                }
            )
        return json.dumps(
            {"cases": cases}, ensure_ascii=False, indent=2
        )


def _param_from_dict(d: dict[str, Any]) -> Any:
    from .models import ParamInfo

    return ParamInfo(
        name=d.get("name", "x"),
        annotation=d.get("annotation"),
        default=d.get("default"),
    )


def _nominal(name: str, offset: int = 0) -> Any:
    if name in ("n", "count", "size", "length", "num"):
        return 3 + offset
    if name in ("s", "text", "string", "name", "value"):
        return f"sample{offset}"
    if name in ("items", "data", "lst", "array"):
        return [1, 2, 3]
    if name.startswith("is_") or name in ("flag", "enable"):
        return True
    return 1 + offset


def _boundary(name: str) -> Any:
    if name in ("n", "count", "size", "length", "num"):
        return 0
    if name in ("s", "text", "string", "name", "value"):
        return ""
    if name in ("items", "data", "lst", "array"):
        return []
    return 0


def _invalid(name: str) -> Any:
    if name in ("n", "count", "size", "length", "num"):
        return -1
    if name in ("s", "text", "string", "name", "value"):
        return None
    if name in ("items", "data", "lst", "array"):
        return "not-a-list"
    return None


class OpenAIProvider(BaseProvider):
    """OpenAI-compatible Chat Completions provider (lazy deps)."""

    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        **client_kwargs: Any,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._client_kwargs = client_kwargs
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        # Prefer the official SDK; fall back to a raw requests call.
        try:  # pragma: no cover - depends on environment
            from openai import OpenAI

            kwargs = dict(self._client_kwargs)
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = ("sdk", OpenAI(**kwargs))
            return self._client
        except Exception:
            pass
        # No SDK: use requests lazily.
        self._client = ("requests", None)
        return self._client

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        kind, client = self._get_client()
        if kind == "sdk":  # pragma: no cover - depends on environment
            resp = client.chat.completions.create(
                model=self.model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return resp.choices[0].message.content or ""
        # requests fallback
        import requests  # lazy

        url = (self.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""


_PROVIDERS = {
    "mock": MockProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str = "mock", **kwargs: Any) -> BaseProvider:
    """Return a provider instance by name (``mock`` | ``openai``)."""
    name = (name or "mock").lower()
    if name not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider {name!r}. Available: {sorted(_PROVIDERS)}"
        )
    return _PROVIDERS[name](**kwargs)
