"""
Tests for the Epic 15 Story 3 recommend interactions feature:
``PrepareInteractions`` node golden codegen, ``temporal_split``/``random_split``
correctness, and ``Recommender``/``InteractionMatrix`` type-token catalog registration.

1. **Golden-code quality (Part A):** ``compile_to_code`` for a
   ``LoadSample -> PrepareInteractions`` graph is syntactically valid Python and
   passes ``ruff check`` — parse/lint only, never executed.
2. **Split correctness & determinism (Part B):** ``temporal_split`` and
   ``random_split`` return correct ``InteractionMatrix`` pairs, are deterministic,
   do not mutate input, and raise typed errors on invalid args.
3. **Type-token compatibility (Part C):** ``Recommender`` and ``InteractionMatrix``
   are registered in the default type catalog, are subtypes of ``any``, are flat
   (unrelated to ``DataFrame`` or each other), and are self-compatible.
4. **Cold-start filtering (Part D):** ``min_user_interactions``/``min_item_interactions``
   filtering under every ``cold_start_mode`` -- including the cascade case where dropping
   low-count items pushes a user below ``min_user_interactions`` (and vice versa), which
   the gate must resolve to a fixed point rather than leaving stragglers below threshold.
"""

from __future__ import annotations

import ast
import subprocess
import sys

import pandas as pd
import pytest

from emergentflow.codegen.compiler import compile_to_code
from emergentflow.ir.common import Direction
from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.nodes.examples import LoadSample, PrepareInteractions
from emergentflow.recommend import prepare_interactions, random_split, temporal_split
from emergentflow.recommend.errors import InvalidRecommenderParamsError
from emergentflow.types import registry
from emergentflow.types.compatibility import Compatibility, is_compatible
from emergentflow.types.registry import TOP_TYPE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _out_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.OUT and p.name == name)


def _in_port(node, name):
    return next(p for p in node.ports if p.direction == Direction.IN and p.name == name)


# ---------------------------------------------------------------------------
# Part A — Golden ast.parse / ruff check for PrepareInteractions codegen
# ---------------------------------------------------------------------------


def _build_prepare_interactions_graph() -> Graph:
    load = LoadSample().instantiate(name="iris", label="Load Sample")
    prepare = PrepareInteractions().instantiate(
        label="Prepare Interactions",
        user_col="sepal length (cm)",
        item_col="sepal width (cm)",
    )
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_out_port(load, "frame").id),
        target=PortRef(node_id=prepare.id, port_id=_in_port(prepare, "frame").id),
    )
    return Graph(nodes={load.id: load, prepare.id: prepare}, edges={edge.id: edge})


def test_prepare_interactions_codegen_is_parseable() -> None:
    code = compile_to_code(_build_prepare_interactions_graph())
    ast.parse(code)


def test_prepare_interactions_codegen_is_ruff_clean() -> None:
    code = compile_to_code(_build_prepare_interactions_graph())
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "-"],
        input=code,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Part B — temporal_split / random_split correctness + determinism +
#          no-mutation + typed errors
# ---------------------------------------------------------------------------


def test_temporal_split_returns_interaction_matrices() -> None:
    df = pd.DataFrame(
        {
            "user": ["u1"] * 5,
            "item": [f"i{j}" for j in range(5)],
            "ts": list(range(5)),
        }
    )
    train, test = temporal_split(
        df,
        user_col="user",
        item_col="item",
        timestamp_col="ts",
        test_ratio=0.4,
    )
    assert train.n_interactions == 3
    assert test.n_interactions == 2
    assert "i3" in test.item_index and "i4" in test.item_index
    assert "i3" not in train.item_index and "i4" not in train.item_index


def test_temporal_split_is_deterministic() -> None:
    df = pd.DataFrame(
        {
            "user": ["u1"] * 5,
            "item": [f"i{j}" for j in range(5)],
            "ts": list(range(5)),
        }
    )
    train_a, test_a = temporal_split(
        df,
        user_col="user",
        item_col="item",
        timestamp_col="ts",
        test_ratio=0.4,
    )
    train_b, test_b = temporal_split(
        df,
        user_col="user",
        item_col="item",
        timestamp_col="ts",
        test_ratio=0.4,
    )
    assert train_a.n_interactions == train_b.n_interactions
    assert test_a.n_interactions == test_b.n_interactions


def test_temporal_split_does_not_mutate_input() -> None:
    df = pd.DataFrame(
        {
            "user": ["u1"] * 5,
            "item": [f"i{j}" for j in range(5)],
            "ts": list(range(5)),
        }
    )
    df_before = df.copy()
    temporal_split(
        df,
        user_col="user",
        item_col="item",
        timestamp_col="ts",
        test_ratio=0.4,
    )
    pd.testing.assert_frame_equal(df, df_before)


