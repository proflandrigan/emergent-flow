# Versioning & Releases

The Emergent Flow SDK uses Semantic Versioning to manage releases and communicates changes to users
through version numbers. This document describes the versioning scheme and the automated tag-driven
release process.

## Semantic Versioning

Emergent Flow follows [Semantic Versioning](https://semver.org/) for the SDK package:

- **MAJOR** — incremented for incompatible API changes.
- **MINOR** — incremented for backward-compatible new features.
- **PATCH** — incremented for backward-compatible bug fixes.

### Pre-1.0 semantics

The SDK is currently at version `0.1.0` and operates under pre-1.0 semantics. During the `0.y.z`
phase:

- A **minor version bump** (e.g., `0.1.0` → `0.2.0`) **may introduce breaking changes**. Users
  should review release notes carefully.
- A **patch version bump** (e.g., `0.1.0` → `0.1.1`) indicates backward-compatible fixes only.

Once the SDK reaches `1.0.0`, MAJOR version bumps will be required for all breaking changes, and
the versioning contract becomes the standard SemVer promise.

## Three kinds of version

Version numbers appear in three distinct contexts within the SDK ecosystem. It is important to
keep them separate:

| Version Type | Scope | Managed by | Example |
| --- | --- | --- | --- |
| **SDK package version** | The `emergentflow` Python package on PyPI. | This document; bumped in `emergentflow/__init__.py::__version__`. | `0.1.0` |
| **IR schema version** | The serialization format of the intermediate representation (graphs). Applies to `schema_version` embedded in `.ef.json` files. | Story 9 (migration framework); no migration logic in this release. | `1` (current) |
| **Node catalog version** | The version of a node's contract (inputs, outputs, metadata). Set per-node in the node's catalog entry. | Individual node authors; does not affect SDK releases. | `1`, `2`, etc. |

Only the **SDK package version** is the subject of this document and the release workflow.

## Where the version lives

The SDK version is single-sourced in one place:

```
emergentflow/__init__.py::__version__ = "0.1.0"
```

This value is:

- Read directly by consumers: `from emergentflow import __version__`.
- Exposed to the build system via `pyproject.toml` dynamic version configuration:

```toml
[tool.setuptools.dynamic]
version = { attr = "emergentflow.__version__" }
```

This ensures the version number is always consistent: bump it in `__init__.py`, and the
built wheel and source distribution automatically get the same version.

## Release process

To release a new version of the SDK, follow these steps **in order**:

1. **Update the version** in `emergentflow/__init__.py`:
   ```python
   __version__ = "0.2.0"  # Change only this line
   ```

2. **Update the changelog** or release notes (if they exist in the repository).
   Describe the new features, bug fixes, and any breaking changes (especially important
   in the `0.y.z` phase).

3. **Create a pull request** on `main` with your version bump and changelog updates.
   Ensure that CI is green (tests pass, linting checks pass).

4. **Merge the PR** to `main`.

5. **Tag the release** on `main` with a git tag matching the version, prefixed with `v`:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

6. **The Release workflow runs automatically:**
   - GitHub Actions detects the `v*` tag.
   - Builds sdist and wheel with `uv build`.
   - Publishes to PyPI using Trusted Publishing (see below).
   - The new version becomes available to install via `pip install emergentflow==0.2.0`.

## Trusted Publishing

The release workflow uses **PyPI Trusted Publishing** (OIDC) to authenticate to PyPI. This means:

- **No API token secret is stored** in the repository or in GitHub's action secrets.
- **Authentication is automatic**: the GitHub Actions job exchanges a short-lived OIDC token
  for a PyPI API token at publish time.
- The repository and PyPI project must be linked ahead of time.

### Current status

The workflow in `.github/workflows/release.yml` is a **scaffold** that has not yet been exercised.
Before the first real release:

- PyPI Trusted Publishing must be configured for the `emergentflow` project on PyPI.
- Consult [PyPI's Trusted Publishing docs](https://docs.pypi.org/trusted-publishers/) for setup.
- Once configured, the workflow will publish automatically on each `v*` tag push.

## See also

- [Public API Conventions](public-api-conventions.md) — how to maintain backward compatibility.
- [Package Layout](package-layout.md) — the structure of the repository.
