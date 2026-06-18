# Codegen Compiler (Story 5)

The code-generation engine (`colonymind.codegen`, Epic 2) turns a graph IR into runnable Python code (`cm.compile_to_code`, Story 5). This document details the key decisions and architectural patterns adopted during the implementation of the compiler.

## Public surface

The `compile_to_code` function is exposed through the lazily-imported `cm` namespace:

```python
import colonymind as cm

source = cm.compile_to_code(graph)  # str — a complete, runnable Python module
```

For details on how the compiler traverses the graph, refer to [How codegen traversal works](codegen-traversal.md). Further architectural decisions are captured in [ADR 0008: Codegen templating vs AST](adr/0008-codegen-templating-vs-ast.md), [ADR 0009: Codegen binding context](adr/0009-codegen-binding-context.md), and [ADR 0010: Codegen package placement](adr/0010-codegen-package-placement.md).

## Module shape

The generated Python module is structured with a `def main() -> None:` function wrapping a flat sequence of per-node statements, guarded by an `if __name__ == "__main__": main()` block. This design ensures that importing the generated module does not inadvertently execute the pipeline as a side effect, mirroring the `run()`/`main()`/guard pattern found in `examples/vertical_slice/demo.py`.

## Dangling required IN ports are a hard compile-time error

Any required input (IN) port on a node that remains unconnected at compile-time will result in an `UnboundInputError`. The compiler treats these as hard errors rather than attempting silent fallbacks. This "fail fast and clearly" approach, consistent with `docs/public-api-conventions.md`, prevents runtime failures that would otherwise occur when the generated code references an undefined variable.

## Import collection

All `import` statements gathered from individual node code fragments are consolidated into a `set` to ensure uniqueness, then `sorted()` alphabetically, and finally joined to form the import block of the generated module. Currently, the reference-node catalog primarily emits `"import colonymind as cm"`. The alphabetical join is only a stable pre-order: the formatting pass (below) runs `ruff check --select I` over the assembled module, so the final import block is grouped isort-clean (stdlib before third-party) even once the node catalog emits a more diverse mix of imports.

## The ruff normalization passes

As specified in [ADR 0008](adr/0008-codegen-templating-vs-ast.md), a ruff normalization step is the final stage before `compile_to_code` returns the generated source code. This is invoked via `colonymind.codegen.formatting.format_source`, which shells out to `python -m ruff` twice over stdin: first `ruff check --select I --fix` to organize imports (since `ruff format` never reorders them, a stdlib + third-party mix would otherwise emit `I001`-dirty output), then `ruff format` to normalize whitespace, quotes and line length. The `--select I` flag forces the import-order rule regardless of config discovery, and every `I` violation is auto-fixable, so the pass only fails if the assembled source does not parse. Consequently, `ruff` is now a runtime dependency (listed in `[project.dependencies]` in `pyproject.toml`), not solely a development tool, due to its integral role in maintaining code style and consistency.

## Paradigm scope

The `compile_to_code` function is designed to exclusively handle graphs and nodes adhering to `Paradigm.FUNCTIONAL`. Any attempt to compile a `Paradigm.DECLARATIVE` graph or node will raise a `CodegenError`. Support for the declarative paradigm, involving `libcst`-based transformations, is slated for Epic 2 Story 8.
