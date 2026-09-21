"""
Utilities for parsing files dependencies.
"""

import ast
from collections.abc import Mapping
from pathlib import Path

from stooge.exceptions import StoogeParseError


def parse_local(
    path: Path, overrides: Mapping[str, Path] | None = None
) -> dict[str, Path]:
    """
    Statically parse path variables from a project's ``local.py`` module.

    Parameters
    ----------
    path
        Either the path to ``local.py`` or the project directory that
        contains ``local.py``.
    overrides
        Optional mapping of variable name to replacement path. Overridden
        names are bound to the replacement value instead of their assigned
        expression, so later variables derived from them follow the override.

    Returns
    -------
    dict[str, Path]
        Mapping of variable name to normalized ``Path`` values. Supported
        expressions are ``Path`` construction, ``.parent``, path joins using
        string literals, and aliases of earlier path variables.

    Raises
    ------
    FileNotFoundError
        If ``local.py`` cannot be found.
    StoogeParseError
        If a path assignment uses an unsupported expression, or an override
        names a variable that ``local.py`` never assigns.
    """
    local_path = Path(path)
    project_path = local_path if local_path.is_dir() else local_path.parent
    if local_path.is_dir():
        local_path = local_path / "local.py"
    if not local_path.exists():
        raise FileNotFoundError(f"Cannot find local.py at '{local_path}'")

    try:
        tree = ast.parse(local_path.read_text(), filename=str(local_path))
    except SyntaxError as exc:
        raise StoogeParseError(f"Cannot parse local.py: {exc}") from exc

    overrides = dict(overrides or {})
    out: dict[str, Path] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if not isinstance(target, ast.Name) or target.id.startswith("_"):
            continue
        if target.id in overrides:
            out[target.id] = _normalize_project_path(
                overrides[target.id], project_path.resolve()
            )
            continue
        try:
            value = _evaluate_path_expression(
                statement.value,
                known_paths=out,
                local_file=local_path.resolve(),
            )
        except StoogeParseError as exc:
            raise StoogeParseError(
                f"Unsupported local.py path expression for '{target.id}' "
                f"on line {statement.lineno}: {exc}"
            ) from exc
        if value is not None:
            out[target.id] = _normalize_project_path(value, project_path.resolve())

    unknown = sorted(set(overrides) - set(out))
    if unknown:
        available = ", ".join(sorted(out))
        raise StoogeParseError(
            f"Unknown local variable(s) {', '.join(unknown)}; available: {available}"
        )
    return out


def parse_script(
    script_path: Path, param_dict: Mapping[str, Path]
) -> dict[str, set[Path]]:
    """
    Parse script usage of ``local`` variables into inputs and outputs.

    Parameters
    ----------
    script_path
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
    dict[str, set[Path]]
        Dictionary with keys ``inputs`` and ``outputs`` containing sets of
        project-relative paths used by the script. Output paths are those whose
        variable name or artifact file name starts with the script prefix
        (for example ``a010``).
    """
    script_path = Path(script_path)
    tree = ast.parse(script_path.read_text())
    local_names = set(param_dict)
    script_prefix = script_path.stem.split("_")[0]

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

    inputs: set[Path] = set()
    outputs: set[Path] = set()
    for var_name in used_names:
        file_path = Path(param_dict[var_name])
        is_output_name = var_name.startswith(script_prefix)
        is_output_path = file_path.name.startswith(script_prefix)
        if is_output_name or is_output_path:
            outputs.add(file_path)
        else:
            inputs.add(file_path)
    return {"inputs": inputs, "outputs": outputs}


def _normalize_project_path(path: Path, project_path: Path) -> Path:
    """Return a path relative to the project when possible."""
    path = Path(path)
    project_path = Path(project_path)
    if not path.is_absolute():
        return path
    try:
        return path.relative_to(project_path)
    except ValueError:
        return path


def _evaluate_path_expression(
    node: ast.expr,
    *,
    known_paths: Mapping[str, Path],
    local_file: Path,
) -> Path | None:
    """Evaluate one supported static path expression, or ignore non-path data."""
    if isinstance(node, ast.Name):
        if node.id in known_paths:
            return known_paths[node.id]
        if node.id == "__file__":
            return local_file
        return None

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id != "Path":
            if _references_path_data(node, known_paths):
                raise StoogeParseError(
                    "function calls other than Path(...) are forbidden"
                )
            return None
        if node.keywords or len(node.args) != 1:
            raise StoogeParseError("Path(...) requires exactly one argument")
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return Path(argument.value)
        if isinstance(argument, ast.Name) and argument.id == "__file__":
            return local_file
        raise StoogeParseError("Path(...) accepts a string literal or __file__")

    if isinstance(node, ast.Attribute) and node.attr == "parent":
        base = _evaluate_path_expression(
            node.value,
            known_paths=known_paths,
            local_file=local_file,
        )
        if base is None:
            if _references_path_data(node, known_paths):
                raise StoogeParseError(
                    ".parent must follow a supported path expression"
                )
            return None
        return base.parent

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        base = _evaluate_path_expression(
            node.left,
            known_paths=known_paths,
            local_file=local_file,
        )
        if base is None:
            if _references_path_data(node, known_paths):
                raise StoogeParseError("path joins must start from a known path")
            return None
        if not isinstance(node.right, ast.Constant) or not isinstance(
            node.right.value, str
        ):
            raise StoogeParseError("path joins require string literals")
        return base / node.right.value

    if _references_path_data(node, known_paths):
        raise StoogeParseError("expression is not part of the static path contract")
    return None


def _references_path_data(node: ast.AST, known_paths: Mapping[str, Path]) -> bool:
    """Return whether an expression appears intended to calculate a path."""
    path_names = set(known_paths) | {"Path", "__file__"}
    return any(
        isinstance(child, ast.Name) and child.id in path_names
        for child in ast.walk(node)
    )


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
