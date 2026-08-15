2. Ensembling / blending / stacking
ensemble_model (bagging/boosting wrapper around a single estimator) — no equivalent node.
blend_models (weighted average of multiple models) — no equivalent node.
stack_models (stacking ensemble) — no equivalent node.
emergent flow has individual fit_estimator/train_* nodes and compare_models, but no metalevel ensemble operations that combine fitted models.

3. Model tuning beyond grid search
tune_model (randomized / automated hyperparameter search with CV) — emergent flow has grid_search but no randomized/automated tuner.

4. Post-fit model operations
calibrate_model (probability calibration) — no equivalent node.
optimize_threshold (classification decision-threshold optimization) — no equivalent node.
finalize_model (refit on the full dataset after CV) — no equivalent node (emergent flow fit_estimator fits once; no "fit on all data after validation" step).