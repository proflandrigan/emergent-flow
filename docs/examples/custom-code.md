# Custom Code

Write custom Python transforms as graph nodes. Define a `transform(value)` function;
Emergent Flow compiles and executes it in a fresh namespace.

## 1. Basic Usage

```python
import emergentflow as ef

code = """
def transform(value):
    return value.upper()
"""

result = ef.script.run_code(code, "hello world")
print(result)  # "HELLO WORLD"
```

`run_code(code, value)` compiles *code*, extracts the top-level `transform` function, calls
`transform(value)`, and returns its result.

## 2. DataFrame Transforms

```python
import pandas as pd

df = pd.DataFrame({"name": ["Alice", "Bob"], "score": [85, 92]})

code = """
def transform(value):
    df = value.copy()
    df["grade"] = df["score"].apply(lambda s: "A" if s >= 90 else "B")
    return df
"""

result = ef.script.run_code(code, df)
print(result)
```

```
    name  score grade
0  Alice     85     B
1    Bob     92     A
```

## 3. Using External Libraries

```python
code = """
import numpy as np

def transform(value):
    df = value.copy()
    df["log_score"] = np.log(df["score"])
    return df
"""

result = ef.script.run_code(code, df)
```

Any library installed in the environment is available inside custom code — imports at the
top of *code* are executed in the same fresh namespace as `transform`.

## 4. Error Handling

```python
# Missing transform function -> CustomCodeError
try:
    ef.script.run_code("x = 1", "hello")
except ef.script.CustomCodeError as e:
    print(e)  # "custom code must define a callable named 'transform'; found nothing."

# Syntax error -> CustomCodeError
try:
    ef.script.run_code("def transform(value): return value +", "hello")
except ef.script.CustomCodeError as e:
    print(e)  # "custom code failed to compile: ..."
```

`CustomCodeError` (a `ValueError` subclass) covers exactly two cases: *code* fails to
parse/compile, or the compiled code does not define a callable named `transform`. Runtime
errors raised *inside* `transform()` itself propagate as-is — they are not wrapped in
`CustomCodeError`.

## 5. Complex Example: Feature Engineering

```python
code = """
import pandas as pd

def transform(value):
    df = value.copy()
    # Create interaction features
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    for i, col1 in enumerate(numeric_cols):
        for col2 in numeric_cols[i+1:]:
            df[f"{col1}_x_{col2}"] = df[col1] * df[col2]
    return df
"""

df = ef.data.load_sample("iris")
result = ef.script.run_code(code, df)
print(result.shape)  # more columns than the original
```

> **In the Canvas:** Add a `custom_code` node and write your `def transform(value):` function
> in the Config tab's code editor. The node receives the upstream DataFrame (or any value) as
> `value` and passes its return value downstream. The generated Python module inlines your
> transform function with AST-based variable renaming. See
> [Canvas UI Guide](canvas-ui-guide.md).

## Security Note

Custom code runs with full interpreter privileges — the same trust level as the local
Emergent Flow server. Never run custom code from untrusted sources.
