"""
emergentflow.api
~~~~~~~~~~~~~~
Runtime enforcement of the SDK design philosophy (Epic 1, Story 7).

Every public SDK operation ("wrapper") must return a *serializable + inspectable*
result: a Pydantic model, a dataclass instance, a tidy DataFrame, or a JSON-native
value (``dict`` / ``list`` / ``str`` / ``int`` / ``float`` / ``bool`` / ``None``).
Opaque, library-internal handles are forbidden as the sole return — they cannot be
serialized for the IR's artifact store nor inspected by users.

This module provides the runtime contract that backs that rule:

* :func:`is_inspectable` — predicate.
* :func:`assert_inspectable` — raises :class:`InspectableContractError` on violation.
* :func:`public_op` — decorator that registers a wrapper in :data:`PUBLIC_OPS` and
  validates its return value on every call.

DataFrame support is *duck-typed* (``to_dict`` + ``shape`` + ``columns``) so neither
pandas nor polars becomes an import-time dependency of the core SDK.

See ``docs/sdk-design-philosophy.md`` and ``docs/public-api-conventions.md``.
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast, overload

from pydantic import BaseModel

__all__ = [
    "InspectableContractError",
    "is_inspectable",
    "assert_inspectable",
    "public_op",
    "PUBLIC_OPS",
]

F = TypeVar("F", bound=Callable[..., Any])

#: Registry of every operation decorated with :func:`public_op`, keyed by op name.
PUBLIC_OPS: dict[str, Callable[..., Any]] = {}


class InspectableContractError(TypeError):
    """Raised when a public operation returns a non-inspectable object.

    A subclass of :class:`TypeError` because it signals a wrong *return type*: the
    operation produced something that is not serializable + inspectable.
    """


def _is_dataframe_like(obj: Any) -> bool:
    """Duck-typed tidy-DataFrame check (matches pandas and polars DataFrames).

    Avoids importing pandas/polars so the core SDK stays dependency-light.
    """
    return hasattr(obj, "to_dict") and hasattr(obj, "shape") and hasattr(obj, "columns")


def is_inspectable(obj: Any) -> bool:
    """Return ``True`` if *obj* is a serializable + inspectable SDK result.

    Accepted: JSON-native scalars (``None``/``bool``/``int``/``float``/``str``),
    Pydantic models, dataclass instances, tidy DataFrames (duck-typed), and
    ``dict``/``list``/``tuple`` containers whose contents are themselves inspectable
    (dict keys must be strings). Everything else — bare objects, generators, file
    handles, ``bytes`` — is rejected.
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return True
    if isinstance(obj, BaseModel):
        return True
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return True
    if _is_dataframe_like(obj):
        return True
    if isinstance(obj, Mapping):
        return all(isinstance(key, str) for key in obj) and all(
            is_inspectable(value) for value in obj.values()
        )
    if isinstance(obj, (list, tuple)):
        return all(is_inspectable(item) for item in obj)
    return False


def assert_inspectable(obj: Any, *, where: str = "operation") -> None:
    """Raise :class:`InspectableContractError` if *obj* is not inspectable.

    *where* is interpolated into the message to identify the offending operation.
    """
    if not is_inspectable(obj):
        raise InspectableContractError(
            f"{where} returned a non-inspectable object of type "
            f"{type(obj).__name__!r}; public SDK operations must return a "
            "serializable + inspectable result (Pydantic model, dataclass, tidy "
            "DataFrame, or JSON-native value). See docs/sdk-design-philosophy.md."
        )


@overload
def public_op(func: F) -> F: ...
@overload
def public_op(*, name: str | None = ...) -> Callable[[F], F]: ...
def public_op(func: F | None = None, *, name: str | None = None) -> F | Callable[[F], F]:
    """Mark a function as a public SDK operation and enforce its return contract.

    Usable bare (``@public_op``) or parameterized (``@public_op(name="ef.stats.anova")``).
    On every call the wrapped function's return value is checked with
    :func:`assert_inspectable`; the op is also recorded in :data:`PUBLIC_OPS` so a
    test sweep can enforce the contract across the whole catalog.
    """

    def decorate(fn: F) -> F:
        op_name = name or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            assert_inspectable(result, where=f"public op {op_name!r}")
            return result

        wrapper.__cm_public_op__ = True  # type: ignore[attr-defined]
        PUBLIC_OPS[op_name] = wrapper
        return cast(F, wrapper)

    if func is not None:
        return decorate(func)
    return decorate
