"""Return user-facing information about a Stooge project."""

from pathlib import Path

from stooge.constants import toml_path
from stooge.exceptions import StoogeParseError
from stooge.project import Project, load_project
from stooge.runner import task_stale_reason


def info(project_path: str | Path | None = None) -> dict:
    """Return detailed, JSON-serializable project and task information."""
    path = (Path(project_path) if project_path is not None else Path.cwd()).resolve()
    manifest_exists = (path / toml_path).is_file()
    manifest_current = False
    if manifest_exists:
        try:
            manifest_current = Project.read_toml(path).sources_are_current()
        except StoogeParseError:
            manifest_current = False

    project = load_project(path, persist=False)
    tasks = {}
    for task_id, task in sorted(project.tasks.items()):
        reason = task_stale_reason(project, task_id, strict_inputs=False)
        tasks[task_id] = {
            "script": task.script.as_posix(),
            "inputs": [item.as_posix() for item in task.inputs],
            "outputs": [item.as_posix() for item in task.outputs],
            "dependencies": list(task.dependencies),
            "stale": reason is not None,
            "reason": reason.value if reason is not None else "up_to_date",
        }
    return {
        "stooge_version": project.stooge_version,
        "schema_version": project.schema_version,
        "backend": project.backend,
        "tasks": tasks,
        "execution_order": project.execution_order(),
        "manifest_exists": manifest_exists,
        "manifest_current": manifest_current,
    }
