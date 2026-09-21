"""Typer command-line interface for Stooge projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from stooge.exceptions import StoogeError
from stooge.info import info as info_project
from stooge.init import init as init_project
from stooge.overrides import resolve_overrides
from stooge.project import Project, reparse_project
from stooge.remove import remove_task_outputs
from stooge.runner import run_project
from stooge.version import __version__

app = typer.Typer(help="Reproducible research project workflows.")


def _fail(exc: StoogeError, command: str, *, as_json: bool = False) -> None:
    """Render a domain error in the selected output format and exit."""
    if as_json:
        envelope = {
            "command": command,
            "ok": False,
            "kind": exc.kind,
            "error": str(exc),
            **exc.payload,
        }
        typer.echo(json.dumps(envelope))
    else:
        typer.echo(str(exc), err=True)
        executed = exc.payload.get("executed")
        if executed:
            typer.echo(f"Executed before failure: {', '.join(executed)}", err=True)
    raise typer.Exit(code=1)


def _json_success(command: str, payload: dict) -> None:
    """Emit one consistent success envelope for machine consumers."""
    typer.echo(json.dumps({"command": command, "ok": True, **payload}))


def _project_tasks(project: Project) -> dict[str, dict]:
    """Serialize parsed task definitions for CLI output."""
    return {
        task_id: {
            "script": task.script.as_posix(),
            "inputs": [item.as_posix() for item in task.inputs],
            "outputs": [item.as_posix() for item in task.outputs],
            "dependencies": list(task.dependencies),
        }
        for task_id, task in sorted(project.tasks.items())
    }


@app.command("init")
def init(
    path: Annotated[Path | None, typer.Argument()] = None,
    backend: Annotated[str, typer.Option("--backend")] = "uv",
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Create or initialize a Stooge project directory."""
    try:
        project_path = init_project(path, backend=backend)
    except StoogeError as exc:
        _fail(exc, "init", as_json=as_json)
    if as_json:
        _json_success("init", {"path": str(project_path), "backend": backend})
        return
    typer.echo(str(project_path))


@app.command("info")
def info(
    path: Annotated[Path | None, typer.Argument()] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Inspect project tasks, state, and execution order."""
    try:
        data = info_project(path)
    except StoogeError as exc:
        _fail(exc, "info", as_json=as_json)
    if as_json:
        _json_success("info", data)
        return
    typer.echo(f"Backend: {data['backend']}")
    typer.echo(f"Manifest current: {data['manifest_current']}")
    for task_id, task in data["tasks"].items():
        typer.echo(f"{task_id}: {task['reason']}")


@app.command("parse")
def parse(
    path: Annotated[Path | None, typer.Argument()] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Validate without writing.")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Parse and validate project tasks and dependencies."""
    project_path = path if path is not None else Path.cwd()
    try:
        project = reparse_project(project_path, persist=not dry_run)
    except StoogeError as exc:
        _fail(exc, "parse", as_json=as_json)
    if as_json:
        _json_success(
            "parse",
            {
                "dry_run": dry_run,
                "tasks": _project_tasks(project),
                "execution_order": project.execution_order(),
            },
        )
        return
    typer.echo(f"Parsed {len(project.tasks)} task(s): {', '.join(project.tasks)}")


@app.command("run")
def run(
    task_id: Annotated[str, typer.Argument()],
    path: Annotated[Path | None, typer.Argument()] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    force_all: Annotated[bool, typer.Option("--force-all")] = False,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    set_: Annotated[
        list[str] | None,
        typer.Option(
            "--set",
            metavar="NAME=PATH",
            help=(
                "Temporarily override a local.py path for this run; repeatable. "
                "The run is ephemeral: the manifest is never read as "
                "authoritative or written. Relative paths resolve against the "
                "project root. Overrides --local-file values."
            ),
        ),
    ] = None,
    local_file: Annotated[
        Path | None,
        typer.Option(
            "--local-file",
            help=(
                "Python file of static path assignments overriding matching "
                "local.py variables for this ephemeral run; non-matching "
                "variables are helpers and are ignored."
            ),
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Run or preview stale tasks needed to build a target task."""
    project_path = path if path is not None else Path.cwd()
    try:
        overrides = resolve_overrides(project_path, set_, local_file)
        report = run_project(
            project_path,
            task_id,
            force=force,
            force_all=force_all,
            debug=debug,
            dry_run=dry_run,
            overrides=overrides,
        )
    except StoogeError as exc:
        _fail(exc, "run", as_json=as_json)
    plan = [
        {
            "task_id": planned_id,
            "reason": reason.value,
            "scheduled": planned_id in report.planned,
        }
        for planned_id, reason in report.reasons.items()
    ]
    if as_json:
        payload = {
            "target": report.target,
            "dry_run": dry_run,
            "plan": plan,
            "planned": list(report.planned),
            "executed": list(report.executed),
        }
        if report.overrides:
            payload["overrides"] = report.overrides
            payload["ephemeral"] = True
        _json_success("run", payload)
        return
    if report.overrides:
        rendered = ", ".join(
            f"{name}={value}" for name, value in report.overrides.items()
        )
        typer.echo(f"Overrides (ephemeral): {rendered}")
    if not report.planned:
        typer.echo(f"{task_id} is up to date")
        return
    verb = "Would execute" if dry_run else "Executed"
    selected = ", ".join(
        f"{planned_id} ({report.reasons[planned_id].value})"
        for planned_id in report.planned
    )
    typer.echo(f"{verb}: {selected}")


@app.command("remove")
def remove(
    task_id: Annotated[str, typer.Argument()],
    path: Annotated[Path | None, typer.Argument()] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Remove or preview the declared outputs for one task."""
    project_path = path if path is not None else Path.cwd()
    try:
        removed = remove_task_outputs(project_path, task_id, dry_run=dry_run)
    except StoogeError as exc:
        _fail(exc, "remove", as_json=as_json)
    if as_json:
        _json_success(
            "remove",
            {
                "task_id": task_id,
                "dry_run": dry_run,
                "removed": [item.as_posix() for item in removed],
            },
        )
        return
    action = "Would remove" if dry_run else "Removed"
    typer.echo(f"{action} {len(removed)} output(s)")


@app.command("version")
def version():
    """Print the installed Stooge version."""
    typer.echo(__version__)


def main():
    """Run the command-line application."""
    app()


if __name__ == "__main__":
    main()
