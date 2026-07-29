"""
emergentflow.data.documents
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Document ingestion loader (Epic 16, Story 20) -- the RAG loader half only.

``load_documents`` chunks PDF/text/markdown files into a tidy ``(doc_id, chunk_id, text,
metadata...)`` frame -- a "DocumentFrame": a plain, tagged DataFrame, not embeddings. **No
embedding or retrieval happens here** -- that is Epic 11's job (the vector-store/retriever
surface). This loader only produces the frame those consume; where a research flow needs
retrieval, it wires this loader's output into the Epic 11 surface.

PDF parsing is gated behind the optional ``[docs]`` extra (pypdf, MIT); text/markdown files
need no extra. A base install missing pypdf that tries to load a ``.pdf`` file raises a typed
``MissingOptionalDependencyError``, never an opaque ``ImportError``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from emergentflow.api import public_op
from emergentflow.data.errors import DataLoadError, MissingOptionalDependencyError

__all__ = ["SUPPORTED_EXTENSIONS", "load_documents"]

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".markdown")


def _require_docs_extra() -> None:
    if importlib.util.find_spec("pypdf") is None:
        raise MissingOptionalDependencyError("emergentflow[docs]")


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_pdf_file(path: Path) -> str:
    _require_docs_extra()
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split *text* into overlapping fixed-size character chunks, deterministic left-to-right.

    A pure sliding-window split (no sentence/paragraph awareness) -- kept dependency-free
    rather than pulling in a tokenizer/NLP library for what this loader needs to guarantee:
    deterministic, reproducible chunk boundaries for the same input.
    """
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            f"chunk_overlap must be >= 0 and < chunk_size, got chunk_overlap={chunk_overlap}, "
            f"chunk_size={chunk_size}"
        )
    if not text:
        return [""]
    step = chunk_size - chunk_overlap
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        chunks.append(text[start : start + chunk_size])
        start += step
    return chunks


@public_op(name="ef.data.load_documents")
def load_documents(
    path: str,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 100,
) -> pd.DataFrame:
    """Chunk PDF/text/markdown file(s) at *path* into a tidy DocumentFrame.

    *path* is either a single file (``.pdf``/``.txt``/``.md``/``.markdown``) or a directory,
    in which case every file directly inside it (non-recursive) matching
    :data:`SUPPORTED_EXTENSIONS` is processed, in sorted filename order for determinism.

    Each file is read to plain text (pypdf page extraction for ``.pdf``, ``utf-8`` read for
    the rest), then split into overlapping *chunk_size*/*chunk_overlap* character chunks via
    :func:`_chunk_text`.

    Returns
    -------
    pd.DataFrame
        Columns ``doc_id`` (the file's stem), ``chunk_id`` (``f"{doc_id}_{chunk_index}"``),
        ``chunk_index`` (0-based position within the document), ``text`` (the chunk's content),
        ``source_path`` (the file's path as a string), ``char_count`` (``len(text)``). One row
        per chunk, ordered by file (sorted) then ``chunk_index``.

    Raises
    ------
    ValueError
        If *path* is empty/not a string, or *chunk_size*/*chunk_overlap* are invalid (see
        :func:`_chunk_text`).
    DataLoadError
        If *path* does not exist, a directory at *path* contains no supported files, or a
        single-file *path* has an unsupported extension.
    MissingOptionalDependencyError
        If any ``.pdf`` file is encountered and the ``[docs]`` extra (pypdf) is not installed.

    Note
    ----
    This loader produces a frame only -- **no embedding or retrieval**. That surface is Epic
    11 (RAG); this loader's output is meant to feed into it, not duplicate it.
    """
    if not path or not isinstance(path, str):
        raise ValueError(f"path must be a non-empty string, got {path!r}")

    p = Path(path)
    if not p.exists():
        raise DataLoadError(f"path does not exist: {path!r}")

    if p.is_dir():
        files = sorted(
            f for f in p.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not files:
            raise DataLoadError(
                f"directory {path!r} contains no supported files "
                f"(expected one of {SUPPORTED_EXTENSIONS})"
            )
    else:
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise DataLoadError(
                f"unsupported file type {p.suffix!r} for {path!r}; "
                f"expected one of {SUPPORTED_EXTENSIONS}"
            )
        files = [p]

    rows: list[dict[str, object]] = []
    for file_path in files:
        doc_id = file_path.stem
        ext = file_path.suffix.lower()
        text = _read_pdf_file(file_path) if ext == ".pdf" else _read_text_file(file_path)
        chunks = _chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        for i, chunk in enumerate(chunks):
            rows.append(
                {
                    "doc_id": doc_id,
                    "chunk_id": f"{doc_id}_{i}",
                    "chunk_index": i,
                    "text": chunk,
                    "source_path": str(file_path),
                    "char_count": len(chunk),
                }
            )

    return pd.DataFrame(
        rows, columns=["doc_id", "chunk_id", "chunk_index", "text", "source_path", "char_count"]
    )
