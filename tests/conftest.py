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
def spf_example_project(tmpdir_factory):
    """Set up a simple stooge project in a temporary directory and return path."""
    spf_example = stooge._template_path.parent / "spf_example"
    path = Path(tmpdir_factory.mktemp("simple_proj")) / "spf_example"
    shutil.copytree(spf_example, path)
    return stooge.init(path)
