"""
emergentflow.data.warehouse
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The data-source connector seam (Epic 13, ADR 0018): a second injected
effectful-client boundary mirroring ``emergentflow.llm`` (ADR 0017).

Nodes never open a database connection directly; they build a pure,
JSON-native ``QueryRequest`` and hand it to an injected ``WarehouseClient``.
This keeps ``execute`` / ``compile_to_code`` pure per ADR 0002 while real
warehouse queries happen only at the edge. Connection references in the IR are
a profile *name* only — never a credential (ADR 0018 secrets rule).

Submodules: ``protocol`` (the ``WarehouseClient``/``QueryRequest``/``QueryResult`` seam
types), ``replay`` (the pure, fixture-backed ``ReplayWarehouseClient``), ``query``
(``ef.data.query``, the one wrapper query nodes route through), ``profiles`` (the
local, secret-free ``ConnectionProfile`` store), ``credentials`` (env-var credential
resolution at the effect edge), ``preflight`` (the pre-run connection/credential
presence check), ``adapter_client`` (the effectful, per-dialect-adapter-dispatching
``WarehouseClient``), and ``params`` (the ``ConnectionRef`` node-param convention).
Concrete per-dialect adapters (DuckDB/BigQuery/Redshift/Postgres) and the query node
types themselves ship in later Epic 13 stories. This ``__init__`` deliberately stays
import-light and re-exports nothing — import the submodule you need directly.
"""

from __future__ import annotations
