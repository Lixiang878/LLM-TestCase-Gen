"""Data models shared across the toolkit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ParamInfo:
    """A single function parameter."""

    name: str
    annotation: str | None = None
    default: str | None = None

    @property
    def is_required(self) -> bool:
        return self.default is None


@dataclass
class FunctionSpec:
    """A structured description of a callable extracted from source."""

    name: str
    signature: str
    params: list[ParamInfo] = field(default_factory=list)
    docstring: str = ""
    returns: str = ""
    source: str = ""
    file: str = ""
    lineno: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestCase:
    """A single generated test case."""

    __test__ = False  # tell pytest this is not a test class

    id: str
    target: str
    kind: str  # normal | boundary | exception
    description: str
    inputs: dict[str, Any]
    expected: str = ""
    assertions: list[str] = field(default_factory=list)
    provider: str = "unknown"
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TestCase":
        d = dict(d)
        d.pop("id", None)  # regenerated deterministically below
        target = d.get("target", "unknown")
        kind = d.get("kind", "normal")
        description = d.get("description", "")
        inputs = d.get("inputs", {}) or {}
        # Deterministic id from content so identical cases collide.
        fingerprint = json.dumps(
            {"target": target, "kind": kind, "inputs": inputs},
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        _id = hashlib.sha1(fingerprint).hexdigest()[:12]
        return cls(
            id=_id,
            target=target,
            kind=kind,
            description=description,
            inputs=inputs,
            expected=d.get("expected", ""),
            assertions=list(d.get("assertions", [])),
            provider=d.get("provider", "unknown"),
            raw=d.get("raw", ""),
        )

    def canonical_key(self) -> str:
        """Stable key for de-duplication (ignores id/description/assertions)."""

        def _norm(v: Any) -> Any:
            if isinstance(v, dict):
                return {k: _norm(v[k]) for k in sorted(v)}
            if isinstance(v, list):
                return [_norm(x) for x in v]
            if isinstance(v, float):
                return round(v, 9)
            return v

        payload = json.dumps(
            {"target": self.target, "kind": self.kind, "inputs": _norm(self.inputs)},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()
