# API Implementation and Test Plan

This document outlines a concrete plan to implement and test the README-defined API:
- `stooge init <project_name> --backend ...`
- `stooge run <task_id> [--force] [--force-all]`
- `stooge remove <task_id>`
- `stooge parse [path]`

## 1. Current State (Code Audit)

- Implemented now:
  - `stooge init [path]` in `src/stooge/cli.py` (basic project scaffold only).
  - `stooge info [path]`.
  - `stooge version`.
- Partially available internals:
  - Script discovery and local artifact parsing in `src/stooge/utils.py`.
  - Metadata read/write in `src/stooge/core/meta.py` (`.stooge/metadata.toml` with `spf_version`).
- Missing or stubbed:
  - `parse` CLI command and parser implementation (`src/stooge/parse/project.py` is stubbed).
  - `run` and `remove` command implementation.
  - Any persistent DAG/task cache for incremental execution.
  - Any command tests for `run/remove/parse`.

## 2. API Contract Decisions (Before Coding)

- Canonical task ID format: `aNNN` (for example `a030`).
- Canonical config file: `local.py`.
- `run <task_id>` semantics:
  - Execute tasks needed to produce target outputs.
  - By default, execute only stale or missing tasks.
  - `--force`: run target task even if fresh.
  - `--force-all`: run all upstream tasks for target regardless of freshness.
- `remove <task_id>` semantics:
  - Remove outputs produced by the specified task ID only.
  - Do not remove unrelated or downstream outputs.
- `parse [path]` semantics:
  - Build and persist task graph + metadata for diagnostics and faster future runs.

## 3. Data Model and Metadata Plan

- Extend `.stooge/metadata.toml` to include:
  - `spf_version`
  - `project_root`
  - `generated_at`
  - `[tasks.<task_id>]`
  - `script_path`
  - `file_inputs` (list)
  - `file_outputs` (list)
  - `script_mtime`
  - `output_mtimes` (map: output path -> mtime or null if missing)
- Add typed helpers in `src/stooge/core/meta.py`:
  - `read_metadata(path) -> dict`
  - `write_metadata(path, data: dict | None = None)`
  - `update_task_metadata(path, task_map)`

## 4. Parse Implementation Plan

- Create parser module in `src/stooge/parse/project.py`:
  - `parse_project(path) -> dict[task_id, task_spec]`
  - Use `get_python_scripts` and `get_project_task_list` from `utils.py`.
  - Validate naming and uniqueness:
    - Script names begin with `aNNN`.
    - No duplicate task IDs.
    - Each task has at least one output.
  - Add deterministic sort order by task ID.
- Add CLI command in `src/stooge/cli.py`:
  - `stooge parse [path]`
  - Print summary: task count, IDs, and warning/error count.
  - Persist parsed graph into metadata.

## 5. Run Implementation Plan

- Add runner module `src/stooge/core/run.py`:
  - `plan_run(path, target_id, force=False, force_all=False) -> list[task_id]`
  - `execute_plan(path, task_ids) -> run_report`
- Build dependency graph from parsed inputs/outputs:
  - Edge A -> B when an output of A is used as input of B.
- Determine stale state per task:
  - Any output missing => stale.
  - Any input newer than output => stale.
  - Script newer than output => stale.
- Build execution set:
  - Upstream closure for target task.
  - Filter by stale unless force modes override.
- Execute tasks:
  - Run scripts in project root as subprocess (`python <script_path>`).
  - Stop on first failure and return non-zero CLI exit.
- Add CLI command:
  - `stooge run <task_id> [--force] [--force-all]`
  - Output execution plan before running.

## 6. Remove Implementation Plan

- Add module `src/stooge/core/remove.py`:
  - `remove_task_outputs(path, task_id) -> removed_paths`
- Resolve outputs from parsed metadata/task map.
- Delete files only (not directories) unless empty-dir cleanup is explicitly requested later.
- Add CLI command:
  - `stooge remove <task_id>`
  - Show removed files and count.
  - Return clean error if task ID is unknown.

## 7. Error Handling and UX Plan

- Add/extend exceptions in `src/stooge/exceptions.py`:
  - `SPFTaskNotFoundError`
  - `SPFParseError`
  - `SPFRunError`
- CLI behavior:
  - User-facing short errors via Typer.
  - Non-zero exits on parse/run/remove failures.
  - Actionable hints (for example: run `stooge parse`).

## 8. Testing Plan

### Unit tests

- `tests/test_parse_project.py`
  - Parses known example project and returns expected IDs.
  - Fails on invalid script naming.
  - Fails on duplicate IDs.
- New `tests/test_run.py`
  - Staleness detection for missing output.
  - Staleness detection for input newer than output.
  - `--force` and `--force-all` planning behavior.
- New `tests/test_remove.py`
  - Removes only outputs for specified task.
  - Unknown task returns expected error.
- Expand `tests/test_meta.py` (new)
  - Metadata contains parsed task graph and timestamps.
  - Metadata round-trip is stable.

### CLI tests

- Expand `tests/test_cli.py`:
  - `parse` command success and output text.
  - `run` happy path on `spf_example`.
  - `run` failure propagation when script errors.
  - `remove` removes expected files.
  - Invalid task IDs return non-zero.

### Integration tests

- Add marker `integration` tests using temp project:
  - Full flow: `init -> parse -> run a030 -> remove a020 -> run a030`.
  - Assert rebuilt artifacts after remove.

## 9. Implementation Order

1. Implement parser (`parse_project`) and tests.
2. Extend metadata format and persistence; add tests.
3. Implement `stooge parse` command.
4. Implement run planning logic + unit tests.
5. Implement task execution + CLI `run` tests.
6. Implement remove logic + CLI tests.
7. Final pass for error messages and docs alignment.

## 10. Acceptance Criteria

- README-documented commands exist and are wired in CLI help.
- `stooge parse` generates persistent metadata with task graph.
- `stooge run a030` correctly executes only needed tasks by freshness rules.
- `--force` and `--force-all` behave as documented.
- `stooge remove a020` removes only `a020` outputs.
- Test suite includes coverage for parse/run/remove behavior and passes locally.
