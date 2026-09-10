"""
emergentflow.causal
~~~~~~~~~~~~~~~~~~~
Causal-inference operations (issue #164 Gap 1).

Thin wrappers over scikit-learn / statsmodels (both hard deps) implementing the
classical observational-study toolset: propensity-score fitting with balancing
diagnostics (``fit_propensity``), ATE estimation by IPW / AIPW / matching /
regression adjustment (``estimate_effect``), difference-in-differences
(``did``), and unmeasured-confounding sensitivity analysis (``sensitivity`` /
``e_value`` / ``rosenbaum_gamma``). Each public operation validates its inputs at
the boundary (fail fast, clear typed errors rooted at :class:`CausalError`) and
otherwise defers to the trusted underlying libraries -- no reimplementation of the
underlying estimators.

Inference across the family honours nested/clustered observational data: effect
estimates accept a ``cluster_col`` routed through the same cluster-robust covariance
machinery as ``ef.stats.fit_model``, and the balancing/overlap diagnostics on
``fit_propensity`` are always returned (never optional) so a user sees whether
weighting removed the selection imbalance before trusting any estimate.
"""

from __future__ import annotations

from emergentflow.causal.dr import estimate_effect
from emergentflow.causal.errors import (
    CausalError,
    InvalidTreatmentError,
    MissingOptionalDependencyError,
    UnknownMethodError,
)
from emergentflow.causal.matching import match_nearest
from emergentflow.causal.panel import did
from emergentflow.causal.propensity import PropensityResult, fit_propensity
from emergentflow.causal.registry import (
    EstimatorSpec,
    get_estimator_spec,
    keys_for_archetype,
    known_method_keys,
    register_estimator,
)
from emergentflow.causal.sensitivity import e_value, rosenbaum_gamma, sensitivity

__all__ = [
    "CausalError",
    "PropensityResult",
    "EstimatorSpec",
    "InvalidTreatmentError",
    "MissingOptionalDependencyError",
    "UnknownMethodError",
    "did",
    "e_value",
    "estimate_effect",
    "fit_propensity",
    "get_estimator_spec",
    "keys_for_archetype",
    "known_method_keys",
    "match_nearest",
    "register_estimator",
    "rosenbaum_gamma",
    "sensitivity",
]

# Importing the seed catalog registers the method allow-list entries into the registry the
# moment ``emergentflow.causal`` is imported -- the same import-for-side-effect pattern
# ``emergentflow.ml`` uses for its estimator catalog. Kept last so the public ops above are
# fully defined first. The lint suppression marks it as not-at-top (E402) and
# unused-but-intentional (F401).
from emergentflow.causal import catalog  # noqa: E402, F401
