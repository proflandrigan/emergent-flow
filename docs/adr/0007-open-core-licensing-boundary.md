# ADR 0007 — Open-core licensing boundary (Apache-2.0 SDK, proprietary platform)

- **Status:** Accepted — amended by [ADR 0013](0013-single-repo-bundled-ui-topology.md) (UI
  placement: the single-user canvas moves into this open package; the licensing model and the
  one-way dependency rule below are preserved)
- **Date:** 2026-06-17
- **Deciders:** Colony Mind core team

## Context

As the Colony Mind SDK reaches technical maturity, we must define the boundary between the open-source components and the proprietary platform features. This decision is required by Epic 1 Story 10 to ensure packaging and distribution strategies align with our commercial goals before the core SDK hardens.

Several forces are at play:
- **Adoption & Anti-lock-in:** To drive developer adoption, the SDK must deliver on the promise of "glass-box" Python. Users must be able to export, run, and modify their pipelines without being forced into a proprietary cloud platform.
- **Commercial Viability:** The project must maintain a sustainable business model. Features that provide significant operational or collaborative value (managed hosting, real-time collaboration, enterprise management) are the natural candidates for a proprietary platform.
- **Portability:** The SDK must stand alone. It must be installable via standard Python tools and remain fully functional without any platform dependencies.
- **License Compatibility:** To ensure the SDK can be embedded in both open and closed systems, we must avoid copyleft dependencies that could impose licensing obligations on downstream users or our own proprietary platform.

The IR machinery, codegen, and the standard node library form the natural "open core" of the project.

## Decision

We will implement an open-core model with the following definitions and rules:

1. **Licensing:** The `colonymind` Python SDK will be licensed under the **Apache License, Version 2.0 (Apache-2.0)**. This permissive license provides an explicit patent grant and ensures the SDK is freely embeddable.
2. **Document-only Boundary:** The boundary is enforced by code location. This repository contains only the open SDK. The platform/product code will live in a **separate, private repository** and will never be published here.
3. **SDK Inventory:** The open-source SDK includes:
   - IR schema and models (`colonymind/ir`).
   - The node-definition contract and registry (`colonymind/nodes`).
   - Graph serialization, versioning, and migrations.
   - The functional-pipeline node families (`data`, `clean`, `stats`, `ml`, `reports`).
   - The compile-to-code and execution machinery.
4. **Platform Inventory:** The proprietary platform includes:
   - The infinite-canvas visual UI (React Flow / Rete.js).
   - Real-time multiplayer and collaboration servers.
   - Managed hosting, execution orchestration, and billing.
   - The operational storage-tiering layer (managed Redis/object-store).
   - Premium connector nodes.
5. **One-way Dependency Rule:** The proprietary platform may depend on the open SDK. The open SDK **must not** depend on or import any platform-only code.
6. **Premium Nodes:** Premium nodes will be developed as plugins in the proprietary repository and integrated via the entry-point mechanism defined in [ADR 0006](0006-node-registry-and-plugin-discovery.md).
7. **License Optionality:** Contributions to the SDK will be accepted under a license-grant CLA. This ensures the project retains the option to relicense the SDK in the future if the commercial or legal landscape changes.

## Consequences

**Positive:**
- Drives adoption by offering a high-quality, permissively licensed toolset with no vendor lock-in.
- Simplifies packaging and distribution for the open-source community.
- Allows the SDK to be embedded in the proprietary platform without licensing conflicts.
- Clear separation of concerns between the execution engine (SDK) and the operational/UX layer (Platform).

**Negative / obligations:**
- We must rigorously enforce the one-way dependency rule to prevent proprietary "leaks" into the SDK.
- We must maintain a strict dependency audit to ensure all runtime dependencies remain Apache-2.0 compatible (see [../licensing-and-dependencies.md](../licensing-and-dependencies.md)).
- Contributors must sign a CLA, which may slightly increase the friction for community contributions.

**Deferred:**
- The actual creation and organization of the proprietary repository.
- The catalog of specific premium nodes to be developed.
- Implementation of automated linting to enforce the one-way dependency rule.
