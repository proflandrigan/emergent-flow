"""Tests for the estimator-catalog-entry generator (emergentflow.ml.generator).

Tests ``generate_estimator_catalog_entries`` with hand-constructed ``EstimatorSpec``
fixtures (not the live seed catalog) for determinism and independence from future
allow-list growth.
"""

from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from emergentflow.ml.generator import generate_estimator_catalog_entries
from emergentflow.ml.registry import (
    EstimatorSpec,
    KwargSpec,
    get_estimator_spec,
    known_estimator_keys,
)


def _make_spec(
    key: str = "LogisticRegression",
    import_path: str = "sklearn.linear_model.LogisticRegression",
    sklearn_class: type = LogisticRegression,
    archetype: str = "fit",
    task: str | None = "classification",
    description: str = "",
    accepted_kwargs: dict | None = None,
) -> EstimatorSpec:
    if accepted_kwargs is None:
        accepted_kwargs = {
            "max_iter": KwargSpec(default=1000, help="Maximum solver iterations."),
            "random_state": KwargSpec(default=0, help="Seed for reproducibility."),
        }
    return EstimatorSpec(
        key=key,
        import_path=import_path,
        sklearn_class=sklearn_class,
        archetype=archetype,  # type: ignore[arg-type]
        task=task,
        description=description,
        accepted_kwargs=accepted_kwargs,
    )


# ---------------------------------------------------------------------------
# node_type mapping per archetype
# ---------------------------------------------------------------------------


def test_node_type_fit_archetype():
    specs = [_make_spec(archetype="fit")]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["node_type"] == "ml.fit_estimator"


def test_node_type_fit_transform_archetype():
    specs = [_make_spec(archetype="fit_transform")]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["node_type"] == "ml.fit_transform"


def test_node_type_cluster_detect_archetype():
    specs = [_make_spec(archetype="cluster_detect")]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["node_type"] == "ml.cluster_detect"


# ---------------------------------------------------------------------------
# sorting
# ---------------------------------------------------------------------------


def test_output_sorted_by_key():
    specs = [
        _make_spec(key="ZLast", import_path="sklearn.foo.ZLast"),
        _make_spec(key="Alpha", import_path="sklearn.foo.Alpha"),
    ]
    entries = generate_estimator_catalog_entries(specs)
    keys = [e["key"] for e in entries]
    assert keys == ["Alpha", "ZLast"]


# ---------------------------------------------------------------------------
# label humanization
# ---------------------------------------------------------------------------


def test_label_humanizes_camel_case():
    specs = [_make_spec(key="RandomForestClassifier")]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["label"] == "Random Forest Classifier"


# ---------------------------------------------------------------------------
# category from import path
# ---------------------------------------------------------------------------


def test_category_from_import_path():
    specs = [
        _make_spec(
            key="RF",
            import_path="sklearn.ensemble.RandomForestClassifier",
            sklearn_class=RandomForestClassifier,
        )
    ]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["category"] == "Ensemble"


# ---------------------------------------------------------------------------
# description from real sklearn class
# ---------------------------------------------------------------------------


def test_description_non_empty_for_real_class():
    specs = [_make_spec(sklearn_class=LogisticRegression)]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["description"] != ""


def test_curated_description_takes_priority_over_docstring():
    specs = [_make_spec(sklearn_class=LogisticRegression, description="A curated one-liner.")]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["description"] == "A curated one-liner."


def test_empty_curated_description_falls_back_to_docstring():
    specs = [_make_spec(sklearn_class=LogisticRegression, description="")]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["description"] != ""
    assert entries[0]["description"] != "A curated one-liner."


# ---------------------------------------------------------------------------
# params structure and type inference
# ---------------------------------------------------------------------------


def test_params_has_one_entry_per_accepted_kwarg():
    specs = [_make_spec()]
    entries = generate_estimator_catalog_entries(specs)
    params = entries[0]["params"]
    assert len(params) == 2
    names = [p["name"] for p in params]
    assert names == sorted(names)


def test_params_keys_present():
    specs = [_make_spec()]
    entries = generate_estimator_catalog_entries(specs)
    for param in entries[0]["params"]:
        assert set(param) == {"name", "type", "default", "help"}


def test_param_type_bool():
    specs = [
        _make_spec(
            accepted_kwargs={"flag": KwargSpec(default=True, help="A flag.")},
        )
    ]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["params"][0]["type"] == "bool"


def test_param_type_int():
    specs = [
        _make_spec(
            accepted_kwargs={"count": KwargSpec(default=42, help="Count.")},
        )
    ]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["params"][0]["type"] == "int"


def test_param_type_float():
    specs = [
        _make_spec(
            accepted_kwargs={"rate": KwargSpec(default=0.5, help="Rate.")},
        )
    ]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["params"][0]["type"] == "float"


def test_param_type_str():
    specs = [
        _make_spec(
            accepted_kwargs={"name": KwargSpec(default="hello", help="Name.")},
        )
    ]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["params"][0]["type"] == "str"


def test_param_type_any_for_none():
    specs = [
        _make_spec(
            accepted_kwargs={"maybe": KwargSpec(default=None, help="Maybe.")},
        )
    ]
    entries = generate_estimator_catalog_entries(specs)
    assert entries[0]["params"][0]["type"] == "any"


# ---------------------------------------------------------------------------
# purity
# ---------------------------------------------------------------------------


def test_pure_function():
    specs = [
        _make_spec(key="B", import_path="sklearn.foo.B"),
        _make_spec(key="A", import_path="sklearn.foo.A"),
    ]
    first = generate_estimator_catalog_entries(specs)
    second = generate_estimator_catalog_entries(specs)
    assert first == second
    assert first is not second


# ---------------------------------------------------------------------------
# golden: the full generated estimator catalog, pinned to the curated allow-list
# ---------------------------------------------------------------------------


def _live_estimator_specs() -> list[EstimatorSpec]:
    return [get_estimator_spec(key) for key in known_estimator_keys()]


def test_every_registered_estimator_has_a_curated_description():
    """Every curated allow-list entry has a non-empty, hand-written description.

    Guards against a future estimator being added to the allow-list without also curating
    its description (which would silently fall back to the raw sklearn docstring).
    """
    for spec in _live_estimator_specs():
        assert spec.description.strip(), f"{spec.key!r} has no curated description."


def test_generated_catalog_uses_curated_descriptions_not_docstrings():
    """The generated entry's description is the curated one verbatim, not the docstring."""
    entries = {e["key"]: e for e in generate_estimator_catalog_entries(_live_estimator_specs())}
    for spec in _live_estimator_specs():
        assert entries[spec.key]["description"] == spec.description.strip()


def test_generated_catalog_keys_match_allow_list_exactly():
    """The generated entry set is exactly the curated allow-list -- pinned, not enumerated.

    This is what makes the catalog independent of the installed sklearn version: it always
    reflects ``known_estimator_keys()`` (the curated registry), never
    ``sklearn.utils.all_estimators()``.
    """
    entries = generate_estimator_catalog_entries(_live_estimator_specs())
    assert sorted(e["key"] for e in entries) == known_estimator_keys()


def test_estimator_catalog_golden(snapshot) -> None:
    """Pin the full generated estimator-catalog entry list (stable ordering + shape)."""
    assert generate_estimator_catalog_entries(_live_estimator_specs()) == snapshot
