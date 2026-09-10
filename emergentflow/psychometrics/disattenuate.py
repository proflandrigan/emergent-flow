"""
emergentflow.psychometrics.disattenuate
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Correction for measurement error in a correlation (issue #164 Gap 3b).

``ef.psychometrics.disattenuate`` corrects an observed correlation between two measured
variables for attenuation by each variable's reliability, and -- crucially -- reports
``max_attainable_r = sqrt(reliability_x * reliability_y)``, the ceiling the observed
correlation is really competing against. This is the number users most need and least
often compute: an observed ``r = 0.42`` against an outcome with reliability ``0.80`` is
0.47 of the attainable maximum, not 0.42 of 1.0. Pure numpy; no optional dependencies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from emergentflow.api import public_op
from emergentflow.psychometrics.errors import PsychometricsError

__all__ = ["disattenuate"]


@public_op(name="ef.psychometrics.disattenuate")
def disattenuate(
    r: float,
    *,
    reliability_x: float,
    reliability_y: float = 1.0,
    n: int | None = None,
) -> pd.DataFrame:
    """Correct an observed correlation for attenuation due to measurement error.

    ``r`` is the observed Pearson correlation; ``reliability_x``/``reliability_y`` are the
    reliabilities (Cronbach's alpha, test-retest, ...) of the two variables, each in
    ``(0, 1]``. The disattenuated correlation is
    ``r_corrected = r / sqrt(reliability_x * reliability_y)``, and the attainable ceiling
    is ``max_attainable_r = sqrt(reliability_x * reliability_y)`` -- the number users most
    need and least often compute.

    When ``n`` is given, a 95% CI on the corrected correlation is reported using the
    Fisher-z approximation (``se = 1 / sqrt(n - 3)``) scaled by the same denominator.

    Returns a tidy one-row frame with ``observed_r``, ``corrected_r``, ``max_attainable_r``,
    ``attenuation_ratio`` (``observed_r / max_attainable_r`` -- the fraction of the
    attainable ceiling actually observed), and (when ``n`` given) ``ci_low``/``ci_high``.
    Never mutates inputs.
    """
    if not (0.0 < reliability_x <= 1.0) or not (0.0 < reliability_y <= 1.0):
        raise PsychometricsError("reliability_x and reliability_y must each be in (0, 1].")
    if not (-1.0 <= r <= 1.0):
        raise PsychometricsError(f"observed r must be in [-1, 1]; got {r!r}.")
    denom = float(np.sqrt(reliability_x * reliability_y))
    corrected = float(r / denom)
    max_attainable = denom
    ratio = float(abs(r) / denom) if denom else float("nan")

    row: dict[str, float] = {
        "observed_r": float(r),
        "corrected_r": corrected,
        "max_attainable_r": max_attainable,
        "attenuation_ratio": ratio,
    }
    if n is not None:
        if int(n) < 4:
            raise PsychometricsError("n must be >= 4 to compute a Fisher-z CI.")
        se = float(1.0 / np.sqrt(int(n) - 3))
        z = 1.959963984540054
        # Variance of corrected r via delta method on the Fisher-z of the observed r.
        fisher_se = se / (1 - r**2)
        row["ci_low"] = float(corrected - z * fisher_se / denom if denom else float("nan"))
        row["ci_high"] = float(corrected + z * fisher_se / denom if denom else float("nan"))
    return pd.DataFrame([row])
