"""Tests for the built-in type catalog and the out-of-core type plugin stub."""

import importlib.metadata
import sys
from pathlib import Path

from emergentflow.types import registry
from emergentflow.types.compatibility import Compatibility, is_compatible
from emergentflow.types.registry import TOP_TYPE, TypeDef, TypeRegistry

STUB = Path(__file__).resolve().parent.parent / "examples" / "type_plugin_stub"
sys.path.insert(0, str(STUB))

from ef_timeseries.types import TIMESERIES  # noqa: E402


class TestBuiltinCatalog:
    def test_builtin_tokens_registered(self):
        tokens = {
            "any",
            "DataFrame",
            "ClassifierResult",
            "AnovaResult",
            "HTML",
            "Tensor",
            "Model",
            "Transformer",
        }
        for token in tokens:
            assert registry.is_registered(token)

    def test_builtins_are_subtypes_of_any(self):
        builtin_tokens = {
            "DataFrame",
            "ClassifierResult",
            "AnovaResult",
            "HTML",
            "Tensor",
            "Model",
            "Transformer",
        }
        for token in builtin_tokens:
            assert registry.is_subtype(token, TOP_TYPE)

    def test_builtins_not_subtypes_of_each_other(self):
        assert not registry.is_subtype("Transformer", "Model")
        assert not registry.is_subtype("Model", "Transformer")

    def test_builtin_catalog_has_exactly_one_declared_subtype_edge(self):
        # The built-in catalog carries exactly one explicit subtype edge --
        # DocumentFrame <: DataFrame (Epic 16, Story 22). Every other built-in token
        # relates to the others only implicitly, via "any".
        type_dict = registry.to_dict()
        subtypes = type_dict["subtypes"]
        assert subtypes == [["DocumentFrame", "DataFrame"]]


class TestEpic16TypeWiring:
    def test_document_frame_is_a_dataframe_subtype(self):
        assert registry.is_subtype("DocumentFrame", "DataFrame") is True

    def test_document_frame_wires_into_a_dataframe_port(self):
        assert is_compatible("DocumentFrame", "DataFrame").verdict is Compatibility.COMPATIBLE

    def test_dataframe_does_not_wire_into_a_document_frame_port(self):
        # The edge is one-directional.
        assert is_compatible("DataFrame", "DocumentFrame").verdict is Compatibility.INCOMPATIBLE

    def test_report_does_not_wire_into_a_dataframe_port(self):
        assert is_compatible("Report", "DataFrame").verdict is Compatibility.INCOMPATIBLE

    def test_report_wires_into_a_wildcard_port(self):
        # This is how the research.build_report node's variadic sections IN port
        # accepts it.
        assert is_compatible("Report", "any").verdict is Compatibility.COMPATIBLE

    def test_lineage_is_inspect_only(self):
        assert is_compatible("Lineage", "DataFrame").verdict is Compatibility.INCOMPATIBLE
        assert is_compatible("Lineage", "Report").verdict is Compatibility.INCOMPATIBLE
        assert is_compatible("Lineage", "DocumentFrame").verdict is Compatibility.INCOMPATIBLE
        assert is_compatible("Lineage", "any").verdict is Compatibility.COMPATIBLE

    def test_epic16_tokens_are_registered(self):
        for token in ("Report", "Lineage", "DocumentFrame"):
            assert registry.is_registered(token)


class TestTypePluginStub:
    def test_stub_typedef_shape(self):
        assert TIMESERIES.token == "TimeSeries"
        assert TIMESERIES.supertypes == ("DataFrame",)

    def test_discover_registers_stub(self, monkeypatch):
        class _StubEP:
            name = "time_series"
            value = "ef_timeseries.types:TIMESERIES"

            def load(self):
                return TIMESERIES

        def fake_entry_points(*, group):
            return [_StubEP()] if group == "emergentflow.types" else []

        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
        reg = TypeRegistry()
        reg.register(TypeDef(token="DataFrame"))
        problems = reg.discover()
        assert problems == []
        assert "TimeSeries" in reg
        assert reg.is_subtype("TimeSeries", "DataFrame") is True
        assert reg.is_subtype("TimeSeries", TOP_TYPE) is True


class TestPluginPyproject:
    def test_pyproject_declares_entry_point_group(self):
        text = (STUB / "pyproject.toml").read_text(encoding="utf-8")
        assert '[project.entry-points."emergentflow.types"]' in text

    def test_pyproject_names_timeseries(self):
        text = (STUB / "pyproject.toml").read_text(encoding="utf-8")
        assert "ef_timeseries.types:TIMESERIES" in text
