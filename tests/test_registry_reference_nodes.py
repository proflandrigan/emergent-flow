"""Tests for declarative registration of the reference nodes.

Importing ``emergentflow.nodes`` pulls in the reference-node package, firing the
``@register`` decorators on all five Story 8 reference nodes and populating the
default ``registry``.  These tests assert that the end-to-end registration path
works correctly and that the registry public API is re-exported from
``emergentflow.nodes``.
"""

import subprocess
import sys

import emergentflow.nodes.examples  # noqa: F401 — import triggers registration
from emergentflow.nodes import registry
from emergentflow.nodes.examples import (
    Anova,
    GenerateHtmlSummary,
    ImputeMissing,
    LoadCsv,
    TrainClassifier,
)
from emergentflow.nodes.registry import NodeRegistry


class TestReferenceNodesRegistered:
    def test_reference_nodes_registered(self):
        """Both reference nodes are present in the default registry after import."""
        assert "data.load_csv" in registry
        assert "clean.impute_missing" in registry

    def test_importing_package_alone_registers_reference_nodes(self):
        """Importing only ``emergentflow.nodes`` (not ``.examples``) registers them.

        Runs in a fresh subprocess so no other test's ``import
        emergentflow.nodes.examples`` can mask the regression: ``emergentflow.nodes``
        must pull the reference nodes in on its own.
        """
        code = (
            "import emergentflow.nodes as n; "
            "assert 'data.load_csv' in n.registry, 'load_csv not registered'; "
            "assert 'clean.impute_missing' in n.registry, 'impute not registered'"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_get_returns_reference_class(self):
        """registry.get() returns the exact class objects, not copies."""
        assert registry.get("data.load_csv") is LoadCsv
        assert registry.get("clean.impute_missing") is ImputeMissing

    def test_by_family_data(self):
        """LoadCsv appears in the 'data' family listing."""
        assert LoadCsv in registry.by_family("data")

    def test_default_registry_validates_clean(self):
        """Reference nodes are well-formed; a fresh isolated registry validates clean."""
        fresh = NodeRegistry()
        fresh.register(LoadCsv)
        fresh.register(ImputeMissing)
        assert fresh.validate() == []

    def test_package_reexports(self):
        """All nine registry names are importable directly from emergentflow.nodes."""
        from emergentflow.nodes import (  # noqa: F401
            ENTRY_POINT_GROUP,
            NodeRegistry,
            by_family,
            by_port_type,
            discover,
            get,
            register,
            registry,
            validate,
        )

    def test_all_five_families_registered(self):
        """All five Story 8 reference node types are present in the default registry."""
        expected_types = {
            "data.load_csv",
            "clean.impute_missing",
            "stats.anova",
            "ml.train_classifier",
            "reports.generate_html_summary",
        }
        assert all(t in registry for t in expected_types)

        assert registry.get("stats.anova") is Anova
        assert registry.get("ml.train_classifier") is TrainClassifier
        assert registry.get("reports.generate_html_summary") is GenerateHtmlSummary
