"""Tests for case execution (the part that actually runs generated tests)."""

from llm_testcase_gen.parser import parse_source
from llm_testcase_gen.models import TestCase
from llm_testcase_gen.runner import run_cases, export_pytest, RunResult
from llm_testcase_gen.dedupe import dedupe_similar

# A deliberately buggy target so we can prove the runner catches failures.
_SRC = '''
def divide(a: float, b: float) -> float:
    """Divide a by b."""
    return a / b
'''


def _case(target, kind, inputs, assertions, desc="d"):
    return TestCase.from_dict(
        {"target": target, "kind": kind, "inputs": inputs,
         "description": desc, "assertions": assertions}
    )


def test_run_cases_marks_passing():
    spec = parse_source(_SRC)[0]
    cases = [
        _case("divide", "normal", {"a": 6, "b": 3}, ["result == 2"]),
        _case("divide", "normal", {"a": 1, "b": 1}, ["result == 1"]),
    ]
    run = run_cases(spec, cases)
    assert run.passed == 2
    assert run.failed == 0


def test_run_cases_flags_zero_division_as_failed():
    # Mock providers sometimes emit b=0 boundary cases; the runner must
    # surface the runtime error rather than report a green "pass".
    spec = parse_source(_SRC)[0]
    cases = [_case("divide", "boundary", {"a": 1, "b": 0}, ["result is not None"])]
    run = run_cases(spec, cases)
    assert run.failed == 1
    assert "ZeroDivisionError" in run.results[0].detail


def test_run_cases_flags_failed_assertion():
    spec = parse_source(_SRC)[0]
    cases = [_case("divide", "normal", {"a": 6, "b": 3}, ["result == 3"])]
    run = run_cases(spec, cases)
    assert run.failed == 1
    assert run.results[0].detail.startswith("assertion failed")


def test_executable_coverage_counts_functions():
    spec = parse_source(_SRC)[0]
    cases = [_case("divide", "normal", {"a": 6, "b": 3}, ["result == 2"])]
    run = run_cases(spec, cases)
    assert run.executable_coverage(["divide"]) == 1.0
    assert run.executable_coverage(["divide", "missing"]) == 0.5


def test_export_pytest_is_self_contained(tmp_path):
    spec = parse_source(_SRC)[0]
    cases = [_case("divide", "normal", {"a": 6, "b": 3}, ["result == 2"])]
    out = tmp_path / "test_gen.py"
    export_pytest(spec, cases, out)
    content = out.read_text(encoding="utf-8")
    assert "from __future__ import annotations" in content
    assert "def divide" in content
    assert "def test_divide_" in content
    # It must actually import and run under pytest.
    import subprocess, sys
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr[-500:]


def test_dedupe_similar_collapses_near_duplicates():
    a = _case("foo", "normal", {"x": 1}, ["result == 1"], "check result equals one")
    b = _case("foo", "normal", {"x": 1}, ["result == 1"], "verify result is equal to 1")
    c = _case("foo", "normal", {"x": 2}, ["result == 2"], "different input entirely")
    unique, removed = dedupe_similar([a, b, c], threshold=0.9)
    assert len(unique) == 2
    assert len(removed) == 1


def test_dedupe_similar_keeps_distinct():
    a = _case("foo", "normal", {"x": 1}, ["result == 1"])
    b = _case("foo", "normal", {"x": 2}, ["result == 2"])
    unique, removed = dedupe_similar([a, b], threshold=0.8)
    assert len(unique) == 2
    assert removed == []


def test_case_id_distinguishes_assertions():
    # Bug guard: same input but different assertions must NOT collapse to one
    # id (that previously caused export_pytest_module to overwrite cases).
    a = _case("foo", "normal", {"x": 1}, ["result == 1"])
    b = _case("foo", "normal", {"x": 1}, ["result == 2"])
    assert a.id != b.id
    assert a.canonical_key() != b.canonical_key()


def test_export_pytest_keeps_distinct_assertion_cases(tmp_path):
    spec = parse_source(_SRC)[0]
    cases = [
        _case("divide", "normal", {"a": 6, "b": 3}, ["result == 2"]),
        _case("divide", "normal", {"a": 6, "b": 3}, ["result == 6 / 3"]),
    ]
    out = tmp_path / "test_gen.py"
    export_pytest(spec, cases, out)
    names = [ln for ln in out.read_text(encoding="utf-8").splitlines()
             if ln.startswith("def test_divide_")]
    assert len(names) == 2
    assert names[0] != names[1]


def test_runner_sandbox_exposes_builtins():
    src = '''
def ordered(xs):
    return sorted(xs)
'''
    spec = parse_source(src)[0]
    cases = [_case("ordered", "normal", {"xs": [3, 1, 2]}, ["result == [1, 2, 3]"])]
    run = run_cases(spec, cases)
    assert run.passed == 1


def test_runner_does_not_shadow_result_with_input():
    # A parameter literal named "result" must not clobber the return value in
    # the assertion namespace.
    src = '''
def add(result, b):
    return result + b
'''
    spec = parse_source(src)[0]
    cases = [_case("add", "normal", {"result": 2, "b": 3}, ["result == 5"])]
    run = run_cases(spec, cases)
    assert run.passed == 1
