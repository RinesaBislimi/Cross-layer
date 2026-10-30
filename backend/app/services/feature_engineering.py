
from __future__ import annotations

import json
import logging
from typing import List

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from ..models.log_events import LogEvent

logger = logging.getLogger(__name__)

_CICIDS_ORIG_COLS: List[str] = [
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

CICIDS_FEATURE_COLS: List[str] = [
    c.replace("/", "_per_").replace(" ", "_").replace(".", "_")
    for c in _CICIDS_ORIG_COLS
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

def _safe_float(val) -> float:
    try:
        f = float(val)
        return f if np.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0

_BGL_TRAIN_LIMIT = 150_000

def build_bgl_features(db: Session, limit: int = _BGL_TRAIN_LIMIT) -> pd.DataFrame:
    events: List[LogEvent] = (
        db.query(LogEvent).filter(LogEvent.source == "BGL").limit(limit).all()
    )

    rows = []
    for e in events:
        text = e.raw or ""
        lower = text.lower()
        rows.append(
            {
                "id": e.id,
                "text_len": len(text),
                "num_spaces": text.count(" "),
                "has_error": int("error" in lower),
                "has_fail": int("fail" in lower),
                "has_fatal": int("fatal" in lower),
                "has_kernel": int("kernel" in lower),
                "has_warning": int("warning" in lower or "warn" in lower),
                "has_info": int('"info"' in lower or " info " in lower),
                "has_mcsm": int("mcsm" in lower),
                "has_ras": int('"ras"' in lower or " ras " in lower),
                "label": e.label if e.label is not None else 0,
            }
        )

    return pd.DataFrame(rows)

_CICIDS_TRAIN_LIMIT = 150_000

def build_cicids_features(db: Session, limit: int = _CICIDS_TRAIN_LIMIT) -> pd.DataFrame:
    events: List[LogEvent] = (
        db.query(LogEvent).filter(LogEvent.source == "CICIDS2017").limit(limit).all()
    )

    rows = []
    for e in events:
        feat_json = e.features or {}
        if isinstance(feat_json, str):
            try:
                feat_json = json.loads(feat_json)
            except Exception:
                feat_json = {}

        row: dict = {"id": e.id, "label": e.label if e.label is not None else 0}
        for orig, safe in zip(_CICIDS_ORIG_COLS, CICIDS_FEATURE_COLS):
            row[safe] = _safe_float(feat_json.get(orig, 0))

        rows.append(row)

    df = pd.DataFrame(rows)

    num_cols = [c for c in CICIDS_FEATURE_COLS if c in df.columns]
    if num_cols and df[num_cols].sum().sum() == 0:
        logger.warning(
            "CICIDS: no numerical features found in DB. "
            "Re-ingest with POST /admin/ingest/cicids for proper ML features. "
            "Falling back to text_len."
        )
        df["text_len"] = [len(e.raw or "") for e in events]
        return df[["id", "text_len", "label"]]

    return df

_TDA_TRAIN_LIMIT = 80_000

def build_tda_features(db: Session, limit: int = _TDA_TRAIN_LIMIT) -> pd.DataFrame:
    events: List[LogEvent] = (
        db.query(LogEvent)
        .filter(LogEvent.source == "TDA")
        .limit(limit)
        .all()
    )
    if not events:
        return pd.DataFrame()

    rows = []
    for e in events:
        feat_json = e.features or {}
        if isinstance(feat_json, str):
            try:
                feat_json = json.loads(feat_json)
            except Exception:
                feat_json = {}

        try:
            user_id = int(feat_json.get("user", 0) or 0)
        except (TypeError, ValueError):
            user_id = 0
        try:
            table_id = int(feat_json.get("table", 0) or 0)
        except (TypeError, ValueError):
            table_id = 0

        ts = e.timestamp
        hour = ts.hour if ts else 0
        dow = ts.weekday() if ts else 0

        rows.append(
            {
                "id": e.id,
                "user_id": user_id,
                "table_id": table_id,
                "hour_of_day": hour,
                "day_of_week": dow,
                "_db_label": e.label if e.label is not None else 0,
            }
        )

    df = pd.DataFrame(rows)

    df["user_access_count"]  = df.groupby("user_id")["id"].transform("count")
    df["table_access_count"] = df.groupby("table_id")["id"].transform("count")

    X = df[TDA_FEATURE_COLS].fillna(0).astype(float)

    if df["_db_label"].sum() > 0:
        df["label"] = df["_db_label"]
        logger.info("TDA: using %d DB anomaly labels", int(df["label"].sum()))
    else:
        # TDA has no verified ground truth: generate synthetic (pseudo) labels
        # with Isolation Forest (contamination=0.05), exactly as described in the
        # manuscript. Supervised metrics obtained against these labels therefore
        # measure agreement with the pseudo-labeller, not independently verified
        # anomaly-detection accuracy (see the paper's threats to validity).
        logger.info("TDA: no labels — running IsolationForest for synthetic labels (%d rows)", len(df))
        iso = IsolationForest(n_estimators=100, contamination=0.05, random_state=42, n_jobs=-1)
        iso_pred = iso.fit_predict(X)
        df["label"] = (iso_pred == -1).astype(int)
        logger.info(
            "TDA: IsolationForest labelled %d / %d rows as anomalies",
            int(df["label"].sum()), len(df),
        )

    return df

_CROSS_TRAIN_LIMIT = 200_000

_CROSS_N_BUCKETS = 300

def build_cross_layer_time_features(
    db: Session,
    window_minutes: int = 10,
    limit: int = _CROSS_TRAIN_LIMIT,
) -> pd.DataFrame:
    layers_loaded: dict = {}

    for layer in ["system", "network", "application", "security"]:
        rows = (
            db.query(LogEvent.label)
            .filter(LogEvent.layer == layer)
            .limit(limit)
            .all()
        )
        if rows:
            layers_loaded[layer] = [int(r[0] == 1) for r in rows]

    if len(layers_loaded) < 2:
        return pd.DataFrame()

    n_buckets = _CROSS_N_BUCKETS

    per_layer_median: dict = {}
    for layer, labels in layers_loaded.items():
        n = len(labels)
        sizes = [int((bucket_idx + 1) * n / n_buckets) - int(bucket_idx * n / n_buckets)
                 for bucket_idx in range(n_buckets)]
        per_layer_median[layer] = float(np.median(sizes)) if sizes else 1.0

    result_rows = []

    for bucket_idx in range(n_buckets):
        row: dict = {}
        layers_with_anomaly = 0
        layers_present = 0

        for layer, labels in layers_loaded.items():
            n = len(labels)
            start = int(bucket_idx * n / n_buckets)
            end   = int((bucket_idx + 1) * n / n_buckets)
            bucket = labels[start:end]
            bucket_size = len(bucket)
            anomaly_count = sum(bucket)

            row[f"count_{layer}"] = bucket_size

            median_size = max(per_layer_median[layer], 1.0)
            row[f"burst_{layer}"] = round(bucket_size / median_size, 3)

            if bucket_size > 0:
                layers_present += 1
                if anomaly_count > 0:
                    layers_with_anomaly += 1

        row["active_layers"] = layers_present

        row["label"] = int(layers_with_anomaly >= 2)

        if layers_present >= 2:
            result_rows.append(row)

    return pd.DataFrame(result_rows)

def build_cross_layer_features(
    db: Session,
    window_minutes: int = 10,
    min_layers: int = 2,
    limit: int = _CROSS_TRAIN_LIMIT,
) -> pd.DataFrame:
    rows_q = (
        db.query(
            LogEvent.entity,
            LogEvent.timestamp,
            LogEvent.layer,
            LogEvent.source,
            LogEvent.label,
        )
        .filter(LogEvent.entity.isnot(None), LogEvent.entity != "")
        .order_by(LogEvent.timestamp.desc())
        .limit(limit)
    )

    rows = rows_q.all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["entity", "timestamp", "layer", "source", "label"])
    df["label"] = (df["label"] == 1).astype(int)
    df = df[df["timestamp"].notna()]

    wm = max(1, window_minutes)
    df["window_start"] = df["timestamp"].apply(
        lambda ts: ts.replace(minute=(ts.minute // wm) * wm, second=0, microsecond=0)
    )

    agg = df.groupby(["entity", "window_start"]).agg(
        label=("label", "max"),
    ).reset_index()

    for layer in ["system", "network", "application", "security"]:
        sub = df[df["layer"] == layer].groupby(["entity", "window_start"]).size()
        agg = agg.merge(
            sub.rename(f"count_{layer}").reset_index(),
            on=["entity", "window_start"],
            how="left",
        )
        agg[f"count_{layer}"] = agg[f"count_{layer}"].fillna(0).astype(int)

    layer_cols = [c for c in agg.columns if c.startswith("count_")]
    agg["n_layers_present"] = (agg[layer_cols] > 0).sum(axis=1)
    agg = agg[agg["n_layers_present"] >= min_layers].drop(columns=["n_layers_present"])
    return agg
