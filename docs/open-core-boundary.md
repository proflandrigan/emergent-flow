# Open-Core Boundary

Emergent Flow is developed using an open-core model. The foundational SDK is open source under the Apache License, Version 2.0 (Apache-2.0), while the collaborative platform, visual orchestration, and enterprise features are proprietary.

## What is in the open-source SDK (Apache-2.0)

The `emergentflow` Python SDK, contained in this repository, includes all the machinery required to define, serialize, and execute graph-based data pipelines:

- **IR schema & models (`emergentflow/ir`):** The internal representation of the graph, including models for nodes, edges, and schemas.
- **Node-definition contract:** The standard interface for defining new node types with serializable specs and Python behavior.
- **Node registry & plugin discovery (`emergentflow/nodes`):** The machinery for indexing node types and discovering third-party nodes via entry points.
- **Serialization:** Logic for graph serialization and deserialization (JSON).
- **Schema versioning & migrations:** The system for evolving the IR and migrating legacy graphs.
- **Functional-pipeline node families:** The standard catalog of data processing nodes, including `emergentflow/data` (loading), `clean`, `stats`, `ml`, and `reports`.
- **Execution machinery:** The compile-to-code and execute-the-IR engine that turns graphs into runnable Python.

## What is platform-only (proprietary)

The platform components are maintained in a separate, private repository and are never published in this repository. These include:

- **Infinite-canvas visual UI:** The React Flow / Rete.js frontend for visual graph authoring.
- **Collaboration server:** Real-time multiplayer and CRDT-based collaboration machinery.
- **Hosting & orchestration:** The managed environment for executing and scaling pipelines.
- **Storage-tiering operational layer:** The managed Redis and object-store integration for artifact persistence.
- **Enterprise features:** Authentication, billing, team management, and audit logs.
- **Premium connector nodes:** Proprietary nodes for specific enterprise data sources or services.

## The dependency rule

We enforce a strict one-way dependency rule to ensure the SDK remains independent and portable:

- **Platform → SDK:** The proprietary platform may depend on and import the `emergentflow` open-source SDK.
- **SDK ↛ Platform:** The open-source SDK MUST NOT depend on or import any platform-only code.

This ensures that the SDK remains fully functional and installable on its own (`pip install emergentflow`) without leaking any proprietary dependencies or "phoning home" to the platform.

## Premium nodes

Premium nodes are not part of the core SDK. They are implemented as out-of-core plugins using the standard entry-point mechanism defined in [ADR 0006](adr/0006-node-registry-and-plugin-discovery.md). Because they live in the proprietary repository, they can be shipped to customers without requiring any changes to the core SDK.

## Rationale

An open, permissively licensed SDK drives adoption by delivering on the project's core promise: **glass-box, exportable, lock-in-free Python**. Users can build and run their pipelines locally with the SDK, ensuring they are never locked into the proprietary platform.

The platform provides the commercial value through the collaborative canvas, managed hosting, and enterprise integrations.

Apache-2.0 was selected over MIT for its explicit patent grant. A permissive license was chosen over a copyleft license (like GPL) so the SDK can be freely embedded in both open-source and proprietary software (including our own platform). This commitment to permissiveness led to the replacement of GPL-3.0 dependencies, such as `pingouin`, as documented in [Dependency Licensing & Compatibility](licensing-and-dependencies.md).

## Related

- [ADR 0007: Open-core licensing boundary](adr/0007-open-core-licensing-boundary.md)
- [Dependency Licensing & Compatibility](licensing-and-dependencies.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
