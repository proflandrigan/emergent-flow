"""Tests for the ``Clients`` bundle + ``ClientKind`` enum (ADR 0018, Task 08)."""

import dataclasses

import pytest

from emergentflow.clients import ClientKind, Clients


def test_client_kind_members() -> None:
    assert ClientKind.LLM.value == "llm"
    assert ClientKind.WAREHOUSE.value == "warehouse"
    assert ClientKind.HTTP.value == "http"


def test_clients_defaults_none() -> None:
    clients = Clients()
    assert clients.llm is None
    assert clients.warehouse is None


def test_clients_http_defaults_none() -> None:
    assert Clients().http is None


def test_clients_for_kind() -> None:
    clients = Clients(llm="L", warehouse="W")
    assert clients.for_kind(ClientKind.LLM) == "L"
    assert clients.for_kind(ClientKind.WAREHOUSE) == "W"


def test_clients_for_kind_http() -> None:
    assert Clients(http="H").for_kind(ClientKind.HTTP) == "H"


def test_from_legacy_client_maps_to_llm() -> None:
    clients = Clients.from_legacy_client("X")
    assert clients.llm == "X"
    assert clients.warehouse is None


def test_from_legacy_client_leaves_http_none() -> None:
    assert Clients.from_legacy_client("X").http is None


def test_clients_is_frozen() -> None:
    clients = Clients()
    with pytest.raises(dataclasses.FrozenInstanceError):
        clients.llm = "mutated"  # type: ignore[misc]
