"""Tests for emergentflow.script.run_code."""

from __future__ import annotations

import pytest

from emergentflow.script import CustomCodeError, run_code


class TestRunCode:
    def test_run_code_calls_transform(self) -> None:
        code = "def transform(value):\n    return value + 1"
        assert run_code(code, 41) == 42

    def test_run_code_supports_inline_imports(self) -> None:
        code = "def transform(value):\n    import math\n    return math.sqrt(value)"
        assert run_code(code, 16) == 4.0

    def test_run_code_missing_transform_raises(self) -> None:
        code = "x = 1"
        with pytest.raises(CustomCodeError, match="transform"):
            run_code(code, None)

    def test_run_code_syntax_error_raises(self) -> None:
        code = "def transform(value)\n    return value"
        with pytest.raises(CustomCodeError):
            run_code(code, None)

    def test_run_code_non_str_raises_custom_code_error(self) -> None:
        with pytest.raises(CustomCodeError, match="failed to compile"):
            run_code(None, 1)

    def test_run_code_propagates_runtime_errors(self) -> None:
        code = "def transform(value):\n    return value['missing']"
        with pytest.raises(KeyError):
            run_code(code, {})

    def test_run_code_isolated_namespace(self) -> None:
        code1 = "def transform(value):\n    return value"
        code2 = "def transform(value):\n    return helper()"
        run_code(code1, 1)
        with pytest.raises(NameError):
            run_code(code2, None)
