"""Tests for emergentflow.research.report (Epic 16, Story 16) and its edge exporter,
emergentflow.codegen.export.export_report.
"""

from __future__ import annotations

import pandas as pd
import pytest

from emergentflow.api import is_inspectable
from emergentflow.codegen.export import export_report
from emergentflow.ir.common import Direction
from emergentflow.ir.graph import Graph
from emergentflow.ir.node import Node
from emergentflow.ir.params import Param
from emergentflow.ir.port import Port
from emergentflow.research.report import (
    Report,
    ReportMeta,
    Section,
    build_report,
    section_from_value,
    sections_from_values,
)
from emergentflow.research.reproducibility import capture_run
from emergentflow.viz.models import PlotSpec


def test_section_from_value_detects_table():
    frame = pd.DataFrame({"a": [1]})
    section = section_from_value(frame, title="t")
    assert section.kind == "table"


def test_section_from_value_detects_figure():
    spec = PlotSpec(chart="scatter", spec={"data": [], "layout": {}})
    section = section_from_value(spec, title="t")
    assert section.kind == "figure"


def test_section_from_value_detects_html():
    section = section_from_value("<!doctype html><html></html>", title="t")
    assert section.kind == "html"


def test_section_from_value_detects_markdown():
    section = section_from_value("just some text", title="t")
    assert section.kind == "markdown"


def test_section_from_value_explicit_kind_overrides_detection():
    section = section_from_value("looks like markdown", title="t", kind="html")
    assert section.kind == "html"


def test_section_from_value_unrecognized_type_without_kind_raises():
    with pytest.raises(TypeError):
        section_from_value(object(), title="t")


def test_section_rejects_unknown_kind():
    with pytest.raises(ValueError):
        Section(kind="not-a-real-kind", title="t", content="x")


def test_sections_from_values_default_titles():
    sections = sections_from_values(["a", "b", "c"])
    assert [s.title for s in sections] == ["Section 1", "Section 2", "Section 3"]


def test_sections_from_values_explicit_titles_and_kinds():
    sections = sections_from_values(
        ["plain text", "<!doctype html><html></html>"],
        titles=["First", "Second"],
        kinds=[None, "markdown"],
    )
    assert sections[0].title == "First"
    assert sections[0].kind == "markdown"
    assert sections[1].title == "Second"
    # explicit kind="markdown" overrides the html-shaped content's auto-detection
    assert sections[1].kind == "markdown"


def test_sections_from_values_short_titles_list_falls_back_per_index():
    sections = sections_from_values(["a", "b"], titles=["Only First"])
    assert sections[0].title == "Only First"
    assert sections[1].title == "Section 2"


def test_build_report_composes_all_kinds():
    meta = ReportMeta(title="Full Report", author="Ada", description="desc")
    sections = [
        section_from_value("markdown text", title="Intro"),
        section_from_value(pd.DataFrame({"x": [1, 2]}), title="A table"),
        section_from_value(
            PlotSpec(chart="scatter", spec={"data": [], "layout": {}}), title="A figure"
        ),
    ]
    report = build_report(sections=sections, meta=meta)
    assert isinstance(report, Report)
    assert "<h1>Full Report</h1>" in report.html
    assert "Intro" in report.html
    assert "<table" in report.html
    assert "plotspec-json" in report.html
    assert report.pdf_bytes is None


def test_build_report_result_is_inspectable():
    report = build_report(sections=[section_from_value("x", title="t")], meta=ReportMeta(title="t"))
    assert is_inspectable(report) is True


def test_export_report_writes_html(tmp_path):
    report = build_report(
        sections=[section_from_value("hello", title="t")], meta=ReportMeta(title="My Export")
    )
    result = export_report(report, tmp_path)
    assert result.html_path.exists()
    assert result.html_path.read_text(encoding="utf-8") == report.html
    assert result.pdf_path is None


def test_export_report_writes_pdf_when_present(tmp_path):
    report = build_report(
        sections=[section_from_value("hello", title="t")], meta=ReportMeta(title="t")
    )
    # Manually attach fake PDF bytes (bypassing render_pdf=True, which needs weasyprint) to
    # exercise export_report's PDF-writing branch in isolation.
    report_with_pdf = Report(
        meta=report.meta, sections=report.sections, html=report.html, pdf_bytes=b"%PDF-fake"
    )
    result = export_report(report_with_pdf, tmp_path)
    assert result.pdf_path is not None
    assert result.pdf_path.read_bytes() == b"%PDF-fake"


def test_export_report_is_idempotent_overwrite(tmp_path):
    meta = ReportMeta(title="Same Name")
    r1 = build_report(sections=[section_from_value("first", title="t")], meta=meta)
    r2 = build_report(sections=[section_from_value("second", title="t")], meta=meta)
    export_report(r1, tmp_path)
    result2 = export_report(r2, tmp_path)
    assert "second" in result2.html_path.read_text(encoding="utf-8")


def test_build_report_embeds_reproducibility_as_a_section():
    loader = Node(
        id="load",
        type="data.load_csv",
        params=[Param(name="path", type_token="str", value="x.csv")],
        ports=[Port(id="p1", name="frame", direction=Direction.OUT, data_type="DataFrame")],
    )
    graph = Graph(nodes={"load": loader}, edges={})
    capture = capture_run(graph)

    report = build_report(
        sections=[section_from_value("intro", title="Intro")],
        meta=ReportMeta(title="With Repro"),
        reproducibility=capture,
    )
    assert len(report.sections) == 2
    repro_section = report.sections[-1]
    assert repro_section.kind == "model_summary"
    assert repro_section.title == "Reproducibility"
    assert repro_section.content is capture
    assert "Reproducibility" in report.html


def test_build_report_without_reproducibility_is_unchanged():
    report = build_report(
        sections=[section_from_value("intro", title="Intro")], meta=ReportMeta(title="No Repro")
    )
    assert len(report.sections) == 1
