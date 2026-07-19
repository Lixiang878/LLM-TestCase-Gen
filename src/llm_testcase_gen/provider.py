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
    """Offline provider that returns deterministic, *runnable* cases.

    It does not call any model. Instead it synthesizes normal / boundary /
    exception inputs from the function signature, then **executes the target
    function** with those inputs to record the true return value as the
    expected assertion. The result is a self-consistent offline fixture: every
    emitted case is valid and re-runnable, so the whole pipeline (parse ->
    dedupe -> coverage -> execute) can be exercised without a network or an
    API key. A real ``OpenAIProvider`` produces cases from a model instead.
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
                    params=[_param_from_dict(p) for p in data.get("params", [])],
                    docstring=data.get("docstring", ""),
                    returns=data.get("returns", ""),
                    source=data.get("source", ""),
                    file=data.get("file", ""),
                    lineno=data.get("lineno", 0),
                )
            except Exception:
                pass
        return FunctionSpec(name="unknown", signature="")

    @staticmethod
    def _call(spec: FunctionSpec, inputs: dict):
        """Execute ``spec`` with *inputs*; return (result, exception|None)."""
        if not spec.source:
            return None, RuntimeError("no source")
        try:
            ns: dict = {}
            exec(  # noqa: S102 - trusted user source
                compile("from __future__ import annotations\n" + spec.source,
                        f"<{spec.name}>", "exec"),
                ns,
            )
            func = ns.get(spec.name)
            if func is None:
                return None, RuntimeError("function not found")
            return func(**inputs), None
        except Exception as exc:  # raised during the call
            return None, exc

    def _render(self, func: FunctionSpec) -> str:
        params = [p.name for p in func.params if not p.name.startswith(("*", "**"))]
        if not params:
            params = ["x"]
        cases: list[dict[str, Any]] = []

        def _make(kind: str, desc: str, inputs: dict, fallback_kind: str):
            result, err = self._call(func, inputs)
            if err is not None:
                # The call raised: reclassify as an exception scenario with no
                # assertion (the runner treats a raised exception as a pass).
                return {
                    "kind": "exception" if kind != "exception" else kind,
                    "description": f"{desc} (raised {type(err).__name__}).",
                    "inputs": inputs,
                    "expected": f"Raises {type(err).__name__}.",
                    "assertions": [],
                }
            return {
                "kind": kind,
                "description": desc,
                "inputs": inputs,
                "expected": f"Returns {result!r}.",
                "assertions": [f"result == {result!r}"],
            }

        # normal
        cases.append(_make(
            "normal", f"Typical call to {func.name} with nominal inputs.",
            {p: _nominal(p) for p in params}, "exception",
        ))
        # boundary
        cases.append(_make(
            "boundary", f"Boundary input for {func.name} (zero / empty edge).",
            {p: _boundary(p) for p in params}, "exception",
        ))
        # exception
        cases.append(_make(
            "exception", f"Invalid input raises for {func.name}.",
            {p: _invalid(p) for p in params}, "exception",
        ))
        # a couple of extra variants for realism
        for i in range(self.seed_cases - 1):
            cases.append(_make(
                "normal", f"Variant {i + 1} of {func.name}.",
                {p: _nominal(p, offset=i + 1) for p in params}, "exception",
            ))
        return json.dumps({"cases": cases}, ensure_ascii=False, indent=2)


def _param_from_dict(d: dict[str, Any]) -> Any:
    from .models import ParamInfo

    return ParamInfo(
        name=d.get("name", "x"),
        annotation=d.get("annotation"),
        default=d.get("default"),
    )


_LIST_PARAMS = (
    "items", "data", "lst", "array", "seq", "list", "arr",
    "values", "vals", "xs",
)
_DIVISOR_PARAMS = ("b", "divisor", "denom", "denominator")


def _nominal(name: str, offset: int = 0) -> Any:
    if name in ("n", "count", "size", "length", "num"):
        return 3 + offset
    if name in ("s", "text", "string", "name", "value"):
        return f"sample{offset}"
    if name in _LIST_PARAMS:
        return [1, 2, 3]
    if name.startswith("is_") or name in ("flag", "enable"):
        return True
    return 1 + offset


def _boundary(name: str) -> Any:
    if name in _DIVISOR_PARAMS:
        return 1  # non-zero so division boundaries do not raise
    if name in ("n", "count", "size", "length", "num"):
        return 0
    if name in ("s", "text", "string", "name", "value"):
        return ""
    if name in _LIST_PARAMS:
        return [1]
    return 0


def _invalid(name: str) -> Any:
    # Type-mismatched values so the call reliably raises (proving the
    # exception path). The runner treats a raised exception as a pass.
    if name in ("n", "count", "size", "length", "num"):
        return "not_a_number"
    if name in _LIST_PARAMS:
        return 5  # a scalar, not iterable -> min()/indexing raises
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
