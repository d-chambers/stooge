"""Plan and execute Stooge project tasks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from stooge.constants import local_path
from stooge.exceptions import StoogeRunError, StoogeTaskNotFoundError
from stooge.project import Project, TaskSpec, load_project, task_fingerprint
from stooge.utils.parse import parse_local

# Stdlib-only bootstrap: build the ``local`` module from the project's real
# local.py, replace every path variable with the resolved override-aware
# values, then run the task script as __main__. Runs in the task environment,
# which may not have stooge installed.
_OVERRIDE_BOOTSTRAP = """
import json, os, runpy, sys, types
from pathlib import Path

_local_file = os.environ["STOOGE_LOCAL_FILE"]
_module = types.ModuleType("local")
_module.__file__ = _local_file
with open(_local_file) as _file_obj:
    _source = _file_obj.read()
exec(compile(_source, _local_file, "exec"), _module.__dict__)
for _name, _value in json.loads(os.environ["STOOGE_LOCAL_VALUES"]).items():
    setattr(_module, _name, Path(_value))
sys.modules["local"] = _module
_script = sys.argv[1]
sys.argv = sys.argv[1:]
if os.environ.get("STOOGE_DEBUG") == "1":
    import pdb
    _debugger = pdb.Pdb()
    _debugger.rcLines.append("continue")
    _debugger.run("runpy.run_path(_script, run_name='__main__')")
else:
    runpy.run_path(_script, run_name="__main__")
