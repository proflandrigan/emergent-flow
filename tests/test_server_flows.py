"""Tests for the flow store (``emergentflow.server.flows``) and its routes.

Three groups:

- ``TestSlugify`` / ``TestFlowStore`` exercise ``FlowStore`` in isolation against a
  ``tmp_path`` directory -- no HTTP, no app.
- ``TestFlowRoutes`` exercises the ``/flows*`` routes wired into
  ``emergentflow.server.app`` through a real ``TestClient``, with the process-wide
  ``get_default_flows`` singleton monkeypatched to a tmp-backed store per test so
  nothing leaks between tests or pollutes the real on-disk default.
- ``TestExamplesRoute`` exercises the ``/examples*`` routes against the repo's real
  ``examples/`` directory.
"""

from __future__ import annotations

import sys
import time

import pytest
from fastapi.testclient import TestClient

from emergentflow.server.app import app
from emergentflow.server.flows import (
    FlowAlreadyExistsError,
    FlowStore,
    InvalidSlugError,
    UnknownFlowError,
    slugify,
)

# The server __init__.py re-exports `app` (the FastAPI instance) as a package attribute,
# so `import emergentflow.server.app as app_module` resolves to the FastAPI object, not
# the module. Access the module through sys.modules instead.
app_module = sys.modules["emergentflow.server.app"]


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("My Cool Flow") == "my-cool-flow"

    def test_special_chars(self) -> None:
        assert slugify("Flow #1 (test)") == "flow-1-test"

    def test_empty(self) -> None:
        assert slugify("") == "untitled"

    def test_all_punctuation(self) -> None:
        assert slugify("---!!!") == "untitled"

    def test_whitespace(self) -> None:
        assert slugify("  hello  world  ") == "hello-world"


