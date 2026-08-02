"""
Epic 17 DoD — dogfood gate: zero validity findings on bundled example graphs.

The experiment-validity rule pack must not be a source of noise on the project's
own pipelines: every bundled example graph (examples/**/*.json) must produce
zero validity findings. Where a demo genuinely trips a rule, the demo is fixed
rather than suppressed. This test fails when a bundled example starts tripping a
rule, forcing the author to either fix the demo or consciously change the pack.

Non-graph files (http fixtures, catalog snapshots) are skipped.
"""

from __future__ import annotations

import pathlib

import pytest

from emergentflow import validate

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_EXAMPLES_DIR = _REPO_ROOT / "examples"


def _example_graph_paths() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for path in sorted(_EXAMPLES_DIR.rglob("*.json")):
        if "http_fixtures" in path.parts:
            continue  # raw HTTP response fixtures, not graphs
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if '"nodes"' not in text or '"edges"' not in text:
            continue  # not a graph-shaped file
        paths.append(path)
    return paths


@pytest.mark.parametrize(
    "path",
    _example_graph_paths(),
    ids=lambda p: str(p.relative_to(_REPO_ROOT)),
)
def test_example_graph_has_zero_validity_findings(path: pathlib.Path) -> None:
    """The rule pack finds nothing on this bundled example graph."""
    from emergentflow.ir.serialize import deserialize_graph

    graph = deserialize_graph(path.read_text(encoding="utf-8"))
    result = validate(graph)
    validity = [d for d in result.diagnostics if d.rule_id is not None]
    assert not validity, (
        f"bundled example {path.relative_to(_REPO_ROOT)} trips "
        f"{len(validity)} validity rule(s): "
        + "; ".join(f"{d.rule_id} on {d.node_id}" for d in validity)
    )
