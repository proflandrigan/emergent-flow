"""Worked example: segmentation study template.

Cap -> scale -> cluster -> validate -> profile -> report.

Loads the bundled wine dataset (178 rows, 13 features, 3 cultivar classes --
simulating an unlabelled segmentation use case). Caps outliers at P95, scales
features, clusters with KMeans, computes cluster-validation metrics, checks
cluster stability via bootstrap, profiles the clusters, and reports summary
statistics.

Run directly:  python examples/segmentation_study/demo.py
"""

from __future__ import annotations

import pathlib
from typing import Any

import emergentflow as ef

HERE = pathlib.Path(__file__).parent


def run(
    *,
    output_dir: pathlib.Path | str = HERE,
    n_clusters: int = 3,
    random_state: int = 0,
) -> dict[str, Any]:
    """Execute the segmentation-study template and return a summary dict.

    Uses the bundled ``wine`` sample dataset (zero filesystem setup). Writes
    no files; returns key metrics from each stage.
    """
    output_dir = pathlib.Path(output_dir)

    # Load
    frame = ef.data.load_sample(name="wine")

    # Cap outliers at P95 (no rows dropped)
    capped = ef.clean.detect_outliers(frame, method="quantile", threshold=0.05, action="clip")

    # Scale features (drop the non-numeric label column used by wine)
    numeric = ef.clean.select_columns(
        capped,
        columns=[
            "alcohol",
            "malic_acid",
            "ash",
            "alcalinity_of_ash",
            "magnesium",
            "total_phenols",
            "flavanoids",
            "nonflavanoid_phenols",
            "proanthocyanins",
            "color_intensity",
            "hue",
            "od280/od315_of_diluted_wines",
            "proline",
        ],
        drop=False,
    )
    _, scaled = ef.ml.fit_transform(numeric, estimator="StandardScaler")

    # Cluster
    _, clustered = ef.ml.fit_and_label(
        scaled,
        estimator="KMeans",
        params={"n_clusters": n_clusters, "random_state": random_state},
    )

    # Validate the clustering
    metrics = ef.stats.cluster_metrics(
        clustered,
        label_col="cluster",
        random_state=random_state,
    )
    stability = ef.stats.cluster_stability(
        scaled,
        estimator="KMeans",
        params={"n_clusters": n_clusters, "random_state": random_state},
        n_resamples=30,
        random_state=random_state,
    )
    profile_df = ef.stats.profile(clustered)
    summary = ef.stats.describe(clustered)

    return {
        "n_rows": int(frame.shape[0]),
        "n_clusters": metrics.n_clusters,
        "silhouette": metrics.silhouette,
        "calinski_harabasz": metrics.calinski_harabasz,
        "davies_bouldin": metrics.davies_bouldin,
        "mean_ari": float(stability["ari"].mean()),
        "profile_columns": list(profile_df.columns),
        "summary_rows": int(summary.shape[0]),
    }


def main() -> None:
    summary = run()
    print(f"Loaded {summary['n_rows']} rows")
    print(f"Clusters: {summary['n_clusters']}")
    print(f"Silhouette       : {summary['silhouette']:.4f}")
    print(f"Calinski-Harabasz: {summary['calinski_harabasz']:.2f}")
    print(f"Davies-Bouldin   : {summary['davies_bouldin']:.4f}")
    print(f"Mean ARI (30 boot): {summary['mean_ari']:.4f}")
    print(f"Profile columns   : {summary['profile_columns']}")
    print(f"Summary rows      : {summary['summary_rows']}")


if __name__ == "__main__":
    main()
