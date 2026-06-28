"""Worked example: the Emergent Flow acceptance-demo pipeline.

load_sample(diabetes) -> drop_missing -> select_columns -> train_test_split
  -> train_regressor -> evaluate
  select_columns also fans out to stats.describe and reports.generate_html_summary

Run directly:  python examples/acceptance_demo/demo.py
"""

from __future__ import annotations

import pathlib
from typing import Any

import emergentflow as ef

HERE = pathlib.Path(__file__).parent


def run(
    *,
    output_dir: pathlib.Path | str = HERE,
) -> dict[str, Any]:
    """Execute the full acceptance-demo pipeline and return a summary dict.

    Uses the bundled ``diabetes`` sample dataset (zero filesystem setup). Writes
    the HTML report to ``output_dir/report.html`` and returns the path plus the
    key inspectable metrics from each stage.
    """
    output_dir = pathlib.Path(output_dir)

    frame = ef.data.load_sample(name="diabetes")
    clean = ef.clean.drop_missing(frame, axis="rows", how="any")
    sel = ef.clean.select_columns(clean, columns=["age", "bmi", "bp", "s1", "target"], drop=False)
    train, test = ef.ml.train_test_split(sel, test_size=0.25, random_state=0)
    model = ef.ml.train_regressor(train, target="target", features=["age", "bmi", "bp", "s1"])
    result = ef.ml.evaluate(model, test)
    summary_df = ef.stats.describe(sel)
    html = ef.reports.generate_html_summary(sel, title="Emergent Flow — Acceptance Demo")

    report_path = output_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")

    return {
        "report_path": report_path,
        "r2": result.metrics["r2"],
        "mae": result.metrics["mae"],
        "n_test": result.n,
        "n_rows": int(frame.shape[0]),
        "describe_rows": int(summary_df.shape[0]),
    }


def main() -> None:
    summary = run()
    print(f"Loaded {summary['n_rows']} rows")
    print(f"Model  : R²={summary['r2']:.3f}  MAE={summary['mae']:.2f}")
    print(f"n_test : {summary['n_test']}")
    print(f"Report : {summary['report_path']}")


if __name__ == "__main__":
    main()
