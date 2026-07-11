"""Read, validate, and persist Stooge project structure."""

from __future__ import annotations

import hashlib
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

from stooge.constants import backends, local_path, toml_path
from stooge.exceptions import StoogeParseError, StoogeRunError
from stooge.utils.dag import topological_sort
from stooge.utils.parse import parse_local, parse_script
from stooge.version import __version__


_TASK_NAME_RE = re.compile(r"^(a\d{3})(?:_.+)?\.py$")
_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TaskSpec:
    """Describe one reproducible project task."""

    task_id: str
    script: Path
    inputs: tuple[Path, ...]
    outputs: tuple[Path, ...]
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Project:
    """Represent a parsed Stooge project and its task graph."""

    root: Path
    backend: str
    tasks: dict[str, TaskSpec]
    source_hashes: dict[str, str]
    executed_hashes: dict[str, str] = field(default_factory=dict)
    executed_task_hashes: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, Path] = field(default_factory=dict)
    schema_version: int = _SCHEMA_VERSION
    stooge_version: str = __version__

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        backend: str | None = None,
        overrides: dict[str, Path] | None = None,
    ) -> Project:
        """Parse project sources into a validated project model."""
        root = Path(path).resolve()
        _validate_project_root(root)
        selected_backend = backend or _read_backend(root) or "uv"
        if selected_backend not in backends:
            raise StoogeParseError(f"Unsupported backend: {selected_backend}")

        overrides = dict(overrides or {})
        scripts = _discover_scripts(root)
        try:
            local_vars = parse_local(root / local_path, overrides=overrides)
            parsed_tasks: dict[str, TaskSpec] = {}
            for task_id, script in scripts.items():
                artifacts = parse_script(script, local_vars)
                inputs = tuple(sorted(artifacts["inputs"], key=str))
                outputs = tuple(sorted(artifacts["outputs"], key=str))
                if not outputs:
                    raise StoogeParseError(
                        f"Task {task_id} does not declare any outputs"
                    )
                # Ephemeral overridden runs may direct outputs anywhere.
                if not overrides:
                    _validate_outputs(root, task_id, outputs)
                parsed_tasks[task_id] = TaskSpec(
                    task_id=task_id,
                    script=script.relative_to(root),
                    inputs=inputs,
                    outputs=outputs,
                )
        except (OSError, SyntaxError, ValueError) as exc:
            if isinstance(exc, StoogeParseError):
                raise
            raise StoogeParseError(f"Cannot parse project: {exc}") from exc

        tasks = _add_dependencies(parsed_tasks)
        _validate_graph(tasks)
        hashes = _calculate_source_hashes(root, scripts.values())
        return cls(
            root=root,
            backend=selected_backend,
            tasks=tasks,
            source_hashes=hashes,
            overrides=overrides,
        )

    @classmethod
    def read_toml(cls, path: str | Path) -> Project:
        """Read a project model from its canonical TOML manifest."""
        root = Path(path).resolve()
        manifest_path = root / toml_path
        if not manifest_path.is_file():
            raise StoogeParseError(f"Cannot find {toml_path} at '{root}'")
        try:
            with manifest_path.open("rb") as file_obj:
                data = tomllib.load(file_obj)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise StoogeParseError(f"Cannot read {toml_path}: {exc}") from exc
        if data.get("schema_version") != _SCHEMA_VERSION:
            raise StoogeParseError("Unsupported .stooge.toml schema version")

        try:
            backend = data["backend"]
            version = data["stooge_version"]
            if backend not in backends:
                raise KeyError(f"unsupported backend '{backend}'")
            tasks: dict[str, TaskSpec] = {}
            for task_id, item in data.get("tasks", {}).items():
                tasks[task_id] = TaskSpec(
                    task_id=task_id,
                    script=Path(item["script"]),
                    inputs=tuple(Path(value) for value in item.get("inputs", [])),
                    outputs=tuple(Path(value) for value in item.get("outputs", [])),
                    dependencies=tuple(item.get("dependencies", [])),
                )
        except (KeyError, TypeError) as exc:
            raise StoogeParseError(f"Invalid {toml_path} manifest: {exc}") from exc
        return cls(
            root=root,
            backend=backend,
            tasks=tasks,
            source_hashes=dict(data.get("source_hashes", {})),
            executed_hashes=dict(data.get("executed_hashes", {})),
            executed_task_hashes=dict(data.get("executed_task_hashes", {})),
            schema_version=data["schema_version"],
            stooge_version=version,
        )

    def write_toml(self) -> Path:
        """Atomically write the canonical project manifest."""
        if self.overrides:
            raise StoogeRunError(
                "Refusing to write the manifest for an overridden project; "
                "override runs are ephemeral"
            )
        manifest_path = self.root / toml_path
        temporary_path = manifest_path.with_suffix(".toml.tmp")
        data = {
            "schema_version": self.schema_version,
            "stooge_version": self.stooge_version,
            "backend": self.backend,
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "executed_hashes": dict(sorted(self.executed_hashes.items())),
            "executed_task_hashes": dict(sorted(self.executed_task_hashes.items())),
            "tasks": {
                task_id: {
                    "script": task.script.as_posix(),
                    "inputs": [path.as_posix() for path in task.inputs],
                    "outputs": [path.as_posix() for path in task.outputs],
                    "dependencies": list(task.dependencies),
                }
                for task_id, task in sorted(self.tasks.items())
            },
        }
        temporary_path.write_text(tomli_w.dumps(data))
        temporary_path.replace(manifest_path)
        return manifest_path

    def sources_are_current(self) -> bool:
        """Return whether stored hashes match current project sources."""
        try:
            scripts = _discover_scripts(self.root)
            hashes = _calculate_source_hashes(self.root, scripts.values())
        except (FileNotFoundError, StoogeParseError):
            return False
        return hashes == self.source_hashes

    def execution_order(self) -> list[str]:
        """Return all task IDs in deterministic topological order."""
        nodes = {
            task_id: {"inputs": task.inputs, "outputs": task.outputs}
            for task_id, task in self.tasks.items()
        }
        return topological_sort(nodes)


