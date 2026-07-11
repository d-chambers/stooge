"""Safely remove declared Stooge task outputs."""

from __future__ import annotations

import shutil
from pathlib import Path

from stooge.exceptions import StoogeRunError, StoogeTaskNotFoundError
from stooge.project import load_project


def remove_task_outputs(
    path: str | Path, task_id: str, *, dry_run: bool = False
) -> tuple[Path, ...]:
    """Remove only the declared outputs belonging to one task."""
    project = load_project(path, persist=not dry_run)
    if task_id not in project.tasks:
        raise StoogeTaskNotFoundError(f"Unknown task ID: {task_id}")

    removed: list[Path] = []
    root = project.root.resolve()
    for output in project.tasks[task_id].outputs:
        candidate = output if output.is_absolute() else root / output
        # Validate a symlink's location without following its external target.
        if candidate.is_symlink():
            safe = candidate.parent.resolve().is_relative_to(root)
        else:
            resolved = candidate.resolve()
            safe = resolved != root and resolved.is_relative_to(root)
        if not safe:
            raise StoogeRunError(f"Refusing to remove unsafe output: '{output}'")
        if not candidate.exists() and not candidate.is_symlink():
            continue
        removed.append(output)
        if dry_run:
            continue
        if candidate.is_symlink() or candidate.is_file():
            candidate.unlink()
        elif candidate.is_dir():
            shutil.rmtree(candidate)
    return tuple(removed)