def test_temporal_split_holds_out_newest_interaction_for_small_users() -> None:
    # A user with 2 interactions at test_ratio 0.25 gives round(0.5) = 0 via banker's
    # rounding; the split must still hold out the user's newest interaction rather than
    # silently dropping them from the test set.
    df = pd.DataFrame(
        {
            "user": ["u1", "u1", "u2", "u2", "u2", "u2"],
            "item": ["a", "b", "a", "b", "c", "d"],
            "ts": [0, 1, 0, 1, 2, 3],
        }
    )
    train, test = temporal_split(
        df,
        user_col="user",
        item_col="item",
        timestamp_col="ts",
        test_ratio=0.25,
    )
    # u1's newest interaction (b) is held out, not abandoned to train.
    assert "u1" in test.user_ids
    assert "b" in test.item_index
    # u1's train row contains only its older interaction (a), not b.
    u1_train = set(train.item_ids[i] for i in train.matrix[train.user_index["u1"]].indices)
    assert u1_train == {"a"}


def test_temporal_split_missing_timestamp_col_raises() -> None:
    df = pd.DataFrame({"user": ["u1"], "item": ["i0"], "ts": [0]})
    with pytest.raises(InvalidRecommenderParamsError):
        temporal_split(
            df,
            user_col="user",
            item_col="item",
            timestamp_col="not_a_col",
            test_ratio=0.4,
        )


@pytest.mark.parametrize("bad_ratio", [0.0, 1.0])
def test_temporal_split_bad_test_ratio_raises(bad_ratio: float) -> None:
    df = pd.DataFrame({"user": ["u1"], "item": ["i0"], "ts": [0]})
    with pytest.raises(InvalidRecommenderParamsError):
        temporal_split(
            df,
            user_col="user",
            item_col="item",
            timestamp_col="ts",
            test_ratio=bad_ratio,
        )


def test_random_split_is_deterministic_given_seed() -> None:
    df = pd.DataFrame(
        {
            "user": ["u1"] * 5,
            "item": [f"i{j}" for j in range(5)],
        }
    )
    train_a, test_a = random_split(
        df,
        user_col="user",
        item_col="item",
        test_ratio=0.4,
        seed=0,
    )
    train_b, test_b = random_split(
        df,
        user_col="user",
        item_col="item",
        test_ratio=0.4,
        seed=0,
    )
    assert train_a.n_interactions == train_b.n_interactions
    assert test_a.n_interactions == test_b.n_interactions


def test_random_split_differs_across_seeds() -> None:
    df = pd.DataFrame(
        {
            "user": [f"u{j}" for j in range(30)],
            "item": [f"i{j}" for j in range(30)],
        }
    )
    _, test_a = random_split(
        df,
        user_col="user",
        item_col="item",
        test_ratio=0.2,
        seed=0,
    )
    _, test_b = random_split(
        df,
        user_col="user",
        item_col="item",
        test_ratio=0.2,
        seed=42,
    )
    assert set(test_a.item_index) != set(test_b.item_index)


def test_random_split_does_not_mutate_input() -> None:
    df = pd.DataFrame(
        {
            "user": ["u1"] * 5,
            "item": [f"i{j}" for j in range(5)],
        }
    )
    df_before = df.copy()
    random_split(df, user_col="user", item_col="item", test_ratio=0.4, seed=0)
    pd.testing.assert_frame_equal(df, df_before)


@pytest.mark.parametrize("bad_ratio", [0.0, 1.0])
def test_random_split_bad_test_ratio_raises(bad_ratio: float) -> None:
    df = pd.DataFrame({"user": ["u1"], "item": ["i0"]})
    with pytest.raises(InvalidRecommenderParamsError):
        random_split(
            df,
            user_col="user",
            item_col="item",
            test_ratio=bad_ratio,
            seed=0,
        )


def test_random_split_never_empties_a_half_for_multiple_rows() -> None:
    # Banker's rounding round(1.5) = 2 on a 2-row frame at 0.75 used to move every row to test,
    # leaving an empty train the caller cannot fit on; round(0.5) = 0 on a tiny frame emptied
    # test. Both halves must stay non-empty for any multi-row frame.
    df = pd.DataFrame({"user": ["u1", "u1"], "item": ["a", "b"]})
    for ratio in (0.25, 0.5, 0.75):
        train, test = random_split(df, user_col="user", item_col="item", test_ratio=ratio, seed=0)
        assert train.n_interactions > 0, f"ratio {ratio}: train half empty"
        assert test.n_interactions > 0, f"ratio {ratio}: test half empty"


