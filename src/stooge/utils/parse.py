"""
Utilities for parsing files dependencies.
"""
import ast
import importlib.util
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Mapping

from stooge.constants import local_path


def _load_module_from_path(path: Path) -> ModuleType:
    """Load and return a module object from a python file path."""
    spec = importlib.util.spec_from_file_location("local", str(path))
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load module from '{path}'")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_local(path: Path) -> dict[str, Path]:
    """
    Parse path variables from a project's ``local.py`` module.

    Parameters
    ----------
    path
        Either the path to ``local.py`` or the project directory that
        contains ``local.py``.

    Returns
    -------
    dict[str, Path]
        Mapping of variable name to ``Path`` value for top-level variables
        in ``local.py`` that are ``Path`` instances.

    Raises
    ------
    FileNotFoundError
        If ``local.py`` cannot be found.
    ValueError
        If a ``local.py`` module cannot be loaded from the given path.
    """
    local_path = Path(path)
    if local_path.is_dir():
        local_path = local_path / "local.py"
    if not local_path.exists():
        raise FileNotFoundError(f"Cannot find local.py at '{local_path}'")

    local_module = _load_module_from_path(local_path)
    out: dict[str, Path] = {}
    for name in dir(local_module):
        if name.startswith("_"):
            continue
        value = getattr(local_module, name)
        if isinstance(value, Path):
            out[name] = value
    return out


def parse_script(path: Path, param_dict: Mapping[str, Path]) -> dict[str, set[str]]:
    """
    Parse script usage of ``local`` variables into inputs and outputs.

    Parameters
    ----------
    path
        Path to the script file to parse.
    param_dict
        Mapping of ``local`` variable name to path, typically from
        :func:`parse_local`.

    Notes
    -----
    ``param_dict`` is of the form ``{variable_name: path}``.
    Local variables are detected for these import styles:
    - ``import local`` / ``import local as x``
    - ``from local import var_name`` (with alias support)
    - ``from local import *`` (best-effort static detection)
    - variables that share the same ID (or the path shares the same id)
      as the script are considered outputs. Otherwise, they are inputs.

    Returns
    -------
    dict[str, set[str]]
        Dictionary with keys ``inputs`` and ``outputs`` containing sets of
        variable names used by the script. Output variables are those whose
        variable name or artifact file name starts with the script prefix
        (for example ``a010``).
    """
    script_path = Path(path)
    tree = ast.parse(script_path.read_text())
    local_names = set(param_dict)
    script_prefix = script_path.name.split("_")[0]

    module_aliases, direct_imports, has_star_import = _collect_local_imports(tree)
    bound_names = _collect_bound_names(tree)
    used_names = _collect_local_usages(
        tree=tree,
        local_names=local_names,
        module_aliases=module_aliases,
        direct_imports=direct_imports,
        has_star_import=has_star_import,
        bound_names=bound_names,
    )

    inputs: set[str] = set()
    outputs: set[str] = set()
    for name in used_names:
        file_name = Path(param_dict[name]).name
        is_output_name = name.startswith(script_prefix)
        is_output_path = file_name.startswith(script_prefix)
        if is_output_name or is_output_path:
            outputs.add(name)
        else:
            inputs.add(name)
    return {"inputs": inputs, "outputs": outputs}


def _collect_local_imports(
    tree: ast.AST,
) -> tuple[set[str], dict[str, str], bool]:
    """Collect local module aliases, direct imports, and wildcard imports."""
    module_aliases: set[str] = set()
    direct_imports: dict[str, str] = {}
    has_star_import = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "local":
                    module_aliases.add(alias.asname or "local")
        elif isinstance(node, ast.ImportFrom) and node.module == "local":
            for alias in node.names:
                if alias.name == "*":
                    has_star_import = True
                else:
                    direct_imports[alias.asname or alias.name] = alias.name
    return module_aliases, direct_imports, has_star_import


def _collect_bound_names(tree: ast.AST) -> set[str]:
    """Collect names that are locally bound in the script."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            out.add(node.id)
    return out


def _collect_local_usages(
    tree: ast.AST,
    local_names: set[str],
    module_aliases: set[str],
    direct_imports: dict[str, str],
    has_star_import: bool,
    bound_names: set[str],
) -> set[str]:
    """Collect local variable names used in script."""
    used_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in module_aliases and node.attr in local_names:
                used_names.add(node.attr)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in direct_imports:
                if direct_imports[node.id] in local_names:
                    used_names.add(direct_imports[node.id])
            elif (
                has_star_import
                and node.id in local_names
                and node.id not in bound_names
            ):
                used_names.add(node.id)
    return used_names


def build_dependency_graph(
    project_path: Path,
) -> dict[str, list[str]]:
    """
    Build a script dependency graph for a project.

    Parameters
    ----------
    project_path
        Path to the project directory.

    Returns
    -------
    dict[str, list[str]]
        Mapping of ``{task_id: [dependent_task_id, ...]}`` where each key is
        a script id and each value lists downstream scripts that depend on it.
    """
    project_path = Path(project_path)
    local_vars = parse_local(project_path / local_path)

    # Collect parsed local-variable usage for each task script.
    script_vars: dict[str, dict[str, set[str]]] = {}
    for script_path in sorted(project_path.glob("*.py")):
        task_id = _get_task_id(script_path)
        if task_id is None:
            continue
        script_vars[task_id] = parse_script(script_path, local_vars)

    # Map output variable name -> producing task id.
    producers: dict[str, set[str]] = defaultdict(set)
    for task_id, var_map in script_vars.items():
        for output_var in var_map["outputs"]:
            producers[output_var].add(task_id)

    # Build adjacency: upstream task -> dependent downstream tasks.
    dependencies: dict[str, set[str]] = {task_id: set() for task_id in script_vars}
    for task_id, var_map in script_vars.items():
        upstream_ids = {
            producer_id
            for input_var in var_map["inputs"]
            for producer_id in producers.get(input_var, set())
            if producer_id != task_id
        }
        for upstream_id in upstream_ids:
            dependencies[upstream_id].add(task_id)

    return {task_id: sorted(dependents) for task_id, dependents in dependencies.items()}


def _get_task_id(script_path: Path) -> str | None:
    """Return task id from script name if it matches the task pattern."""
    stem = script_path.stem
    if len(stem) < 4:
        return None
    if not stem[0].isalpha() or not stem[1:4].isdigit():
        return None
    return stem.split("_")[0]
