"""Tests for DAG utilities."""

import pytest

from stooge.utils.dag import topological_sort


class TestTopologicalSort:
    """Tests for topological sort of DAG task ids."""

    def test_topological_sort_with_dependents_dict(self):
        """Sort tasks when dependencies are {task_id: [dependent_id, ...]}."""
        dependencies = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}

        order = topological_sort(dependencies)

        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_topological_sort_includes_dependents_not_in_keys(self):
        """Include task ids that appear only as dependent values."""
        dependencies = {"a": ["b"]}

        order = topological_sort(dependencies)

        assert set(order) == {"a", "b"}
        assert order.index("a") < order.index("b")

    def test_topological_sort_raises_on_cycle(self):
        """Raise when the dependency graph has a cycle."""
        dependencies = {"a": ["b"], "b": ["a"]}

        with pytest.raises(ValueError, match="Circular dependency detected"):
            _ = topological_sort(dependencies)
