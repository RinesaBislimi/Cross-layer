"""Temporal / order-aware evaluation for CICIDS2017 (answers R2, R4).

The main experiment uses a stratified random 70/15/15 split.  A random split can
overstate performance because flows from the same attack burst can land in both
train and test.  Here we repeat the evaluation with an ORDER-PRESERVING split:
the first 70% of the file (in capture order) is used for training, the next 15%
for validation and the final 15% for testing, so the model is evaluated on
traffic that occurs strictly *after* what it was trained on -- closer to
deployment.  We report the gap between the random and temporal protocols.

Because the shipped CICIDS2017 CSV is grouped by attack type rather than by a
wall-clock timestamp, "temporal" here means capture/file order; we state this
limitation explicitly in the manuscript.

Run:  python experiments/temporal_cicids.py
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

import lightgbm as lgb

from datasets import CICIDS_ORIG_COLS, DATA

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("experiments.temporal_cicids")

RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)


def load_in_order(n: int = 150_000) -> "tuple[pd.DataFrame, np.ndarray]":
    """Load the first n rows in file (capture) order, with the same cleaning."""
    df = pd.read_csv(DATA / "cicids" / "cicids.csv",
                     usecols=CICIDS_ORIG_COLS + ["Attack Type"], nrows=n)
    feat = df[CICIDS_ORIG_COLS].apply(pd.to_numeric, errors="coerce")
    feat = feat.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = (df["Attack Type"].astype(str).str.strip().str.upper()
         .map(lambda v: 0 if v in ("BENIGN", "NORMAL TRAFFIC", "NORMAL",
                                   "BENIGN TRAFFIC", "WHITE") else 1)).to_numpy()
    return feat.reset_index(drop=True), y


def evaluate(X: np.ndarray, y: np.ndarray, tr_idx, te_idx) -> Dict:
    model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8,
                               random_state=42, verbose=-1, n_jobs=-1)
    model.fit(X[tr_idx], y[tr_idx])
    pred = model.predict(X[te_idx])
    proba = model.predict_proba(X[te_idx])[:, 1]
    yte = y[te_idx]
    return {
        "precision": round(float(precision_score(yte, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(yte, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(yte, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(yte, proba)), 4) if len(np.unique(yte)) > 1 else None,
        "n_train": int(len(tr_idx)), "n_test": int(len(te_idx)),
        "test_positive_rate": round(float(yte.mean()), 4),
    }


def main():
    out: Dict = {}
    Xdf, y = load_in_order(150_000)
    X = Xdf.to_numpy(dtype="float64")
    n = len(y)

    # order-preserving 70/15/15
    i70, i85 = int(0.70 * n), int(0.85 * n)
    order_idx = np.arange(n)
    out["temporal"] = evaluate(X, y, order_idx[:i70], order_idx[i85:])
    log.info("TEMPORAL (order-preserving): %s", out["temporal"])

    # stratified random 70/15/15 on the same rows, for a like-for-like comparison
    rng = np.random.RandomState(42)
    perm = rng.permutation(n)
    out["random"] = evaluate(X, y, perm[:i70], perm[i85:])
    log.info("RANDOM (shuffled):          %s", out["random"])

    out["delta_f1_random_minus_temporal"] = round(
        out["random"]["f1"] - out["temporal"]["f1"], 4)
    (RESULTS / "temporal_cicids_results.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
