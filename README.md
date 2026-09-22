# stooge

Stooge is a small CLI and Python framework for reproducible local research
projects. It discovers dependencies between numbered scripts and runs only the
tasks whose declared outputs are missing or stale.

Stooge requires Python 3.12 or newer. Supported execution backends are
[uv](https://docs.astral.sh/uv/) and the current Python interpreter.

## Project structure

Task scripts use canonical IDs: one lowercase letter and three digits, such as
`a010_clean.py`, `a020_calculate.py`, or `v010_plot.py`. The letter is free to
group related tasks; execution order still comes from dependencies. Paths are declared in `local.py`. A path is an output when
its variable name or filename starts with the current script's task ID; other
referenced paths are inputs.

```text
my_project/
├── inputs/raw.csv
├── local.py
├── a010_clean.py
└── a020_calculate.py
```

Stooge reads `local.py` statically and never executes it. Its deliberately
narrow contract supports top-level path assignments built from:

- `Path("literal")` or `Path(__file__).parent`, including `.parent` chains;
- an earlier path variable joined to string literals with `/`; and
- a simple alias of an earlier path variable.

Keep `local.py` free of side effects and project-module imports. Output parent
directories are created immediately before their producing task runs.

Parsing produces a deterministic `.stooge.toml` containing the backend, source
hashes, artifact paths, and direct task dependencies. Generated projects also
include a short `AGENTS.md` with these conventions.

## Initialize, parse, and inspect

The uv backend is the default and includes a minimal `pyproject.toml`.

```bash
stooge init my_project --backend uv
stooge parse my_project
stooge parse my_project --dry-run
stooge info my_project
stooge info my_project --json
```

Use `--backend python` to run tasks with the interpreter that launched Stooge.
`info` is read-only and can inspect a project before its manifest exists.

Parsing rejects dynamic path expressions, duplicate task IDs, duplicate output
producers, dependency cycles, tasks without outputs, and outputs outside the
project root.

## Plan and run

Commands accept an optional project path, so changing directories is not
required:

```bash
stooge run a030 my_project --dry-run
stooge run a030 my_project
stooge run a030 my_project --json
```

A task is stale when an output is missing, its script content hash changed, or
its newest input is newer than its oldest output. Script mtimes alone do not
trigger work. A `local.py` edit only rebuilds tasks whose parsed definitions
change. When an upstream task runs, affected downstream tasks are rebuilt.

- `--dry-run` reports the ordered plan and a reason for each task without
  writing the manifest or outputs.
- `--force` always reruns the target in addition to stale dependencies.
- `--force-all` reruns the target's entire upstream closure.
- `--debug` executes selected scripts under the standard-library debugger.

### Override local paths for one run

For debugging, `run` can temporarily swap `local.py` path values without editing any project file:

```bash
stooge run a030 my_project --set output_path=/tmp/stooge_debug --dry-run --json
stooge run a030 my_project --set output_path=/tmp/stooge_debug --set input_path=alt_inputs
stooge run a030 my_project --local-file debug_local.py
```

- `--set name=path` is repeatable. Relative paths resolve against the project root. Unknown names fail with the list of available variables.
- `--local-file` points at a python file following the same static contract as `local.py`. Variables matching names in `local.py` become overrides; other variables are helpers and are ignored. `--set` wins on conflicts.
- Derived variables are recomputed: overriding `output_path` also moves every path defined from it (e.g. `a030_result = output_path / "result.png"`), both when planning and inside the executing script.
- Overridden runs are **ephemeral**: the manifest is never written, no execution fingerprints are recorded, and fingerprint-based staleness is skipped (plans rest on missing outputs and mtimes at the overridden locations). A later plain `stooge run` behaves as if the overridden run never happened.
- Overridden outputs may resolve outside the project root (e.g. `/tmp`).
- Works with `--dry-run`, `--json`, and `--debug`.

## Remove outputs

Remove or preview only the outputs declared by one task:

```bash
stooge remove a020 my_project --dry-run
stooge remove a020 my_project
stooge remove a020 my_project --json
```

Downstream results are retained and rebuilt when required by a later run.
Files, symlinks, and output directories are supported. Stooge refuses to
remove the project root or paths outside it.

## JSON output

Every command except `version` accepts `--json`. The envelopes are a stable contract for scripts and agents:

- Success: `{"command": "<name>", "ok": true, ...}` with command-specific fields.
- Failure: `{"command": "<name>", "ok": false, "kind": "<kind>", "error": "<message>"}` written to stdout with exit status 1. `kind` is one of `parse_error`, `task_not_found`, `run_error`, `init_error`, or `error`, so callers can branch without parsing the message.
- When `run` fails partway through a plan, the failure envelope also includes `executed`: the task IDs that completed (and were recorded in the manifest) before the failure.
- `run --dry-run` never fails on a missing raw input; the plan reports it as a `missing_input` reason so a build can always be previewed.
- When `--set`/`--local-file` overrides are active, `run` envelopes include `"overrides": {name: path}` and `"ephemeral": true`.

## Development

```bash
pip install -e '.[test]'
pytest
ruff check .
ruff format --check .
```

Stooge is optional by design: scripts remain directly executable in dependency
order. The supported Python API is listed in `stooge.__all__`.
