"""Tests for safe removal of declared task outputs."""

import os
from pathlib import Path

import pytest

from stooge.remove import remove_task_outputs
from stooge.runner import run_project


class TestRemoveTaskOutputs:
    """Tests for exact and dry-run output removal."""

    def test_removes_only_selected_task(self, workflow_project):
        """Keep upstream and downstream outputs when removing one task."""
        run_project(workflow_project, "a030")
        removed = remove_task_outputs(workflow_project, "a020")
        assert removed == (Path("outputs/a020_calc.txt"),)
        assert (workflow_project / "outputs/a010_clean.txt").exists()
        assert not (workflow_project / "outputs/a020_calc.txt").exists()
        assert (workflow_project / "outputs/a030_result.txt").exists()

    def test_dry_run_does_not_remove_output(self, workflow_project):
        """Report a declared output without modifying the filesystem."""
        run_project(workflow_project, "a030")
        removed = remove_task_outputs(workflow_project, "a030", dry_run=True)
        assert len(removed) == 1
        assert (workflow_project / "outputs/a030_result.txt").exists()

    def test_dry_run_does_not_refresh_stale_manifest(self, workflow_project):
        """Keep the manifest byte-identical while previewing removal."""
        manifest = workflow_project / ".stooge.toml"
        before = manifest.read_bytes()
        script = workflow_project / "a030_result.py"
        script.write_text(script.read_text() + "\n# changed\n")
        remove_task_outputs(workflow_project, "a030", dry_run=True)
        assert manifest.read_bytes() == before

    def test_remove_then_run_rebuilds_dependents(self, workflow_project):
        """Rebuild a removed intermediate and its target consumer."""
        run_project(workflow_project, "a030")
        remove_task_outputs(workflow_project, "a020")
        report = run_project(workflow_project, "a030")
        assert report.executed == ("a020", "a030")

    @pytest.mark.skipif(os.name == "nt", reason="Symlink privileges vary on Windows")
    def test_unlinks_output_symlink_without_following_it(
        self, workflow_project, tmp_path
    ):
        """Remove a declared symlink while preserving its external target."""
        external = tmp_path / "external.txt"
        external.write_text("keep")
        output = workflow_project / "outputs/a020_calc.txt"
        output.symlink_to(external)
        removed = remove_task_outputs(workflow_project, "a020")
        assert removed == (Path("outputs/a020_calc.txt"),)
        assert not output.exists()
        assert external.read_text() == "keep"
