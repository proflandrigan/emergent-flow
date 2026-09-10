"""
emergentflow.psychometrics
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Measurement science: item-response-theory ability estimation, scale reliability, and
measurement-error correction (issue #164 Gap 3).

* ``fit_irt``       -- IRT ability estimates (Rasch/2PL/3PL) from long-format item
    responses, girth-backed (optional ``[psychometrics]`` extra).
* ``reliability``   -- Cronbach's alpha / KR-20 with per-item-dropped alpha (numpy only).
* ``disattenuate``  -- correct an observed correlation for measurement error and report
    the attainable ceiling (numpy only).

Each public operation validates its inputs at the boundary (fail fast, clear typed errors
rooted at :class:`PsychometricsError`) and otherwise defers to the underlying trusted
library. ``disattenuate`` in particular addresses a false-negative trap: a tool that
reports ``r = 0.42`` without the outcome's reliability ceiling invites concluding "no
signal" when the ceiling was never 1.0.
"""

from __future__ import annotations

from emergentflow.psychometrics.disattenuate import disattenuate
from emergentflow.psychometrics.errors import (
    MissingOptionalDependencyError,
    PsychometricsError,
)
from emergentflow.psychometrics.irt import IRTResult, fit_irt
from emergentflow.psychometrics.reliability import cronbach_alpha, reliability

__all__ = [
    "IRTResult",
    "PsychometricsError",
    "MissingOptionalDependencyError",
    "cronbach_alpha",
    "disattenuate",
    "fit_irt",
    "reliability",
]
