# Emergent Flow Examples

Emergent Flow is a visual data/ML platform: a Python SDK (`emergentflow`, aliased `ef`) for
building and compiling data/ML pipelines as a graph IR, paired with a local React canvas
(`emergentflow serve`, at `localhost:8765`) for building the same pipelines visually. These
guides walk through both the SDK and the canvas, from installation through advanced topics
like LLM integration and declarative PyTorch models.

## Getting Started

- [Getting Started](getting-started.md) — Installation, first pipeline, launching the canvas

## Core Workflows

- [Data Loading & Cleaning](data-loading-and-cleaning.md) — Loading data and cleaning/transforming it
- [Exploratory Data Analysis](exploratory-data-analysis.md) — EDA, profiling, summary statistics
- [Visualization](visualization.md) — Charts and plots with the curated catalog
- [Feature Engineering](feature-engineering.md) — Scaling, encoding, feature selection

## Modeling

- [Machine Learning](machine-learning.md) — Classification, regression, clustering, pipelines
- [Statistical Modeling](statistical-modeling.md) — Linear models, GLMs, GAMs, mixed models, Bayesian
- [Time Series](time-series.md) — ARIMA, ETS, seasonal decomposition, feature transforms
- [Recommender Systems](recommender-systems.md) — Collaborative filtering, content-based, hybrids

## Advanced Topics

- [LLM Integration](llm-integration.md) — LLM calls, prompt templates, eval runs
- [Text Embeddings](text-embeddings.md) — API and local text embeddings
- [Model Explainability](model-explainability.md) — SHAP values, diagnostic plots
- [Custom Code](custom-code.md) — User-defined Python transforms
- [Declarative PyTorch](declarative-pytorch.md) — PyTorch nn.Module compilation
- [Graph IR & Compilation](graph-ir-and-compilation.md) — Graph IR, compile_to_code, execute
- [Canvas UI Guide](canvas-ui-guide.md) — Using the visual canvas
