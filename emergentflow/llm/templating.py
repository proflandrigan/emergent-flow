"""
emergentflow.llm.templating
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Constrained, pure prompt templating (Epic 9 Story 3).

``{{var}}`` substitution only -- no arbitrary code execution, no I/O (Jinja2 is
deliberately NOT pulled in for the MVP; this keeps the dependency surface and
purity story minimal, mirroring Story 1's dependency-free ``ReplayClient``).
``render_prompt`` builds a ``PromptSpec`` from a system/user template pair and a
variable-binding dict, raising ``PromptVariableError`` on any missing or
extra/unused variable.
"""

from __future__ import annotations

import dataclasses
import re

_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptVariableError(ValueError):
    """Raised when a template's referenced variables and a binding disagree.

    Lists every missing (referenced but not supplied) and/or extra (supplied
    but never referenced) variable name, so the canvas -- or a test -- can
    surface the exact mismatch before a run.
    """


@dataclasses.dataclass(frozen=True)
class PromptSpec:
    """A rendered prompt: system/user text plus the assembled messages list.

    JSON-native (satisfies ``emergentflow.api.is_inspectable``) -- the OUT port
    of ``ef.llm.prompt``, feeding directly into ``ef.llm.call``'s ``messages``.
    """

    system: str
    user: str
    messages: tuple[dict[str, str], ...]


def _find_variables(template: str) -> set[str]:
    """Return the set of ``{{var}}`` names referenced in *template*."""
    return set(_VAR_PATTERN.findall(template))


def _substitute(template: str, variables: dict[str, object]) -> str:
    """Replace every ``{{var}}`` in *template* with ``str(variables[var])``.

    Pure string substitution only -- *template* is never evaluated as code.
    """

    def _replace(match: re.Match[str]) -> str:
        return str(variables[match.group(1)])

    return _VAR_PATTERN.sub(_replace, template)


def render_prompt(system: str, user: str, variables: dict[str, object]) -> PromptSpec:
    """Render *system*/*user* templates against *variables* into a ``PromptSpec``.

    Raises
    ------
    PromptVariableError
        If any ``{{var}}`` referenced in either template is missing from
        *variables*, or if *variables* supplies a key referenced by neither
        template.
    """
    referenced = _find_variables(system) | _find_variables(user)
    provided = set(variables)

    missing = sorted(referenced - provided)
    extra = sorted(provided - referenced)
    errors: list[str] = []
    if missing:
        errors.append(f"missing variable(s): {missing}")
    if extra:
        errors.append(f"extra/unused variable(s) supplied: {extra}")
    if errors:
        raise PromptVariableError("; ".join(errors))

    rendered_system = _substitute(system, variables)
    rendered_user = _substitute(user, variables)
    messages = (
        {"role": "system", "content": rendered_system},
        {"role": "user", "content": rendered_user},
    )
    return PromptSpec(system=rendered_system, user=rendered_user, messages=messages)
