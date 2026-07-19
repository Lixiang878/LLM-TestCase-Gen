"""llm_testcase_gen — LLM-powered unit test case generator.

A lightweight, dependency-free toolkit that turns function signatures and
docstrings into structured unit-test cases with the help of an LLM, then
de-duplicates them and reports coverage across normal / boundary / exception
dimensions.

The *core* (parser, dedupe, coverage, the mock provider) runs on the Python
standard library alone. Network-backed providers (OpenAI / OpenAI-compatible
endpoints such as Wenxin / Qwen) are imported lazily so the package installs
and tests run fully offline.
"""

from .models import FunctionSpec, ParamInfo, TestCase
from .parser import parse_file, parse_source
from .provider import (
    BaseProvider,
    MockProvider,
    OpenAIProvider,
    get_provider,
)
from .prompt_builder import build_generation_messages
from .generator import generate_cases, parse_llm_output
from .dedupe import dedupe
from .coverage import coverage_report

__version__ = "0.1.0"

__all__ = [
    "FunctionSpec",
    "ParamInfo",
    "TestCase",
    "parse_file",
    "parse_source",
    "BaseProvider",
    "MockProvider",
    "OpenAIProvider",
    "get_provider",
    "build_generation_messages",
    "generate_cases",
    "parse_llm_output",
    "dedupe",
    "coverage_report",
    "__version__",
]
