# Dependency Licensing & Compatibility

The emergentflow SDK is licensed under the Apache License, Version 2.0 (Apache-2.0). To maintain the SDK's status as a permissively licensed tool that is freely embeddable, every runtime dependency must be license-compatible with Apache-2.0. This compatibility is a core selection criterion for any wrapped library or framework, used alongside the requirement that libraries return inspectable, structured data (see [SDK Design Philosophy](./sdk-design-philosophy.md)).

## Compatibility matrix

The following table lists the current runtime dependencies and their licenses.

| Dependency | Version constraint | License | Compatible with Apache-2.0? |
|---|---|---|---|
| pydantic | >=2.5,<3 | MIT | Yes |
| pandas | >=2,<3 | BSD-3-Clause | Yes |
| statsmodels | >=0.14,<1 | BSD-3-Clause | Yes |
| scikit-learn | >=1.4 | BSD-3-Clause | Yes |
| scipy | >=1.10 | BSD-3-Clause | Yes |
| ydata-profiling | >=4 | MIT | Yes |
| setuptools | >=68,<81 | MIT | Yes |
| litellm | >=1,<2 | MIT | Yes |
| plotly | >=5,<7 | MIT | Yes |

## Why permissive-only

Apache-2.0 is a permissive license. Using dependencies with similarly permissive licenses (such as MIT and BSD) ensures that no strong copyleft obligations are imposed on the combined distribution. This preserves the open-core goal that the SDK remains freely embeddable in both open-source and proprietary platforms. A required copyleft (GPL, AGPL, or LGPL when statically linked) dependency would defeat this objective by potentially forcing the entire SDK or the platform embedding it to adopt the copyleft license.

For more details on the distinction between the SDK and proprietary components, see the [Open Core Boundary](./open-core-boundary.md).

## Removed: pingouin (GPL-3.0) → statsmodels (BSD-3-Clause)

Previously, `pingouin` was used as the backend for `ef.stats.anova`. However, `pingouin` is licensed under GPL-3.0, a strong copyleft license whose obligations are incompatible with shipping a permissively licensed (Apache-2.0) SDK that requires it as a dependency.

To resolve this, `pingouin` was replaced by `statsmodels` (BSD-3-Clause). `statsmodels` provides one-way ANOVA via `OLS` (Ordinary Least Squares) and `anova_lm`, and it returns tidy `DataFrame`s. This satisfies the SDK's "returns inspectable structured data" selection rule. The public `anova` wrapper interface (`AnovaResult`) was preserved during this transition to ensure no breaking changes for users.

## Optional extra: `[bayes]` (pymc / bambi / arviz)

Epic 12's Bayesian modeling family (Story 7) is shipped as an **optional extra**, installed with
`pip install emergentflow[bayes]`, never as part of the base install. Its three dependencies are
all permissively licensed and compatible with Apache-2.0:

| Dependency | Version constraint | License | Compatible with Apache-2.0? |
|---|---|---|---|
| pymc | >=5,<6 | Apache-2.0 | Yes |
| bambi | >=0.13,<1 | MIT | Yes |
| arviz | >=0.17,<1 | Apache-2.0 | Yes |

The extra is kept optional for two reasons beyond licensing: `pymc` pulls `pytensor` and a C
toolchain, which would slow every base install and CI run, and a large fraction of users never
touch Bayesian modeling. The base package must import and run with all three absent; a Bayesian
node invoked in a base install raises a typed `MissingOptionalDependencyError("emergentflow[bayes]")`
rather than an opaque `ImportError`. This mirrors the repo's existing optional-dependency
discipline (the `torch`-style `pytest.importorskip` pattern and the existing `[server]`/`[llm]`
extras).

## Optional extra: `[recommend]` (implicit)

Epic 15's collaborative-filtering recommender family (Story 8) ships optimized implicit-feedback
matrix factorization (ALS, BPR) as an **optional extra**, installed with
`pip install emergentflow[recommend]`, never as part of the base install. Its one dependency is
permissively licensed and compatible with Apache-2.0:

| Dependency | Version constraint | License | Compatible with Apache-2.0? |
|---|---|---|---|
| implicit | >=0.7,<1 | MIT | Yes |

The base install already covers the sklearn-backed matrix-factorization path (`TruncatedSVD`,
`NMF`) without this extra — `implicit` is kept optional because its ALS/BPR implementations pull
C++/Cython extension builds that would slow every base install and CI run, and most users never
need the optimized implicit-feedback path. The base package must import and run with `implicit`
absent; an ALS/BPR recommender node invoked in a base install raises a typed
`MissingOptionalDependencyError("emergentflow[recommend]")` rather than an opaque `ImportError`.
This mirrors the repo's existing optional-dependency discipline (the `torch`-style
`pytest.importorskip` pattern and the existing `[bayes]`/`[explain]` extras).

`surprise` (BSD-3 but less maintained, pure Python, slower than sklearn's own SVD/NMF), `LensKit`
(MIT but heavy transitive deps), and `RecBole` (MIT but torch-only, overlapping the repo's own
torch-optional deep-recommender path) were all considered and deliberately not added — `implicit`
is the only library needed to cover the optimized implicit-feedback surface.

## Deliberately not added: seaborn

`plotly` (MIT) covers the interactive-charting surface Epic 12 needs, so **seaborn is intentionally
not a dependency**. Beyond avoiding a redundant charting stack, a `seaborn` dependency would drag
`matplotlib` into the render path and invite a PNG/raster "just one chart" escape hatch — exactly
the binary-artifact problem the `PlotSpec` (`fig.to_json()`, JSON-native) contract is
designed to avoid. The pingouin GPL ban recorded above likewise still stands: it is not
reintroduced for any convenience.

## Bundled sample datasets (`ef.data.load_sample`)

`ef.data.load_sample` bundles six sample datasets, split across two licensing categories:

| Dataset | Source | License |
|---|---|---|
| `iris`, `wine`, `diabetes` | scikit-learn's bundled toy datasets | BSD-3-Clause (already a dependency) |
| `web_traffic`, `reviews`, `transactions` | Generated in-process from a fixed seed | None (synthetic, no upstream license) |

The first three wrap real scikit-learn toy datasets and inherit scikit-learn's BSD-3-Clause
license, already covered by the compatibility matrix above. The last three (`web_traffic`, a
daily time series; `reviews`, a short product-review text corpus; `transactions`, a retail
transaction/event table) are synthetic data generated deterministically at call time from a
fixed seed (`emergentflow/data/__init__.py`) — they raise no licensing question at all, since
there is no upstream source, and they are not checked into the repo as data files. They are
not real-world data and must never be presented as such.

## Policy

To ensure ongoing license compliance and maintain the SDK's embeddability:

- New runtime dependencies MUST be under a permissive license (MIT, BSD, Apache-2.0, ISC, PSF) compatible with Apache-2.0.
- Copyleft (GPL/AGPL) libraries MUST NOT be added as *required* runtime dependencies.
- If a copyleft library is the only viable option for a specific feature, it must be implemented as an *optional extra* that the user must explicitly opt into (e.g., `pip install emergentflow[extra-feature]`), with the copyleft implications clearly documented.
- Dependency licenses are re-checked whenever a new dependency is added or an existing one is upgraded.
