"""Tests that every Stooge feature treats all task ID letters the same."""

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from stooge.cli import app
from stooge.exceptions import StoogeParseError
from stooge.info import info
from stooge.project import Project, load_project
from stooge.remove import remove_task_outputs
from stooge.runner import RunReason, plan_run, run_project

runner = CliRunner()


def _script(task_id: str, inputs: tuple[str, ...]) -> str:
    """Return a task script that concatenates its inputs into its output."""
    names = ", ".join((*inputs, f"{task_id}_out"))
    # Each task appends its ID, so file contents also record the build chain.
    reads = " + ".join((*(f"{name}.read_text()" for name in inputs), f"'{task_id}'"))
    return f"from local import {names}\n{task_id}_out.write_text({reads})\n"


def _make_project(root: Path, tasks: dict[str, tuple[str, ...]]) -> Path:
    """Create a project from a mapping of task ID to consumed local variables."""
    (root / "inputs").mkdir(parents=True)
    (root / "inputs/raw.txt").write_text("raw")
    local_lines = [
        "from pathlib import Path",
        "root = Path(__file__).parent",
        "raw = root / 'inputs/raw.txt'",
        "out_dir = root / 'outputs'",
    ]
    # Every task gets one output whose variable and filename carry its ID.
    for task_id, inputs in tasks.items():
        local_lines.append(f"{task_id}_out = out_dir / '{task_id}_out.txt'")
        (root / f"{task_id}_task.py").write_text(_script(task_id, inputs))
    (root / "local.py").write_text("\n".join(local_lines) + "\n")
    Project.from_path(root, backend="python").write_toml()
    return root


def _run_cli(*args: str) -> dict:
    """Invoke the CLI with JSON output and return the decoded envelope."""
    result = runner.invoke(app, [*args, "--json"])
    return json.loads(result.stdout)


def _touch_future(path: Path) -> None:
    """Move a file's mtime forward so it looks newer than its consumers."""
    stat = path.stat()
    later = stat.st_mtime_ns + 10_000_000_000
    os.utime(path, ns=(later, later))


@pytest.fixture
def b_after_a(tmp_path):
    """Return a project whose b010 task consumes the output of a010."""
    return _make_project(tmp_path / "proj", {"a010": ("raw",), "b010": ("a010_out",)})


class TestDiscovery:
    """Tests for which scripts count as tasks."""

    @pytest.mark.parametrize("task_id", ["a010", "b010", "z999"])
    def test_any_lowercase_letter_is_a_task(self, tmp_path, task_id):
        """Discover tasks for letters across the whole alphabet."""
        root = _make_project(tmp_path / "proj", {task_id: ("raw",)})
        assert set(Project.from_path(root).tasks) == {task_id}

    def test_parse_reports_b_task(self, b_after_a):
        """Report the b task through the parse command."""
        payload = _run_cli("parse", str(b_after_a))
        assert payload["ok"] is True
        assert set(payload["tasks"]) == {"a010", "b010"}

    @pytest.mark.parametrize(
        "name",
        [
            "B010_x.py",
            "b10_x.py",
            "ab010_x.py",
            "b0100_x.py",
            "b010x.py",
            "utils.py",
        ],
    )
    def test_non_task_names_are_ignored(self, b_after_a, name):
        """Leave malformed IDs and helper modules out of the task graph."""
        (b_after_a / name).write_text("print('not a task')\n")
        assert set(Project.from_path(b_after_a).tasks) == {"a010", "b010"}

    def test_duplicate_id_is_rejected(self, b_after_a):
        """Reject two scripts that share one full task ID."""
        (b_after_a / "a010_other.py").write_text(_script("a010", ("raw",)))
        with pytest.raises(StoogeParseError, match="Duplicate task ID: a010"):
            Project.from_path(b_after_a)

    def test_same_number_in_other_series_is_not_duplicate(self, tmp_path):
        """Allow a010 and b010 to coexist because their full IDs differ."""
        root = _make_project(tmp_path / "proj", {"a010": ("raw",), "b010": ("raw",)})
        assert set(Project.from_path(root).tasks) == {"a010", "b010"}


class TestOutputClassification:
    """Tests for assigning artifacts to tasks by ID prefix."""

    def test_name_or_filename_prefix_marks_output(self, b_after_a):
        """Treat both a prefixed variable and a prefixed filename as outputs."""
        local = b_after_a / "local.py"
        # One path matches only by variable name, the other only by filename.
        local.write_text(
            local.read_text()
            + "b010_summary = out_dir / 'summary.txt'\n"
            + "flight_table = out_dir / 'b010_table.txt'\n"
        )
        (b_after_a / "b010_task.py").write_text(
            "from local import a010_out, b010_out, b010_summary, flight_table\n"
            "print(a010_out, b010_out, b010_summary, flight_table)\n"
        )
        task = Project.from_path(b_after_a).tasks["b010"]
        assert task.inputs == (Path("outputs/a010_out.txt"),)
        assert set(task.outputs) == {
            Path("outputs/b010_out.txt"),
            Path("outputs/b010_table.txt"),
            Path("outputs/summary.txt"),
        }


