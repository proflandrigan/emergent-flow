"""Tests for the ``Clients`` bundle + ``ClientKind`` enum (ADR 0018, Task 08)."""

import dataclasses

import pytest

from emergentflow.clients import ClientKind, Clients


def test_client_kind_members() -> None:
    assert ClientKind.LLM.value == "llm"
    assert ClientKind.WAREHOUSE.value == "warehouse"


def test_clients_defaults_none() -> None:
    clients = Clients()
    assert clients.llm is None
    assert clients.warehouse is None


def test_clients_for_kind() -> None:
    clients = Clients(llm="L", warehouse="W")
    assert clients.for_kind(ClientKind.LLM) == "L"
    assert clients.for_kind(ClientKind.WAREHOUSE) == "W"


def test_from_legacy_client_maps_to_llm() -> None:
    clients = Clients.from_legacy_client("X")
    assert clients.llm == "X"
    assert clients.warehouse is None


def test_clients_is_frozen() -> None:
    clients = Clients()
    with pytest.raises(dataclasses.FrozenInstanceError):
        clients.llm = "mutated"  # type: ignore[misc]
