"""Constants shared across Stooge modules."""

from pathlib import Path

backends = (
    "uv",
    "python",
)

local_path = "local.py"
toml_path = ".stooge.toml"
_template_path = Path(__file__).parent / "data" / "project_template"
