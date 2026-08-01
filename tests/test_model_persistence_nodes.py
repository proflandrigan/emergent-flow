"""ADR-0002 equivalence tests for the model-persistence reference nodes.

Covers the four node types introduced by the model-persistence feature
(issue #113): ``ml.save_model``, ``ml.load_model``, ``recommend.save_model``,
``recommend.load_model``. Each test builds a small two-node ``load -> save``
graph whose nodes route through the same ``ef.*`` wrapper on both the
``execute`` side and the compiled-code subprocess side, so the ADR-0002
invariant is proven for the new codegen/execute pairs exactly as for the rest
of the catalog.
"""

from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from emergentflow.ir.edge import Edge, PortRef
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.ml import save_model as ml_save_model
from emergentflow.ml import train_regressor
from emergentflow.nodes.examples import (
    LoadModel,
    RecommendLoadModel,
    RecommendSaveModel,
    SaveModel,
)
from emergentflow.recommend import (
    fit as recommend_fit,
)
from emergentflow.recommend import (
    random_split,
)
from emergentflow.recommend import (
    save_model as recommend_save_model,
)
from tests.test_codegen_equivalence import assert_equivalent


def _port_id(node: Node, name: str) -> str:
    return next(p.id for p in node.ports if p.name == name)


def _ml_load_save_graph(src: pathlib.Path, dst: pathlib.Path) -> Graph:
    load = LoadModel().instantiate(path=str(src))
    save = SaveModel().instantiate(path=str(dst))
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_port_id(load, "model")),
        target=PortRef(node_id=save.id, port_id=_port_id(save, "model")),
    )
    return Graph(nodes={load.id: load, save.id: save}, edges={edge.id: edge})


def _recommend_load_save_graph(src: pathlib.Path, dst: pathlib.Path) -> Graph:
    load = RecommendLoadModel().instantiate(path=str(src))
    save = RecommendSaveModel().instantiate(path=str(dst))
    edge = Edge(
        source=PortRef(node_id=load.id, port_id=_port_id(load, "recommender")),
        target=PortRef(node_id=save.id, port_id=_port_id(save, "recommender")),
    )
    return Graph(nodes={load.id: load, save.id: save}, edges={edge.id: edge})


@pytest.mark.equivalence
def test_ml_save_load_nodes_equivalence(tmp_path: pathlib.Path) -> None:
    """ml.load_model -> ml.save_model: execute == running the emitted code."""
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "y": [2.0, 4.0, 6.0, 8.0]})
    model = train_regressor(df, target="y")

    src = tmp_path / "src.joblib"
    dst = tmp_path / "dst.joblib"
    ml_save_model(model, src)

    assert_equivalent(_ml_load_save_graph(src, dst), cwd=tmp_path)


@pytest.mark.equivalence
def test_recommend_save_load_nodes_equivalence(tmp_path: pathlib.Path) -> None:
    """recommend.load_model -> recommend.save_model: execute == running the emitted code."""
    df = pd.DataFrame(
        {
            "user_id": ["u1", "u1", "u1", "u2", "u2", "u3"],
            "item_id": ["i1", "i2", "i3", "i1", "i4", "i2"],
            "rating": [1, 1, 1, 1, 1, 1],
        }
    )
    train, _test = random_split(
        df, user_col="user_id", item_col="item_id", test_ratio=0.2, seed=0, implicit=True
    )
    rec = recommend_fit(train, algorithm="popularity")

    src = tmp_path / "rec.joblib"
    dst = tmp_path / "rec_copy.joblib"
    recommend_save_model(rec, src)

    assert_equivalent(_recommend_load_save_graph(src, dst), cwd=tmp_path)
