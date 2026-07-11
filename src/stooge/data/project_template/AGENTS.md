# Stooge project guidance

This is a Stooge research project. Python scripts are pipeline tasks and also
remain directly executable in task-ID order.

- Name task scripts `a010_name.py`, `a020_name.py`, and so on.
- Declare paths statically in `local.py`; allow only `Path` literals,
  `Path(__file__).parent`, aliases, and `/` joins with string literals.
- Keep `local.py` free of side effects and project-module imports.
- An output's variable name or filename starts with its producing task ID.
  Other `local.py` paths referenced by that script are inputs.

Use `stooge parse` to validate, `stooge run <task> --dry-run --json` to inspect
a build plan, `stooge run <task>` to build, `stooge remove <task>` to clear its
outputs, and `stooge info --json` to inspect project state.

To debug a task with alternate paths, override `local.py` values for one run:
`stooge run <task> --set output_path=<scratch-dir> [--set input_path=...]`.
Derived paths follow the override, the run is ephemeral (project state and
manifest are untouched), and `--dry-run --json` previews the plan first.

All commands support `--json` and return `{"ok": true|false, ...}` envelopes
with typed error kinds; see the "JSON output" section of the Stooge README.