def test_temporal_split_never_empties_a_half_for_a_multi_event_user() -> None:
    # A user with 2 events at 0.75 gives round(1.5) = 2, which used to move the whole slice to
    # test, draining their train half. Both halves must stay non-empty for a >=2-event user.
    df = pd.DataFrame({"user": ["u1", "u1"], "item": ["a", "b"], "ts": [0, 1]})
    for ratio in (0.25, 0.5, 0.75):
        train, test = temporal_split(
            df, user_col="user", item_col="item", timestamp_col="ts", test_ratio=ratio
        )
        assert train.n_interactions > 0, f"ratio {ratio}: train half empty"
        assert test.n_interactions > 0, f"ratio {ratio}: test half empty"


# ---------------------------------------------------------------------------
# Part C — Type-token compatibility tests for Recommender / InteractionMatrix
# ---------------------------------------------------------------------------


def test_recommender_and_interaction_matrix_tokens_registered() -> None:
    assert registry.is_registered("Recommender")
    assert registry.is_registered("InteractionMatrix")


def test_recommender_and_interaction_matrix_are_subtypes_of_any() -> None:
    assert registry.is_subtype("Recommender", TOP_TYPE)
    assert registry.is_subtype("InteractionMatrix", TOP_TYPE)


def test_recommender_and_interaction_matrix_are_flat_not_subtypes_of_each_other_or_dataframe() -> (
    None
):
    assert not registry.is_subtype("Recommender", "DataFrame")
    assert not registry.is_subtype("InteractionMatrix", "DataFrame")
    assert not registry.is_subtype("Recommender", "InteractionMatrix")
    assert not registry.is_subtype("InteractionMatrix", "Recommender")


def test_recommender_incompatible_with_dataframe() -> None:
    result = is_compatible("Recommender", "DataFrame")
    assert result.verdict == Compatibility.INCOMPATIBLE


def test_interaction_matrix_incompatible_with_dataframe() -> None:
    result = is_compatible("InteractionMatrix", "DataFrame")
    assert result.verdict == Compatibility.INCOMPATIBLE


def test_recommender_and_interaction_matrix_self_compatible() -> None:
    result = is_compatible("Recommender", "Recommender")
    assert result.verdict == Compatibility.COMPATIBLE
    result = is_compatible("InteractionMatrix", "InteractionMatrix")
    assert result.verdict == Compatibility.COMPATIBLE


# ---------------------------------------------------------------------------
# Part D — cold-start filtering (min_user_interactions / min_item_interactions)
# ---------------------------------------------------------------------------


def test_warn_and_skip_resolves_cascade_to_a_fixed_point() -> None:
    """u1 has 2 interactions (i1, i2) and clears min_user_interactions=2 on the raw counts,
    but i1 is a singleton and gets dropped as a low-count item; that leaves u1 with only 1
    interaction, which must also be dropped rather than silently left below threshold."""
    df = pd.DataFrame(
        {
            "user": ["u1", "u1", "u2"],
            "item": ["i1", "i2", "i2"],
        }
    )
    with pytest.warns(UserWarning):
        im = prepare_interactions(
            df,
            user_col="user",
            item_col="item",
            min_user_interactions=2,
            min_item_interactions=2,
            cold_start_mode="warn-and-skip",
        )
    assert im.n_interactions == 0
    assert im.user_ids == []
    assert im.item_ids == []


def test_warn_and_skip_keeps_every_remaining_user_and_item_above_threshold() -> None:
    df = pd.DataFrame(
        {
            "user": ["u1", "u1", "u1", "u2", "u2", "u3"],
            "item": ["i1", "i2", "i3", "i2", "i3", "i3"],
        }
    )
    with pytest.warns(UserWarning):
        im = prepare_interactions(
            df,
            user_col="user",
            item_col="item",
            min_user_interactions=2,
            min_item_interactions=2,
            cold_start_mode="warn-and-skip",
        )
    for uid in im.user_ids:
        assert im.matrix[im.user_index[uid]].nnz >= 2
    for iid in im.item_ids:
        assert im.matrix[:, im.item_index[iid]].nnz >= 2


def test_error_mode_raises_on_below_threshold_counts() -> None:
    df = pd.DataFrame({"user": ["u1", "u2"], "item": ["i1", "i1"]})
    with pytest.raises(InvalidRecommenderParamsError):
        prepare_interactions(
            df,
            user_col="user",
            item_col="item",
            min_user_interactions=2,
            cold_start_mode="error",
        )


def test_include_mode_does_not_filter() -> None:
    df = pd.DataFrame({"user": ["u1", "u2"], "item": ["i1", "i1"]})
    im = prepare_interactions(
        df,
        user_col="user",
        item_col="item",
        min_user_interactions=2,
        min_item_interactions=2,
        cold_start_mode="include",
    )
    assert im.n_interactions == 2
    assert set(im.user_ids) == {"u1", "u2"}
