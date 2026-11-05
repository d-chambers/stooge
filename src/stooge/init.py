"""Create new Stooge projects from the bundled template."""

from pathlib import Path

import jinja2

from stooge.constants import _template_path, backends
from stooge.exceptions import StoogeInitError, StoogeParseError
from stooge.project import _TASK_NAME_RE, Project


def _init_directory(
    template_directory: Path,
    output_directory: Path,
    data: dict,
    *,
    backend: str,
) -> None:
    """Render safe template files without overwriting project files."""
    for path in template_directory.rglob("*"):
        relative_path = path.relative_to(template_directory)
        if path.is_dir() or "__pycache__" in relative_path.parts:
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if relative_path.name == "pyproject.toml" and backend != "uv":
            continue

        new_path = output_directory / relative_path
        if new_path.exists():
            continue
        # The starter task is only for projects that have no tasks yet.
        is_starter = _TASK_NAME_RE.match(new_path.name) is not None
        has_tasks = any(
            _TASK_NAME_RE.match(script.name) for script in output_directory.glob("*.py")
        )
        if is_starter and has_tasks:
            continue
        template = jinja2.Template(path.read_text())
        new_path.parent.mkdir(exist_ok=True, parents=True)
        new_path.write_text(template.render(data))


def init(
    path: str | Path | None = None,
    *,
    backend: str = "uv",
) -> Path:
    """Initialize a project directory and its canonical manifest."""
    if backend not in backends:
        choices = ", ".join(backends)
        raise StoogeInitError(f"Unsupported backend '{backend}'; choose from {choices}")
    out_path = (Path(path) if path is not None else Path.cwd()).resolve()
    out_path.mkdir(exist_ok=True, parents=True)
    data = {"project_name": out_path.name, "backend": backend}
    _init_directory(_template_path, out_path, data, backend=backend)

    try:
        Project.from_path(out_path, backend=backend).write_toml()
    except StoogeParseError:
        # Existing user files remain untouched even if they are not parseable yet.
        Project(
            root=out_path,
            backend=backend,
            tasks={},
            source_hashes={},
        ).write_toml()
    return out_path