class TestFlowStore:
    def test_list_empty(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        assert store.list() == []

    def test_save_and_get(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        graph = {"name": "Test Flow", "paradigm": "functional", "nodes": {}, "edges": {}}
        store.save("test-flow", graph)
        result = store.get("test-flow")
        assert result == graph

    def test_save_creates_file(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        graph = {"name": "Test", "nodes": {}, "edges": {}}
        store.save("test", graph)
        assert (tmp_path / "test.ef.json").is_file()

    def test_save_overwrites(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("test", {"name": "v1", "nodes": {}, "edges": {}})
        store.save("test", {"name": "v2", "nodes": {}, "edges": {}})
        assert store.get("test")["name"] == "v2"

    def test_list_returns_entries(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("a", {"name": "Alpha", "nodes": {}, "edges": {}})
        store.save("b", {"name": "Beta", "nodes": {}, "edges": {}})
        entries = store.list()
        assert len(entries) == 2
        slugs = {e["slug"] for e in entries}
        assert slugs == {"a", "b"}
        for entry in entries:
            assert "slug" in entry
            assert "name" in entry
            assert "updated_at" in entry

    def test_list_sorted_newest_first(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("old", {"name": "Old", "nodes": {}, "edges": {}})
        time.sleep(0.05)  # ensure distinct mtimes
        store.save("new", {"name": "New", "nodes": {}, "edges": {}})
        entries = store.list()
        assert entries[0]["slug"] == "new"
        assert entries[1]["slug"] == "old"

    def test_get_unknown_raises(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        with pytest.raises(UnknownFlowError):
            store.get("nonexistent")

    def test_delete(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("doomed", {"name": "Doomed", "nodes": {}, "edges": {}})
        store.delete("doomed")
        assert store.list() == []
        with pytest.raises(UnknownFlowError):
            store.get("doomed")

    def test_delete_unknown_raises(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        with pytest.raises(UnknownFlowError):
            store.delete("ghost")

    def test_rename(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("old-name", {"name": "Flow", "nodes": {}, "edges": {}})
        result = store.rename("old-name", "new-name")
        assert result == {"slug": "new-name", "status": "ok"}
        assert store.get("new-name")["name"] == "Flow"
        with pytest.raises(UnknownFlowError):
            store.get("old-name")

    def test_rename_unknown_source_raises(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        with pytest.raises(UnknownFlowError):
            store.rename("ghost", "new")

    def test_rename_target_exists_raises(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("a", {"name": "A", "nodes": {}, "edges": {}})
        store.save("b", {"name": "B", "nodes": {}, "edges": {}})
        with pytest.raises(FlowAlreadyExistsError):
            store.rename("a", "b")

    def test_rename_to_same_slug_is_a_no_op_not_a_conflict(self, tmp_path) -> None:
        # A display-name-only edit that slugifies to the same slug (e.g. "my flow" ->
        # "My Flow", both -> "my-flow") must not be reported as a conflict against itself --
        # the "already exists" file IS the source file.
        store = FlowStore(tmp_path)
        store.save("my-flow", {"name": "my flow", "nodes": {}, "edges": {}})
        result = store.rename("my-flow", "my-flow")
        assert result == {"slug": "my-flow", "status": "ok"}
        assert store.get("my-flow")["name"] == "my flow"

    def test_list_skips_corrupt_json(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("good", {"name": "Good", "nodes": {}, "edges": {}})
        (tmp_path / "bad.ef.json").write_text("NOT JSON", encoding="utf-8")
        entries = store.list()
        assert len(entries) == 1
        assert entries[0]["slug"] == "good"

    def test_creates_root_dir(self, tmp_path) -> None:
        sub = tmp_path / "flows" / "nested"
        FlowStore(sub)
        assert sub.is_dir()

    # Regression tests for a path-traversal fix: every FlowStore method resolves a slug to a
    # path via `_path()`. Before the fix, `rename()` had no such guard -- proven concretely:
    # `store.rename("legit", "../evil")` moved the flow file to
    # `root.parent / "evil.ef.json"`, i.e. outside the store entirely, via the underlying
    # `os.replace()`. `save()` happened to be accidentally shielded (its atomic-write temp
    # file is created with a `.{slug}-` prefix, which breaks a leading ".." into an inert
    # "..."), but that was luck, not a guarantee -- `_path()` now rejects any slug that isn't
    # shaped like `slugify()`'s own output, closing the hole for every method uniformly.
    @pytest.mark.parametrize(
        "evil_slug",
        [
            "../evil",
            "../../../../tmp/evil",
            "a/b",
            "a/../../evil",
            "",
            "UPPER",
            "has spaces",
            ".",
            "..",
        ],
    )
    def test_path_rejects_traversal_and_malformed_slugs(self, tmp_path, evil_slug) -> None:
        store = FlowStore(tmp_path)
        with pytest.raises(InvalidSlugError):
            store.get(evil_slug)
        with pytest.raises(InvalidSlugError):
            store.save(evil_slug, {"name": "x", "nodes": {}, "edges": {}})
        with pytest.raises(InvalidSlugError):
            store.delete(evil_slug)

    def test_rename_rejects_traversal_in_new_slug(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        store.save("legit", {"name": "Legit", "nodes": {}, "edges": {}})
        with pytest.raises(InvalidSlugError):
            store.rename("legit", "../evil")
        # The flow must be untouched -- the rejected rename must not have partially applied.
        assert store.get("legit")["name"] == "Legit"
        assert not (tmp_path.parent / "evil.ef.json").exists()

    def test_rename_rejects_traversal_in_old_slug(self, tmp_path) -> None:
        store = FlowStore(tmp_path)
        with pytest.raises(InvalidSlugError):
            store.rename("../whatever", "new")


@pytest.fixture
def flow_client(tmp_path, monkeypatch) -> TestClient:
    """A TestClient wired to a tmp-backed FlowStore in place of the process singleton.

    ``app.py`` imports ``get_default_flows`` by name (``from ... import get_default_flows``)
    and calls the bare name inside each route, so the routes resolve it out of
    ``emergentflow.server.app``'s module namespace -- patch it there, not on
    ``emergentflow.server.flows``.
    """
    store = FlowStore(tmp_path / "flows")
    monkeypatch.setattr(app_module, "get_default_flows", lambda: store)
    return TestClient(app)


class TestFlowRoutes:
    def test_list_empty(self, flow_client: TestClient) -> None:
        r = flow_client.get("/flows")
        assert r.status_code == 200
        assert r.json() == {"flows": []}

    def test_create_and_get(self, flow_client: TestClient) -> None:
        graph = {"name": "Test", "paradigm": "functional", "nodes": {}, "edges": {}}
        r = flow_client.post("/flows", json={"graph": graph, "slug": "test"})
        assert r.status_code == 200
        assert r.json()["slug"] == "test"

        r = flow_client.get("/flows/test")
        assert r.status_code == 200
        assert r.json()["name"] == "Test"

    def test_create_without_slug_derives_from_name(self, flow_client: TestClient) -> None:
        graph = {"name": "My Cool Flow", "nodes": {}, "edges": {}}
        r = flow_client.post("/flows", json={"graph": graph})
        assert r.status_code == 200
        assert r.json()["slug"] == "my-cool-flow"

    # Regression test: `graph["name"]` is client-controlled, untyped JSON. A non-string,
    # truthy value (a number, a list, `true`) used to reach `slugify()` unguarded --
    # `slugify()` calls `.strip()` on it, which raised an uncaught `AttributeError` and made
    # this route return a bare 500 instead of a handled error response.
    @pytest.mark.parametrize("bad_name", [123, True, ["a", "list"], {"nested": "dict"}])
    def test_create_with_non_string_name_falls_back_to_untitled(
        self, flow_client: TestClient, bad_name
    ) -> None:
        graph = {"name": bad_name, "nodes": {}, "edges": {}}
        r = flow_client.post("/flows", json={"graph": graph})
        assert r.status_code == 200
        assert r.json()["slug"] == "untitled"

    def test_create_with_null_name_falls_back_to_untitled(self, flow_client: TestClient) -> None:
        graph = {"name": None, "nodes": {}, "edges": {}}
        r = flow_client.post("/flows", json={"graph": graph})
        assert r.status_code == 200
        assert r.json()["slug"] == "untitled"

    def test_update(self, flow_client: TestClient) -> None:
        graph = {"name": "v1", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "test"})
        graph2 = {"name": "v2", "nodes": {}, "edges": {}}
        r = flow_client.put("/flows/test", json={"graph": graph2})
        assert r.status_code == 200
        assert flow_client.get("/flows/test").json()["name"] == "v2"

    def test_delete(self, flow_client: TestClient) -> None:
        graph = {"name": "Test", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "doomed"})
        r = flow_client.delete("/flows/doomed")
        assert r.status_code == 200
        assert flow_client.get("/flows/doomed").status_code == 404

    def test_rename(self, flow_client: TestClient) -> None:
        graph = {"name": "Test", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "old"})
        r = flow_client.post("/flows/old/rename", json={"new_slug": "new"})
        assert r.status_code == 200
        assert r.json()["slug"] == "new"
        assert flow_client.get("/flows/new").status_code == 200
        assert flow_client.get("/flows/old").status_code == 404

    def test_get_unknown_returns_404(self, flow_client: TestClient) -> None:
        r = flow_client.get("/flows/nope")
        assert r.status_code == 404

    def test_delete_unknown_returns_404(self, flow_client: TestClient) -> None:
        r = flow_client.delete("/flows/nope")
        assert r.status_code == 404

    def test_rename_unknown_returns_404(self, flow_client: TestClient) -> None:
        r = flow_client.post("/flows/nope/rename", json={"new_slug": "whatever"})
        assert r.status_code == 404

    def test_create_missing_graph_returns_400(self, flow_client: TestClient) -> None:
        r = flow_client.post("/flows", json={"not_graph": 1})
        assert r.status_code == 400

    def test_update_missing_graph_returns_400(self, flow_client: TestClient) -> None:
        r = flow_client.put("/flows/test", json={"not_graph": 1})
        assert r.status_code == 400

    def test_rename_missing_new_slug_returns_400(self, flow_client: TestClient) -> None:
        graph = {"name": "Test", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "old"})
        r = flow_client.post("/flows/old/rename", json={})
        assert r.status_code == 400

    def test_rename_conflict_returns_409(self, flow_client: TestClient) -> None:
        graph = {"name": "A", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "a"})
        flow_client.post("/flows", json={"graph": graph, "slug": "b"})
        r = flow_client.post("/flows/a/rename", json={"new_slug": "b"})
        assert r.status_code == 409

    # Regression test: renaming a slug to itself (the case a display-name-only edit that
    # happens to slugify identically produces, e.g. "my flow" -> "My Flow") must succeed as
    # a no-op, not report a false 409 conflict against its own file.
    def test_rename_to_same_slug_returns_200(self, flow_client: TestClient) -> None:
        graph = {"name": "my flow", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "my-flow"})
        r = flow_client.post("/flows/my-flow/rename", json={"new_slug": "my-flow"})
        assert r.status_code == 200
        assert r.json()["slug"] == "my-flow"
        assert flow_client.get("/flows/my-flow").status_code == 200

    # Regression test for a path-traversal fix (see TestFlowStore's traversal tests): a
    # request-body `new_slug` reaches FlowStore.rename() unvalidated by this route, so the
    # store itself must be the thing that rejects it. Before the fix this call moved the
    # saved flow file to a directory outside the flow store's root via `os.replace()`.
    def test_rename_rejects_path_traversal_returns_400(self, flow_client: TestClient) -> None:
        graph = {"name": "Legit", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "legit"})
        r = flow_client.post("/flows/legit/rename", json={"new_slug": "../evil"})
        assert r.status_code == 400
        # The original flow must still be there, untouched, under its original slug.
        assert flow_client.get("/flows/legit").status_code == 200

    def test_create_rejects_path_traversal_slug_returns_400(self, flow_client: TestClient) -> None:
        graph = {"name": "Test", "nodes": {}, "edges": {}}
        r = flow_client.post("/flows", json={"graph": graph, "slug": "../../etc/evil"})
        assert r.status_code == 400

    def test_get_rejects_malformed_slug_returns_400(self, flow_client: TestClient) -> None:
        r = flow_client.get("/flows/Not%20A%20Slug")
        assert r.status_code == 400

    def test_list_reflects_created_flows(self, flow_client: TestClient) -> None:
        graph = {"name": "A", "nodes": {}, "edges": {}}
        flow_client.post("/flows", json={"graph": graph, "slug": "a"})
        r = flow_client.get("/flows")
        assert r.status_code == 200
        slugs = {entry["slug"] for entry in r.json()["flows"]}
        assert slugs == {"a"}


class TestExamplesRoute:
    def test_list_examples(self) -> None:
        client = TestClient(app)
        r = client.get("/examples")
        assert r.status_code == 200
        data = r.json()
        assert "examples" in data
        # The repo has example JSON files; at minimum functional_pipeline.json exists.
        names = [e["name"] for e in data["examples"]]
        assert any("Functional" in n for n in names)

    def test_get_example_by_path(self) -> None:
        client = TestClient(app)
        r = client.get("/examples")
        examples = r.json()["examples"]
        assert examples
        first_path = examples[0]["path"]
        r = client.get(f"/examples/{first_path}")
        assert r.status_code == 200
        assert "nodes" in r.json()

    def test_get_nonexistent_example(self) -> None:
        client = TestClient(app)
        r = client.get("/examples/does-not-exist.json")
        assert r.status_code == 404

    # The traversal guard in get_example() (`target.is_relative_to(_EXAMPLES_DIR)`) was
    # already correct pre-fix; this test just closes the coverage gap the task flagged
    # ("directory traversal on /examples is guarded -- verify it's correct"). A *literal*
    # "../pyproject.toml" gets collapsed by the HTTP client before the request is even sent
    # (so it never reaches `_EXAMPLES_DIR`'s handler at all -- it'd hit the unrelated
    # catch-all static route instead), so this uses a percent-encoded ".." to exercise the
    # handler's own `resolve()` + `is_relative_to()` check directly.
    def test_get_example_rejects_path_traversal(self) -> None:
        client = TestClient(app)
        r = client.get("/examples/%2e%2e/pyproject.toml")
        assert r.status_code == 404
        assert "example not found" in r.json()["error"]

    def test_get_example_rejects_absolute_path_escape(self) -> None:
        client = TestClient(app)
        r = client.get("/examples/foo/%2e%2e/%2e%2e/pyproject.toml")
        assert r.status_code == 404
        assert "example not found" in r.json()["error"]
