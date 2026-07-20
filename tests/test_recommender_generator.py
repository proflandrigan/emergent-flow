"""Tests for the recommender-catalog-entry generator (emergentflow.recommend.generator).

Tests ``generate_recommender_catalog_entries`` with hand-constructed ``RecommenderSpec``
fixtures (not the live seed catalog) for determinism and independence from future
allow-list growth, plus a handful of assertions pinned to specific curated algorithms
(``popularity``, ``als``) and a full-catalog integration check.
"""

from __future__ import annotations

from typing import Any

from emergentflow.nodes.catalog import CATALOG_VERSION, export_catalog
from emergentflow.recommend.generator import generate_recommender_catalog_entries
from emergentflow.recommend.registry import (
    RecommenderParamSpec,
    RecommenderSpec,
    get_recommender_spec,
    known_recommender_keys,
)


def _stub_fitter(interactions: Any, item_features: Any, params: dict) -> Any:
    raise NotImplementedError("stub -- never called by generator tests")


def _stub_recommend_fn(recommender: Any, user_ids: Any, n: int, exclude_known: bool) -> Any:
    raise NotImplementedError("stub -- never called by generator tests")


def _make_spec(
    key: str = "popularity",
    family: str = "baseline",
    description: str = "A baseline algorithm.",
    requires_extra: str | None = None,
    param_metadata: tuple[RecommenderParamSpec, ...] = (),
) -> RecommenderSpec:
    return RecommenderSpec(
        key=key,
        family=family,  # type: ignore[arg-type]
        fitter=_stub_fitter,
        recommend_fn=_stub_recommend_fn,
        similar_items_fn=None,
        description=description,
        requires_extra=requires_extra,
        param_metadata=param_metadata,
    )


# ---------------------------------------------------------------------------
# node_type / family / label / category
# ---------------------------------------------------------------------------


def test_node_type_is_recommend_fit():
    specs = [_make_spec()]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["node_type"] == "recommend.fit"


def test_family_passthrough():
    specs = [_make_spec(family="collaborative")]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["family"] == "collaborative"


def test_label_humanizes_snake_case():
    specs = [_make_spec(key="popularity_segmented")]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["label"] == "Popularity Segmented"


def test_label_humanizes_short_key():
    specs = [_make_spec(key="svd_cf")]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["label"] == "Svd Cf"


def test_category_humanizes_family():
    specs = [_make_spec(family="collaborative")]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["category"] == "Collaborative"


# ---------------------------------------------------------------------------
# sorting
# ---------------------------------------------------------------------------


def test_output_sorted_by_key():
    specs = [_make_spec(key="zlast"), _make_spec(key="alpha")]
    entries = generate_recommender_catalog_entries(specs)
    keys = [e["key"] for e in entries]
    assert keys == ["alpha", "zlast"]


# ---------------------------------------------------------------------------
# description
# ---------------------------------------------------------------------------


def test_description_is_stripped():
    specs = [_make_spec(description="  padded description.  ")]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["description"] == "padded description."


# ---------------------------------------------------------------------------
# requires_extra
# ---------------------------------------------------------------------------


def test_requires_extra_none_by_default():
    specs = [_make_spec()]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["requires_extra"] is None


def test_requires_extra_passthrough():
    specs = [_make_spec(requires_extra="emergentflow[recommend]")]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["requires_extra"] == "emergentflow[recommend]"


# ---------------------------------------------------------------------------
# params: order, shape, choices
# ---------------------------------------------------------------------------


def test_entry_keys_present():
    specs = [_make_spec()]
    entries = generate_recommender_catalog_entries(specs)
    assert set(entries[0]) == {
        "key",
        "node_type",
        "family",
        "label",
        "category",
        "description",
        "requires_extra",
        "params",
    }


def test_params_preserve_declared_order_not_sorted():
    specs = [
        _make_spec(
            param_metadata=(
                RecommenderParamSpec(name="zeta", type="int"),
                RecommenderParamSpec(name="alpha", type="int"),
            )
        )
    ]
    entries = generate_recommender_catalog_entries(specs)
    names = [p["name"] for p in entries[0]["params"]]
    assert names == ["zeta", "alpha"]


def test_param_keys_present():
    specs = [_make_spec(param_metadata=(RecommenderParamSpec(name="n", type="int", default=None),))]
    entries = generate_recommender_catalog_entries(specs)
    for param in entries[0]["params"]:
        assert set(param) == {"name", "type", "default", "help", "choices", "required"}


def test_param_without_choices_is_none():
    specs = [_make_spec(param_metadata=(RecommenderParamSpec(name="n", type="int", default=None),))]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["params"][0]["choices"] is None


def test_param_with_choices_is_list():
    specs = [
        _make_spec(
            param_metadata=(
                RecommenderParamSpec(
                    name="score_type",
                    type="str",
                    default="count",
                    choices=("count", "mean_rating", "weighted"),
                ),
            )
        )
    ]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["params"][0]["choices"] == ["count", "mean_rating", "weighted"]


def test_param_required_passthrough():
    specs = [
        _make_spec(
            param_metadata=(RecommenderParamSpec(name="segment_col", type="str", required=True),)
        )
    ]
    entries = generate_recommender_catalog_entries(specs)
    assert entries[0]["params"][0]["required"] is True


# ---------------------------------------------------------------------------
# purity / determinism
# ---------------------------------------------------------------------------


def test_pure_function():
    specs = [_make_spec(key="b"), _make_spec(key="a")]
    first = generate_recommender_catalog_entries(specs)
    second = generate_recommender_catalog_entries(specs)
    assert first == second
    assert first is not second


# ---------------------------------------------------------------------------
# pinned to specific live curated algorithms
# ---------------------------------------------------------------------------


def test_popularity_entry_shape():
    spec = get_recommender_spec("popularity")
    entries = generate_recommender_catalog_entries([spec])
    entry = entries[0]
    assert entry["node_type"] == "recommend.fit"
    assert entry["family"] == "baseline"
    names = [p["name"] for p in entry["params"]]
    assert names == [p.name for p in spec.param_metadata]
    score_type_param = next(p for p in entry["params"] if p["name"] == "score_type")
    assert score_type_param["choices"] == ["count", "mean_rating", "weighted"]


def test_als_requires_extra_surfaced():
    spec = get_recommender_spec("als")
    entries = generate_recommender_catalog_entries([spec])
    assert entries[0]["requires_extra"] == "emergentflow[recommend]"


# ---------------------------------------------------------------------------
# full-catalog integration
# ---------------------------------------------------------------------------


def test_export_catalog_includes_recommenders():
    artifact = export_catalog()
    assert artifact["catalog_version"] == CATALOG_VERSION
    assert CATALOG_VERSION == 5
    recommenders = artifact["recommenders"]
    assert len(recommenders) == 15
    keys = [e["key"] for e in recommenders]
    assert keys == sorted(keys)
    assert keys == known_recommender_keys()
