"""
tests/test_collab_review.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Epic 14, Story 6 -- review-thread models and SessionStore methods (part 1: no HTTP routes yet,
those are a separate task). Findings anchor to real graph elements; the store rejects an
unanchored finding rather than storing a review that points at nothing.
"""

from __future__ import annotations

import pytest

from emergentflow.codegen.validation import Diagnostic, Severity
from emergentflow.collab.review import (
    AnchorError,
    ReviewComment,
    ReviewStatus,
    ReviewThread,
    validate_anchors,
)
from emergentflow.collab.session import SessionStore, UnknownReviewError, UnknownSessionError
from emergentflow.ir.common import Direction
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.ir.port import Port


def _graph_with_one_node() -> Graph:
    node = Node(
        id="n1",
        type="data.load_csv",
        ports=[Port(id="p1", name="frame", direction=Direction.OUT, data_type="DataFrame")],
    )
    return Graph(nodes={"n1": node}, edges={})


class TestReviewThreadModel:
    def test_defaults(self) -> None:
        thread = ReviewThread(author="ml_engineer")
        assert thread.status == ReviewStatus.OPEN
        assert thread.findings == []
        assert thread.comments == []
        assert thread.fix is None

    def test_round_trips_through_json(self) -> None:
        thread = ReviewThread(
            author="ml_engineer",
            findings=[
                Diagnostic(severity=Severity.WARNING, code="w1", message="check this", node_id="n1")
            ],
        )
        dumped = thread.model_dump(mode="json")
        restored = ReviewThread.model_validate(dumped)
        assert restored == thread


class TestValidateAnchors:
    def test_passes_for_a_finding_with_no_anchor(self) -> None:
        validate_anchors(
            _graph_with_one_node(), [Diagnostic(severity=Severity.INFO, code="c", message="m")]
        )

    def test_passes_for_a_finding_anchored_to_a_real_node(self) -> None:
        validate_anchors(
            _graph_with_one_node(),
            [Diagnostic(severity=Severity.WARNING, code="w", message="m", node_id="n1")],
        )

    def test_rejects_a_finding_anchored_to_an_unknown_node(self) -> None:
        with pytest.raises(AnchorError):
            validate_anchors(
                _graph_with_one_node(),
                [
                    Diagnostic(
                        severity=Severity.WARNING, code="w", message="m", node_id="does-not-exist"
                    )
                ],
            )

    def test_rejects_a_finding_anchored_to_an_unknown_port(self) -> None:
        with pytest.raises(AnchorError):
            validate_anchors(
                _graph_with_one_node(),
                [
                    Diagnostic(
                        severity=Severity.WARNING, code="w", message="m", port_id="does-not-exist"
                    )
                ],
            )


class TestSessionStoreReviews:
    def test_add_review_stores_and_returns_the_thread(self) -> None:
        store = SessionStore()
        session = store.create(_graph_with_one_node())
        thread = ReviewThread(
            author="ml_engineer",
            findings=[
                Diagnostic(severity=Severity.INFO, code="c", message="looks fine", node_id="n1")
            ],
        )

        result = store.add_review(session.id, thread)

        assert result.id == thread.id
        assert store.get(session.id).collab.reviews[thread.id].author == "ml_engineer"

    def test_add_review_rejects_an_unanchored_finding(self) -> None:
        store = SessionStore()
        session = store.create(_graph_with_one_node())
        thread = ReviewThread(
            author="ml_engineer",
            findings=[
                Diagnostic(severity=Severity.WARNING, code="w", message="m", node_id="ghost")
            ],
        )

        with pytest.raises(AnchorError):
            store.add_review(session.id, thread)

    def test_add_review_unknown_session_raises(self) -> None:
        store = SessionStore()
        with pytest.raises(UnknownSessionError):
            store.add_review("no-such-session", ReviewThread(author="x"))

    def test_add_review_comment_appends_and_returns_the_thread(self) -> None:
        store = SessionStore()
        session = store.create(_graph_with_one_node())
        thread = store.add_review(session.id, ReviewThread(author="ml_engineer"))

        result = store.add_review_comment(
            session.id, thread.id, ReviewComment(author="human", text="thanks, fixing now")
        )

        assert len(result.comments) == 1
        assert result.comments[0].text == "thanks, fixing now"

    def test_add_review_comment_unknown_review_raises(self) -> None:
        store = SessionStore()
        session = store.create(_graph_with_one_node())
        with pytest.raises(UnknownReviewError):
            store.add_review_comment(
                session.id, "no-such-review", ReviewComment(author="human", text="hi")
            )

    def test_review_added_event_is_published(self) -> None:
        store = SessionStore()
        session = store.create(_graph_with_one_node())
        q = store.subscribe(session.id)

        thread = store.add_review(session.id, ReviewThread(author="ml_engineer"))

        event = q.get(timeout=1.0)
        assert event == {"type": "review_added", "session_id": session.id, "review_id": thread.id}

    def test_review_comment_added_event_is_published(self) -> None:
        store = SessionStore()
        session = store.create(_graph_with_one_node())
        thread = store.add_review(session.id, ReviewThread(author="ml_engineer"))
        q = store.subscribe(session.id)

        comment = store.add_review_comment(
            session.id, thread.id, ReviewComment(author="human", text="ok")
        ).comments[-1]

        event = q.get(timeout=1.0)
        assert event == {
            "type": "review_comment_added",
            "session_id": session.id,
            "review_id": thread.id,
            "comment_id": comment.id,
        }
