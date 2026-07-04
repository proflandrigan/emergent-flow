"""
emergentflow.eval
~~~~~~~~~~~~~~~~~
The compare/eval-run seam (Epic 9 Story 5): run one prompt template over
N inputs x M model variants, producing the tidy DataFrame the Prompt Lab
compare grid (Epic 9 Story 8) renders and `emergentflow.llm.aggregate.summarize_run`
(Story 4) consumes. `emergentflow.eval.label` (Story 6) is the pure join that
merges human labels onto that DataFrame. `emergentflow.eval.export` (Story 7)
is the I/O-isolated exporter that writes labeled rows to JSONL eval-set/fine-tune
files.
"""

from __future__ import annotations

from emergentflow.eval.export import DatasetExportManifest, export_eval_set, export_finetune
from emergentflow.eval.label import LabelColumnError, label
from emergentflow.eval.run import run

__all__ = [
    "DatasetExportManifest",
    "LabelColumnError",
    "export_eval_set",
    "export_finetune",
    "label",
    "run",
]
