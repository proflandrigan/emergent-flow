"""Epic 16, Story 24's optional-extra + offline-discipline audit.

Every optional extra Epic 16 added stays genuinely optional -- a base install raises a typed
``MissingOptionalDependencyError``, never an opaque ``ImportError`` -- the default (non-extra)
code path still works with the extra's module hidden, ``[all]`` really does list every defined
extra, and no ingestion node reaches the network in CI.

The base-install lanes (Group A) do not require the probed packages to be absent from the dev
venv -- they monkeypatch the probe (``importlib.util.find_spec``) so the gate behaves as if the
extra were not installed, regardless of the actual dev environment. Mirrors
``tests/test_clean_fuzzy_missing_extra.py``.
"""

from __future__ import annotations

import importlib.util
import pathlib
import tomllib

import pandas as pd
import pytest

from emergentflow.clean import MissingOptionalDependencyError as CleanMissingExtraError
from emergentflow.clean import redact_pii
from emergentflow.data import MissingOptionalDependencyError as DataMissingExtraError
from emergentflow.data import load_documents
from emergentflow.data.http.fetch import MissingHttpClientError
from emergentflow.ml import MissingOptionalDependencyError as MlMissingExtraError
from emergentflow.ml import reduce_dimensions
from emergentflow.nodes import get as get_node_definition
from emergentflow.research import MissingOptionalDependencyError as ResearchMissingExtraError
from emergentflow.research import ReportMeta, Section, build_report

_REPO_ROOT = pathlib.Path(__file__).parent.parent
_DOCS_FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "documents"


def _hide_modules(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Make ``importlib.util.find_spec`` report *names* as not installed.

    Delegates to the real ``find_spec`` for every other module name, exactly like
    ``tests/test_clean_fuzzy_missing_extra.py``'s inline closure -- returning ``None``
    unconditionally would break pandas/numpy imports along the way.
    """
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
        if name in names:
            return None
        return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)


# ---------------------------------------------------------------------------
# Group A -- the four new base-install typed-error lanes
# ---------------------------------------------------------------------------


def test_load_documents_without_docs_extra_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "pypdf")

    with pytest.raises(DataMissingExtraError) as exc_info:
        load_documents(str(_DOCS_FIXTURE_DIR / "sample.pdf"))

    assert "emergentflow[docs]" in str(exc_info.value)


def test_redact_pii_presidio_without_pii_extra_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "presidio_analyzer", "presidio_anonymizer")
    frame = pd.DataFrame({"email": ["a@example.com"]})

    with pytest.raises(CleanMissingExtraError) as exc_info:
        redact_pii(frame, engine="presidio")

    assert "emergentflow[pii]" in str(exc_info.value)


def test_build_report_pdf_without_report_pdf_extra_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "weasyprint")
    sections = [Section(kind="markdown", title="t", content="x")]
    meta = ReportMeta(title="T")

    with pytest.raises(ResearchMissingExtraError) as exc_info:
        build_report(sections, meta, render_pdf=True)

    assert "emergentflow[report-pdf]" in str(exc_info.value)


def test_reduce_dimensions_umap_without_umap_extra_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "umap")
    frame = pd.DataFrame({"a": [1.0, 2, 3, 4], "b": [2.0, 1, 4, 3]})

    with pytest.raises(MlMissingExtraError) as exc_info:
        reduce_dimensions(frame, feature_cols=["a", "b"], method="umap")

    assert "emergentflow[umap]" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Group B -- the default paths still work without the extra
# ---------------------------------------------------------------------------


def test_load_documents_markdown_works_without_docs_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "pypdf")

    result = load_documents(str(_DOCS_FIXTURE_DIR / "sample.md"))

    assert not result.empty


def test_redact_pii_regex_engine_works_without_pii_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "presidio_analyzer", "presidio_anonymizer")
    frame = pd.DataFrame({"email": ["a@example.com"]})

    result = redact_pii(frame, engine="regex")

    assert result.loc[0, "email"] != "a@example.com"


def test_build_report_html_works_without_report_pdf_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "weasyprint")
    sections = [Section(kind="markdown", title="t", content="x")]
    meta = ReportMeta(title="T")

    report = build_report(sections, meta)

    assert report.html
    assert report.pdf_bytes is None


def test_reduce_dimensions_pca_works_without_umap_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hide_modules(monkeypatch, "umap")
    frame = pd.DataFrame({"a": [1.0, 2, 3, 4], "b": [2.0, 1, 4, 3]})

    result = reduce_dimensions(frame, feature_cols=["a", "b"], method="pca")

    assert result is not None


# ---------------------------------------------------------------------------
# Group C -- the [all] extra audit
# ---------------------------------------------------------------------------


def test_all_extra_lists_every_optional_extra() -> None:
    with open(_REPO_ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)

    optional_deps = data["project"]["optional-dependencies"]
    defined = set(optional_deps) - {"all"}

    all_entry = optional_deps["all"][0]
    bracketed = all_entry[all_entry.index("[") + 1 : all_entry.index("]")]
    covered = {part.strip() for part in bracketed.split(",")}

    assert defined == covered, f"extras missing from [all]: {sorted(defined - covered)}"


# ---------------------------------------------------------------------------
# Group D -- offline discipline
# ---------------------------------------------------------------------------


def test_epic16_extras_are_declared_in_pyproject() -> None:
    with open(_REPO_ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)

    optional_deps = data["project"]["optional-dependencies"]
    epic16_extras = {"cloud", "excel", "fuzzy", "umap", "report-pdf", "docs", "pii"}

    assert epic16_extras <= set(optional_deps)


def test_no_hard_dependency_on_any_optional_package() -> None:
    with open(_REPO_ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)

    optional_package_names = {
        "rapidfuzz",
        "openpyxl",
        "pypdf",
        "presidio-analyzer",
        "presidio-anonymizer",
        "weasyprint",
        "umap-learn",
        "s3fs",
        "gcsfs",
        "adlfs",
        "fsspec",
    }

    hard_dep_names = set()
    for requirement in data["project"]["dependencies"]:
        cut = len(requirement)
        for ch in ">=<[!~ ;":
            idx = requirement.find(ch)
            if idx != -1:
                cut = min(cut, idx)
        hard_dep_names.add(requirement[:cut].strip())

    assert not (optional_package_names & hard_dep_names)


def test_http_ingestion_nodes_require_an_injected_client() -> None:
    http_fetch_defn = get_node_definition("data.http_fetch")()
    node = http_fetch_defn.instantiate(url="https://example.invalid/x")
    with pytest.raises(MissingHttpClientError):
        http_fetch_defn.execute(node, inputs={})

    load_sheet_defn = get_node_definition("data.load_google_sheet")()
    sheet_node = load_sheet_defn.instantiate(spreadsheet_id="s")
    with pytest.raises(MissingHttpClientError):
        load_sheet_defn.execute(sheet_node, inputs={})


def test_fetch_module_does_not_import_live_networking() -> None:
    # urllib.request legitimately lives in emergentflow/data/http/live.py, the injected
    # live HttpClient -- the point of this assertion is that the pure fetch/parse path in
    # fetch.py never pulls it in, so importing fetch.py alone can never touch the network.
    source = (_REPO_ROOT / "emergentflow" / "data" / "http" / "fetch.py").read_text()

    assert "import urllib.request" not in source
    assert "import requests" not in source
    assert "import httpx" not in source
