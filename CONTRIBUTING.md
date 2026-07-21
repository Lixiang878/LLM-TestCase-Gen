# Contributing

Thanks for your interest in improving `llm-testcase-gen`. Contributions of all
kinds are welcome: bug reports, documentation, new providers, and prompt
improvements.

## Development setup

```bash
git clone https://github.com/Lixiang878/LLM-TestCase-Gen.git
cd LLM-TestCase-Gen
pip install -e ".[dev]"
pytest -q
```

## Guidelines

- The **core** must stay dependency-free (Python standard library only).
  Network-backed providers are isolated and import lazily.
- Add/extend `tests/` for any behavioral change; the suite runs fully offline.
- Keep prompts in `prompt_builder.py` configurable and strategy-scoped.
- Format with `ruff format` (or `black`) and lint with `ruff` before opening a PR.
- Open an issue first for large changes so we can agree on the design.

## Commit messages

Use short, imperative summaries, e.g. `fix: handle async generators in parser`.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
