"""Tests for run planning and task execution."""

import os
import shutil

import pytest

from stooge.exceptions import StoogeRunError, StoogeTaskNotFoundError
from stooge.project import Project
from stooge.runner import RunReason, plan_run, run_project


class TestPlanRun:
    """Tests for stale-task selection and propagation."""

    def test_missing_outputs_select_upstream_chain(self, workflow_project):
        """Build all tasks when every generated output is missing."""
        project = Project.read_toml(workflow_project)
        plan = plan_run(project, "a030")
        assert plan.task_ids == ("a010", "a020", "a030")
        assert plan.reasons["a010"] is RunReason.MISSING_OUTPUT

    def test_force_selects_only_fresh_target(self, workflow_project):
        """Force reruns a fresh target without rerunning fresh upstream tasks."""
        run_project(workflow_project, "a030")
        project = Project.read_toml(workflow_project)
        assert plan_run(project, "a030", force=True).task_ids == ("a030",)

    def test_force_all_selects_entire_closure(self, workflow_project):
        """Force-all selects every upstream task regardless of freshness."""
        run_project(workflow_project, "a030")
        project = Project.read_toml(workflow_project)
        assert plan_run(project, "a030", force_all=True).task_ids == (
            "a010",
            "a020",
            "a030",
        )

    def test_force_all_still_validates_raw_inputs(self, workflow_project):
        """Do not defer missing raw input failures to a subprocess."""
        (workflow_project / "inputs/raw.txt").unlink()
        project = Project.read_toml(workflow_project)
        with pytest.raises(StoogeRunError, match="input does not exist"):
            plan_run(project, "a030", force_all=True)

    def test_scheduled_upstream_propagates_to_target(self, workflow_project):
        """Rebuild downstream tasks when an intermediate output is removed."""
        run_project(workflow_project, "a030")
        (workflow_project / "outputs/a020_calc.txt").unlink()
        project = Project.read_toml(workflow_project)
        plan = plan_run(project, "a030")
        assert plan.task_ids == ("a020", "a030")
        assert plan.reasons["a030"] is RunReason.UPSTREAM_REBUILT

    def test_unknown_target_raises(self, workflow_project):
        """Return a domain error for an unknown task ID."""
        project = Project.read_toml(workflow_project)
        with pytest.raises(StoogeTaskNotFoundError, match="Unknown task ID"):
            plan_run(project, "a999")


class TestRunProject:
    """Tests for executing planned tasks."""

    def test_run_then_noop(self, workflow_project):
        """Execute a chain once and report it fresh on the next run."""
        first = run_project(workflow_project, "a030")
        second = run_project(workflow_project, "a030")
        assert first.executed == ("a010", "a020", "a030")
        assert second.executed == ()
        result = workflow_project / "outputs/a030_result.txt"
        assert result.read_text() == "raw-clean-calc-result"

    def test_newer_input_rebuilds_chain(self, workflow_project):
        """Rebuild all affected tasks after an external input changes."""
        run_project(workflow_project, "a030")
        raw = workflow_project / "inputs/raw.txt"
        raw.write_text("new")
        stat = raw.stat()
        os.utime(raw, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        report = run_project(workflow_project, "a030")
        assert report.executed == ("a010", "a020", "a030")

    def test_missing_external_input_raises(self, workflow_project):
        """Fail before execution when a required raw input is missing."""
        (workflow_project / "inputs/raw.txt").unlink()
        with pytest.raises(StoogeRunError, match="input does not exist"):
            run_project(workflow_project, "a030")

    def test_dry_run_is_read_only(self, workflow_project):
        """Return a reasoned plan without writing outputs or the manifest."""
        manifest = workflow_project / ".stooge.toml"
        before = manifest.read_bytes()
        report = run_project(workflow_project, "a030", dry_run=True)
        assert report.planned == ("a010", "a020", "a030")
        assert report.executed == ()
        assert report.reasons["a010"] is RunReason.MISSING_OUTPUT
        assert manifest.read_bytes() == before
        assert not (workflow_project / "outputs/a030_result.txt").exists()

    def test_script_content_hash_marks_task_stale(self, workflow_project):
        """Detect script edits even when its mtime is deliberately preserved."""
        run_project(workflow_project, "a030")
        script = workflow_project / "a030_result.py"
        stat = script.stat()
        script.write_text(script.read_text() + "\n# content changed\n")
        os.utime(script, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        report = run_project(workflow_project, "a030")
        assert report.executed == ("a030",)
        assert report.reasons["a030"] is RunReason.SCRIPT_CHANGED

    def test_failed_script_remains_stale(self, workflow_project):
        """Do not mark changed source successful when its execution fails."""
        run_project(workflow_project, "a030")
        script = workflow_project / "a030_result.py"
        script.write_text(
            "from local import a030_result\n"
            "print(a030_result)\n"
            "raise RuntimeError('broken')\n"
        )
        with pytest.raises(StoogeRunError, match="Task a030 failed"):
            run_project(workflow_project, "a030")
        preview = run_project(workflow_project, "a030", dry_run=True)
        assert preview.planned == ("a030",)
        assert preview.reasons["a030"] is RunReason.SCRIPT_CHANGED

    def test_script_mtime_alone_does_not_mark_task_stale(self, workflow_project):
        """Ignore script timestamp changes when its content hash is unchanged."""
        run_project(workflow_project, "a030")
        script = workflow_project / "a030_result.py"
        stat = script.stat()
        os.utime(script, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        assert run_project(workflow_project, "a030").executed == ()

    def test_local_comment_does_not_rebuild_tasks(self, workflow_project):
        """Do not rebuild tasks when local.py reparses to identical definitions."""
        run_project(workflow_project, "a030")
        local = workflow_project / "local.py"
        local.write_text(local.read_text() + "\n# documentation only\n")
        assert run_project(workflow_project, "a030").executed == ()

    def test_runner_creates_output_parents(self, workflow_project):
        """Create declared output parents only when a task is executed."""
        shutil.rmtree(workflow_project / "outputs")
        report = run_project(workflow_project, "a030")
        assert report.executed == ("a010", "a020", "a030")
        assert (workflow_project / "outputs/a030_result.txt").is_file()
