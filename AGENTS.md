# AGENTS.md

This file defines practical guidance for coding agents working in this repository.

## Project Purpose
- `stooge` is a small Python CLI/framework for reproducible research project scaffolding.
- Primary entrypoint is the `stooge` CLI (`stooge.cli:app`, Typer-based).

## Important Repository Structure
- `src/stooge/`: package source code.
- `tests/`: pytest test suite.
- `docs/`: Sphinx docs.
- `pyproject.toml`: primary packaging/dependency metadata.

## Working Rules
- Prefer minimal, targeted edits over broad refactors.
- Keep Python compatibility at `>=3.12`.
- Preserve CLI behavior unless explicitly asked to change it.
- Do not remove or silently bypass tests.

## Dev Setup and Validation
- Install editable package with test extras:
  - `pip install -e '.[test]'`
- Run tests:
  - `pytest`
- Run focused tests while iterating:
  - `pytest tests/test_init.py -q`
- If pre-commit is installed, run:
  - `pre-commit run -a`

## Code Style and Quality
- Follow existing style (88-char line length, Ruff config in `pyproject.toml`).
- Keep functions small and explicit.
- Always write docstrings. For private functions these can be a single line, for public api use full numpy style docstrings.
- Add/adjust tests for behavior changes.
- Avoid introducing new dependencies unless necessary.
- Tests should always use pytest and be grouped into classes.
- Comments are good. Strive for making a comment in the code anytime it is complicated to aid reliability. Make a comment at least every 8 lines.

## Packaging Notes
- Version is dynamic via setuptools SCM/git versioning in `pyproject.toml`.

## Documentation Expectations
- Update docs and/or README when user-facing CLI behavior changes.
- Prefer concise doc updates aligned with current code behavior.

## Safe Change Checklist
- Code compiles/imports.
- Tests pass locally (or report what could not be run).
- CLI entrypoint still works.
- No unrelated file churn.
