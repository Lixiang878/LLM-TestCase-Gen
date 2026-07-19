"""Source-code parsing: extract callable specifications via the ``ast`` module."""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path
from typing import Iterable

from .models import FunctionSpec, ParamInfo


def _annotation_to_str(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return None


def _default_to_str(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive
        return None


def _build_params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ParamInfo]:
    params: list[ParamInfo] = []
    for arg in fn.args.args:
        params.append(
            ParamInfo(
                name=arg.arg,
                annotation=_annotation_to_str(arg.annotation),
                default=None,
            )
        )
    # Positional-only args
    for arg in getattr(fn.args, "posonlyargs", []):
        params.append(
            ParamInfo(
                name=arg.arg,
                annotation=_annotation_to_str(arg.annotation),
                default=None,
            )
        )
    # *args
    if fn.args.vararg:
        params.append(
            ParamInfo(
                name="*" + fn.args.vararg.arg,
                annotation=_annotation_to_str(fn.args.vararg.annotation),
                default=None,
            )
        )
    # Keyword-only args (with or without defaults)
    kwo = fn.args.kwonlyargs
    kwd = fn.args.kw_defaults
    for arg, default in zip(kwo, kwd):
        params.append(
            ParamInfo(
                name=arg.arg,
                annotation=_annotation_to_str(arg.annotation),
                default=_default_to_str(default),
            )
        )
    # **kwargs
    if fn.args.kwarg:
        params.append(
            ParamInfo(
                name="**" + fn.args.kwarg.arg,
                annotation=_annotation_to_str(fn.args.kwarg.annotation),
                default=None,
            )
        )
    # Positional defaults applied right-to-left
    defaults = list(fn.args.defaults)
    if defaults:
        for p, d in zip(reversed(params), reversed(defaults)):
            if not p.name.startswith(("*", "**")):
                p.default = _default_to_str(d)
    return params


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        return ast.unparse(fn).split("\n", 1)[0].rstrip(":")
    except Exception:  # pragma: no cover - defensive
        return f"def {fn.name}(...)"


def _returns_to_str(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    if fn.returns is None:
        return ""
    return _annotation_to_str(fn.returns) or ""


def _extract_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    file: str,
) -> FunctionSpec:
    docstring = ast.get_docstring(fn) or ""
    try:
        body_src = ast.get_source_segment(source, fn) or ""
    except Exception:  # pragma: no cover - defensive
        body_src = ""
    return FunctionSpec(
        name=fn.name,
        signature=_signature(fn),
        params=_build_params(fn),
        docstring=docstring,
        returns=_returns_to_str(fn),
        source=body_src,
        file=file,
        lineno=fn.lineno,
    )


def _iter_functions(
    tree: ast.AST, source: str, file: str
) -> Iterable[FunctionSpec]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip nested functions to keep the top-level surface clear,
            # unless explicitly wanted. Nested are still reachable via
            # parse_source(all_nested=True).
            yield _extract_function(node, source, file)


def parse_source(
    source: str,
    file: str = "<string>",
    *,  # noqa: D401 - simple signature
    include_private: bool = False,
    include_nested: bool = False,
) -> list[FunctionSpec]:
    """Parse Python *source* text and return callable specifications."""
    tree = ast.parse(source)
    specs: list[FunctionSpec] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not include_nested and _has_enclosing_function(fn, tree):
            continue
        if not include_private and fn.name.startswith("_"):
            continue
        specs.append(_extract_function(fn, source, file))
    return specs


def _has_enclosing_function(node: ast.AST, tree: ast.AST) -> bool:
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if candidate is node:
                continue
            for child in ast.walk(candidate):
                if child is node:
                    return True
    return False


def parse_file(
    path: str | Path,
    *,
    include_private: bool = False,
    include_nested: bool = False,
) -> list[FunctionSpec]:
    """Parse a Python *path* and return top-level callable specifications."""
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    return parse_source(
        source,
        file=str(p),
        include_private=include_private,
        include_nested=include_nested,
    )


def detect_encoding(path: str | Path) -> str:
    """Best-effort encoding detection (PEP 263 cookie, else utf-8)."""
    try:
        with open(path, "rb") as fh:
            with tokenize.open(path) as _:  # validates PEP263 cookie
                pass
    except Exception:  # pragma: no cover - defensive
        pass
    with open(path, "rb") as fh:
        raw = fh.read(io.DEFAULT_BUFFER_SIZE)
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        return encoding
    except Exception:  # pragma: no cover - defensive
        return "utf-8"