class TestCrossSeriesDependencies:
    """Tests for dependencies and ordering across letter series."""

    def test_b_task_builds_a_dependency_first(self, b_after_a):
        """Build the a producer before the b consumer."""
        report = run_project(b_after_a, "b010")
        assert report.executed == ("a010", "b010")
        output = b_after_a / "outputs/b010_out.txt"
        assert output.read_text() == "rawa010b010"

    def test_b_task_goes_stale_when_a_output_changes(self, b_after_a):
        """Rebuild only the consumer when the upstream output gets newer."""
        run_project(b_after_a, "b010")
        _touch_future(b_after_a / "outputs/a010_out.txt")
        report = run_project(b_after_a, "b010", dry_run=True)
        assert report.planned == ("b010",)
        assert report.reasons["b010"] is RunReason.STALE_INPUT

    def test_a_script_change_rebuilds_b_task(self, b_after_a):
        """Propagate an upstream script change into the other series."""
        run_project(b_after_a, "b010")
        script = b_after_a / "a010_task.py"
        script.write_text(script.read_text() + "# changed\n")
        report = run_project(b_after_a, "b010", dry_run=True)
        assert report.planned == ("a010", "b010")
        assert report.reasons["b010"] is RunReason.UPSTREAM_REBUILT

    def test_a_task_can_consume_b_output(self, tmp_path):
        """Order a lower letter after the higher letter it depends on."""
        root = _make_project(
            tmp_path / "proj", {"a010": ("b010_out",), "b010": ("raw",)}
        )
        assert Project.from_path(root).tasks["a010"].dependencies == ("b010",)
        assert run_project(root, "a010").executed == ("b010", "a010")

    def test_dependencies_can_alternate_between_series(self, tmp_path):
        """Follow a chain that crosses between series more than once."""
        tasks = {
            "a010": ("raw",),
            "b010": ("a010_out",),
            "a020": ("b010_out",),
        }
        root = _make_project(tmp_path / "proj", tasks)
        assert run_project(root, "a020").executed == ("a010", "b010", "a020")

    def test_independent_tasks_run_in_sorted_order(self, tmp_path):
        """Break ties by task ID when dependencies do not decide the order."""
        # Declared out of order so dictionary order cannot produce a false pass.
        tasks = {
            "c010": ("b010_out", "a020_out", "a010_out"),
            "b010": ("raw",),
            "a020": ("raw",),
            "a010": ("raw",),
        }
        root = _make_project(tmp_path / "proj", tasks)
        expected = ("a010", "a020", "b010", "c010")
        assert tuple(Project.from_path(root).execution_order()) == expected
        assert run_project(root, "c010").executed == expected

    def test_cycle_across_series_is_rejected(self, tmp_path):
        """Reject a dependency cycle that spans two series."""
        root = tmp_path / "proj"
        with pytest.raises(StoogeParseError, match="Circular"):
            _make_project(root, {"a010": ("b010_out",), "b010": ("a010_out",)})


