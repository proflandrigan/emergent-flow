"""
emergentflow.collab.tours
~~~~~~~~~~~~~~~~~~~~~~~~~~
Guided tours (issue #171): an agent-authored, ordered walkthrough of a graph. Each step either
highlights a set of nodes (``focus``, optionally expanded ``reach`` up/down/both the DAG) or a
``route`` between two nodes, with a markdown ``note`` and optional ``unknowns``.

Tours live on ``CollaborationState.tours``, BESIDE the graph, never on it (ADR 0019): this module
is never imported by emergentflow/__init__.py or emergentflow/ir/*. It must not import
``emergentflow.collab.review`` or ``emergentflow.collab.session`` (review imports this module).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from emergentflow.collab.anchors import AnchorError, missing_node_ids
from emergentflow.ir.common import IRId, new_id
from emergentflow.ir.graph import Graph

MAX_TITLE = 200
MAX_ID = 200
MAX_CONCLUSION = 4_000
MAX_NOTE = 16_000
MAX_AUTHOR = 200
MAX_STEPS = 100
MAX_FOCUS = 50
MAX_UNKNOWNS = 20
MAX_UNKNOWN_LEN = 1_000

TourReach = Literal["up", "down", "both"]


def _reject_blank(value: str, what: str) -> str:
    if not value.strip():
        raise ValueError(f"{what} must not be empty or whitespace-only")
    return value


class TourStep(BaseModel):
    """One step of a tour: a focus set (with optional reach) or a route, plus a note."""

    model_config = ConfigDict(extra="forbid")

    focus: list[IRId] = Field(default_factory=list, max_length=MAX_FOCUS)
    reach: TourReach | None = None
    route: tuple[IRId, IRId] | None = None
    note: str = Field(min_length=1, max_length=MAX_NOTE)
    unknowns: list[str] = Field(default_factory=list, max_length=MAX_UNKNOWNS)

    @field_validator("note")
    @classmethod
    def _note_not_blank(cls, v: str) -> str:
        return _reject_blank(v, "note")

    @field_validator("focus")
    @classmethod
    def _focus_valid(cls, v: list[IRId]) -> list[IRId]:
        seen: set[str] = set()
        for node_id in v:
            _reject_blank(node_id, "focus id")
            if node_id in seen:
                raise ValueError(f"duplicate focus id {node_id!r}")
            seen.add(node_id)
        return v

    @field_validator("route")
    @classmethod
    def _route_valid(cls, v: tuple[IRId, IRId] | None) -> tuple[IRId, IRId] | None:
        if v is not None:
            for node_id in v:
                _reject_blank(node_id, "route endpoint")
        return v

    @field_validator("unknowns")
    @classmethod
    def _unknowns_valid(cls, v: list[str]) -> list[str]:
        for entry in v:
            _reject_blank(entry, "unknowns entry")
            if len(entry) > MAX_UNKNOWN_LEN:
                raise ValueError(f"unknowns entry exceeds {MAX_UNKNOWN_LEN} characters")
        return v

    @model_validator(mode="after")
    def _check_shape(self) -> TourStep:
        if self.route is not None:
            if self.focus or self.reach is not None:
                raise ValueError("a step's route cannot be combined with focus/reach")
            return self
        if not self.focus:
            if self.reach is not None:
                raise ValueError("a step's reach requires a non-empty focus")
            raise ValueError("a step needs either a non-empty focus or a route")
        return self


class Tour(BaseModel):
    """An ordered guided walkthrough of the session graph."""

    model_config = ConfigDict(extra="forbid")

    id: IRId = Field(default_factory=new_id, max_length=MAX_ID)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    conclusion: str = Field(min_length=1, max_length=MAX_CONCLUSION)
    steps: list[TourStep] = Field(min_length=1, max_length=MAX_STEPS)
    author: str = Field(min_length=1, max_length=MAX_AUTHOR)

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, v: str) -> str:
        v = _reject_blank(v, "id")
        # The id is a single REST path segment (PUT/DELETE /sessions/{id}/tours/{tour_id}): a "/"
        # or a dot segment is split/normalised before routing, leaving the tour unreachable.
        if "/" in v or v in {".", ".."}:
            raise ValueError("id must not contain '/' or be '.' or '..'")
        return v

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        return _reject_blank(v, "title")

    @field_validator("conclusion")
    @classmethod
    def _conclusion_not_blank(cls, v: str) -> str:
        return _reject_blank(v, "conclusion")

    @field_validator("author")
    @classmethod
    def _author_not_blank(cls, v: str) -> str:
        return _reject_blank(v, "author")


class TourAnchorError(AnchorError):
    """A tour step names node ids absent from the session graph. ``missing`` lists every
    (step_index, node_id) pair, in step order, so callers can report all of them at once."""

    def __init__(self, missing: list[tuple[int, str]]) -> None:
        self.missing = missing
        detail = ", ".join(f"step {i}: {nid!r}" for i, nid in missing)
        super().__init__(f"tour anchors to unknown node ids ({detail}).")

    def details(self) -> list[dict[str, object]]:
        return [{"step": i, "node_id": nid} for i, nid in self.missing]


def step_anchor_ids(step: TourStep) -> list[IRId]:
    """The node ids a step references: its focus list, or its route endpoints."""
    if step.route is not None:
        return list(step.route)
    return list(step.focus)


def validate_tour_anchors(graph: Graph, tour: Tour) -> None:
    """Raise TourAnchorError naming EVERY missing (step index, node id) pair. Pure."""
    missing: list[tuple[int, str]] = []
    for index, step in enumerate(tour.steps):
        for node_id in missing_node_ids(graph, step_anchor_ids(step)):
            missing.append((index, node_id))
    if missing:
        raise TourAnchorError(missing)
