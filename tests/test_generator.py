"""End-to-end generation test using the offline MockProvider."""

from llm_testcase_gen.parser import parse_source
from llm_testcase_gen.provider import MockProvider, get_provider
from llm_testcase_gen.generator import generate_cases, parse_llm_output
from llm_testcase_gen.dedupe import dedupe
from llm_testcase_gen.coverage import coverage_report


SRC = '''
def divide(a: float, b: float) -> float:
    """Divide a by b."""
    return a / b

def clamp(x: int, lo: int, hi: int) -> int:
    """Clamp x into [lo, hi]."""
    return max(lo, min(hi, x))
'''


def test_get_provider_mock():
    p = get_provider("mock")
    assert p.name == "mock"


def test_mock_provider_emits_json():
    spec = parse_source(SRC)[0]
    provider = MockProvider()
    text = provider.generate_cases(spec, system="", user=_user_footer(spec))
    cases = parse_llm_output(text, target=spec.name)
    assert len(cases) >= 3
    kinds = {c.kind for c in cases}
    assert "normal" in kinds and "boundary" in kinds and "exception" in kinds


def _user_footer(spec):
    import json
    from llm_testcase_gen.prompt_builder import build_generation_messages

    msgs = build_generation_messages(spec, "normal")
    return msgs[1]["content"]


def test_generate_cases_full_pipeline():
    specs = parse_source(SRC)
    provider = MockProvider()
    all_cases = []
    for spec in specs:
        all_cases.extend(
            generate_cases(spec, provider, strategies=["normal", "boundary", "exception"])
        )
    unique, _ = dedupe(all_cases)
    rep = coverage_report(unique)
    assert rep["function_count"] == 2
    assert rep["coverage_score"] == 1.0
    # Each function should have all three dimensions represented.
    for fn, info in rep["functions"].items():
        assert info["missing_dimensions"] == []