class TestCommands:
    """Tests that CLI commands and the manifest handle other series."""

    def test_dry_run_json(self, b_after_a):
        """Plan a b task through the CLI without building anything."""
        payload = _run_cli("run", "b010", str(b_after_a), "--dry-run")
        assert payload["ok"] is True
        assert payload["planned"] == ["a010", "b010"]
        assert not (b_after_a / "outputs").exists()

    def test_run_json(self, b_after_a):
        """Build a b task through the CLI."""
        payload = _run_cli("run", "b010", str(b_after_a))
        assert payload["executed"] == ["a010", "b010"]
        assert (b_after_a / "outputs/b010_out.txt").is_file()

    def test_set_override(self, b_after_a, tmp_path):
        """Redirect b task outputs for one ephemeral run with --set."""
        scratch = tmp_path / "scratch"
        before = (b_after_a / ".stooge.toml").read_text()
        args = ("run", "b010", str(b_after_a), "--set", f"out_dir={scratch}")
        payload = _run_cli(*args)
        assert payload["ephemeral"] is True
        assert (scratch / "b010_out.txt").read_text() == "rawa010b010"
        # Ephemeral runs must leave project state exactly as it was.
        assert not (b_after_a / "outputs").exists()
        assert (b_after_a / ".stooge.toml").read_text() == before

    def test_local_file_override(self, b_after_a, tmp_path):
        """Redirect b task outputs for one ephemeral run with --local-file."""
        scratch = tmp_path / "scratch"
        override = tmp_path / "debug_local.py"
        override.write_text(
            f"from pathlib import Path\nout_dir = Path({str(scratch)!r})\n"
        )
        args = ("run", "b010", str(b_after_a), "--local-file", str(override))
        payload = _run_cli(*args)
        assert payload["executed"] == ["a010", "b010"]
        assert (scratch / "b010_out.txt").is_file()

    def test_remove(self, b_after_a):
        """Remove only the b task's outputs."""
        run_project(b_after_a, "b010")
        removed = remove_task_outputs(b_after_a, "b010")
        assert removed == (Path("outputs/b010_out.txt"),)
        assert (b_after_a / "outputs/a010_out.txt").is_file()
        assert not (b_after_a / "outputs/b010_out.txt").exists()

    def test_remove_json(self, b_after_a):
        """Remove a b task's outputs through the CLI."""
        run_project(b_after_a, "b010")
        payload = _run_cli("remove", "b010", str(b_after_a))
        assert payload["ok"] is True
        assert not (b_after_a / "outputs/b010_out.txt").exists()

    def test_info_json(self, b_after_a):
        """Describe a b task and its cross-series dependency in info output."""
        run_project(b_after_a, "b010")
        payload = _run_cli("info", str(b_after_a))
        assert payload["execution_order"] == ["a010", "b010"]
        task = payload["tasks"]["b010"]
        assert task["dependencies"] == ["a010"]
        assert task["stale"] is False
        assert info(b_after_a)["tasks"]["b010"]["reason"] == "up_to_date"

    def test_manifest_round_trip(self, b_after_a):
        """Persist b tasks and their fingerprints through the manifest."""
        run_project(b_after_a, "b010")
        stored = load_project(b_after_a)
        assert stored.tasks["b010"].dependencies == ("a010",)
        assert set(stored.executed_hashes) == {"a010", "b010"}
        # A second run finds everything current and rebuilds nothing.
        assert run_project(b_after_a, "b010").executed == ()


class TestExistingProjects:
    """Tests that projects using only the a series are unaffected."""

    def test_a_only_manifest_is_stable(self, workflow_project):
        """Keep the manifest byte-identical and rebuild nothing on a repeat run."""
        run_project(workflow_project, "a030")
        manifest = workflow_project / ".stooge.toml"
        before = manifest.read_text()
        assert run_project(workflow_project, "a030").executed == ()
        assert manifest.read_text() == before


class TestRunAll:
    """Tests that --all builds every task across independent series."""

    @pytest.fixture
    def two_branches(self, tmp_path):
        """Return a project with an a branch and a b branch that never meet."""
        # Declared out of order so dictionary order cannot produce a false pass.
        tasks = {"b010": ("raw",), "a020": ("a010_out",), "a010": ("raw",)}
        return _make_project(tmp_path / "proj", tasks)

    def test_plan_without_target_covers_every_task(self, two_branches):
        """Plan every task in execution order when no target is given."""
        plan = plan_run(load_project(two_branches), None)
        assert plan.target is None
        assert plan.task_ids == ("a010", "a020", "b010")

    def test_force_without_target_reruns_every_task(self, two_branches):
        """Treat every task as a target, so force reruns all of them."""
        run_project(two_branches, None)
        plan = plan_run(load_project(two_branches), None, force=True)
        assert plan.task_ids == ("a010", "a020", "b010")
        assert set(plan.reasons.values()) == {RunReason.FORCED}

    def test_run_all_then_noop(self, two_branches):
        """Build both branches once and find them current on the next run."""
        assert run_project(two_branches, None).executed == ("a010", "a020", "b010")
        assert run_project(two_branches, None).executed == ()

    def test_dry_run_json(self, two_branches):
        """Preview the combined plan through the CLI without building."""
        payload = _run_cli("run", "--all", str(two_branches), "--dry-run")
        assert payload["ok"] is True
        assert payload["target"] is None
        assert payload["planned"] == ["a010", "a020", "b010"]
        assert not (two_branches / "outputs").exists()

    def test_run_from_cwd(self, two_branches, monkeypatch):
        """Use the current directory when --all is given no path."""
        monkeypatch.chdir(two_branches)
        first = runner.invoke(app, ["run", "--all"])
        second = runner.invoke(app, ["run", "--all"])
        assert first.exit_code == 0
        assert "b010 (missing_output)" in first.stdout
        assert second.stdout.strip() == "All tasks are up to date"

    def test_task_id_with_all_is_rejected(self, two_branches):
        """Refuse a task ID together with --all instead of guessing intent."""
        result = runner.invoke(app, ["run", "a010", str(two_branches), "--all"])
        assert result.exit_code == 2
        assert "--all takes no task ID" in result.output

    def test_missing_target_is_usage_error(self, two_branches, monkeypatch):
        """Ask for a task ID or --all when neither is given."""
        monkeypatch.chdir(two_branches)
        result = runner.invoke(app, ["run"])
        assert result.exit_code == 2
        assert "give a task ID or --all" in result.output
