# Experiments package — reproduces every table and figure of the paper

All scripts read the raw CSV files in `backend/data/` directly; the database and
API are **not** required. Results are written as JSON to `results/` and figures
as PNG to `figures/`. Run everything from `backend/`:

```bash
python experiments/run_models.py          # Table 7, Fig. 3: 6 models x 3 datasets x 5 seeds (~45 min)
python experiments/temporal_cicids.py     # Table 8: order-preserving vs random split on CICIDS2017
python experiments/correlation_eval.py    # Tables 9-10, Fig. 4: correlation engine, W sensitivity, ablation
python experiments/second_stage_eval.py   # Table 11: learned second-stage incident classifier
python experiments/benchmark.py           # Table 12: throughput, latency, memory (run on an idle machine)
python experiments/make_figures.py        # Figs. 1-4
python experiments/temporal_cicids_true.py <GeneratedLabelledFlows.zip>   # Table 8 (timestamped per-day flows)
python experiments/ait_ads_eval.py <dir with ait_ads.zip + labels.csv>      # Table 13 (AIT Alert Data Set)
```

| Script | Answers reviewer points |
|---|---|
| `datasets.py` | documented cleaning (inf/NaN/duplicates), stratified subsampling, class proportions, BGL alert-flag labels, TDA Isolation-Forest pseudo-labels (contamination 0.05) — R3, R4 |
| `run_models.py` | all six models on all datasets, precision/recall/F1/ROC-AUC mean ± SD over five seeds, 5-fold CV on the train partition only, train-only scaling (no leakage), train/inference time — R1.4, R2, R3, R4 |
| `temporal_cicids.py` | order-preserving (block) split for CICIDS2017 — R2, R4 |
| `correlation_eval.py` | alerts before/after, reconstructed incidents, false correlations, incident P/R/F1, W sensitivity, layer-order ablation, cross-seed variance — R1.1, R2, R3, R4 |
| `second_stage_eval.py` | learned cross-layer incident classifier vs rule baseline — R4 ("the cross-layer part is not ML") |
| `benchmark.py` | events/s, per-event latency (mean, p99), correlation scaling exponent, peak memory — R1.5, R3 |

Protocol: each dataset is subsampled once (seed 42); for each of the seeds
42, 7, 13, 21, 2024 the sample is split 70/15/15 (stratified); five-fold CV runs
on the 70 % train partition only; headline metrics are measured on the untouched
15 % test partition; the `StandardScaler` for SVM/MLP is fitted on the train
partition only.

Environment: Python 3.9, scikit-learn 1.5.1, xgboost 2.1.1, lightgbm 4.5.0,
pandas 2.2.2, numpy 1.26.4, matplotlib.
