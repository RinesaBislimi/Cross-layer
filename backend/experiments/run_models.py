"""Train and evaluate all six models on all three datasets.

Evaluation protocol (answers R2's "how do 70/15/15 and five-fold CV interact"):
  * Each dataset is first subsampled ONCE (random_state=42) and the class
    proportions are reported.
  * For each of N random seeds, the subsample is split 70/15/15
    (train/validation/test) with stratification. The seed controls the data
    partition and the model's stochastic initialisation.
  * Five-fold stratified cross-validation is run on the 70% TRAIN partition only
    (for a variance estimate / model selection); the headline precision, recall,
    F1 and ROC-AUC are measured on the untouched 15% TEST partition.
  * Scaling: StandardScaler is fit on the TRAIN partition only and applied to
    val/test (prevents leakage, relevant for SVM and MLP).
  * We report mean +/- SD of the test metrics across the N seeds, plus train and
    inference time (and events/sec), directly addressing R1.4, R2 and R4.

Run:  python -m experiments.run_models            (from backend/)
      python experiments/run_models.py
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier

import lightgbm as lgb

from datasets import Dataset, load_cicids, load_bgl, load_tda

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("experiments.run_models")

RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

SEEDS = [42, 7, 13, 21, 2024]
MODELS = ["rf", "xgboost", "lgbm", "svm", "mlp", "isolation_forest"]
SCALED = {"svm", "mlp"}  # tree models are scale-invariant


def make_model(kind: str, seed: int, pos_rate: float):
    if kind == "rf":
        return RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=-1)
    if kind == "xgboost":
        return XGBClassifier(n_estimators=100, learning_rate=0.1, max_depth=8,
                             random_state=seed, eval_metric="logloss", n_jobs=-1)
    if kind == "lgbm":
        return lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8,
                                  random_state=seed, verbose=-1, n_jobs=-1)
    if kind == "svm":
        return CalibratedClassifierCV(LinearSVC(random_state=seed, max_iter=2000, dual="auto"), cv=3)
    if kind == "mlp":
        return MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=300,
                             random_state=seed, early_stopping=True, validation_fraction=0.1)
    if kind == "isolation_forest":
        cont = float(min(0.5, max(0.01, pos_rate)))
        return IsolationForest(n_estimators=100, contamination=cont,
                               random_state=seed, n_jobs=-1)
    raise ValueError(kind)


def eval_once(kind: str, ds: Dataset, seed: int) -> Dict:
    X = ds.X.to_numpy(dtype="float64")
    y = ds.y
    strat = y if len(np.unique(y)) > 1 else None
    X_tr, X_tmp, y_tr, y_tmp = train_test_split(
        X, y, test_size=0.30, random_state=seed, stratify=strat)
    strat2 = y_tmp if len(np.unique(y_tmp)) > 1 else None
    X_val, X_te, y_val, y_te = train_test_split(
        X_tmp, y_tmp, test_size=0.50, random_state=seed, stratify=strat2)

    if kind in SCALED:
        sc = StandardScaler().fit(X_tr)
        X_tr, X_val, X_te = sc.transform(X_tr), sc.transform(X_val), sc.transform(X_te)

    pos_rate = float(y_tr.mean())
    model = make_model(kind, seed, pos_rate)

    t0 = time.perf_counter()
    if kind == "isolation_forest":
        model.fit(X_tr)                      # unsupervised: labels not used in fit
    else:
        model.fit(X_tr, y_tr)
    train_time = time.perf_counter() - t0

    t1 = time.perf_counter()
    if kind == "isolation_forest":
        raw = model.predict(X_te)
        y_pred = (raw == -1).astype(int)
        scores = -model.score_samples(X_te)  # higher = more anomalous
    else:
        y_pred = model.predict(X_te)
        if hasattr(model, "predict_proba"):
            scores = model.predict_proba(X_te)[:, 1]
        else:
            scores = y_pred.astype(float)
    infer_time = time.perf_counter() - t1

    prec = precision_score(y_te, y_pred, zero_division=0)
    rec = recall_score(y_te, y_pred, zero_division=0)
    f1 = f1_score(y_te, y_pred, zero_division=0)
    try:
        auc = roc_auc_score(y_te, scores) if len(np.unique(y_te)) > 1 else float("nan")
    except ValueError:
        auc = float("nan")
    tn, fp, fn, tp = confusion_matrix(y_te, y_pred, labels=[0, 1]).ravel()

    # 5-fold CV on the TRAIN partition (supervised models only)
    cv_f1_mean = cv_f1_std = float("nan")
    if kind != "isolation_forest" and len(np.unique(y_tr)) > 1:
        try:
            skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
            cv = cross_val_score(make_model(kind, seed, pos_rate), X_tr, y_tr,
                                 cv=skf, scoring="f1", n_jobs=-1)
            cv_f1_mean, cv_f1_std = float(cv.mean()), float(cv.std())
        except Exception as e:  # noqa: BLE001
            log.warning("CV failed for %s/%s: %s", kind, ds.name, e)

    n_te = len(y_te)
    return {
        "precision": prec, "recall": rec, "f1": f1, "roc_auc": auc,
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        "train_time_s": train_time, "infer_time_s": infer_time,
        "events_per_s": n_te / infer_time if infer_time > 0 else float("nan"),
        "cv_f1_mean": cv_f1_mean, "cv_f1_std": cv_f1_std,
        "n_train": int(len(y_tr)), "n_test": n_te,
    }


def agg(runs: List[Dict], key: str):
    vals = np.array([r[key] for r in runs if not (isinstance(r[key], float) and np.isnan(r[key]))], dtype="float64")
    if len(vals) == 0:
        return {"mean": float("nan"), "std": float("nan")}
    return {"mean": float(vals.mean()), "std": float(vals.std())}


def main():
    loaders = {
        "CICIDS2017": lambda: load_cicids(150_000),
        "BGL": lambda: load_bgl(150_000),
        "TDA": lambda: load_tda(80_000),
    }
    out: Dict = {"seeds": SEEDS, "datasets": {}, "models": MODELS}
    for dsname, loader in loaders.items():
        log.info("=== loading %s ===", dsname)
        ds = loader()
        out["datasets"][dsname] = {"summary": ds.summary(),
                                   "feature_names": ds.feature_names,
                                   "models": {}}
        for kind in MODELS:
            log.info("--- %s / %s ---", dsname, kind)
            runs = []
            for seed in SEEDS:
                try:
                    runs.append(eval_once(kind, ds, seed))
                except Exception as e:  # noqa: BLE001
                    log.error("FAILED %s/%s seed=%s: %s", dsname, kind, seed, e)
            if not runs:
                continue
            summary = {m: agg(runs, m) for m in
                       ["precision", "recall", "f1", "roc_auc",
                        "train_time_s", "infer_time_s", "events_per_s",
                        "cv_f1_mean"]}
            summary["runs"] = runs
            out["datasets"][dsname]["models"][kind] = summary
            s = summary
            log.info("%s/%s  F1=%.4f+/-%.4f  AUC=%.4f  P=%.4f R=%.4f  train=%.2fs",
                     dsname, kind, s["f1"]["mean"], s["f1"]["std"],
                     s["roc_auc"]["mean"], s["precision"]["mean"],
                     s["recall"]["mean"], s["train_time_s"]["mean"])
            # checkpoint after every model so partial results survive
            (RESULTS / "model_results.json").write_text(json.dumps(out, indent=2))
    (RESULTS / "model_results.json").write_text(json.dumps(out, indent=2))
    log.info("DONE -> %s", RESULTS / "model_results.json")


if __name__ == "__main__":
    main()
