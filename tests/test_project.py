"""Tests for parsed project models and manifests."""

import tomllib
from pathlib import Path

import pytest

from stooge.exceptions import StoogeParseError, StoogeRunError
from stooge.project import Project, load_project


class TestProjectFromPath:
    """Tests for creating project structures from source files."""

    def test_from_path_returns_complete_project(self, example_project):
        """Parse task paths and direct dependencies from the example."""
        project = Project.from_path(example_project)
        assert set(project.tasks) == {"a010", "a020", "a030"}
        assert project.tasks["a020"].dependencies == ("a010",)
        assert project.tasks["a030"].dependencies == ("a020",)

    def test_rejects_duplicate_task_ids(self, workflow_project):
        """Reject two scripts that share a canonical task ID."""
        (workflow_project / "a010_other.py").write_text(
            "from local import a010_clean\nx = a010_clean\n"
        )
        with pytest.raises(StoogeParseError, match="Duplicate task ID"):
            Project.from_path(workflow_project)

    def test_rejects_task_without_output(self, workflow_project):
        """Require each discovered task to declare an output."""
        (workflow_project / "a040_bad.py").write_text(
            "from local import raw\nprint(raw)\n"
        )
        with pytest.raises(StoogeParseError, match="does not declare any outputs"):
            Project.from_path(workflow_project)

    def test_accepts_task_name_without_underscore(self, tmp_path):
        """Detect output prefixes for canonical names such as a010.py."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "root = Path(__file__).parent\n"
            "a010_out = root / 'outputs/result.txt'\n"
        )
        (tmp_path / "a010.py").write_text(
            "from local import a010_out\nprint(a010_out)\n"
        )
        project = Project.from_path(tmp_path, backend="python")
        assert project.tasks["a010"].outputs == (Path("outputs/result.txt"),)

    def test_private_helpers_are_not_task_inputs(self, tmp_path):
        """Discover public artifacts derived from a private project base."""
        (tmp_path / "local.py").write_text(
            "from pathlib import Path\n"
            "_base = Path(__file__).parent\n"
            "data_path = _base / Path('data')\n"
            "das_data_path = _base.parent / 'recordings'\n"
            "source_csv_path = _base / 'inputs' / 'sources'\n"
            "a010_output = data_path / 'a010_output.h5'\n"
        )
        (tmp_path / "a010_extract.py").write_text(
            "import local\n"
            "print(local._base, local.das_data_path, local.source_csv_path)\n"
            "print(local.a010_output)\n"
        )
        project = Project.from_path(tmp_path)
        task = project.tasks["a010"]
        assert set(task.inputs) == {
            tmp_path.parent / "recordings",
            Path("inputs/sources"),
        }
        assert task.outputs == (Path("data/a010_output.h5"),)


class TestProjectOverrides:
    """Tests for ephemeral override-aware project models."""

    def test_overridden_project_refuses_manifest_write(self, workflow_project):
        """Keep override runs ephemeral by refusing manifest persistence."""
        overrides = {"out_dir": workflow_project.parent / "elsewhere"}
        project = Project.from_path(workflow_project, overrides=overrides)
        assert project.overrides == overrides
        with pytest.raises(StoogeRunError, match="ephemeral"):
            project.write_toml()

    def test_overridden_outputs_may_leave_project_root(self, workflow_project):
        """Skip the inside-project output rail for overridden runs only."""
        outside = workflow_project.parent / "outside_outputs"
        project = Project.from_path(workflow_project, overrides={"out_dir": outside})
        assert project.tasks["a010"].outputs[0] == outside / "a010_clean.txt"


class TestProjectManifest:
    """Tests for deterministic manifest persistence and refresh."""

    def test_toml_round_trip(self, workflow_project):
        """Write and read the same project task model."""
        project = Project.read_toml(workflow_project)
        assert project.tasks["a030"].dependencies == ("a020",)
        with (workflow_project / ".stooge.toml").open("rb") as file_obj:
            data = tomllib.load(file_obj)
        assert data["schema_version"] == 1
        assert list(data["tasks"]) == ["a010", "a020", "a030"]

    def test_load_refreshes_changed_sources(self, workflow_project):
        """Refresh the manifest after a task source changes."""
        script = workflow_project / "a030_result.py"
        script.write_text(script.read_text() + "\n# changed\n")
        project = load_project(workflow_project)
        assert project.sources_are_current()
        assert (
            Project.read_toml(workflow_project).source_hashes == project.source_hashes
        )
