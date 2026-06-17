# Dependency Licensing & Compatibility

The colonymind SDK is licensed under the Apache License, Version 2.0 (Apache-2.0). To maintain the SDK's status as a permissively licensed tool that is freely embeddable, every runtime dependency must be license-compatible with Apache-2.0. This compatibility is a core selection criterion for any wrapped library or framework, used alongside the requirement that libraries return inspectable, structured data (see [SDK Design Philosophy](./sdk-design-philosophy.md)).

## Compatibility matrix

The following table lists the current runtime dependencies and their licenses.

| Dependency | Version constraint | License | Compatible with Apache-2.0? |
|---|---|---|---|
| pydantic | >=2.5,<3 | MIT | Yes |
| pandas | >=2,<3 | BSD-3-Clause | Yes |
| statsmodels | >=0.14,<1 | BSD-3-Clause | Yes |
| scikit-learn | >=1.4 | BSD-3-Clause | Yes |
| ydata-profiling | >=4 | MIT | Yes |
| setuptools | >=68,<81 | MIT | Yes |

## Why permissive-only

Apache-2.0 is a permissive license. Using dependencies with similarly permissive licenses (such as MIT and BSD) ensures that no strong copyleft obligations are imposed on the combined distribution. This preserves the open-core goal that the SDK remains freely embeddable in both open-source and proprietary platforms. A required copyleft (GPL, AGPL, or LGPL when statically linked) dependency would defeat this objective by potentially forcing the entire SDK or the platform embedding it to adopt the copyleft license.

For more details on the distinction between the SDK and proprietary components, see the [Open Core Boundary](./open-core-boundary.md).

## Removed: pingouin (GPL-3.0) → statsmodels (BSD-3-Clause)

Previously, `pingouin` was used as the backend for `cm.stats.anova`. However, `pingouin` is licensed under GPL-3.0, a strong copyleft license whose obligations are incompatible with shipping a permissively licensed (Apache-2.0) SDK that requires it as a dependency.

To resolve this, `pingouin` was replaced by `statsmodels` (BSD-3-Clause). `statsmodels` provides one-way ANOVA via `OLS` (Ordinary Least Squares) and `anova_lm`, and it returns tidy `DataFrame`s. This satisfies the SDK's "returns inspectable structured data" selection rule. The public `anova` wrapper interface (`AnovaResult`) was preserved during this transition to ensure no breaking changes for users.

## Policy

To ensure ongoing license compliance and maintain the SDK's embeddability:

- New runtime dependencies MUST be under a permissive license (MIT, BSD, Apache-2.0, ISC, PSF) compatible with Apache-2.0.
- Copyleft (GPL/AGPL) libraries MUST NOT be added as *required* runtime dependencies.
- If a copyleft library is the only viable option for a specific feature, it must be implemented as an *optional extra* that the user must explicitly opt into (e.g., `pip install colonymind[extra-feature]`), with the copyleft implications clearly documented.
- Dependency licenses are re-checked whenever a new dependency is added or an existing one is upgraded.
