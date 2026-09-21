"""
Tests for getting info from stooge project.
"""

import pytest

import stooge


@pytest.fixture(scope="class")
def example_info(example_project):
    """Return the info dict."""
    info = stooge.info(example_project)
    return info


class TestInfo:
    """Test case for getting stooge project info."""

    def test_info(self, example_info):
        """Get info, test basics."""
        assert isinstance(example_info, dict)
        assert len(example_info)
        assert example_info["stooge_version"] == stooge.__version__
        assert example_info["schema_version"] == 1
        assert list(example_info["tasks"]) == ["a010", "a020", "a030"]
        assert example_info["execution_order"] == ["a010", "a020", "a030"]
        assert example_info["tasks"]["a020"]["dependencies"] == ["a010"]

    def test_info_without_manifest_is_read_only(self, workflow_project):
        """Parse in memory when the manifest is missing without recreating it."""
        manifest = workflow_project / ".stooge.toml"
        manifest.unlink()
        data = stooge.info(workflow_project)
        assert data["manifest_exists"] is False
        assert data["manifest_current"] is False
        assert list(data["tasks"]) == ["a010", "a020", "a030"]
        assert not manifest.exists()

    def test_info_has_no_filesystem_side_effects(self, tmp_path):
        """Static inspection creates neither outputs nor a manifest."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "a010_out = root / 'outputs/result.txt'\n"
        )
        (tmp_path / "a010_task.py").write_text(
            "from local import a010_out\nprint(a010_out)\n"
        )
        data = stooge.info(tmp_path)
        assert data["tasks"]["a010"]["reason"] == "missing_output"
        assert not (tmp_path / "outputs").exists()
        assert not (tmp_path / ".stooge.toml").exists()
