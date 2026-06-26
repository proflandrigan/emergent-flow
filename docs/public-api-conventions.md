# Public API Conventions

This document defines the conventions for the emergentflow SDK's public API. These standards ensure that all wrapped operations are predictable, inspectable, and maintainable across the library's namespaces.

## Naming

**Package and Alias:**
- The package is `emergentflow`; the public alias is `import emergentflow as ef`. Never use `omnicanvas` or `oc`.

**Namespace Structure:**
- Functional namespaces are noun-based domains: `ef.data`, `ef.clean`, `ef.stats`, `ef.ml`, `ef.reports`.
- Each namespace groups related operations by domain.

**Function Names:**
- Functions are `lower_snake_case` verb phrases that clearly describe the operation: `load_csv`, `impute_missing`, `anova`, `train_classifier`, `generate_html_summary`.
- Function names should state the action without ambiguity.

**Parameters:**
- Parameter names are `lower_snake_case`.
- Avoid abbreviations except well-known, domain-standard ones: `df` (DataFrame), `csv` (file format).

## Signatures

All public functions must follow these signature conventions:

**Parameter Order:**
- The primary data argument is the first positional parameter (e.g., `df`, `data`).
- All other parameters are keyword-only (enforced via `*` in the signature).
- Every parameter and return value must be type-annotated.

**Defaults:**
- Keyword-only parameters have explicit defaults.
- Defaults should be sensible and well-documented.

**Input Immutability:**
- Public functions must not mutate their input arguments.
- Return new objects instead of modifying inputs in-place.

**Example Signature Pattern:**
```python
def anova(df: pd.DataFrame, *, group_col: str, value_col: str, alpha: float = 0.05) -> AnovaResult:
    """
    Perform one-way ANOVA on grouped data.
    
    Args:
        df: Input DataFrame.
        group_col: Column name for grouping variable.
        value_col: Column name for continuous variable.
        alpha: Significance level (default 0.05).
    
    Returns:
        AnovaResult: Structured result with test statistic, p-value, and effect size.
    """
    ...
```

## Return Objects

Every public function must return a **serializable and inspectable object**:

**Required Properties:**
- Return values must be Pydantic models, dataclasses, or tidy DataFrames (never opaque library-internal handles as the sole return).
- Every return object must be JSON-serializable and human-readable.
- Users must be able to inspect the structure without specialized knowledge.

**Multi-Value Returns:**
- Prefer named structured results (a model or dataclass) over bare tuples.
- This makes code more readable and future-proof for API extensions.

**Enforcement:**
- These conventions are enforced at runtime and in CI by `emergentflow.api`: decorate every
  wrapper with `@ef.public_op` (it validates the return via `assert_inspectable` on each
  call and registers it in `PUBLIC_OPS`), and `tests/test_api_conventions.py` sweeps the
  registry to flag opaque/non-serializable returns. See
  [SDK Design Philosophy](sdk-design-philosophy.md). Compliance is a design-time requirement.

## Determinism & Purity

**Thin Wrappers:**
- Public functions are thin, direct wrappers over trusted underlying libraries.
- The SDK adds convenience, schema alignment, and consistency—not reimplementation.

**Determinism:**
- Given the same inputs, a function must produce the same output.
- Where randomness is necessary, it must be seeded deterministically (e.g., via explicit `random_seed` parameter).

**Purity:**
- Functions should be pure: no hidden global state, no side effects beyond what the function name implies.
- The only expected I/O is what the function signature declares.

## Errors

**Exception Strategy:**
- Raise specific, typed exceptions with actionable error messages.
- Do not mask underlying library errors; wrap them with context if needed.

**Input Validation:**
- Validate inputs at the boundary (at the public function entry point).
- Mirror the IR's validate-on-load posture: fail fast and clearly.

**Example:**
```python
def load_csv(filepath: str, *, encoding: str = "utf-8") -> DataLoadResult:
    if not filepath or not isinstance(filepath, str):
        raise ValueError(f"filepath must be a non-empty string, got {filepath!r}")
    if not Path(filepath).exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    ...
```

## Before / After Example

**Illustrative Example (Story 8 implements these functions):**

**Compliant Pattern:**
```python
# Good: returns an inspectable, structured result
result = ef.stats.anova(df, group_col="group", value_col="score", alpha=0.05)

# result is an AnovaResult dataclass with:
#   - f_statistic: float
#   - p_value: float
#   - effect_size: float
#   - summary: pd.DataFrame (group means, counts, etc.)

print(result.p_value)  # 0.0234
print(result.summary)  # readable table of group stats
```

**Anti-Pattern (do NOT follow):**
```python
# Bad: returns an opaque handle
handle = external_lib.anova(df, group_col="group", value_col="score")
# Users cannot inspect handle without knowing external_lib's internals
# No way to serialize or introspect the result
```

The compliant pattern ensures that:
- Results are human-readable and machine-serializable.
- Users understand what they are working with.
- The API is stable and extensible.

## Related Documentation

For more information, see:
- [SDK Design Philosophy](sdk-design-philosophy.md) — the thin/deterministic/pure rules and their enforcement.
- [Package Layout](package-layout.md) — structure of the SDK's namespaces and modules.
- [Versioning and Releases](versioning-and-releases.md) — semantic versioning and release process.
