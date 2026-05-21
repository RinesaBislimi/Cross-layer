"""Live log ingestion endpoint — accept a single event, score it in real-time."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.log_events import LogEvent
from ..models.incidents import Incident

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


# ── Pydantic input schema ─────────────────────────────────────────────────────

class LogEventIn(BaseModel):
    layer:     str                          # bgl | cicids | tda | network | system | application
    source:    str = ""
    entity:    Optional[str] = None
    message:   str = ""
    timestamp: Optional[str] = None        # ISO-8601 or None → server time
    features:  Optional[Dict[str, Any]] = None
    raw:       Optional[str] = None
    metadata:  Optional[Dict[str, Any]] = None


# ── Model loader (cached) ─────────────────────────────────────────────────────

_model_cache: Dict[str, Any] = {}


def _load_model(name: str):
    if name in _model_cache:
        return _model_cache[name]
    from pathlib import Path
    from ..config import get_settings
    from ..services.ingestion import _backend_root
    import joblib

    cfg   = get_settings()
    paths = {
        "bgl":         cfg.BGL_MODEL_PATH,
        "cicids":      cfg.CICIDS_MODEL_PATH,
        "tda":         cfg.TDA_MODEL_PATH,
        "cross_layer": cfg.CROSS_LAYER_MODEL_PATH,
    }
    if name not in paths:
        return None
    full = Path(paths[name])
    if not full.is_absolute():
        full = (_backend_root() / full).resolve()
    if not full.is_file():
        return None
    try:
        model = joblib.load(full)
        _model_cache[name] = model
        return model
    except Exception as exc:
        logger.warning("Could not load model '%s': %s", name, exc)
        return None


def _score_event(event: LogEventIn, fallback_label: int = 0) -> tuple[int, float]:
    """Return (label, confidence) by running the appropriate model.

    Falls back to fallback_label (default 0) if no model is available.
    Pass the event's original DB label as fallback_label to get meaningful
    simulation results even before training.
    """
    layer_map = {
        "bgl": "bgl", "system": "bgl",
        "cicids": "cicids", "network": "cicids",
        "tda": "tda", "application": "tda",
    }
    model_key = layer_map.get((event.layer or "").lower(), "")
    model = _load_model(model_key) if model_key else None

    if model is None:
        conf = 0.75 if fallback_label == 1 else 0.1
        return fallback_label, conf

    try:
        from ..services.feature_engineering import (
            BGL_FEATURE_COLS, CICIDS_FEATURE_COLS, TDA_FEATURE_COLS,
        )
        import numpy as np

        col_map = {
            "bgl":   BGL_FEATURE_COLS,
            "cicids": CICIDS_FEATURE_COLS,
            "tda":   TDA_FEATURE_COLS,
        }
        feat_cols = col_map.get(model_key, [])
        feats = event.features or {}

        # Build feature vector — missing features default to 0
        vec = np.array([[feats.get(c, 0) for c in feat_cols]], dtype=float)

        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(vec)[0]
            label = int(np.argmax(proba))
            conf  = float(proba[label])
        else:
            pred  = model.predict(vec)[0]
            label = int(pred)
            conf  = 1.0

        return label, conf

    except Exception as exc:
        logger.warning("Scoring failed for %s event: %s", event.layer, exc)
        return 0, 0.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/event")
def ingest_event(payload: LogEventIn, db: Session = Depends(get_db)):
    """Ingest a single log event, score it with the trained ML model, and return
    the scored result.  If the event is an anomaly, it is also written to the DB.
    """
    ts = datetime.utcnow()
    if payload.timestamp:
        try:
            ts = datetime.fromisoformat(payload.timestamp.replace("Z", "+00:00"))
            ts = ts.replace(tzinfo=None)
        except ValueError:
            pass

    label, confidence = _score_event(payload)

    log_event = LogEvent(
        layer      = payload.layer,
        source     = payload.source or payload.layer,
        entity     = payload.entity,
        label      = label,
        confidence = confidence,
        message    = payload.message[:2000] if payload.message else "",
        timestamp  = ts,
        features   = payload.features,
        raw        = (payload.raw or "")[:500],
        metadata_json = json.dumps(payload.metadata) if payload.metadata else None,
    )
    db.add(log_event)
    db.commit()
    db.refresh(log_event)

    result = {
        "id":         log_event.id,
        "layer":      log_event.layer,
        "entity":     log_event.entity,
        "label":      label,
        "confidence": round(confidence, 4),
        "timestamp":  ts.isoformat(),
        "anomaly":    label == 1,
    }

    # If anomaly detected → broadcast via WebSocket
    if label == 1:
        try:
            from ..ws.realtime import manager
            asyncio.get_event_loop().run_until_complete(
                manager.broadcast({
                    "type":    "log_anomaly",
                    "layer":   payload.layer,
                    "entity":  payload.entity,
                    "message": payload.message[:200],
                    "confidence": confidence,
                    "timestamp": ts.isoformat(),
                })
            )
        except Exception:
            pass  # WebSocket broadcast is best-effort

    return result


@router.post("/events/batch")
def ingest_batch(events: List[LogEventIn], db: Session = Depends(get_db)):
    """Ingest and score a batch of log events (up to 500 at once)."""
    if len(events) > 500:
        raise HTTPException(status_code=400, detail="Batch size limit is 500 events.")

    results = []
    anomalies_created = []

    for payload in events:
        ts = datetime.utcnow()
        if payload.timestamp:
            try:
                ts = datetime.fromisoformat(payload.timestamp.replace("Z", "+00:00"))
                ts = ts.replace(tzinfo=None)
            except ValueError:
                pass

        label, confidence = _score_event(payload)

        log_event = LogEvent(
            layer         = payload.layer,
            source        = payload.source or payload.layer,
            entity        = payload.entity,
            label         = label,
            confidence    = confidence,
            message       = payload.message[:2000] if payload.message else "",
            timestamp     = ts,
            features      = payload.features,
            raw           = (payload.raw or "")[:500],
            metadata_json = json.dumps(payload.metadata) if payload.metadata else None,
        )
        db.add(log_event)
        results.append({"label": label, "confidence": round(confidence, 4), "anomaly": label == 1})

        if label == 1:
            anomalies_created.append(log_event)

    db.commit()

    # Evaluate alert rules against batch anomalies
    if anomalies_created:
        try:
            from ..services.alert_service import evaluate_and_fire
            db.refresh(anomalies_created[0])  # ensure IDs are populated
        except Exception:
            pass

    return {
        "processed":    len(results),
        "anomalies":    sum(1 for r in results if r["anomaly"]),
        "results":      results,
    }
