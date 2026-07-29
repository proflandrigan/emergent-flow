"""
emergentflow.research.report
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Multi-section report builder (Epic 16, Story 16).

A ``Report`` composes ordered ``Section``s -- markdown text, an already-rendered HTML
fragment, a ``PlotSpec`` figure, a tidy DataFrame table, or a dataclass "model summary" (e.g.
``TTestResult``, ``CrosstabResult``, a traced ``Lineage``) -- into one document. ``build_report``
is a pure function: given the same ``sections``/``meta``/``render_pdf`` it always returns the
same ``Report``, with the HTML render computed inline (no wall-clock/filesystem/network
access). ``render_pdf=True`` additionally renders PDF bytes via weasyprint (the optional
``[report-pdf]`` extra).
"""

from __future__ import annotations

import dataclasses as _dc
import html as _html
import importlib.util
import json as _json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from emergentflow.api import public_op
from emergentflow.research.errors import MissingOptionalDependencyError
from emergentflow.research.reproducibility import ReproducibilityCapture
from emergentflow.viz.models import PlotSpec

__all__ = [
    "SECTION_KINDS",
    "Section",
    "ReportMeta",
    "Report",
    "build_report",
    "section_from_value",
    "sections_from_values",
]

SECTION_KINDS = ("markdown", "html", "figure", "table", "model_summary")


@dataclass
class Section:
    """One section of a composed report.

    Attributes
    ----------
    kind: one of SECTION_KINDS.
    title: display title for this section.
    content: the section's payload -- a ``str`` for "markdown"/"html", a
        :class:`~emergentflow.viz.models.PlotSpec` for "figure", a ``pandas.DataFrame`` for
        "table", or any ``@dataclass`` instance for "model_summary" (e.g. a stats result, a
        traced ``Lineage``).
    """

    kind: str
    title: str
    content: Any

    def __post_init__(self) -> None:
        if self.kind not in SECTION_KINDS:
            raise ValueError(f"Section.kind {self.kind!r} is not one of {SECTION_KINDS!r}.")


@dataclass
class ReportMeta:
    """Caller-supplied report metadata. No field here is ever populated by reading the wall
    clock or the environment inside ``build_report`` -- that would break purity; a caller who
    wants a timestamp passes one in explicitly."""

    title: str
    author: str | None = None
    generated_at: str | None = None
    description: str | None = None


@dataclass
class Report:
    """A composed, multi-section report (Epic 16, Story 16).

    Attributes
    ----------
    meta: the caller-supplied :class:`ReportMeta`.
    sections: the ordered sections composing this report.
    html: the rendered, self-contained HTML document (base install).
    pdf_bytes: the rendered PDF, or ``None`` unless ``build_report(..., render_pdf=True)`` was
        used (``[report-pdf]`` extra only). Not JSON-serializable -- degrades to
        ``{"kind": "unsupported"}`` on the result-payload contract (mirrors
        ``FittedStatsModel.results``), never rendered directly by the payload contract.
    """

    meta: ReportMeta
    sections: list[Section] = field(default_factory=list)
    html: str = ""
    pdf_bytes: bytes | None = None


def _escape(text: str) -> str:
    return _html.escape(text)


