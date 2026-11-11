"""Tests for run planning and task execution."""

import os
import shutil
import tomllib
from pathlib import Path

import pytest
import tomli_w

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

    def test_runs_task_led_by_another_letter(self, workflow_project):
        """Run a v-prefixed task after the a-prefixed tasks it reads."""
        local = workflow_project / "local.py"
        local.write_text(local.read_text() + "v010_plot = out_dir / 'v010_plot.txt'\n")
        (workflow_project / "v010_plot.py").write_text(
            "from local import a030_result, v010_plot\n"
            "v010_plot.write_text(a030_result.read_text() + '-plot')\n"
        )
        result = run_project(workflow_project, "v010")
        assert result.executed == ("a010", "a020", "a030", "v010")
        plot = workflow_project / "outputs/v010_plot.txt"
        assert plot.read_text() == "raw-clean-calc-result-plot"

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


class TestHelperModules:
    """Tests for staleness from project modules imported by tasks."""

    @pytest.fixture
    def helper_project(self, workflow_project):
        """Make a020 import a project package that imports another helper."""
        package = workflow_project / "helpers"
        package.mkdir()
        (package / "__init__.py").write_text("from .text import SUFFIX\n")
        (package / "text.py").write_text("from constants import SUFFIX\n")
        (workflow_project / "constants.py").write_text("SUFFIX = '-calc'\n")
        (workflow_project / "a020_calc.py").write_text(
            "from local import a010_clean, a020_calc\n"
            "from helpers import SUFFIX\n"
            "a020_calc.write_text(a010_clean.read_text() + SUFFIX)\n"
        )
        run_project(workflow_project, "a030")
        return workflow_project

    @staticmethod
    def _edit_keeping_mtime(path, text):
        """Change file content while preserving its modification time."""
        stat = path.stat()
        path.write_text(text)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    def test_task_records_imported_modules(self, helper_project):
        """List transitively imported project modules on the task."""
        project = Project.read_toml(helper_project)
        assert project.tasks["a020"].modules == (
            Path("constants.py"),
            Path("helpers/__init__.py"),
            Path("helpers/text.py"),
        )
        assert project.tasks["a010"].modules == ()

    def test_helper_edit_rebuilds_importing_task(self, helper_project):
        """Rebuild a task and its consumers after an imported module changes."""
        constants = helper_project / "constants.py"
        self._edit_keeping_mtime(constants, "SUFFIX = '-new'\n")
        report = run_project(helper_project, "a030")
        assert report.executed == ("a020", "a030")
        assert report.reasons["a010"] is RunReason.UP_TO_DATE
        assert report.reasons["a020"] is RunReason.SCRIPT_CHANGED
        result = helper_project / "outputs/a030_result.txt"
        assert result.read_text() == "raw-clean-new-result"
        assert run_project(helper_project, "a030").executed == ()

    def test_helper_mtime_alone_does_not_rebuild(self, helper_project):
        """Ignore helper timestamp changes when its content is unchanged."""
        constants = helper_project / "constants.py"
        stat = constants.stat()
        os.utime(constants, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        assert run_project(helper_project, "a030").executed == ()

    def test_new_helper_import_is_tracked(self, helper_project):
        """Track a module that an edited helper starts importing."""
        (helper_project / "extra.py").write_text("X = 1\n")
        text = helper_project / "helpers/text.py"
        self._edit_keeping_mtime(text, "from constants import SUFFIX\nimport extra\n")
        assert run_project(helper_project, "a030").executed == ("a020", "a030")
        self._edit_keeping_mtime(helper_project / "extra.py", "X = 2\n")
        assert run_project(helper_project, "a030").executed == ("a020", "a030")

    @staticmethod
    def _write_pre_module_manifest(root):
        """Rewrite the manifest as written before modules were recorded."""
        manifest = root / ".stooge.toml"
        data = tomllib.loads(manifest.read_text())
        for task_id, task in data["tasks"].items():
            for module in task.pop("modules"):
                data["source_hashes"].pop(module, None)
            # Older versions recorded the bare script hash for each run.
            data["executed_hashes"][task_id] = data["source_hashes"][task["script"]]
        manifest.write_text(tomli_w.dumps(data))

    def test_pre_module_manifest_stays_up_to_date(self, helper_project):
        """Carry over tasks with unchanged scripts when upgrading a manifest."""
        self._write_pre_module_manifest(helper_project)
        assert not Project.read_toml(helper_project).sources_are_current()
        assert run_project(helper_project, "a030").executed == ()
        # The run recorded module-aware hashes, so helper edits now count.
        assert Project.read_toml(helper_project).modules_tracked
        constants = helper_project / "constants.py"
        self._edit_keeping_mtime(constants, "SUFFIX = '-new'\n")
        assert run_project(helper_project, "a030").executed == ("a020", "a030")

    def test_pre_module_manifest_keeps_script_edits_stale(self, helper_project):
        """Still rebuild an upgraded task whose script itself changed."""
        self._write_pre_module_manifest(helper_project)
        script = helper_project / "a020_calc.py"
        self._edit_keeping_mtime(script, script.read_text() + "# changed\n")
        report = run_project(helper_project, "a030")
        assert report.executed == ("a020", "a030")
        assert report.reasons["a020"] is RunReason.SCRIPT_CHANGED
