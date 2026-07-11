"""
pytest configuration for stooge
"""

import shutil
from pathlib import Path

import pytest

import stooge

# --- Parsing/configuration

test_path = Path(__file__).parent
test_data_path = test_path / "test_data"


def pytest_addoption(parser):
    """Add obsplus' pytest command options."""
    parser.addoption(
        "--integration",
        action="store_true",
        dest="run_integration",
        default=False,
        help="Run integration tests",
    )


def pytest_collection_modifyitems(config, items):
    """Configure obsplus' pytest command line options."""
    marks = {}
    if not config.getoption("--integration"):
        msg = "needs --integration option to run"
        marks["integration"] = pytest.mark.skip(reason=msg)

    for item in items:
        marks_to_apply = set(marks)
        item_marks = set(item.keywords)
        for mark_name in marks_to_apply & item_marks:
            item.add_marker(marks[mark_name])


# --- fixtures


@pytest.fixture(scope="class")
def example_project(tmpdir_factory):
    """Set up a simple stooge project in a temporary directory and return path."""
    example = stooge._template_path.parent / "example_project"
    path = Path(tmpdir_factory.mktemp("simple_proj")) / "example_project"
    shutil.copytree(example, path)
    return stooge.init(path)


@pytest.fixture
def workflow_project(tmp_path):
    """Create a dependency chain using only the Python standard library."""
    root = tmp_path / "workflow"
    (root / "inputs").mkdir(parents=True)
    (root / "outputs").mkdir()
    (root / "inputs" / "raw.txt").write_text("raw")
    (root / "local.py").write_text(
        "from pathlib import Path\n"
        "root = Path(__file__).parent\n"
        "raw = root / 'inputs/raw.txt'\n"
        "out_dir = root / 'outputs'\n"
        "a010_clean = out_dir / 'a010_clean.txt'\n"
        "a020_calc = out_dir / 'a020_calc.txt'\n"
        "a030_result = out_dir / 'a030_result.txt'\n"
    )
    scripts = {
        "a010_clean.py": (
            "from local import raw, a010_clean\n"
            "a010_clean.write_text(raw.read_text() + '-clean')\n"
        ),
        "a020_calc.py": (
            "from local import a010_clean, a020_calc\n"
            "a020_calc.write_text(a010_clean.read_text() + '-calc')\n"
        ),
        "a030_result.py": (
            "from local import a020_calc, a030_result\n"
            "a030_result.write_text(a020_calc.read_text() + '-result')\n"
        ),
    }
    for name, contents in scripts.items():
        (root / name).write_text(contents)

    from stooge.project import Project

    Project.from_path(root, backend="python").write_toml()
    return root
