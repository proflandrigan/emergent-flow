"""Tests for the ``Schema`` type token and the ``ConnectionRef`` param convention.

Epic 13 Story 3 (ADR 0018): a warehouse introspection frame validates as the
``Schema`` port ``data_type``; a warehouse query node references a connection
profile *name* via a ``connection`` param carrying the ``ConnectionRef``
type-token and a ``"connection"`` widget hint.
"""

from __future__ import annotations

from emergentflow.data.warehouse.params import (
    CONNECTION_REF_TOKEN,
    CONNECTION_WIDGET,
    connection_param,
)
from emergentflow.nodes.spec import ParamSpec
from emergentflow.types import registry


def test_schema_token_registered() -> None:
    assert registry.is_registered("Schema")
    assert "introspection" in registry.get("Schema").description


def test_connection_param_shape() -> None:
    param = connection_param()
    assert param.type_token == CONNECTION_REF_TOKEN
    assert param.required is True
    assert param.hints is not None
    assert param.hints.widget == CONNECTION_WIDGET
    assert param.name == "connection"


def test_connection_param_custom_name_and_optional() -> None:
    param = connection_param("src", required=False)
    assert param.name == "src"
    assert param.required is False


def test_connection_param_serializes_roundtrip() -> None:
    param = connection_param()
    dumped = param.model_dump()
    restored = ParamSpec.model_validate(dumped)
    assert restored == param

    allowed_fields = {"name", "type_token", "default", "required", "label", "help", "hints"}
    assert set(dumped.keys()) <= allowed_fields
    credential_ish = {"credential", "password", "secret", "token", "api_key", "value"}
    assert not (set(dumped.keys()) & credential_ish)


def test_connection_ref_token_value() -> None:
    assert CONNECTION_REF_TOKEN == "ConnectionRef"
    assert CONNECTION_WIDGET == "connection"
