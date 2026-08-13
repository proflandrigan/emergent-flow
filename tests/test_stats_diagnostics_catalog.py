"""
Golden + equivalence tests for the Epic 12 Story 6 diagnostic catalog (VIF/normality/
heteroscedasticity/autocorrelation) and its two node types (``DiagnosticFrame``,
``DiagnosticModel``).

Mirrors ``tests/test_stats_regression_catalog.py``'s two-part shape, applied to both node
types. Diagnostic keys are pulled dynamically from the live registry (safe here -- unlike the
fit_model archetype, no later task in this epic's scope adds more diagnostics).
"""

from __future__ import annotations

import ast
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import (
    DiagnosticFrame,
    DiagnosticModel,
    FitLinearRegression,
    LoadSample,
)
from emergentflow.stats import diagnostic, fit_model
from emergentflow.stats.diagnostics import get_diagnostic_spec, known_diagnostic_keys
from emergentflow.stats.errors import InvalidModelSpecError

_FRAME_DIAGNOSTIC_KEYS = [k for k in known_diagnostic_keys() if get_diagnostic_spec(k).needs_frame]
_MODEL_DIAGNOSTIC_KEYS = [k for k in known_diagnostic_keys() if get_diagnostic_spec(k).needs_model]


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


def _run_codegen(definition, node, scope):
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 -- test-only, on our own emitted code
    return scope


def _regression_df(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 100
    x1 = rng.normal(size=n)
    x2 = rng.normal(size=n)
    y = 2 * x1 + 3 * x2 + rng.normal(scale=0.5, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "y": y})


# ---------------------------------------------------------------------------
# 1. Golden-code quality: one representative graph per node type.
# ---------------------------------------------------------------------------


def _build_load_diagnostic_frame_graph() -> Graph:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    diag = DiagnosticFrame().instantiate(
        diagnostic="vif", spec_extra={"columns": ["age", "bmi"]}, label="VIF"
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=diag.id, port_id=_in_port(diag, "frame").id),
    )
    return Graph(nodes={load.id: load, diag.id: diag}, edges={edge.id: edge})


def _build_load_fit_diagnostic_model_graph() -> Graph:
    load = LoadSample().instantiate(name="diabetes", label="Load Sample")
    fit = FitLinearRegression().instantiate(
        estimator="OLS", target="target", fixed_effects=["age", "bmi"], label="Fit OLS"
    )
    diag = DiagnosticModel().instantiate(diagnostic="normality", label="Normality")
    load_to_fit = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=fit.id, port_id=_in_port(fit, "frame").id),
    )
    fit_to_diag = Edge(
        source=PortRef(node_id=fit.id, port_id=_out_port(fit, "model").id),
        target=PortRef(node_id=diag.id, port_id=_in_port(diag, "model").id),
    )
    return Graph(
        nodes={load.id: load, fit.id: fit, diag.id: diag},
        edges={load_to_fit.id: load_to_fit, fit_to_diag.id: fit_to_diag},
    )


@pytest.mark.parametrize(
    "builder",
    [_build_load_diagnostic_frame_graph, _build_load_fit_diagnostic_model_graph],
    ids=["diagnostic_frame", "diagnostic_model"],
)
def test_diagnostics_codegen_is_parseable(builder) -> None:
    code = compile_to_code(builder())
    ast.parse(code)


@pytest.mark.parametrize(
    "builder",
    [_build_load_diagnostic_frame_graph, _build_load_fit_diagnostic_model_graph],
    ids=["diagnostic_frame", "diagnostic_model"],
)
def test_diagnostics_codegen_is_ruff_clean(builder) -> None:
    code = compile_to_code(builder())
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 2. ADR-0002 equivalence: every registered diagnostic key.
# ---------------------------------------------------------------------------


@pytest.mark.equivalence
@pytest.mark.parametrize("diagnostic_key", _FRAME_DIAGNOSTIC_KEYS)
def test_diagnostic_frame_equivalence_matrix(diagnostic_key: str) -> None:
    df = _regression_df()
    defn = DiagnosticFrame()
    node = defn.instantiate(diagnostic=diagnostic_key, spec_extra={"columns": ["x1", "x2"]})
    executed = defn.execute(node, inputs={"frame": df.copy()})["diagnostics"]
    scope = _run_codegen(defn, node, {"frame": df.copy()})
    pd.testing.assert_frame_equal(executed, scope["diagnostics"])


@pytest.mark.equivalence
@pytest.mark.parametrize("diagnostic_key", _MODEL_DIAGNOSTIC_KEYS)
def test_diagnostic_model_equivalence_matrix(diagnostic_key: str) -> None:
    df = _regression_df()
    fit_defn = FitLinearRegression()
    fit_node = fit_defn.instantiate(estimator="OLS", target="y", fixed_effects=["x1", "x2"])
    fitted_model = fit_defn.execute(fit_node, inputs={"frame": df.copy()})["model"]

    defn = DiagnosticModel()
    node = defn.instantiate(diagnostic=diagnostic_key)
    executed = defn.execute(node, inputs={"model": fitted_model})["diagnostics"]
    scope = _run_codegen(defn, node, {"model": fitted_model})
    pd.testing.assert_frame_equal(executed, scope["diagnostics"])


# ---------------------------------------------------------------------------
# 3. Regression tests: typed errors instead of raw numpy/statsmodels leaks.
# ---------------------------------------------------------------------------


def test_vif_rejects_non_numeric_columns() -> None:
    df = _regression_df()
    df["cat"] = np.where(df["x1"] > 0, "high", "low")

    with pytest.raises(InvalidModelSpecError):
        diagnostic(df, diagnostic="vif", spec={"columns": ["x1", "cat"]})

    # The valid numeric-only path still works and returns a tidy DataFrame.
    result = diagnostic(df, diagnostic="vif", spec={"columns": ["x1", "x2"]})
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == [
        "diagnostic",
        "statistic",
        "p_value",
        "detail",
    ]


def test_heteroscedasticity_rejects_intercept_only_model() -> None:
    df = _regression_df()

    intercept_only = fit_model(df[["y"]], model="OLS", spec={"target": "y"})
    with pytest.raises(InvalidModelSpecError):
        diagnostic(
            None,
            diagnostic="heteroscedasticity",
            model=intercept_only,
        )

    # A valid multi-feature model still returns a tidy DataFrame.
    fitted = fit_model(df, model="OLS", spec={"target": "y", "fixed_effects": ["x1", "x2"]})
    result = diagnostic(None, diagnostic="heteroscedasticity", model=fitted)
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == [
        "diagnostic",
        "statistic",
        "p_value",
        "detail",
    ]
