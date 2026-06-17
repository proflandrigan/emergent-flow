"""Worked example: the Colony Mind functional-pipeline vertical slice.

load_csv -> impute_missing -> (anova, train_classifier, generate_html_summary)

Run directly:  python examples/vertical_slice/demo.py
"""

from __future__ import annotations

import pathlib
from typing import Any

import colonymind as cm

HERE = pathlib.Path(__file__).parent
SAMPLE_CSV = HERE / "sample.csv"


def run(
    *,
    csv_path: pathlib.Path | str = SAMPLE_CSV,
    output_dir: pathlib.Path | str = HERE,
) -> dict[str, Any]:
    """Execute the full vertical slice and return a summary dict.

    Writes the HTML report to ``output_dir/report.html`` and returns the path
    plus the key inspectable metrics from each stage.
    """
    output_dir = pathlib.Path(output_dir)
    frame = cm.data.load_csv(str(csv_path))
    clean = cm.clean.impute_missing(frame, strategy="median")
    anova_result = cm.stats.anova(clean, group_col="cohort", value_col="score")
    classifier = cm.ml.train_classifier(
        clean, target="converted", features=["age", "spend", "score"], random_state=0
    )
    html = cm.reports.generate_html_summary(clean, title="Colony Mind — Vertical Slice")
    report_path = output_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return {
        "report_path": report_path,
        "anova_p_value": anova_result.p_value,
        "anova_f_statistic": anova_result.f_statistic,
        "accuracy": classifier.accuracy,
        "n_rows": int(frame.shape[0]),
    }


def main() -> None:
    summary = run()
    print(f"Loaded {summary['n_rows']} rows")
    print(f"ANOVA  : F={summary['anova_f_statistic']:.2f}  p={summary['anova_p_value']:.4g}")
    print(f"Model  : accuracy={summary['accuracy']:.3f}")
    print(f"Report : {summary['report_path']}")


if __name__ == "__main__":
    main()
