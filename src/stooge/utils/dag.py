"""
Utilities for working with the DAG
"""

import heapq
from collections.abc import Iterable


def topological_sort(nodes: dict[str, dict[str, Iterable[str]]]) -> list[str]:
    """
    Return tasks in topological order based on input/output artifacts.

    Parameters
    ----------
    nodes
        Dictionary mapping ``task_id`` to metadata with ``inputs`` and
        ``outputs`` iterables, e.g.
        ``{"a001": {"inputs": {"x"}, "outputs": {"y"}}}``.

    Returns
    -------
    List[str]
        Task IDs in execution order.

    Notes
    -----
    - (Kahn's algorithm)[https://en.wikipedia.org/wiki/Topological_sorting]

    Raises
    ------
    ValueError
        If circular dependency is detected in the task graph.
    """
    all_task_ids = set(nodes)
    normalized: dict[str, dict[str, set[str]]] = {}
    for task_id, metadata in nodes.items():
        # Normalize inputs/outputs to sets to simplify edge construction.
        normalized[task_id] = {
            "inputs": set(metadata.get("inputs", set())),
            "outputs": set(metadata.get("outputs", set())),
        }

    # Build output->producer mapping, then derive upstream->downstream edges.
    producers_by_output: dict[str, set[str]] = {}
    for task_id, metadata in normalized.items():
        for output_name in metadata["outputs"]:
            producers_by_output.setdefault(output_name, set()).add(task_id)

    in_degree = {task_id: 0 for task_id in all_task_ids}
    adjacency: dict[str, set[str]] = {task_id: set() for task_id in all_task_ids}
    for task_id, metadata in normalized.items():
        upstream_ids: set[str] = set()
        for input_name in metadata["inputs"]:
            upstream_ids.update(producers_by_output.get(input_name, set()))
        upstream_ids.discard(task_id)
        in_degree[task_id] = len(upstream_ids)
        for upstream_id in upstream_ids:
            adjacency[upstream_id].add(task_id)

    # Start with tasks that have no dependencies in lexical order.
    queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
    heapq.heapify(queue)
    result = []

    while queue:
        current = heapq.heappop(queue)
        result.append(current)

        # Reduce in-degree for dependent tasks
        for downstream_id in adjacency[current]:
            in_degree[downstream_id] -= 1
            if in_degree[downstream_id] == 0:
                heapq.heappush(queue, downstream_id)

    if len(result) != len(all_task_ids):
        raise ValueError("Circular dependency detected in pipe")

    return result
