"""Execute and export generated test cases as *runnable* verification.

This module is what separates a test-case *generator* from a text
*summarizer*: every ``TestCase`` produced by the LLM is actually executed
against the real target function, and each of its assertions is evaluated.
The outcome (pass / fail / exception) is reported per case, and an
"executable coverage" score tells you how many target functions have at
least one passing test.

Safety note
-----------
Generated ``assertions`` are model-authored expressions. They are evaluated
in a restricted namespace (``__builtins__`` removed; only ``result``, the
case inputs, and a minimal math allowlist are exposed). The target function
is likewise executed in that namespace. This is a *best-effort* sandbox, not
a security boundary: do not point this at untrusted model output in a
shared/multi-tenant environment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .models import FunctionSpec, TestCase

# Minimal allowlist exposed to generated assertion expressions.
_SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "round": round, "len": len,
    "float": float, "int": int, "str": str, "bool": bool, "sum": sum,
    "any": any, "all": all, "isinstance": isinstance, "type": type,
    "sorted": sorted, "list": list, "dict": dict, "tuple": tuple,
    "set": set, "range": range, "zip": zip, "enumerate": enumerate,
    "repr": repr, "True": True, "False": False, "None": None, "math": math,
}


@dataclass
class CaseResult:
    case_id: str
    target: str
    kind: str
    passed: bool
    detail: str

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "target": self.target,
            "kind": self.kind,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class RunResult:
    results: list[CaseResult] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def to_dict(self) -> dict:
        return {
            "total": len(self.results),
            "passed": self.passed,
            "failed": self.failed,
            "error": self.error,
            "cases": [r.to_dict() for r in self.results],
        }

    def executable_coverage(self, targets: Iterable[str]) -> float:
        """Fraction of *targets* that have at least one passing case."""
        targets = list(targets)
        if not targets:
            return 0.0
        ok = {r.target for r in self.results if r.passed}
        return sum(1 for t in targets if t in ok) / len(targets)


def _load_function(spec: FunctionSpec):
    """Compile and return the target function from its embedded source.

    The function source is the user's own code (parsed from their file), so it
    is executed with the normal builtins. Only the *assertions* are sandboxed.
    """
    if not spec.source:
        raise ValueError(f"no source available for {spec.name!r}")
    namespace: dict = {}
    # PEP 563: keep annotations as strings so undefined annotation names
    # (e.g. ``List``) do not break compilation of the embedded source.
    src = "from __future__ import annotations\n" + spec.source
    try:
        exec(compile(src, f"<{spec.name}>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"failed to compile {spec.name}: {exc}") from exc
    if spec.name not in namespace:
        raise ValueError(f"{spec.name!r} not found after executing source")
    return namespace[spec.name]


def run_cases(spec: FunctionSpec, cases: Iterable[TestCase]) -> RunResult:
    """Execute *cases* against the real target function and evaluate assertions.

    Semantics are *kind*-aware:

    * ``normal`` / ``boundary`` — the call must succeed; every assertion is
      then evaluated. A raised exception or a failed assertion marks the case
      failed.
    * ``exception`` — the call is *expected* to raise. The case passes if the
      call raised (the assertion list is ignored, since ``pytest.raises``-style
      syntax is not supported by the sandbox); it fails if the call returns
      normally.

    Any exception type/message is captured as ``detail``.
    """
    result = RunResult()
    try:
        func = _load_function(spec)
    except ValueError as exc:
        result.error = str(exc)
        return result

    for case in cases:
        passed = True
        detail = "ok"
        try:
            call_kwargs = dict(case.inputs or {}) if isinstance(case.inputs, dict) else {}
            try:
                result_val = func(**call_kwargs)
                raised = None
            except Exception as exc:  # call raised
                raised = exc

            if case.kind == "exception":
                if raised is not None:
                    detail = f"raised as expected: {type(raised).__name__}"
                else:
                    passed = False
                    detail = "expected an exception but the call succeeded"
                result.results.append(
                    CaseResult(case.id, case.target, case.kind, passed, detail)
                )
                continue

            # normal / boundary: a raise is a failure.
            if raised is not None:
                result.results.append(
                    CaseResult(case.id, case.target, case.kind, False,
                               f"{type(raised).__name__}: {raised}")
                )
                continue

            ns = {"__builtins__": _SAFE_BUILTINS}
            ns.update({k: v for k, v in (case.inputs or {}).items()})
            # Keep `result` pointing at the return value even if an input
            # parameter happens to be named "result" (assertions reference it).
            ns["result"] = result_val
            assertions = case.assertions or []
            if not assertions:
                detail = "no assertions (call succeeded)"
            for assertion in assertions:
                if not eval(assertion, ns):  # noqa: S307 - sandboxed
                    passed = False
                    detail = f"assertion failed: {assertion}"
                    break
        except Exception as exc:  # a malformed assertion expression
            passed = False
            detail = f"{type(exc).__name__}: {exc}"
        result.results.append(
            CaseResult(case.id, case.target, case.kind, passed, detail)
        )
    return result


def export_pytest(
    spec: FunctionSpec, cases: Iterable[TestCase], path: str | Path
) -> Path:
    """Write a self-contained, runnable pytest module for one *spec*.

    Convenience wrapper around :func:`export_pytest_module` for a single
    function. The target function source is embedded (with
    ``from __future__ import annotations`` so annotation names need not be
    imported). Exception-kind cases are wrapped in ``pytest.raises`` so the
    exported file passes ``pytest`` cleanly.
    """
    return export_pytest_module([(spec, list(cases))], path)


def export_pytest_module(
    items: Iterable[tuple[FunctionSpec, list[TestCase]]],
    path: str | Path,
) -> Path:
    """Write a single self-contained pytest module for *multiple* functions.

    Each ``(spec, cases)`` pair contributes its embedded function source and
    one test per case. Exception-kind cases are emitted as
    ``with pytest.raises(Exception):`` blocks so the file is green under
    ``pytest``.
    """
    path = Path(path)
    lines: list[str] = []
    lines.append('"""Auto-generated tests (llm-testcase-gen)."""')
    lines.append("from __future__ import annotations")
    lines.append("import pytest")
    lines.append("")
    for spec, cases in items:
        lines.append(f"# --- {spec.name} ---")
        for src_line in (spec.source or "").splitlines():
            lines.append(src_line)
        lines.append("")
        for case in cases:
            fn = f"test_{spec.name}_{case.id}"
            lines.append(f"def {fn}():")
            lines.append(f"    \"\"\"{case.kind}: {case.description}\"\"\"")
            args = ", ".join(f"{k}={v!r}" for k, v in (case.inputs or {}).items())
            call = f"{spec.name}({args})" if args else f"{spec.name}()"
            if case.kind == "exception":
                lines.append(f"    with pytest.raises(Exception):")
                lines.append(f"        {call}")
            else:
                lines.append(f"    result = {call}")
                for assertion in (case.assertions or []):
                    lines.append(f"    assert {assertion}")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def format_run_report(run: RunResult, targets: Iterable[str]) -> str:
    targets = list(targets)
    lines = [
        "=" * 52,
        "  LLM Test-Case Generation — Execution Report",
        "=" * 52,
        f"  Total cases : {len(run.results)}",
        f"  Passed      : {run.passed}",
        f"  Failed      : {run.failed}",
        f"  Exec coverage: {run.executable_coverage(targets):.0%} "
        f"({len({r.target for r in run.results if r.passed})}/{len(targets)} functions)",
        "-" * 52,
    ]
    if run.error:
        lines.append(f"  [fatal] {run.error}")
    for r in run.results:
        mark = "PASS" if r.passed else "FAIL"
        lines.append(f"  [{mark}] {r.target}/{r.kind}/{r.case_id}: {r.detail}")
    lines.append("=" * 52)
    return "\n".join(lines)