"""


class RunReason(str, Enum):
    """Explain why a task is or is not selected for execution."""

    MISSING_OUTPUT = "missing_output"
    MISSING_INPUT = "missing_input"
    STALE_INPUT = "stale_input"
    SCRIPT_CHANGED = "script_changed"
    DEFINITION_CHANGED = "definition_changed"
    UPSTREAM_REBUILT = "upstream_rebuilt"
    FORCED = "forced"
    UP_TO_DATE = "up_to_date"


@dataclass(frozen=True)
class RunPlan:
    """Describe ordered tasks and reasons for a target closure."""

    target: str
    task_ids: tuple[str, ...]
    reasons: dict[str, RunReason]


@dataclass(frozen=True)
class RunReport:
    """Describe planned and successfully executed tasks."""

    target: str
    planned: tuple[str, ...]
    executed: tuple[str, ...]
    reasons: dict[str, RunReason]
    overrides: dict[str, str] = field(default_factory=dict)


def plan_run(
    project: Project,
    target: str,
    *,
    force: bool = False,
    force_all: bool = False,
    strict_inputs: bool = True,
    check_fingerprints: bool = True,
) -> RunPlan:
    """Return the upstream tasks needed to build a target and their reasons."""
    if target not in project.tasks:
        raise StoogeTaskNotFoundError(f"Unknown task ID: {target}")
    closure = _upstream_closure(project, target)
    order = [task_id for task_id in project.execution_order() if task_id in closure]
    natural_reasons = {
        task_id: task_stale_reason(
            project,
            task_id,
            strict_inputs=strict_inputs,
            check_fingerprints=check_fingerprints,
        )
        for task_id in order
    }

    if force_all:
        scheduled = set(closure)
        reasons = {task_id: RunReason.FORCED for task_id in order}
    else:
        scheduled = {
            task_id for task_id, reason in natural_reasons.items() if reason is not None
        }
        reasons = {
            task_id: reason or RunReason.UP_TO_DATE
            for task_id, reason in natural_reasons.items()
        }
        if force:
            scheduled.add(target)
            reasons[target] = RunReason.FORCED

        # A rebuilt producer makes every consumer on the target path stale.
        for task_id in order:
            task = project.tasks[task_id]
            if any(dependency in scheduled for dependency in task.dependencies):
                if reasons[task_id] in {
                    RunReason.UP_TO_DATE,
                    RunReason.MISSING_INPUT,
                }:
                    reasons[task_id] = RunReason.UPSTREAM_REBUILT
                scheduled.add(task_id)
    selected = tuple(task_id for task_id in order if task_id in scheduled)
    return RunPlan(target=target, task_ids=selected, reasons=reasons)


def run_project(
    path: str | Path,
    target: str,
    *,
    force: bool = False,
    force_all: bool = False,
    debug: bool = False,
    dry_run: bool = False,
    overrides: dict[str, Path] | None = None,
) -> RunReport:
    """Load a project, plan a target, and optionally execute selected tasks."""
    overrides = dict(overrides or {})
    if overrides:
        # Overridden runs are ephemeral: parse fresh and never persist.
        project = Project.from_path(path, overrides=overrides)
    else:
        project = load_project(path, persist=False)
    reported_overrides = {
        name: str(value) for name, value in sorted(project.overrides.items())
    }
    plan = plan_run(
        project,
        target,
        force=force,
        force_all=force_all,
        strict_inputs=not dry_run,
        check_fingerprints=not overrides,
    )
    if dry_run:
        return RunReport(
            target=target,
            planned=plan.task_ids,
            executed=(),
            reasons=plan.reasons,
            overrides=reported_overrides,
        )

    environment = _task_environment(project, debug=debug)
    executed: list[str] = []
    for task_id in plan.task_ids:
        task = project.tasks[task_id]
        for output in task.outputs:
            output_path = output if output.is_absolute() else project.root / output
            output_path.parent.mkdir(parents=True, exist_ok=True)
        command = _task_command(project, task, debug=debug)
        try:
            result = subprocess.run(
                command, cwd=project.root, check=False, env=environment
            )
        except FileNotFoundError as exc:
            raise StoogeRunError(
                f"Cannot execute {project.backend} backend: {command[0]} was not found",
                executed=list(executed),
            ) from exc
        if result.returncode:
            raise StoogeRunError(
                f"Task {task_id} failed with exit code {result.returncode}",
                executed=list(executed),
            )
        executed.append(task_id)
        if overrides:
            continue
        executed_hashes = dict(project.executed_hashes)
        executed_task_hashes = dict(project.executed_task_hashes)
        executed_hashes[task_id] = project.source_hashes[task.script.as_posix()]
        executed_task_hashes[task_id] = task_fingerprint(task)
        project = replace(
            project,
            executed_hashes=executed_hashes,
            executed_task_hashes=executed_task_hashes,
        )
        project.write_toml()
    if not plan.task_ids and not overrides:
        project.write_toml()
    return RunReport(
        target=target,
        planned=plan.task_ids,
        executed=tuple(executed),
        reasons=plan.reasons,
        overrides=reported_overrides,
    )


def task_stale_reason(
    project: Project,
    task_id: str,
    *,
    strict_inputs: bool = True,
    check_fingerprints: bool = True,
) -> RunReason | None:
    """Return why a task is stale, or ``None`` when it is current."""
    task = project.tasks[task_id]
    produced_paths = {
        output
        for project_task in project.tasks.values()
        for output in project_task.outputs
    }
    input_times: list[int] = []
    produced_input_missing = False
    for input_path in task.inputs:
        timestamp = _artifact_time(project.root, input_path, newest=True)
        if timestamp is None:
            if input_path in produced_paths:
                produced_input_missing = True
                continue
            if strict_inputs:
                raise StoogeRunError(
                    f"Task {task.task_id} input does not exist: '{input_path}'"
                )
            return RunReason.MISSING_INPUT
        input_times.append(timestamp)

    output_times: list[int] = []
    for output in task.outputs:
        timestamp = _artifact_time(project.root, output, newest=False)
        if timestamp is None:
            return RunReason.MISSING_OUTPUT
        output_times.append(timestamp)
    if produced_input_missing:
        return RunReason.MISSING_INPUT
    if check_fingerprints:
        script_hash = project.source_hashes[task.script.as_posix()]
        if project.executed_hashes.get(task_id) != script_hash:
            return RunReason.SCRIPT_CHANGED
        if project.executed_task_hashes.get(task_id) != task_fingerprint(task):
            return RunReason.DEFINITION_CHANGED
    if input_times and min(output_times) < max(input_times):
        return RunReason.STALE_INPUT
    return None


def _upstream_closure(project: Project, target: str) -> set[str]:
    """Return a target task and all of its transitive dependencies."""
    output: set[str] = set()
    pending = [target]
    while pending:
        task_id = pending.pop()
        if task_id in output:
            continue
        output.add(task_id)
        pending.extend(project.tasks[task_id].dependencies)
    return output


def _artifact_time(root: Path, artifact: Path, *, newest: bool) -> int | None:
    """Return the newest or oldest timestamp represented by an artifact."""
    path = artifact if artifact.is_absolute() else root / artifact
    if not path.exists():
        return None
    if not path.is_dir():
        return path.stat().st_mtime_ns

    descendants = [child for child in path.rglob("*") if child.is_file()]
    if not descendants:
        return path.stat().st_mtime_ns
    times = [child.stat().st_mtime_ns for child in descendants]
    return max(times) if newest else min(times)


def _task_environment(project: Project, *, debug: bool) -> dict[str, str] | None:
    """Build the subprocess environment carrying resolved override values."""
    if not project.overrides:
        return None
    local_values = parse_local(project.root / local_path, overrides=project.overrides)
    payload = {
        name: str(value if value.is_absolute() else project.root / value)
        for name, value in local_values.items()
    }
    environment = os.environ | {
        "STOOGE_LOCAL_VALUES": json.dumps(payload),
        "STOOGE_LOCAL_FILE": str(project.root / local_path),
    }
    if debug:
        environment["STOOGE_DEBUG"] = "1"
    return environment


def _task_command(project: Project, task: TaskSpec, *, debug: bool) -> list[str]:
    """Build an argument-safe subprocess command for a task."""
    script = task.script.as_posix()
    if project.overrides:
        # The bootstrap injects override-aware local values; debug mode is
        # selected via STOOGE_DEBUG in the environment.
        python_args = ["python", "-c", _OVERRIDE_BOOTSTRAP, script]
    elif debug:
        python_args = ["python", "-m", "pdb", "-c", "continue", script]
    else:
        python_args = ["python", script]
    if project.backend == "uv":
        return ["uv", "run", "--project", str(project.root), *python_args]
    if project.backend == "python":
        return [sys.executable, *python_args[1:]]
    raise StoogeRunError(f"Unsupported backend: {project.backend}")
