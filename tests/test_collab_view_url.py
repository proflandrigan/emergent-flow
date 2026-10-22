"""
tests/test_collab_view_url.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tests for ``emergentflow.collab.mcp.build_view_url`` (issue #168): the pure function that
builds canvas deep links. View state lives in the URL hash only and never touches the IR.
No ``fastmcp`` needed.
"""

from __future__ import annotations

import pytest

from emergentflow.collab import mcp as mcp_mod

BASE = "http://127.0.0.1:8765/?session=s1"


@pytest.fixture(autouse=True)
def _base(monkeypatch) -> None:
    monkeypatch.setattr(mcp_mod, "OPEN_IN_UI_BASE", "http://127.0.0.1:8765")


def test_no_args_is_byte_identical() -> None:
    assert mcp_mod.build_view_url("s1") == "http://127.0.0.1:8765/?session=s1"


def test_focus_single() -> None:
    assert mcp_mod.build_view_url("s1", focus="n1") == BASE + "#focus=n1"


def test_focus_multiple_with_reach_alias() -> None:
    url = mcp_mod.build_view_url("s1", focus=["a", "b"], reach="downstream")
    assert url == BASE + "#focus=a,b&reach=down"


def test_reach_case_insensitive() -> None:
    assert mcp_mod.build_view_url("s1", focus="a", reach="UP") == BASE + "#focus=a&reach=up"


def test_route() -> None:
    assert mcp_mod.build_view_url("s1", route=("a", "b")) == BASE + "#route=a~b"


def test_lens() -> None:
    assert mcp_mod.build_view_url("s1", lens=["ml", "data"]) == BASE + "#lens=ml~data"


def test_edge_proposal_review_each_emitted() -> None:
    assert mcp_mod.build_view_url("s1", edge="e1") == BASE + "#edge=e1"
    assert mcp_mod.build_view_url("s1", proposal="p1") == BASE + "#proposal=p1"
    assert mcp_mod.build_view_url("s1", review="r1") == BASE + "#review=r1"


def test_combined_order() -> None:
    url = mcp_mod.build_view_url(
        "s1",
        review="r",
        proposal="p",
        edge="e",
        lens=["ml"],
        route=("a", "b"),
        reach="both",
        focus="f",
    )
    assert url == BASE + "#focus=f&reach=both&route=a~b&lens=ml&edge=e&proposal=p&review=r"


def test_ids_are_encoded() -> None:
    assert mcp_mod.build_view_url("s1", focus="a~b") == BASE + "#focus=a%7Eb"
    assert mcp_mod.build_view_url("s1", focus="a,b") == BASE + "#focus=a%2Cb"
    assert mcp_mod.build_view_url("s1", focus="a b") == BASE + "#focus=a%20b"
    assert mcp_mod.build_view_url("s1", focus="a&b") == BASE + "#focus=a%26b"
    assert mcp_mod.build_view_url("s1", focus="a#b") == BASE + "#focus=a%23b"


def test_bad_reach_raises() -> None:
    with pytest.raises(ValueError, match="reach must be one of"):
        mcp_mod.build_view_url("s1", focus="a", reach="sideways")


def test_reach_without_focus_raises() -> None:
    with pytest.raises(ValueError, match="reach requires focus"):
        mcp_mod.build_view_url("s1", reach="up")


@pytest.mark.parametrize("route", [["a"], ["a", "b", "c"]])
def test_bad_route_raises(route) -> None:
    with pytest.raises(ValueError, match="route must be"):
        mcp_mod.build_view_url("s1", route=route)


def test_base_read_at_call_time(monkeypatch) -> None:
    monkeypatch.setattr(mcp_mod, "OPEN_IN_UI_BASE", "http://127.0.0.1:9000")
    assert mcp_mod.build_view_url("s1") == "http://127.0.0.1:9000/?session=s1"
