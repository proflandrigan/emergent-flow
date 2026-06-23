"""
Golden snapshot tests of `cm.validate` diagnostics over the Story 8 fixture
corpus, mirroring Epic 2's golden codegen corpus; regenerate with
`uv run pytest tests/test_validation_golden.py --snapshot-update`. Also note
a parametrized sanity test asserts the expected top-level severity per case.
"""

from __future__ import annotations

import pytest

from colonymind.codegen.validation import validate
from tests.fixtures.validation_corpus import CORPUS

_CASES = [pytest.param(case, id=case.name) for case in CORPUS]


@pytest.mark.parametrize("case", _CASES)
def test_diagnostics_golden(case, snapshot) -> None:
    """Each corpus graph produces stable, snapshotted diagnostics."""
    diagnostics = validate(
        case.graph,
        node_registry=case.node_registry,
        type_registry=case.type_registry,
    )
    assert diagnostics.model_dump(mode="json") == snapshot


@pytest.mark.parametrize("case", _CASES)
def test_expected_severity(case) -> None:
    """The corpus's declared expected_severity matches what validate reports."""
    diagnostics = validate(
        case.graph,
        node_registry=case.node_registry,
        type_registry=case.type_registry,
    )
    if case.expected_severity == "error":
        assert not diagnostics.ok
        assert diagnostics.errors
    elif case.expected_severity == "warning":
        assert diagnostics.ok  # warnings do not flip ok
        assert diagnostics.warnings
    else:  # None -> clean
        assert diagnostics.ok
        assert not diagnostics.diagnostics
