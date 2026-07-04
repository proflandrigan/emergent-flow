"""
emergentflow.eval.export
~~~~~~~~~~~~~~~~~~~~~~~~
The I/O-isolated dataset exporter for the Prompt Lab eval seam (Epic 9, Story 7).

`export_eval_set` and `export_finetune` are the I/O wrappers around
`emergentflow.eval.label`'s (Story 6) output: they read a labeled results
DataFrame and write it to disk in one of two JSONL shapes. `execute`, `codegen`,
and the pure `emergentflow.eval.run.run`/`emergentflow.eval.label.label` functions
never touch the filesystem (ADR 0002); all filesystem access for dataset export
lives here, matching the I/O-isolation pattern established by
`emergentflow.codegen.export.export_script`.

Both exports operate only on rows with a non-null `label` (`df["label"].notna()`);
unlabeled rows are excluded from both formats. This is a deliberate choice: an
"eval set" or a fine-tune set is *judged* data, not raw unreviewed generations —
a row that has not been labeled has not been vetted for inclusion, so it is
silently dropped rather than exported.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

import pandas as pd

from emergentflow.api import public_op


@dataclass(frozen=True)
class DatasetExportManifest:
    """What `export_eval_set`/`export_finetune` wrote to disk."""

    path: pathlib.Path
    row_count: int
    byte_size: int


def rows_to_jsonl_bytes(rows: list[dict]) -> bytes:
    """Encode *rows* as UTF-8 JSONL bytes, one JSON object per line. No I/O."""
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    return text.encode("utf-8")


def _write_jsonl(path: str | pathlib.Path, rows: list[dict]) -> DatasetExportManifest:
    """Write *rows* as JSONL to *path*, creating parent directories as needed."""
    out_path = pathlib.Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = rows_to_jsonl_bytes(rows)
    out_path.write_bytes(data)

    return DatasetExportManifest(path=out_path, row_count=len(rows), byte_size=len(data))


def build_eval_set_rows(df: pd.DataFrame) -> list[dict]:
    """Filter *df* to labeled rows and shape each as an eval-set JSON record.

    Only rows with a non-null `label` are kept (see module docstring for the
    rationale); unlabeled rows are silently skipped. Each record has keys
    `input`, `output`, `label`, and (only when present) `score` and `rubric`.

    Raises:
        ValueError: If any labeled row's `input` is not a `dict`.
    """
    labeled = df[df["label"].notna()]

    rows: list[dict] = []
    for record in labeled.to_dict(orient="records"):
        if not isinstance(record["input"], dict):
            raise ValueError(
                f"export_eval_set: row {record.get('row_id')!r} has non-dict 'input': "
                f"{type(record['input']).__name__}"
            )
        out: dict = {
            "input": record["input"],
            "output": record["output"],
            "label": record["label"],
        }
        # `score`/`rubric` are optional columns (only guaranteed present when *df*
        # came from `ef.eval.label`, which fills them with `None`); a caller posting
        # rows straight to this function (e.g. the `/export/eval_set` route) may omit
        # them entirely, so read via `.get` rather than assuming the key exists.
        score = record.get("score")
        if pd.notna(score):
            out["score"] = float(score)
        rubric = record.get("rubric")
        if pd.notna(rubric):
            out["rubric"] = str(rubric)
        rows.append(out)

    return rows


def build_finetune_rows(df: pd.DataFrame) -> list[dict]:
    """Filter *df* to labeled rows and shape each as a fine-tune JSON record.

    Only rows with a non-null `label` are kept (same rule as
    `build_eval_set_rows`; see module docstring for the rationale). Each
    record is `{"messages": [...]}`: the row's `messages` list with one
    appended `{"role": "assistant", "content": ...}` message, where the
    content is the row's `output` directly if it is a `str`, or a
    JSON-encoded string if it is a `dict`.

    Raises:
        ValueError: If any labeled row's `messages` is not a non-empty list.
    """
    labeled = df[df["label"].notna()]

    rows: list[dict] = []
    for record in labeled.to_dict(orient="records"):
        messages = record["messages"]
        if not isinstance(messages, list) or len(messages) == 0:
            raise ValueError(
                f"export_finetune: row {record.get('row_id')!r} has non-list or "
                f"empty 'messages': {messages!r}"
            )
        output = record["output"]
        content = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
        assistant_message = {"role": "assistant", "content": content}
        rows.append({"messages": [*messages, assistant_message]})

    return rows


@public_op(name="ef.export_eval_set")
def export_eval_set(df: pd.DataFrame, path: str | pathlib.Path) -> DatasetExportManifest:
    """Export labeled rows of *df* (`ef.eval.label`'s output) as a judged eval set.

    Only rows with a non-null `label` are exported (see module docstring for the
    rationale); unlabeled rows are silently skipped.

    Each exported row is a JSON object with keys `input`, `output`, `label`, and
    (only when present) `score` and `rubric`, written one per line to *path* as
    UTF-8 JSONL. Parent directories of *path* are created if missing.

    Raises:
        ValueError: If, after filtering to labeled rows, any row's `input` is
            not a `dict`.

    Returns:
        A `DatasetExportManifest` describing what was written.
    """
    return _write_jsonl(path, build_eval_set_rows(df))


@public_op(name="ef.export_finetune")
def export_finetune(df: pd.DataFrame, path: str | pathlib.Path) -> DatasetExportManifest:
    """Export labeled rows of *df* (`ef.eval.label`'s output) as fine-tune examples.

    Only rows with a non-null `label` are exported (same rule as
    `export_eval_set`; see module docstring for the rationale).

    Each exported row is `{"messages": [...]}`: the row's `messages` list with
    one appended `{"role": "assistant", "content": ...}` message, where the
    content is the row's `output` directly if it is a `str`, or a JSON-encoded
    string if it is a `dict`. Written one JSON object per line to *path* as
    UTF-8 JSONL. Parent directories of *path* are created if missing.

    Raises:
        ValueError: If, after filtering to labeled rows, any row's `messages`
            is not a non-empty list.

    Returns:
        A `DatasetExportManifest` describing what was written.
    """
    return _write_jsonl(path, build_finetune_rows(df))
