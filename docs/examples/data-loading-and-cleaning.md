# Data Loading & Cleaning

Emergent Flow's `ef.data` family loads tabular data — from files, bundled samples, or a data
warehouse — into tidy pandas DataFrames, and `ef.clean` provides composable operations for
handling missing values, selecting columns, casting types, and filtering rows. This guide walks
through both families and shows a realistic pipeline chaining several cleaning steps together.

## 1. Loading Data

### load_sample (no files needed)

Emergent Flow bundles a few small, permissively-licensed sample datasets (via scikit-learn) so
you can try things out with zero files on disk:

```python
import emergentflow as ef

df = ef.data.load_sample("iris")
print(df.shape)   # (150, 5)
print(df.head())
```

| sepal length (cm) | sepal width (cm) | petal length (cm) | petal width (cm) | target |
| ---: | ---: | ---: | ---: | ---: |
| 5.1 | 3.5 | 1.4 | 0.2 | 0 |
| 4.9 | 3.0 | 1.4 | 0.2 | 0 |
| 4.7 | 3.2 | 1.3 | 0.2 | 0 |
| 4.6 | 3.1 | 1.5 | 0.2 | 0 |
| 5.0 | 3.6 | 1.4 | 0.2 | 0 |

Available samples: `"iris"` (classification), `"wine"` (classification), `"diabetes"`
(regression). Each returns a DataFrame with the dataset's feature columns plus a `target` column.

### load_csv

```python
df = ef.data.load_csv("data/sales.csv", encoding="utf-8")
```

Given a CSV like:

```
date,product,quantity,revenue
2024-01-01,Widget A,100,2500.00
2024-01-02,Widget B,75,1875.00
2024-01-03,Widget A,120,3000.00
```

`load_csv` returns:

| date | product | quantity | revenue |
| --- | --- | ---: | ---: |
| 2024-01-01 | Widget A | 100 | 2500.00 |
| 2024-01-02 | Widget B | 75 | 1875.00 |
| 2024-01-03 | Widget A | 120 | 3000.00 |

`encoding` defaults to `"utf-8"` and is otherwise a thin pass-through to `pandas.read_csv`.

### load_json

```python
df = ef.data.load_json("data/events.json", orient="records")

# JSON Lines format
df = ef.data.load_json("data/logs.jsonl", lines=True)
```

`orient` is passed straight through to `pandas.read_json` (e.g. `"records"`); set `lines=True`
to read a `.jsonl`/newline-delimited-JSON file, one JSON object per line.

### load_parquet

```python
df = ef.data.load_parquet("data/large_dataset.parquet", columns=["user_id", "score"])
```

`columns`, when given, reads only that subset of columns (pushed down to the pyarrow engine)
rather than loading the whole file and selecting afterward.

## 2. Cleaning Data

Every `ef.clean` operation returns a **new** DataFrame — the input is never mutated — so you can
chain them freely, or reuse the original frame across several branches of a pipeline.

### Setup

```python
import pandas as pd
import numpy as np

df = pd.DataFrame({
    "name": ["Alice", "Bob", None, "Diana", "Eve"],
    "age": [25, np.nan, 30, np.nan, 22],
    "salary": [50000, 60000, np.nan, 70000, 45000],
    "department": ["Engineering", "Sales", "Engineering", None, "Sales"],
})
```

| name | age | salary | department |
| --- | ---: | ---: | --- |
| Alice | 25.0 | 50000.0 | Engineering |
| Bob | NaN | 60000.0 | Sales |
| None | 30.0 | NaN | Engineering |
| Diana | NaN | 70000.0 | None |
| Eve | 22.0 | 45000.0 | Sales |

### impute_missing

```python
# Impute numeric columns with mean (default)
cleaned = ef.clean.impute_missing(df, strategy="mean")
```

`age` and `salary` are the only numeric columns, so both are imputed. `age`'s NaNs become the
mean of `25, 30, 22` = `25.67`; `salary`'s NaN becomes the mean of `50000, 60000, 70000, 45000`
= `56250.0`:

| age (before) | age (after) | salary (before) | salary (after) |
| ---: | ---: | ---: | ---: |
| 25.0 | 25.0 | 50000.0 | 50000.0 |
| NaN | 25.67 | 60000.0 | 60000.0 |
| 30.0 | 30.0 | NaN | 56250.0 |
| NaN | 25.67 | 70000.0 | 70000.0 |
| 22.0 | 22.0 | 45000.0 | 45000.0 |