def load_project(path: str | Path, *, persist: bool = True) -> Project:
    """Load a current manifest, reparsing changed sources when needed."""
    root = Path(path).resolve()
    try:
        stored = Project.read_toml(root)
    except StoogeParseError:
        stored = None
    if stored is not None and stored.sources_are_current():
        return stored

    project = reparse_project(root, previous=stored, persist=False)
    if persist:
        project.write_toml()
    return project


def reparse_project(
    path: str | Path,
    *,
    previous: Project | None = None,
    persist: bool = True,
) -> Project:
    """Parse sources while retaining last-successful execution fingerprints."""
    root = Path(path).resolve()
    if previous is None:
        try:
            previous = Project.read_toml(root)
        except StoogeParseError:
            previous = None
    backend = previous.backend if previous is not None else None
    parsed = Project.from_path(root, backend=backend)
    if previous is not None:
        parsed = replace(
            parsed,
            executed_hashes={
                task_id: value
                for task_id, value in previous.executed_hashes.items()
                if task_id in parsed.tasks
            },
            executed_task_hashes={
                task_id: value
                for task_id, value in previous.executed_task_hashes.items()
                if task_id in parsed.tasks
            },
        )
    if persist:
        parsed.write_toml()
    return parsed


def task_fingerprint(task: TaskSpec) -> str:
    """Return a deterministic hash of a task's parsed artifact definition."""
    values = [
        task.task_id,
        task.script.as_posix(),
        *(path.as_posix() for path in task.inputs),
        "--outputs--",
        *(path.as_posix() for path in task.outputs),
        "--dependencies--",
        *task.dependencies,
    ]
    return hashlib.sha256("\0".join(values).encode()).hexdigest()


def _validate_project_root(root: Path) -> None:
    """Raise a parse error when required project inputs are absent."""
    if not root.is_dir():
        raise StoogeParseError(f"Project directory does not exist: '{root}'")
    if not (root / local_path).is_file():
        raise StoogeParseError(f"Cannot find {local_path} at '{root}'")


def _discover_scripts(root: Path) -> dict[str, Path]:
    """Discover canonical task scripts and reject duplicate task IDs."""
    scripts: dict[str, Path] = {}
    for script in sorted(root.glob("*.py")):
        match = _TASK_NAME_RE.match(script.name)
        if match is None:
            continue
        task_id = match.group(1)
        if task_id in scripts:
            raise StoogeParseError(f"Duplicate task ID: {task_id}")
        scripts[task_id] = script
    if not scripts:
        raise StoogeParseError(f"No task scripts found at '{root}'")
    return scripts


def _validate_outputs(root: Path, task_id: str, outputs: tuple[Path, ...]) -> None:
    """Ensure task outputs remain safely inside the project root."""
    resolved_root = root.resolve()
    for output in outputs:
        resolved = (
            output.resolve() if output.is_absolute() else (root / output).resolve()
        )
        if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
            raise StoogeParseError(
                f"Task {task_id} output must be inside the project: '{output}'"
            )


def _add_dependencies(tasks: dict[str, TaskSpec]) -> dict[str, TaskSpec]:
    """Derive direct upstream task IDs from shared artifact paths."""
    producers: dict[Path, str] = {}
    for task_id, task in tasks.items():
        for output in task.outputs:
            if output in producers:
                other = producers[output]
                raise StoogeParseError(
                    f"Output '{output}' is produced by both {other} and {task_id}"
                )
            producers[output] = task_id

    output: dict[str, TaskSpec] = {}
    for task_id, task in tasks.items():
        dependencies = {
            producers[input_path]
            for input_path in task.inputs
            if input_path in producers and producers[input_path] != task_id
        }
        output[task_id] = replace(task, dependencies=tuple(sorted(dependencies)))
    return output


def _validate_graph(tasks: dict[str, TaskSpec]) -> None:
    """Validate that the artifact dependency graph is acyclic."""
    nodes = {
        task_id: {"inputs": task.inputs, "outputs": task.outputs}
        for task_id, task in tasks.items()
    }
    try:
        topological_sort(nodes)
    except ValueError as exc:
        raise StoogeParseError(str(exc)) from exc


def _calculate_source_hashes(root: Path, scripts) -> dict[str, str]:
    """Calculate deterministic hashes for local.py and all task scripts."""
    paths = [root / local_path, *sorted(scripts)]
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def _read_backend(root: Path) -> str | None:
    """Read only the configured backend from an existing manifest."""
    manifest_path = root / toml_path
    if not manifest_path.is_file():
        return None
    try:
        with manifest_path.open("rb") as file_obj:
            return tomllib.load(file_obj).get("backend")
    except (OSError, tomllib.TOMLDecodeError):
        return None
