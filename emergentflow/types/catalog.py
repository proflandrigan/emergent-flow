"""
emergentflow.types.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~
Built-in type catalog for Emergent Flow.

Importing this module registers the core data-type tokens into the default type
registry as an import-time side effect, mirroring how importing
``emergentflow.nodes`` fires every reference node's self-registration.

The tokens were inventoried from the ``data_type=`` strings used across
``emergentflow/nodes/examples/``. The built-in catalog is intentionally **flat** —
every token is an implicit subtype of ``"any"`` and no explicit subtype edges are
declared among the built-ins. Explicit subtyping is demonstrated by the
out-of-core plugin stub (``examples/type_plugin_stub``) and the unit tests.
"""

from __future__ import annotations

from emergentflow.types.registry import TypeDef, register_type

register_type(
    TypeDef(token="DataFrame", description="A tabular dataset (pandas DataFrame-shaped data).")
)
register_type(
    TypeDef(
        token="ClassifierResult",
        description="The fitted-classifier result produced by a training node.",
    )
)
register_type(
    TypeDef(
        token="AnovaResult",
        description="The result table produced by an ANOVA statistical test.",
    )
)
register_type(TypeDef(token="TTestResult", description="The result of a two-sample t-test."))
register_type(TypeDef(token="HTML", description="A rendered HTML document/report fragment."))
register_type(
    TypeDef(
        token="Tensor",
        description=(
            "An n-dimensional numeric tensor (structural token only; per-dimension "
            "shape inference is deferred to roadmap Epic 10)."
        ),
    )
)
register_type(
    TypeDef(token="Model", description="A fitted machine-learning model (estimator + metadata).")
)
register_type(TypeDef(token="Predictions", description="A DataFrame of model predictions."))
register_type(
    TypeDef(token="EvaluationResult", description="Evaluation metrics for a fitted model.")
)
