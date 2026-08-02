"""
Epic 17 Story 8 — rule-pack documentation coverage gate.

Every registered validity rule must appear in ``docs/experiment-validity-rules.md``
(by its machine-readable id), and every rule documented there must be registered.
This is the CI check that fails when a rule lacks a doc entry or a doc entry
names a rule that no longer exists.
"""

from __future__ import annotations

import pathlib

from emergentflow.validity import registry as validity_registry

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DOC_PATH = _REPO_ROOT / "docs" / "experiment-validity-rules.md"


def _documented_rule_ids() -> set[str]:
    """Every rule id mentioned in the doc's rule-catalog section.

    Rule ids appear as ``- **`rule_id`**`` bullets (e.g.
    ``- **`fit_before_split`**``). Any id spelled in that form counts.
    """
    text = _DOC_PATH.read_text(encoding="utf-8")
    ids: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- **`"):
            candidate = stripped[len("- **`") :].split("`", 1)[0]
            if candidate and candidate.isidentifier():
                ids.add(candidate)
    return ids


def test_every_registered_rule_is_documented() -> None:
    registered = {rule.id for rule in validity_registry.all()}
    documented = _documented_rule_ids()
    missing = sorted(registered - documented)
    assert not missing, f"validity rules missing from docs/experiment-validity-rules.md: {missing}"


def test_every_documented_rule_is_registered() -> None:
    registered = {rule.id for rule in validity_registry.all()}
    documented = _documented_rule_ids()
    stale = sorted(documented - registered)
    assert not stale, (
        f"docs/experiment-validity-rules.md documents rules that are not registered: {stale}"
    )


def test_rule_pack_has_at_least_ten_rules() -> None:
    assert len(validity_registry.all()) >= 10
