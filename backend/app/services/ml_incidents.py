
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Incident, LogEvent
from .feature_engineering import (
    BGL_FEATURE_COLS,
    CICIDS_FEATURE_COLS,
    TDA_FEATURE_COLS,
    _CICIDS_ORIG_COLS,
)
from .ingestion import _backend_root
from .ml_models import load_model

logger = logging.getLogger(__name__)

def _resolve_model_path(rel: str) -> Optional[Path]:
    if not rel:
        return None
    p = Path(rel)
    if p.is_file():
        return p.resolve()
    q = (_backend_root() / rel).resolve()
    if q.is_file():
        return q
    return None

def _window_floor(ts: datetime, merge_minutes: int) -> datetime:
    m = max(1, int(merge_minutes))
    return ts.replace(minute=(ts.minute // m) * m, second=0, microsecond=0)

def _features_bgl(e: LogEvent) -> Dict[str, Any]:
    text = e.raw or ""
    lower = text.lower()
    return {
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
    }

def _features_cicids(e: LogEvent) -> Dict[str, Any]:
    import json
    feat_json = e.features or {}
    if isinstance(feat_json, str):
        try:
            feat_json = json.loads(feat_json)
        except Exception:
            feat_json = {}
    row: Dict[str, Any] = {}
    for orig, safe in zip(_CICIDS_ORIG_COLS, CICIDS_FEATURE_COLS):
        v = feat_json.get(orig, 0)
        try:
            f = float(v)
            row[safe] = f if np.isfinite(f) else 0.0
        except (TypeError, ValueError):
            row[safe] = 0.0
    if all(row.get(s, 0) == 0 for s in CICIDS_FEATURE_COLS):
        row["text_len"] = len(e.raw or "")
    return row

def _features_tda(e: LogEvent) -> Dict[str, Any]:
    import json
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
    return {
        "user_id": user_id,
        "table_id": table_id,
        "hour_of_day": ts.hour if ts else 0,
        "day_of_week": ts.weekday() if ts else 0,
        "user_access_count": 0,
        "table_access_count": 0,
    }

def _anomaly_proba(model: Any, X: pd.DataFrame, feature_cols: List[str]) -> np.ndarray:
    Xf = X[feature_cols].fillna(0).astype(float)
    if not hasattr(model, "predict_proba"):
        return model.predict(Xf).astype(np.float64)

    probas = model.predict_proba(Xf)
    classes = list(getattr(model, "classes_", []))
    if probas.shape[1] == 1:
        return probas[:, 0]
    if 1 in classes:
        return probas[:, classes.index(1)]
    return probas[:, -1]

def _source_time_window(
    db: Session, source: str, lookback_hours: int
) -> Tuple[datetime, datetime]:
    max_ts = (
        db.query(func.max(LogEvent.timestamp))
        .filter(LogEvent.source == source)
        .scalar()
    )
    if max_ts is None:
        dummy = datetime(1970, 1, 1)
        return dummy, dummy

    end = max_ts
    start = end - timedelta(hours=lookback_hours)
    min_ts = (
        db.query(func.min(LogEvent.timestamp))
        .filter(LogEvent.source == source)
        .scalar()
    )
    if min_ts is not None and start < min_ts:
        start = min_ts
    return start, end

def generate_ml_incidents(
    db: Session,
    *,
    lookback_hours: int = 168,
    probability_threshold: float = 0.5,
    batch_size: int = 4000,
    max_events_per_source: int = 80_000,
    merge_window_minutes: int = 15,
    fallback_to_label: bool = True,
) -> Dict[str, Any]:
    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be > 0")
    if not 0 < probability_threshold <= 1:
        raise ValueError("probability_threshold must be in (0, 1]")
    if batch_size < 100:
        raise ValueError("batch_size must be >= 100")
    if merge_window_minutes < 1:
        raise ValueError("merge_window_minutes must be >= 1")

    settings = get_settings()

    layer_jobs: List[Tuple[str, str, List[str], str, Any]] = [
        ("BGL", "BGL", BGL_FEATURE_COLS, settings.BGL_MODEL_PATH, _features_bgl),
        ("CICIDS2017", "CICIDS2017", CICIDS_FEATURE_COLS, settings.CICIDS_MODEL_PATH, _features_cicids),
        ("TDA", "TDA", TDA_FEATURE_COLS, settings.TDA_MODEL_PATH, _features_tda),
    ]

    buckets: DefaultDict[Tuple[str, datetime], List[Tuple[int, float, str, str, datetime]]] = (
        defaultdict(list)
    )

    per_source: Dict[str, Any] = {}
    overall_start: Optional[datetime] = None
    overall_end: Optional[datetime] = None
    anchor = "per_source"

    for source_name, log_source, feature_cols, model_rel, feat_fn in layer_jobs:
        model_path = _resolve_model_path(model_rel)
        model = None
        if model_path is not None:
            try:
                model = load_model(str(model_path))
            except Exception as ex:
                logger.warning("Could not load model %s: %s", model_path, ex)
                model = None

        mode = "model" if model is not None else ("label_fallback" if fallback_to_label else "skipped")
        per_source[source_name] = {"mode": mode, "path": str(model_path) if model_path else None}

        if mode == "skipped":
            continue

        src_start, src_end = _source_time_window(db, log_source, lookback_hours)
        if src_start == src_end:
            per_source[source_name].update({"scanned": 0, "hits": 0, "mode": "no_data"})
            continue

        if overall_start is None or src_start < overall_start:
            overall_start = src_start
        if overall_end is None or src_end > overall_end:
            overall_end = src_end

        last_id = 0
        scanned = 0
        hits = 0

        while scanned < max_events_per_source:
            batch = (
                db.query(LogEvent)
                .filter(
                    LogEvent.source == log_source,
                    LogEvent.timestamp >= src_start,
                    LogEvent.timestamp <= src_end,
                    LogEvent.id > last_id,
                )
                .order_by(LogEvent.id)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            last_id = batch[-1].id
            scanned += len(batch)

            if mode == "model":
                rows = []
                for e in batch:
                    rows.append(feat_fn(e))
                X = pd.DataFrame(rows)
                scores = _anomaly_proba(model, X, feature_cols)
                for e, sc in zip(batch, scores):
                    if float(sc) >= probability_threshold:
                        hits += 1
                        ek = (e.entity or "").strip() or f"_unscoped:{e.layer}"
                        wf = _window_floor(e.timestamp, merge_window_minutes)
                        buckets[(ek, wf)].append(
                            (e.id, float(sc), log_source, e.layer, e.timestamp)
                        )
            else:
                for e in batch:
                    if e.label == 1:
                        hits += 1
                        ek = (e.entity or "").strip() or f"_unscoped:{e.layer}"
                        wf = _window_floor(e.timestamp, merge_window_minutes)
                        buckets[(ek, wf)].append(
                            (e.id, 1.0, log_source, e.layer, e.timestamp)
                        )

        per_source[source_name]["scanned"] = scanned
        per_source[source_name]["hits"] = hits
        logger.info(
            "ML scoring %s: mode=%s scanned=%s hits=%s window=[%s, %s]",
            source_name, mode, scanned, hits, src_start, src_end,
        )

    created = 0
    for (entity_key, wf), items in buckets.items():
        if not items:
            continue
        items.sort(key=lambda t: t[4])
        event_ids = [t[0] for t in items]
        score_vals = [t[1] for t in items]
        sources = {t[2] for t in items}
        layers = sorted({t[3] for t in items})
        max_score = max(score_vals)
        start_t = items[0][4]
        end_t = items[-1][4]

        if max_score >= 0.9:
            severity = "critical"
        elif max_score >= 0.75:
            severity = "high"
        elif max_score >= 0.55:
            severity = "medium"
        else:
            severity = "low"

        ent = None if entity_key.startswith("_unscoped:") else entity_key[:100]
        source_list = sorted(sources)
        type_s = (
            f"ML:{'+'.join(source_list)}"
            if len(source_list) > 1
            else f"ML:{source_list[0]}"
        )[:100]

        layer_str = " + ".join(l.capitalize() for l in layers)
        ent_label = f'Entity "{ent}"' if ent else layer_str + " layer"
        description = (
            f"ML model flagged {len(event_ids)} anomalous event{'s' if len(event_ids) != 1 else ''} "
            f"from {ent_label} (source{'s' if len(source_list) > 1 else ''}: {', '.join(source_list)}). "
            f"Highest anomaly score: {max_score * 100:.1f}% — classified as {severity} severity."
        )

        incident = Incident(
            entity=ent,
            type=type_s,
            severity=severity,
            start_time=start_t,
            end_time=end_t,
            events=event_ids[:5000],
            attributes={
                "description": description,
                "generated_from": "ml_incidents",
                "merge_window_minutes": merge_window_minutes,
                "probability_threshold": probability_threshold,
                "max_score": max_score,
                "num_events": len(event_ids),
                "events_truncated": len(event_ids) > 5000,
                "layers": layers,
                "sources": source_list,
                "time_bucket": wf.isoformat(),
                "time_anchor": anchor,
            },
        )
        db.add(incident)
        created += 1
        if created % 200 == 0:
            db.commit()
            logger.info("ML incidents committed: %s", created)

    db.commit()

    return {
        "created": created,
        "buckets": len(buckets),
        "correlation_mode": "ml",
        "time_anchor": anchor,
        "window_start": overall_start,
        "window_end": overall_end,
        "per_source": per_source,
        "parameters": {
            "lookback_hours": lookback_hours,
            "probability_threshold": probability_threshold,
            "batch_size": batch_size,
            "max_events_per_source": max_events_per_source,
            "merge_window_minutes": merge_window_minutes,
            "fallback_to_label": fallback_to_label,
        },
    }
