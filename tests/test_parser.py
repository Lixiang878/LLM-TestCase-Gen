"""Tests for the source-code parser."""

from llm_testcase_gen.parser import parse_source
from llm_testcase_gen.models import ParamInfo


def test_parse_simple_function():
    src = '''
def add(a: int, b: int = 1) -> int:
    """Add two numbers."""
    return a + b
'''
    specs = parse_source(src)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "add"
    assert spec.docstring.strip() == "Add two numbers."
    assert spec.returns == "int"
    names = [p.name for p in spec.params]
    assert names == ["a", "b"]
    b = spec.params[1]
    assert b.annotation == "int"
    assert b.default == "1"


def test_parse_skips_private_by_default():
    src = '''
def public(x):
    return x

def _private(y):
    return y
'''
    specs = parse_source(src)
    assert [s.name for s in specs] == ["public"]
    specs2 = parse_source(src, include_private=True)
    assert {s.name for s in specs2} == {"public", "_private"}


def test_parse_kwonly_and_varargs():
    src = '''
def f(a, *args, b=2, **kw):
    pass
'''
    spec = parse_source(src)[0]
    names = [p.name for p in spec.params]
    assert names == ["a", "*args", "b", "**kw"]
    assert spec.params[2].default == "2"


def test_parse_async():
    src = '''
async def fetch(url: str) -> dict:
    """Fetch a url."""
    return {}
'''
    spec = parse_source(src)[0]
    assert spec.name == "fetch"
    assert spec.returns == "dict"
