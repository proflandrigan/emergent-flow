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
register_type(
    TypeDef(
        token="Transformer",
        description=(
            "A fitted unsupervised transformer (e.g. a scaler or PCA) that has "
            "learned parameters but is not a predictor."
        ),
    )
)
register_type(
    TypeDef(
        token="ModelSummary",
        description=(
            "A structural, JSON-native inspectable summary of a fitted model or "
            "transformer (accuracy/coefficients, explained variance, cluster sizes, ...)."
        ),
    )
)
register_type(
    TypeDef(
        token="PromptSpec",
        description=(
            "A rendered LLM prompt ({system, user, messages}) produced by "
            "ef.llm.prompt and consumed by ef.llm.call (Epic 9)."
        ),
    )
)
register_type(
    TypeDef(
        token="LLMResponse",
        description=(
            "The inspectable result of one LLM completion call: text/parsed "
            "data, usage, cost_usd, latency_ms, finish_reason (Epic 9, ADR 0017)."
        ),
    )
)
register_type(
    TypeDef(
        token="VariableBinding",
        description=(
            "One row of variable-name -> value bindings used to render an "
            "ef.llm.prompt template (Epic 9)."
        ),
    )
)
register_type(
    TypeDef(
        token="StatsModel",
        description=(
            "A fitted statistical model (OLS/GLM/MixedLM/GAM and their Bayesian "
            "counterparts) produced by ef.stats.fit_model (Epic 12). Distinct from Epic 8's "
            "'Model' predictor and 'Transformer': it carries a tidy coefficient/summary frame "
            "and diagnostics, and wires into coefficient-plot and diagnostic nodes, not into a "
            "DataFrame input."
        ),
    )
)
register_type(
    TypeDef(
        token="PlotSpec",
        description=(
            "A terminal render payload: the plotly figure JSON (fig.to_json()) produced "
            "by ef.viz.plot (Epic 12). JSON-native by construction; a terminal output that is "
            "rendered by the Results tab and does not wire downstream."
        ),
    )
)
register_type(
    TypeDef(
        token="Schema",
        description=(
            "A tidy schema-introspection frame (database/schema/table/column/data_type/"
            "nullable) produced by warehouse introspection through the WarehouseClient seam "
            "(Epic 13, ADR 0018)."
        ),
    )
)
register_type(
    TypeDef(
        token="CostEstimate",
        description=(
            "Cost/byte-scan metadata (bytes_scanned/cost_usd/dialect) for a warehouse query, "
            "produced alongside a query node's 'frame' DataFrame output whether or not the "
            "query ran under dry_run (Epic 13, ADR 0018). A terminal, JSON-native summary -- "
            "does not carry query data, so it is distinct from 'frame'."
        ),
    )
)
register_type(
    TypeDef(
        token="ForecastResult",
        description=(
            "A fitted forecast produced by ef.timeseries.forecast_arima/forecast_ets: a "
            "tidy step/forecast/lower_ci/upper_ci frame, JSON-native fit stats, and the live "
            "statsmodels results object."
        ),
    )
)
register_type(
    TypeDef(
        token="DecomposeResult",
        description=(
            "The trend/seasonal/residual decomposition produced by "
            "ef.timeseries.seasonal_decompose: a tidy observed/trend/seasonal/residual frame "
            "plus the model and period used."
        ),
    )
)
register_type(
    TypeDef(
        token="Recommender",
        description=(
            "A fitted recommender model produced by ef.recommend.fit (Epic 15): baseline, "
            "content-based, collaborative, or deep-learning. Distinct from Epic 8's 'Model' and "
            "Epic 12's 'StatsModel' -- it wires into recommend/evaluate/similar-items nodes, not "
            "into a DataFrame input."
        ),
    )
)
register_type(
    TypeDef(
        token="InteractionMatrix",
        description=(
            "A prepared sparse user-item interaction dataset produced by "
            "ef.recommend.prepare_interactions (Epic 15): wraps a scipy CSR matrix plus "
            "user/item id mappings, inspectable via a tidy summary. Wires into recommender-fit "
            "nodes, not into a plain DataFrame consumer."
        ),
    )
)
register_type(
    TypeDef(
        token="RecommendationResult",
        description=(
            "The terminal recommendation payload produced by "
            "ef.recommend.recommend/similar_items (Epic 15): a tidy "
            "user_id/item_id/rank/score DataFrame."
        ),
    )
)
register_type(
    TypeDef(
        token="EvalResult",
        description=(
            "The evaluation of a fitted recommender against held-out interactions, produced by "
            "ef.recommend.evaluate (Epic 15): a tidy per-user precision/recall/ndcg/hit/AP frame "
            "plus a system-level aggregate dict (mean ranking metrics, coverage, diversity, "
            "novelty)."
        ),
    )
)
