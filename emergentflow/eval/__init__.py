"""
emergentflow.eval
~~~~~~~~~~~~~~~~~
The compare/eval-run seam (Epic 9 Story 5): run one prompt template over
N inputs x M model variants, producing the tidy DataFrame the Prompt Lab
compare grid (Epic 9 Story 8) renders and `emergentflow.llm.aggregate.summarize_run`
(Story 4) consumes.
"""

from __future__ import annotations

from emergentflow.eval.run import run

__all__ = ["run"]
