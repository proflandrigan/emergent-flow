"""Tests for ``emergentflow.llm.prompt_from_file`` and the ``llm.prompt_from_file`` node."""

from __future__ import annotations

from pathlib import Path

import pytest

import emergentflow as ef
from emergentflow.ir import Graph
from emergentflow.llm import prompt_from_file
from emergentflow.nodes.examples.llm_prompt_from_file import LlmPromptFromFile


def test_prompt_from_file_reads_text(tmp_path: Path) -> None:
    filepath = tmp_path / "prompt.md"
    filepath.write_text("You are a helpful assistant.")
    result = prompt_from_file(str(filepath))
    assert result == "You are a helpful assistant."


def test_prompt_from_file_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        prompt_from_file("/nonexistent/path/to/prompt.md")


def test_prompt_from_file_empty_path_raises() -> None:
    with pytest.raises(ValueError):
        prompt_from_file("")


def test_node_execute_reads_text(tmp_path: Path) -> None:
    filepath = tmp_path / "prompt.md"
    filepath.write_text("You are a helpful assistant.")
    node = LlmPromptFromFile().instantiate(path=str(filepath))
    out = LlmPromptFromFile().execute(node, inputs={})
    assert out == {"text": "You are a helpful assistant."}


def test_node_codegen_emits_ef_llm_prompt_from_file(tmp_path: Path) -> None:
    filepath = tmp_path / "prompt.md"
    filepath.write_text("You are a helpful assistant.")
    node = LlmPromptFromFile().instantiate(path=str(filepath))
    frag = LlmPromptFromFile().preview(node)
    assert "ef.llm.prompt_from_file(" in frag.body
    assert str(filepath) in frag.body


def test_adr_0002_equivalence(tmp_path: Path) -> None:
    filepath = tmp_path / "prompt.md"
    content = "You are a helpful assistant."
    filepath.write_text(content)
    node = LlmPromptFromFile().instantiate(path=str(filepath))
    graph = Graph(nodes={node.id: node})

    exec_results = ef.execute(graph)
    exec_text = exec_results[node.id]["text"]

    source = ef.compile_to_code(graph)
    scope: dict = {}
    exec(source, scope)  # noqa: S102 -- test-only, trusted source
    compiled_results = scope["main"]()
    compiled_text = next(iter(compiled_results.values()))

    assert exec_text == compiled_text == content
