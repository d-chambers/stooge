"""Resolve ephemeral local.py overrides for a single run."""

from __future__ import annotations

from pathlib import Path

from stooge.constants import local_path
from stooge.exceptions import StoogeParseError
from stooge.utils.parse import parse_local


def resolve_overrides(
    root: str | Path,
    sets: list[str] | None = None,
    local_file: str | Path | None = None,
) -> dict[str, Path]:
    """
    Combine ``--set`` entries and an override file into one override mapping.

    Parameters
    ----------
    root
        Project directory containing the canonical ``local.py``.
    sets
        ``name=path`` strings. Relative paths resolve against the project
        root; these take precedence over ``local_file`` values.
    local_file
        Optional python file following the static ``local.py`` contract.
        Variables matching names defined in the project's ``local.py``
        become overrides; other variables are treated as helpers and ignored.

    Returns
    -------
    dict[str, Path]
        Mapping of local variable name to replacement path.

    Raises
    ------
    StoogeParseError
        If a ``--set`` entry is malformed or names an unknown variable.
    """
    if not sets and local_file is None:
        return {}
    root = Path(root).resolve()
    try:
        base_names = set(parse_local(root / local_path))
    except FileNotFoundError as exc:
        raise StoogeParseError(str(exc)) from exc

    overrides: dict[str, Path] = {}
    if local_file is not None:
        file_path = Path(local_file)
        if not file_path.is_file():
            raise StoogeParseError(f"Cannot find override file: '{file_path}'")
        file_root = file_path.resolve().parent
        file_vars = parse_local(file_path)
        for name, value in file_vars.items():
            if name in base_names:
                overrides[name] = value if value.is_absolute() else file_root / value

    for entry in sets or []:
        name, separator, value = entry.partition("=")
        if not separator or not name or not value:
            raise StoogeParseError(
                f"Invalid --set entry '{entry}'; expected the form name=path"
            )
        overrides[name] = Path(value)

    available = ", ".join(sorted(base_names))
    for name, value in overrides.items():
        if name not in base_names:
            raise StoogeParseError(
                f"Unknown local variable '{name}'; available: {available}"
            )
        if not value.is_absolute():
            overrides[name] = root / value
    return overrides
