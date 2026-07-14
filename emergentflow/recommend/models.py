"""
emergentflow.recommend.models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The shared inspectable representations for fitted recommenders (Epic 15, Story 2).

``FittedRecommender`` is the ONE dataclass every recommender archetype (baseline/content/
collaborative/deep) rides inside, mirroring ``emergentflow.ml.FittedModel`` and
``emergentflow.stats.models.FittedStatsModel``. The live model object rides in the ``model``
field so a fitted recommender can flow fit -> recommend/similar_items in-memory (execute) and as
a plain variable (compiled code); the dataclass is inspectable under the ``@public_op`` contract,
and on the result-payload contract the ``model`` field degrades to ``{"kind": "unsupported"}``
automatically (``to_payload`` recurses dataclass fields), while ``fit_stats`` renders as a plain
JSON object.

``RecommendationResult`` is the terminal recommendation payload -- a tidy ranked list of items per
user -- produced by ``ef.recommend.recommend``/``ef.recommend.similar_items``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class FittedRecommender:
    """A fitted recommender plus inspectable metadata (the Epic 15 model representation).

    Attributes
    ----------
    algorithm: the curated algorithm key that produced this fit (e.g. ``"popularity"``).
    algorithm_family: which of the four fixed archetypes this algorithm belongs to --
        ``"baseline"``, ``"content"``, ``"collaborative"``, or ``"deep"``.
    n_users: number of users the recommender was fit on.
    n_items: number of items the recommender was fit on.
    fit_stats: JSON-native training metrics (sparsity, coverage, convergence info, ...).
    model: the live model object (a lightweight dict/DataFrame for baselines, a fitted sklearn/
        implicit/torch object for other families); not JSON-serialized -- degrades to
        ``{"kind": "unsupported"}`` on the result-payload contract, never rendered directly.
    """

    algorithm: str
    algorithm_family: str
    n_users: int
    n_items: int
    fit_stats: dict[str, Any] = field(default_factory=dict)
    model: Any = None


@dataclass
class RecommendationResult:
    """The terminal recommendation payload: a tidy ranked list of items per user.

    Attributes
    ----------
    recommendations: tidy DataFrame with columns ``user_id``, ``item_id``, ``rank``, ``score``.
        JSON-native; round-trips through the result-payload contract untouched (rendered as a
        plain table, unlike ``FittedRecommender.model``).
    """

    recommendations: pd.DataFrame
