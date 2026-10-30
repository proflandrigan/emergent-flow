"""Drift and shape tests for the generated agent reply contract module."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "export_agent_contract",
    _REPO / "scripts" / "export_agent_contract.py",
)
assert _spec is not None and _spec.loader is not None
export_agent_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_agent_contract)


def test_generated_module_matches_markdown_source() -> None:
    assert export_agent_contract.main(["--check"]) == 0


def test_reply_contract_constant_equals_markdown() -> None:
    from emergentflow.collab.reply_contract import REPLY_CONTRACT

    source = (_REPO / "agents" / "_reply-contract.md").read_text(encoding="utf-8")
    assert REPLY_CONTRACT.rstrip("\n") == source.rstrip("\n")
    assert REPLY_CONTRACT.startswith("# Reply contract")


def test_render_rejects_triple_quotes_and_backslashes() -> None:
    with pytest.raises(ValueError):
        export_agent_contract.render('a """ b')
    with pytest.raises(ValueError):
        export_agent_contract.render("a \\ b")


def test_reply_contract_module_imports_nothing_heavy() -> None:
    code = (
        "import sys; import emergentflow.collab.reply_contract; "
        "bad=[m for m in ('litellm','fastmcp','fastapi','torch') if m in sys.modules]; "
        "print(bad); raise SystemExit(1 if bad else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], check=False)
    assert result.returncode == 0
