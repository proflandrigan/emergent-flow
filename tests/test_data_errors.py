"""Tests for ``emergentflow.data.errors`` (Epic 16 typed error hierarchy)."""

from __future__ import annotations

import emergentflow.data
from emergentflow.data import (
    DataError,
    DataLoadError,
    MissingOptionalDependencyError,
    SchemaContractError,
)
from emergentflow.data.errors import (
    DataError as DataErrorDirect,
)
from emergentflow.data.errors import (
    DataLoadError as DataLoadErrorDirect,
)
from emergentflow.data.errors import (
    MissingOptionalDependencyError as MissingOptionalDependencyErrorDirect,
)
from emergentflow.data.errors import (
    SchemaContractError as SchemaContractErrorDirect,
)


def test_data_load_error_is_value_error() -> None:
    assert issubclass(DataLoadError, ValueError)
    assert issubclass(DataLoadError, DataError)


def test_schema_contract_error_is_data_load_error() -> None:
    assert issubclass(SchemaContractError, DataLoadError)


def test_missing_optional_dependency_error_message() -> None:
    exc = MissingOptionalDependencyError("emergentflow[cloud]")
    assert exc.extra == "emergentflow[cloud]"
    assert "pip install emergentflow[cloud]" in str(exc)


def test_errors_reexported_from_data_package() -> None:
    assert DataError is DataErrorDirect
    assert DataLoadError is DataLoadErrorDirect
    assert SchemaContractError is SchemaContractErrorDirect
    assert MissingOptionalDependencyError is MissingOptionalDependencyErrorDirect

    names = emergentflow.data.__all__  # type: ignore[attr-defined]
    assert "DataError" in names
    assert "DataLoadError" in names
    assert "SchemaContractError" in names
    assert "MissingOptionalDependencyError" in names
