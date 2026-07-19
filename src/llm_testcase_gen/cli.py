"""Command-line interface for llm_testcase_gen."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .coverage import coverage_report, format_report
from .dedupe import dedupe
from .generator import generate_cases, parse_llm_output
from .models import TestCase
from .parser import parse_file
from .provider import get_provider


def _load_specs(args: argparse.Namespace) -> list:
    specs = parse_file(
        args.file,
        include_private=args.include_private,
        include_nested=args.include_nested,
    )
    if args.function:
        specs = [s for s in specs if s.name == args.function]
        if not specs:
            sys.exit(f"[error] function {args.function!r} not found in {args.file}")
    if not specs:
        sys.exit(f"[error] no functions found in {args.file}")
    return specs


def cmd_gen(args: argparse.Namespace) -> int:
    provider = get_provider(args.provider, model=args.model, base_url=args.base_url)
    specs = _load_specs(args)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    all_cases: list[TestCase] = []
    for spec in specs:
        cases = generate_cases(
            spec,
            provider,
            strategies=strategies,
            cases_per_strategy=args.n,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            extra_instructions=args.instructions,
        )
        all_cases.extend(cases)
    if args.dedup:
        all_cases, _removed = dedupe(all_cases)
    if args.out:
        Path(args.out).write_text(
            json.dumps([c.to_dict() for c in all_cases], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[ok] wrote {len(all_cases)} cases -> {args.out}")
    else:
        print(json.dumps([c.to_dict() for c in all_cases], ensure_ascii=False, indent=2))
    return 0


def cmd_dedupe(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.infile).read_text(encoding="utf-8"))
    cases = [TestCase.from_dict(d) for d in data]
    unique, removed = dedupe(cases, keep=args.keep)
    out = Path(args.out)
    out.write_text(
        json.dumps([c.to_dict() for c in unique], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[ok] {len(cases)} -> {len(unique)} unique ({len(removed)} removed) -> {out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.infile).read_text(encoding="utf-8"))
    cases = [TestCase.from_dict(d) for d in data]
    report = coverage_report(cases)
    print(format_report(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """End-to-end offline demo using the mock provider."""
    sample = Path(__file__).resolve().parents[2] / "examples" / "sample_math.py"
    if not sample.exists():
        sys.exit(f"[error] sample not found: {sample}")
    provider = get_provider("mock")
    specs = parse_file(sample)
    specs = [s for s in specs if s.name in ("divide", "clamp", "first", "normalize")] or specs
    all_cases: list[TestCase] = []
    for spec in specs:
        all_cases.extend(
            generate_cases(spec, provider, strategies=["normal", "boundary", "exception"])
        )
    unique, removed = dedupe(all_cases)
    report = coverage_report(unique)
    print(format_report(report))
    print(f"\n[ok] generated {len(all_cases)}, {len(removed)} duplicates removed, "
          f"{len(unique)} unique.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llm-testcase-gen",
        description="Generate unit-test cases for Python functions with an LLM.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gen", help="generate cases for a file/function")
    g.add_argument("--file", "-f", required=True, help="Python source file")
    g.add_argument("--function", "-fn", help="restrict to one function name")
    g.add_argument("--provider", default="mock", help="mock | openai")
    g.add_argument("--model", default="gpt-4o-mini", help="model name (openai)")
    g.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    g.add_argument(
        "--strategies",
        default="normal,boundary,exception",
        help="comma list: normal,boundary,exception",
    )
    g.add_argument("--n", type=int, default=3, help="cases per strategy (openai)")
    g.add_argument("--temperature", type=float, default=0.7)
    g.add_argument("--max-tokens", type=int, default=1024)
    g.add_argument("--instructions", default=None, help="extra prompt instructions")
    g.add_argument("--dedup", action="store_true", help="dedupe before writing")
    g.add_argument("--out", "-o", help="output JSON path")
    g.add_argument("--include-private", action="store_true")
    g.add_argument("--include-nested", action="store_true")
    g.set_defaults(func=cmd_gen)

    d = sub.add_parser("dedupe", help="remove duplicate cases from a JSON file")
    d.add_argument("infile")
    d.add_argument("--out", "-o", required=True)
    d.add_argument("--keep", default="first", choices=["first", "last"])
    d.set_defaults(func=cmd_dedupe)

    r = sub.add_parser("report", help="print coverage report for a JSON file")
    r.add_argument("infile")
    r.add_argument("--json", action="store_true", help="also print JSON report")
    r.set_defaults(func=cmd_report)

    sub.add_parser("demo", help="offline end-to-end demo (mock provider)").set_defaults(
        func=cmd_demo
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