```python
# Impute specific columns with median
cleaned = ef.clean.impute_missing(df, strategy="median", columns=["age"])

# Impute categorical with most_frequent
cleaned = ef.clean.impute_missing(df, strategy="most_frequent", columns=["department"])
```

When `columns` is omitted, the target defaults to every column for `"most_frequent"`, but only
the numeric columns for `"mean"`/`"median"` (undefined on non-numeric data). Available
strategies: `"mean"`, `"median"`, `"most_frequent"`.

### drop_missing

```python
# Drop rows with any missing value
cleaned = ef.clean.drop_missing(df)                          # 2 rows remain (Alice, Eve)

# Drop only if ALL values in a row are missing
cleaned = ef.clean.drop_missing(df, how="all")                # 5 rows remain (no row is fully empty)

# Drop based on specific columns
cleaned = ef.clean.drop_missing(df, subset=["age"])           # 3 rows remain (drops Bob, Diana)

# Drop columns that have any missing values
cleaned = ef.clean.drop_missing(df, axis="columns")           # every column has a missing value here, so all four are dropped
```

`axis="rows"` (default) drops rows; `axis="columns"` drops columns. `how="any"` (default) drops
if any cell is missing; `how="all"` only if every cell in the row is missing. `subset` narrows
which columns are considered and only applies when `axis="rows"`.

### select_columns

```python
# Keep only these columns
subset = ef.clean.select_columns(df, columns=["name", "salary"])

# Drop specific columns (keep the rest)
subset = ef.clean.select_columns(df, columns=["department"], drop=True)
```

With `drop=False` (default) the result contains exactly `columns`, in the given order; with
`drop=True` those columns are removed and the rest kept in their original order.

### cast_types

```python
cleaned = ef.clean.impute_missing(df, strategy="mean", columns=["age"])
typed = ef.clean.cast_types(cleaned, dtypes={"age": "int"})
```

After imputation `age` is `[25.0, 25.67, 30.0, 25.67, 22.0]` (`float64`, since a NaN in an
`int`-backed column forces a float dtype); casting to `"int"` truncates each value, giving
`[25, 25, 30, 25, 22]` as a plain `int64` column. `dtypes` maps column name to one of
`"int"`, `"float"`, `"str"`, `"bool"`, `"category"`.

### filter_rows

```python
# Equality filter
engineers = ef.clean.filter_rows(df, column="department", operator="==", value="Engineering")
# 2 rows: Alice, and the row with a missing name

# Comparison filter
high_salary = ef.clean.filter_rows(df, column="salary", operator=">=", value=55000)
# 2 rows: Bob (60000), Diana (70000)

# Membership filter
subset = ef.clean.filter_rows(df, column="department", operator="isin", value=["Engineering", "Sales"])
# 4 rows: every row except Diana, whose department is missing
```

Available operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `isin` (which requires a list/tuple
`value`).

## 3. Chaining Operations

Because every `ef.data`/`ef.clean` operation takes and returns a plain DataFrame, they compose
naturally with pandas' own `.pipe()`:

```python
df = ef.data.load_csv("data/customers.csv")

clean_df = (
    ef.clean.drop_missing(df, subset=["age", "income"])
    .pipe(ef.clean.cast_types, dtypes={"age": "int"})
    .pipe(ef.clean.filter_rows, column="age", operator=">=", value=18)
    .pipe(ef.clean.select_columns, columns=["name", "age", "income", "region"])
)
```

## 4. In the Canvas

> **In the Canvas:** Add a `load_csv` node, configure its `filepath` parameter, then connect its
> output to a `drop_missing` node. Chain as many cleaning nodes as needed — each takes a
> DataFrame in and passes a cleaned DataFrame out. See [Canvas UI Guide](canvas-ui-guide.md).

## 5. Data Warehouse Queries (optional)

`ef.data.query()` runs read-only SQL against a configured warehouse connection (DuckDB,
Postgres, BigQuery, or Redshift) and returns a tidy DataFrame:

```python
df = ef.data.query(
    connection="my_postgres",
    dialect="postgres",
    sql="SELECT user_id, created_at, revenue FROM orders WHERE revenue > 100",
)
```

This requires both a connection profile configured in
`~/.config/emergentflow/connections.toml` and a warehouse client injected at execution time
(`ef.execute(graph, client=...)` or the compiled module's `main(client=...)`) — see the
connection docs for setup.
