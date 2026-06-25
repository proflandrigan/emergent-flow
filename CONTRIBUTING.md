# Contributing to Emergent Flow

Welcome! We are excited that you want to contribute to the Emergent Flow open-source SDK.

## Contributor License Agreement

All contributors must agree to the [CLA](./CLA.md) before their pull requests can be merged. The CLA Assistant bot will prompt you to agree on your first PR.

Emergent Flow uses a license-grant CLA. This means you retain your copyright, but you grant the project maintainers a broad, relicensable license to your contribution. This allows the project to evolve its licensing in the future if necessary. For more details, see [CLA.md](./CLA.md).

## Development setup

To set up your local development environment, clone the repository and run the following commands:

```
python -m venv .venv && source .venv/bin/activate
pip install -e . --group dev
```

## Checks before opening a PR

We run several checks in CI to ensure code quality. Please run them locally before opening a pull request:

```
ruff check .
ruff format --check .
mypy
pytest
```

## Dependency & licensing rules

Any new runtime dependencies must be Apache-2.0-compatible and permissive. We do not accept dependencies that require copyleft licenses (like GPL or AGPL). For more information, please refer to [Dependency Licensing & Compatibility](./docs/licensing-and-dependencies.md).

## Open-core boundary

Contributions made to this repository are for the open-source SDK. The Emergent Flow platform itself is managed in a separate proprietary repository. Please read the [Open-Core Boundary](./docs/open-core-boundary.md) documentation for more details. 

Remember that SDK code must not import any platform-only code.

## Commit & PR conventions

- Keep pull requests small and focused on a single change.
- Write clear and descriptive commit messages.
- Ensure that CI remains green for your PR.
