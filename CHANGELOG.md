# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-19

### Added
- AST-based function parser (`parser.py`) extracting signatures, parameters
  (annotations + defaults), docstrings, and return types.
- Offline `MockProvider` and network `OpenAIProvider` (OpenAI-compatible).
- Strategy-driven prompt builder: `normal` / `boundary` / `exception`.
- Robust LLM-output JSON parser tolerant of code fences and prose.
- De-duplication by canonical, order-independent input key.
- Coverage report across normal / boundary / exception dimensions.
- CLI (`gen`, `dedupe`, `report`, `demo`) and an offline pytest suite.
