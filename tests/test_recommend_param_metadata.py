"""
tests.test_recommend_param_metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Drift guard for ``RecommenderSpec.param_metadata`` (Epic 15 param-callouts, Task 01).

Ensures every registered recommender algorithm's ``param_metadata`` stays in lockstep with
its ``required_params``/``optional_params`` allow-list, and that every param's ``type`` token
is one of the known curated tokens the config UI understands.
"""

import emergentflow.recommend.catalog  # noqa: F401  (registers algorithms)
from emergentflow.recommend.registry import _REGISTRY


def test_param_metadata_covers_exactly_the_allow_list():
    for key, spec in _REGISTRY.items():
        names = {p.name for p in spec.param_metadata}
        assert names == set(spec.required_params) | set(spec.optional_params), key


def test_param_metadata_required_flags_match_required_params():
    for key, spec in _REGISTRY.items():
        required = {p.name for p in spec.param_metadata if p.required}
        assert required == set(spec.required_params), key


def test_param_metadata_types_are_known_tokens():
    allowed = {"int", "float", "str", "bool", "list", "any"}
    for key, spec in _REGISTRY.items():
        for p in spec.param_metadata:
            assert p.type in allowed, (key, p.name, p.type)
