"""Tests for de-duplication and coverage analysis (offline)."""

from llm_testcase_gen.models import TestCase
from llm_testcase_gen.dedupe import dedupe
from llm_testcase_gen.coverage import coverage_report, format_report


def _case(kind, inputs, target="foo"):
    return TestCase.from_dict(
        {"target": target, "kind": kind, "inputs": inputs, "description": "d"}
    )


def test_dedupe_removes_exact_duplicates():
    a = _case("normal", {"x": 1})
    b = _case("normal", {"x": 1})  # identical -> duplicate
    c = _case("boundary", {"x": 0})
    unique, removed = dedupe([a, b, c])
    assert len(unique) == 2
    assert len(removed) == 1


def test_dedupe_order_independent_key():
    a = _case("normal", {"x": 1, "y": 2})
    b = _case("normal", {"y": 2, "x": 1})  # same content, different order
    unique, removed = dedupe([a, b])
    assert len(unique) == 1
    assert len(removed) == 1


def test_coverage_report_counts_dimensions():
    cases = [
        _case("normal", {"x": 1}),
        _case("boundary", {"x": 0}),
        _case("exception", {"x": -1}),
        _case("normal", {"x": 2}, target="bar"),
    ]
    rep = coverage_report(cases)
    assert rep["total_cases"] == 4
    assert rep["dimensions"]["normal"] == 2
    assert rep["dimensions"]["boundary"] == 1
    assert rep["dimensions"]["exception"] == 1
    assert rep["function_count"] == 2
    # foo has all 3 dims, bar only normal -> 4 of 6 cells filled (rounded).
    assert abs(rep["coverage_score"] - round(4 / 6, 4)) < 1e-9
    assert rep["missing_dimensions"] == []
    # smoke test the formatter
    assert "Coverage Report" in format_report(rep)
