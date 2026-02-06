# Python Coding Guideline

Version: 2026-01-23

## Scope
This guideline applies to all Python code in this repository.

## Mandatory rules
- Keep diffs minimal; do not refactor unless asked.
- Respect feature-first boundaries; avoid importing across features.
- Ensure core does not depend on infra/adapters.
- Use absolute imports only (no relative imports).
- Add and maintain type hints for public APIs.
- Add and maintain docstrings for public APIs.
- Use an error taxonomy and translate exceptions.
- Do not leak raw exceptions across public boundaries.
- Avoid heavy imports or runtime work at module import time.
- Keep code formatted and lint-clean (ruff).

## Recommended practices
- Keep functions small and pure where practical; make side effects explicit.
- Inject time via a clock and use timezone-aware datetimes.
- Set explicit timeouts for any I/O (network, file, subprocess).

## Testing
- Do not perform network calls in unit tests.
