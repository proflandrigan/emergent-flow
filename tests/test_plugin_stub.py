"""Tests for the out-of-core plugin stub (examples/plugin_stub).

The stub package is NOT installed in the test environment; we make it
importable by inserting its root directory at the front of sys.path before
importing from it.
"""

import importlib.metadata
import sys
from pathlib import Path

STUB = Path(__file__).resolve().parent.parent / "examples" / "plugin_stub"
sys.path.insert(0, str(STUB))

from ef_texttools.nodes import ReverseText  # noqa: E402

from emergentflow.nodes.registry import NodeRegistry  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers (mirror the _run_codegen pattern from test_reference_nodes.py)
# ---------------------------------------------------------------------------


def _run_codegen(definition, node, scope):
    """exec a node's preview fragment in *scope* and return the updated scope."""
    frag = definition.preview(node)
    exec(frag.render(), scope)  # noqa: S102 — test-only, on our own emitted code
    return scope


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStubConformsToContract:
    def test_to_spec_type(self):
        """ReverseText().to_spec().type must equal 'text.reverse'."""
        assert ReverseText().to_spec().type == "text.reverse"

    def test_register_and_get(self):
        """A fresh NodeRegistry can register ReverseText and look it up."""
        reg = NodeRegistry()
        reg.register(ReverseText)
        assert "text.reverse" in reg
        assert reg.get("text.reverse") is ReverseText


class TestStubExecute:
    def test_reverses_string(self):
        """execute({'text': 'abc'}) returns {'text': 'cba'}."""
        node = ReverseText().instantiate()
        result = ReverseText().execute(node, {"text": "abc"})
        assert result["text"] == "cba"

    def test_empty_string(self):
        """execute with an empty string returns an empty string."""
        node = ReverseText().instantiate()
        result = ReverseText().execute(node, {"text": ""})
        assert result["text"] == ""


class TestStubCodegenMatchesExecute:
    def test_adr_0002_equivalence(self):
        """ADR-0002: executing the emitted codegen fragment agrees with execute."""
        defn = ReverseText()
        node = defn.instantiate()
        executed = defn.execute(node, {"text": "abc"})
        # The emitted fragment reads from 'text' in scope and writes back to 'text'.
        scope = {"text": "abc"}
        _run_codegen(defn, node, scope)
        assert scope["text"] == executed["text"]


class TestDiscoveredViaEntryPoint:
    def test_discover_registers_stub(self, monkeypatch):
        """Simulating the installed entry point: discover() wires in text.reverse."""

        class _StubEP:
            name = "text_reverse"
            value = "ef_texttools.nodes:ReverseText"

            def load(self):
                return ReverseText

        def fake_entry_points(*, group):
            return [_StubEP()]

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        reg = NodeRegistry()
        problems = reg.discover()
        assert problems == []
        assert "text.reverse" in reg


class TestEntryPointDeclaredInPyproject:
    def test_pyproject_contains_entry_point_group(self):
        """The stub pyproject.toml declares the emergentflow.nodes entry-point group."""
        pyproject = STUB / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        assert '[project.entry-points."emergentflow.nodes"]' in text

    def test_pyproject_names_reversetext(self):
        """The stub pyproject.toml points at ef_texttools.nodes:ReverseText."""
        pyproject = STUB / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        assert "ef_texttools.nodes:ReverseText" in text
