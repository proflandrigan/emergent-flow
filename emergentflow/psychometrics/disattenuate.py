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

    When ``n`` is given, a 95% CI is computed in Fisher-z space on the observed ``r``
    (``se_z = 1 / sqrt(n - 3)``), back-transformed with ``tanh``, and each endpoint is
    then disattenuated by the same denominator as the point estimate (so the interval
    stays inside ``[-1, 1] / denom``).

    Returns a tidy one-row frame with ``observed_r``, ``corrected_r``, ``max_attainable_r``,
    ``attenuation_ratio`` (``observed_r / max_attainable_r`` -- the signed fraction of the
    attainable ceiling actually observed), ``out_of_range`` (``True`` when
    ``|corrected_r| > 1``, i.e. the reliabilities are too low to be consistent with ``r``),
    and (when ``n`` given) ``ci_low``/``ci_high``.
    Never mutates inputs.
    """
    if not (0.0 < reliability_x <= 1.0) or not (0.0 < reliability_y <= 1.0):
        raise PsychometricsError("reliability_x and reliability_y must each be in (0, 1].")
    if not (-1.0 <= r <= 1.0):
        raise PsychometricsError(f"observed r must be in [-1, 1]; got {r!r}.")
    denom = float(np.sqrt(reliability_x * reliability_y))
    corrected = float(r / denom)
    max_attainable = denom

    row: dict[str, float | bool] = {
        "observed_r": float(r),
        "corrected_r": corrected,
        "max_attainable_r": max_attainable,
        # Signed fraction of the attainable ceiling actually observed
        # (observed_r / max_attainable_r).
        "attenuation_ratio": float(r / denom),
        # A corrected correlation beyond +/-1 means the reliabilities are too low to be
        # consistent with the observed r (e.g. r=0.9 with reliabilities 0.5/0.5 -> 1.8);
        # flag it, never hide it.
        "out_of_range": bool(abs(corrected) > 1.0),
    }
    if n is not None:
        n_int = int(n)
        if n_int < 4:
            raise PsychometricsError("n must be >= 4 to compute a Fisher-z CI.")
        if abs(r) >= 1.0:
            # z = atanh(+/-1) is infinite; the interval degenerates to the point.
            row["ci_low"] = corrected
            row["ci_high"] = corrected
        else:
            # 95% CI in Fisher-z space on the OBSERVED r (se_z = 1/sqrt(n-3)), back-transformed
            # with tanh, then each endpoint disattenuated by the same denominator as the point.
            se_z = float(1.0 / np.sqrt(n_int - 3))
            z_r = float(np.arctanh(r))
            z = 1.959963984540054
            row["ci_low"] = float(np.tanh(z_r - z * se_z) / denom)
            row["ci_high"] = float(np.tanh(z_r + z * se_z) / denom)
    return pd.DataFrame([row])
