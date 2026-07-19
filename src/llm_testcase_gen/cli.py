"""Command-line interface for llm_testcase_gen."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .coverage import coverage_report, format_report
from .dedupe import dedupe, dedupe_similar
from .generator import generate_cases, parse_llm_output
from .models import TestCase
from .parser import parse_file
from .provider import get_provider
from .runner import run_cases, export_pytest, export_pytest_module, format_run_report


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
    if args.similar:
        all_cases, _removed_sim = dedupe_similar(all_cases, threshold=args.similar)
        print(f"[ok] similarity dedup removed {len(_removed_sim)} near-duplicate(s)")
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
    sim_unique, sim_removed = dedupe_similar(unique, threshold=0.9)
    report = coverage_report(sim_unique)
    print(format_report(report))
    print(f"\n[ok] generated {len(all_cases)}, {len(removed)} exact dup removed, "
          f"{len(sim_removed)} near-dup removed, {len(sim_unique)} unique.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Generate, (optionally) dedupe, execute, and report on real functions."""
    specs = _load_specs(args)
    provider = get_provider(args.provider, model=args.model, base_url=args.base_url)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    all_cases: list[TestCase] = []
    for spec in specs:
        all_cases.extend(
            generate_cases(
                spec, provider, strategies=strategies,
                cases_per_strategy=args.n, temperature=args.temperature,
                max_tokens=args.max_tokens, extra_instructions=args.instructions,
            )
        )
    if args.dedup:
        all_cases, _ = dedupe(all_cases)
    if args.similar:
        all_cases, _sim = dedupe_similar(all_cases, threshold=args.similar)

    # Execute every generated case against the real target function.
    run_results = []
    targets = []
    for spec in specs:
        spec_cases = [c for c in all_cases if c.target == spec.name]
        if not spec_cases:
            continue
        targets.append(spec.name)
        run_results.append((spec, run_cases(spec, spec_cases)))

    total_pass = sum(r.passed for _, r in run_results)
    total_fail = sum(r.failed for _, r in run_results)
    cov = 0.0
    if targets:
        covered = sum(1 for _, r in run_results if r.passed > 0)
        cov = covered / len(targets)

    lines = [
        "=" * 52,
        "  LLM Test-Case Generation — Execution Report",
        "=" * 52,
        f"  Functions     : {len(targets)}",
        f"  Cases         : {len(all_cases)}",
        f"  Passed        : {total_pass}",
        f"  Failed        : {total_fail}",
        f"  Exec coverage : {cov:.0%}",
        "-" * 52,
    ]
    for spec, r in run_results:
        lines.append(f"  [{spec.name}] {r.passed} passed / {r.failed} failed")
        for cr in r.results:
            mark = "PASS" if cr.passed else "FAIL"
            lines.append(f"    [{mark}] {cr.kind}/{cr.case_id}: {cr.detail}")
    lines.append("=" * 52)
    text = "\n".join(lines)
    print(text)

    if args.export:
        items = [
            (spec, [c for c in all_cases if c.target == spec.name])
            for spec in specs
            if any(c.target == spec.name for c in all_cases)
        ]
        if items:
            p = export_pytest_module(items, args.export)
            print(f"[ok] exported pytest ({len(items)} functions) -> {p}")
    if args.out:
        Path(args.out).write_text(
            json.dumps([c.to_dict() for c in all_cases], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[ok] wrote cases -> {args.out}")
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
    g.add_argument(
        "--similar", type=float, default=0.0,
        help="similarity dedup threshold 0-1 (e.g. 0.85); 0 disables",
    )
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

    rn = sub.add_parser(
        "run", help="generate, execute against the real function, and report",
    )
    rn.add_argument("--file", "-f", required=True, help="Python source file")
    rn.add_argument("--function", "-fn", help="restrict to one function name")
    rn.add_argument("--provider", default="mock", help="mock | openai")
    rn.add_argument("--model", default="gpt-4o-mini", help="model name (openai)")
    rn.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    rn.add_argument(
        "--strategies", default="normal,boundary,exception",
        help="comma list: normal,boundary,exception",
    )
    rn.add_argument("--n", type=int, default=3, help="cases per strategy (openai)")
    rn.add_argument("--temperature", type=float, default=0.7)
    rn.add_argument("--max-tokens", type=int, default=1024)
    rn.add_argument("--instructions", default=None, help="extra prompt instructions")
    rn.add_argument("--dedup", action="store_true", help="exact dedup before run")
    rn.add_argument(
        "--similar", type=float, default=0.9,
        help="similarity dedup threshold 0-1; 0 disables",
    )
    rn.add_argument("--export", help="export a runnable pytest module to this path")
    rn.add_argument("--out", "-o", help="output generated cases JSON")
    rn.add_argument("--include-private", action="store_true")
    rn.add_argument("--include-nested", action="store_true")
    rn.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
