"""
colonymind.nodes.examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Reference node definitions that conform to the Story 3 contract.

These are the real, library-backed Story 8 reference node families — no
longer the dependency-free toys from Story 3. Each node's ``execute`` and
``codegen`` both route through the same ``cm.*`` public-op wrapper
(``colonymind.data``, ``colonymind.clean``, ``colonymind.stats``,
``colonymind.ml``, ``colonymind.reports`` — backed by pandas, scikit-learn,
statsmodels, and ydata-profiling respectively), which keeps ADR 0002's
"execute == compiled code" invariant true by construction and models the
Story 7 "thin wrapper" rule: exported code calls SDK functions rather than
re-implementing them inline.
"""

from .anova import Anova
from .impute import ImputeMissing
from .load_csv import LoadCsv
from .nn_linear import NnLinear
from .nn_module import NnModule
from .nn_relu import NnReLU
from .report import GenerateHtmlSummary
from .train import TrainClassifier

__all__ = [
    "LoadCsv",
    "ImputeMissing",
    "Anova",
    "TrainClassifier",
    "GenerateHtmlSummary",
    "NnLinear",
    "NnReLU",
    "NnModule",
]
