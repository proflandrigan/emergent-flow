"""
colonymind.nodes.examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node definitions that conform to the Story 3 contract.

These are deliberately minimal, dependency-free implementations whose purpose is
to *prove the contract* — not to be the production data-science wrappers (those
arrive in Story 8 on top of this same base class, backed by pandas/Pingouin/etc.).

To keep ADR 0002's "execute == compiled code" invariant trivially true and the
test-suite dependency-free, each node's ``execute`` and ``codegen`` both route
through the same small runtime helper (``read_csv_rows`` / ``impute_missing``).
This also models the Story 7 "thin wrapper" rule: exported code calls SDK
functions rather than re-implementing them inline.
"""

from .impute import ImputeMissing
from .load_csv import LoadCsv

__all__ = ["LoadCsv", "ImputeMissing"]
