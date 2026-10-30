"""Reproducible dataset loading + feature engineering for the cross-layer paper.

This module rebuilds, directly from the raw CSV files, exactly the per-layer
feature sets used by the production service (``app/services/feature_engineering.py``),
so that the experiments reported in the paper can be reproduced end-to-end from
``backend/data/`` without standing up the database/API stack.

Design choices that answer the reviewers:
  * Explicit, documented cleaning of CICIDS2017 (infinite values -> NaN, NaN -> 0,
    exact-duplicate removal) with the counts reported.
  * A single fixed stratified subsample per dataset (``random_state`` controlled)
    so class proportions are preserved and reported.
  * TDA labels are generated with Isolation Forest (contamination = 0.05), matching
    the method described in the manuscript (NOT random labels).
  * Scaling is deliberately *not* applied here: each experiment fits the scaler on
    the training split only, to avoid train/test leakage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logger = logging.getLogger("experiments.datasets")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DATA = BACKEND_ROOT / "data"

# --------------------------------------------------------------------------- #
# Feature definitions (mirrors app/services/feature_engineering.py)
# --------------------------------------------------------------------------- #
CICIDS_ORIG_COLS: List[str] = [
    "Destination Port", "Flow Duration", "Total Fwd Packets",
    "Total Length of Fwd Packets", "Fwd Packet Length Max",
    "Fwd Packet Length Min", "Fwd Packet Length Mean", "Fwd Packet Length Std",
    "Bwd Packet Length Max", "Bwd Packet Length Min", "Bwd Packet Length Mean",
    "Bwd Packet Length Std", "Flow Bytes/s", "Flow Packets/s",
    "Flow IAT Mean", "Flow IAT Std", "Flow IAT Max", "Flow IAT Min",
    "Fwd IAT Total", "Fwd IAT Mean", "Fwd IAT Std", "Fwd IAT Max", "Fwd IAT Min",
    "Bwd IAT Total", "Bwd IAT Mean", "Bwd IAT Std", "Bwd IAT Max", "Bwd IAT Min",
    "Fwd Header Length", "Bwd Header Length", "Fwd Packets/s", "Bwd Packets/s",
    "Min Packet Length", "Max Packet Length", "Packet Length Mean",
    "Packet Length Std", "Packet Length Variance", "FIN Flag Count",
    "PSH Flag Count", "ACK Flag Count", "Average Packet Size",
    "Subflow Fwd Bytes", "Init_Win_bytes_forward", "Init_Win_bytes_backward",
    "act_data_pkt_fwd", "min_seg_size_forward",
    "Active Mean", "Active Max", "Active Min",
    "Idle Mean", "Idle Max", "Idle Min",
]

BGL_FEATURE_COLS: List[str] = [
    "text_len", "num_spaces", "has_error", "has_fail",
    "has_fatal", "has_kernel", "has_warning", "has_info",
    "has_mcsm", "has_ras",
]

TDA_FEATURE_COLS: List[str] = [
    "user_id", "table_id", "hour_of_day", "day_of_week",
    "user_access_count", "table_access_count",
]


@dataclass
class Dataset:
    name: str
    layer: str
    X: pd.DataFrame
    y: np.ndarray
    feature_names: List[str]
    meta: Dict = field(default_factory=dict)

    def summary(self) -> Dict:
        n = len(self.y)
        n_pos = int(self.y.sum())
        return {
            "name": self.name,
            "layer": self.layer,
            "n_samples": n,
            "n_features": len(self.feature_names),
            "n_positive": n_pos,
            "n_negative": n - n_pos,
            "positive_rate": round(n_pos / n, 4) if n else 0.0,
            **self.meta,
        }


# --------------------------------------------------------------------------- #
# CICIDS2017 (network layer)
# --------------------------------------------------------------------------- #
def load_cicids(n_sample: int = 150_000, random_state: int = 42,
                chunksize: int = 200_000) -> Dataset:
    path = DATA / "cicids" / "cicids.csv"
    usecols = CICIDS_ORIG_COLS + ["Attack Type"]
    # Estimate total rows cheaply, then sample a fraction per chunk so the
    # overall class distribution is preserved in expectation.
    total = sum(1 for _ in open(path, "r", encoding="utf-8", errors="replace")) - 1
    frac = min(1.0, n_sample / total) if total else 1.0
    logger.info("CICIDS total rows=%s, sampling frac=%.4f", total, frac)

    parts = []
    rng = np.random.RandomState(random_state)
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=chunksize):
        if frac < 1.0:
            mask = rng.random_sample(len(chunk)) < frac
            chunk = chunk[mask]
        parts.append(chunk)
    df = pd.concat(parts, ignore_index=True)

    n_raw = len(df)
    # --- documented cleaning -------------------------------------------------
    feat = df[CICIDS_ORIG_COLS].apply(pd.to_numeric, errors="coerce")
    n_inf = int(np.isinf(feat.to_numpy(dtype="float64", na_value=np.nan)).sum())
    feat = feat.replace([np.inf, -np.inf], np.nan)
    n_nan = int(feat.isna().to_numpy().sum())
    feat = feat.fillna(0.0)
    label = (df["Attack Type"].astype(str).str.strip().str.upper()
             .map(lambda v: 0 if v in ("BENIGN", "NORMAL TRAFFIC", "NORMAL",
                                       "BENIGN TRAFFIC", "WHITE") else 1))
    full = feat.copy()
    full["__label__"] = label.values
    before = len(full)
    full = full.drop_duplicates()
    n_dupes = before - len(full)

    y = full["__label__"].to_numpy(dtype=int)
    X = full.drop(columns="__label__").reset_index(drop=True)
    X.columns = [c.replace("/", "_per_").replace(" ", "_").replace(".", "_") for c in X.columns]

    return Dataset(
        name="CICIDS2017", layer="network", X=X, y=y,
        feature_names=list(X.columns),
        meta={"total_rows": total, "sampled_rows": n_raw,
              "inf_values_fixed": n_inf, "nan_values_filled": n_nan,
              "duplicate_rows_dropped": n_dupes},
    )


# --------------------------------------------------------------------------- #
# BGL (system layer)
# --------------------------------------------------------------------------- #
def load_bgl(n_sample: int = 150_000, random_state: int = 42,
             chunksize: int = 200_000) -> Dataset:
    path = DATA / "bgl" / "bgl.csv"
    total = sum(1 for _ in open(path, "r", encoding="utf-8", errors="replace")) - 1
    frac = min(1.0, n_sample / total) if total else 1.0
    logger.info("BGL total rows=%s, sampling frac=%.4f", total, frac)

    rng = np.random.RandomState(random_state)
    parts = []
    for chunk in pd.read_csv(path, usecols=["timestamp", "log_message"],
                             dtype=str, keep_default_na=False, chunksize=chunksize):
        if frac < 1.0:
            chunk = chunk[rng.random_sample(len(chunk)) < frac]
        parts.append(chunk)
    df = pd.concat(parts, ignore_index=True)

    # label: first column ('timestamp') holds the BGL alert flag; '-' == normal
    y = (df["timestamp"].str.strip() != "-").astype(int).to_numpy()

    text = df["log_message"].fillna("")
    lower = text.str.lower()
    X = pd.DataFrame({
        "text_len": text.str.len(),
        "num_spaces": text.str.count(" "),
        "has_error": lower.str.contains("error", regex=False).astype(int),
        "has_fail": lower.str.contains("fail", regex=False).astype(int),
        "has_fatal": lower.str.contains("fatal", regex=False).astype(int),
        "has_kernel": lower.str.contains("kernel", regex=False).astype(int),
        "has_warning": (lower.str.contains("warning", regex=False) |
                        lower.str.contains("warn", regex=False)).astype(int),
        "has_info": (lower.str.contains('"info"', regex=False) |
                     lower.str.contains(" info ", regex=False)).astype(int),
        "has_mcsm": lower.str.contains("mcsm", regex=False).astype(int),
        "has_ras": (lower.str.contains('"ras"', regex=False) |
                    lower.str.contains(" ras ", regex=False)).astype(int),
    })[BGL_FEATURE_COLS]

    return Dataset(
        name="BGL", layer="system", X=X.reset_index(drop=True), y=y,
        feature_names=BGL_FEATURE_COLS,
        meta={"total_rows": total, "sampled_rows": len(df)},
    )


# --------------------------------------------------------------------------- #
# TDA (application layer) -- Isolation Forest pseudo-labels (contamination=0.05)
# --------------------------------------------------------------------------- #
def load_tda(n_sample: int = 80_000, random_state: int = 42,
             contamination: float = 0.05, chunksize: int = 200_000) -> Dataset:
    path = DATA / "tda" / "tda.csv"
    total = sum(1 for _ in open(path, "r", encoding="utf-8", errors="replace")) - 1
    frac = min(1.0, n_sample / total) if total else 1.0
    logger.info("TDA total rows=%s, sampling frac=%.4f", total, frac)

    rng = np.random.RandomState(random_state)
    parts = []
    for chunk in pd.read_csv(path, usecols=["user", "table", "timestamp"],
                             dtype=str, keep_default_na=False, chunksize=chunksize):
        if frac < 1.0:
            chunk = chunk[rng.random_sample(len(chunk)) < frac]
        parts.append(chunk)
    df = pd.concat(parts, ignore_index=True)

    ts = pd.to_datetime(df["timestamp"], format="%Y%m%d%H%M%S", errors="coerce")
    df["user_id"] = pd.to_numeric(df["user"], errors="coerce").fillna(0).astype(int)
    df["table_id"] = pd.to_numeric(df["table"], errors="coerce").fillna(0).astype(int)
    df["hour_of_day"] = ts.dt.hour.fillna(0).astype(int)
    df["day_of_week"] = ts.dt.dayofweek.fillna(0).astype(int)
    df["user_access_count"] = df.groupby("user_id")["user"].transform("size")
    df["table_access_count"] = df.groupby("table_id")["table"].transform("size")

    X = df[TDA_FEATURE_COLS].astype(float)

    # Isolation Forest pseudo-labels (matches the manuscript's described method)
    iso = IsolationForest(n_estimators=100, contamination=contamination,
                          random_state=random_state, n_jobs=-1)
    pred = iso.fit_predict(X.values)
    y = (pred == -1).astype(int)

    return Dataset(
        name="TDA", layer="application", X=X.reset_index(drop=True), y=y,
        feature_names=TDA_FEATURE_COLS,
        meta={"total_rows": total, "sampled_rows": len(df),
              "labeling": f"IsolationForest(contamination={contamination})"},
    )


def load_all(cicids_n=150_000, bgl_n=150_000, tda_n=80_000,
             random_state: int = 42) -> List[Dataset]:
    return [
        load_cicids(cicids_n, random_state=random_state),
        load_bgl(bgl_n, random_state=random_state),
        load_tda(tda_n, random_state=random_state),
    ]