def _render_markdown_block(content: str) -> str:
    """A minimal, dependency-free markdown-ish renderer: blank-line-separated paragraphs, each
    HTML-escaped with internal newlines as <br>. Not a full markdown parser -- the project has
    no markdown-rendering hard dependency, and adding one is out of scope for this task."""
    paragraphs = [p for p in content.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{_escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs)


def _render_section_html(section: Section) -> str:
    header = f"<h2>{_escape(section.title)}</h2>"
    if section.kind == "markdown":
        body = _render_markdown_block(str(section.content))
    elif section.kind == "html":
        body = str(section.content)
    elif section.kind == "figure":
        spec = section.content
        if not isinstance(spec, PlotSpec):
            raise TypeError(
                f"Section {section.title!r} has kind='figure' but content is "
                f"{type(spec).__name__}, not a PlotSpec."
            )
        body = (
            f'<pre class="plotspec-json" data-chart="{_escape(spec.chart)}">'
            f"{_escape(_json.dumps(spec.spec))}</pre>"
        )
    elif section.kind == "table":
        frame = section.content
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(
                f"Section {section.title!r} has kind='table' but content is "
                f"{type(frame).__name__}, not a DataFrame."
            )
        body = frame.to_html(index=False)
    elif section.kind == "model_summary":
        model = section.content
        if not _dc.is_dataclass(model) or isinstance(model, type):
            raise TypeError(
                f"Section {section.title!r} has kind='model_summary' but content is not a "
                f"dataclass instance (got {type(model).__name__})."
            )
        rows = []
        for f in _dc.fields(model):
            value = getattr(model, f.name)
            if isinstance(value, pd.DataFrame):
                cell = value.to_html(index=False)
            else:
                cell = f"<code>{_escape(str(value))}</code>"
            rows.append(f"<tr><th>{_escape(f.name)}</th><td>{cell}</td></tr>")
        body = f'<table class="model-summary">{"".join(rows)}</table>'
    else:  # pragma: no cover -- Section.__post_init__ already rejects unknown kinds
        raise ValueError(f"unhandled section kind {section.kind!r}")
    return f'<section class="section section-{section.kind}">{header}{body}</section>'


def _render_html(meta: ReportMeta, sections: list[Section]) -> str:
    body = "\n".join(_render_section_html(s) for s in sections)
    subtitle = (
        f'<p class="report-description">{_escape(meta.description)}</p>' if meta.description else ""
    )
    byline_parts = [p for p in (meta.author, meta.generated_at) if p]
    byline = (
        f'<p class="report-byline">{_escape(" | ".join(byline_parts))}</p>' if byline_parts else ""
    )
    return (
        "<!doctype html>\n"
        '<html><head><meta charset="utf-8">'
        f"<title>{_escape(meta.title)}</title></head>"
        f"<body><h1>{_escape(meta.title)}</h1>{subtitle}{byline}{body}</body></html>"
    )


def _render_pdf(html_doc: str) -> bytes:
    """Render *html_doc* to PDF bytes via weasyprint (``[report-pdf]`` extra only).

    Gated by ``importlib.util.find_spec`` *before* importing weasyprint, so a base install
    raises the typed :class:`MissingOptionalDependencyError` rather than an opaque
    ``ImportError``.
    """
    if importlib.util.find_spec("weasyprint") is None:
        raise MissingOptionalDependencyError("emergentflow[report-pdf]")
    import weasyprint

    result = weasyprint.HTML(string=html_doc).write_pdf()
    return bytes(result)


@public_op(name="ef.research.build_report")
def build_report(
    sections: list[Section],
    meta: ReportMeta,
    *,
    render_pdf: bool = False,
    reproducibility: ReproducibilityCapture | None = None,
) -> Report:
    """Compose *sections* (in order) into one :class:`Report`, with the HTML rendered inline.

    Pure given the same ``render_pdf``/``reproducibility`` arguments: the same
    ``sections``/``meta``/``render_pdf``/``reproducibility`` always yields the same ``Report``
    -- no wall-clock or network access. ``render_pdf=True`` additionally renders ``pdf_bytes``
    via weasyprint (``[report-pdf]`` extra only); a base install raises
    :class:`~emergentflow.research.errors.MissingOptionalDependencyError`.
    ``render_pdf=False`` (the default) leaves ``pdf_bytes`` as ``None`` and needs no optional
    dependency, exactly as before. When ``reproducibility`` is given (e.g. the result of
    ``ef.research.capture_run(graph)``), it is appended to ``sections`` as one additional
    "model_summary" section (Epic 16, Story 18) so the reproducibility snapshot travels with
    the report.
    """
    all_sections = list(sections)
    if reproducibility is not None:
        all_sections.append(section_from_value(reproducibility, title="Reproducibility"))
    html_doc = _render_html(meta, all_sections)
    pdf_bytes = _render_pdf(html_doc) if render_pdf else None
    return Report(meta=meta, sections=all_sections, html=html_doc, pdf_bytes=pdf_bytes)


def section_from_value(value: Any, *, title: str, kind: str | None = None) -> Section:
    """Wrap a raw upstream artifact (a DataFrame, a PlotSpec, a dataclass, or a string) into a
    :class:`Section`, auto-detecting ``kind`` from ``value``'s Python type when not given
    explicitly. Used by the ``build_report`` node (a later task) to translate whatever arrives
    on its variadic ``sections`` port into typed sections; also usable directly by callers who
    already have artifacts in hand and don't want to construct ``Section`` themselves.

    Detection order: ``PlotSpec`` -> "figure", ``pandas.DataFrame`` -> "table", a non-PlotSpec
    dataclass instance -> "model_summary", a ``str`` that looks like an HTML document (starts
    with ``<!doctype html``/``<html``, case-insensitive) -> "html", any other ``str`` ->
    "markdown".

    Raises
    ------
    TypeError
        If *value*'s type doesn't match any of the above and *kind* was not given explicitly.
    """
    if kind is not None:
        return Section(kind=kind, title=title, content=value)

    if isinstance(value, PlotSpec):
        return Section(kind="figure", title=title, content=value)
    if isinstance(value, pd.DataFrame):
        return Section(kind="table", title=title, content=value)
    if _dc.is_dataclass(value) and not isinstance(value, type):
        return Section(kind="model_summary", title=title, content=value)
    if isinstance(value, str):
        lowered = value.lstrip()[:16].lower()
        if lowered.startswith("<!doctype html") or lowered.startswith("<html"):
            return Section(kind="html", title=title, content=value)
        return Section(kind="markdown", title=title, content=value)

    raise TypeError(
        f"cannot infer a Section kind for value of type {type(value).__name__}; "
        "pass kind= explicitly."
    )


def sections_from_values(
    values: list[Any], *, titles: list[str] | None = None, kinds: list[str | None] | None = None
) -> list[Section]:
    """Build one :class:`Section` per entry in *values*, in order, via :func:`section_from_value`.

    ``titles``/``kinds`` are matched positionally to *values*. A missing, out-of-range, or
    falsy title defaults to ``"Section {i+1}"`` (1-indexed); a missing, out-of-range, or falsy
    kind defers to ``section_from_value``'s auto-detection (``kind=None``). Used by the
    ``build_report`` node to translate whatever arrives on its variadic ``sections`` port into
    typed sections.
    """
    result: list[Section] = []
    for i, value in enumerate(values):
        title = (
            titles[i]
            if titles is not None and i < len(titles) and titles[i]
            else f"Section {i + 1}"
        )
        kind = kinds[i] if kinds is not None and i < len(kinds) and kinds[i] else None
        result.append(section_from_value(value, title=title, kind=kind))
    return result
