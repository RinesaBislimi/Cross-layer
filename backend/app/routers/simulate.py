
from __future__ import annotations

import logging
import random
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models.log_events import LogEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["simulate"])

_sim_thread: Optional[threading.Thread] = None
_sim_stop_event = threading.Event()

_sim_status: dict = {
    "running":       False,
    "layer":         None,
    "rate":          0,
    "sent":          0,
    "anomalies":     0,
    "started_at":    None,
    "finished_at":   None,
    "error":         None,
}

class SimulateRequest(BaseModel):
    layer:           str   = "all"
    rate:            float = 10.0
    max_events:      int   = 500
    only_anomalies:  bool  = False
    replay_from_start: bool = True

def _fetch_events_fast(conn, layer: str, label: int, limit: int) -> list[dict]:
    from sqlalchemy import text

    LAYER_MAP = {"bgl": "system", "cicids": "network", "tda": "application"}
    db_layer = LAYER_MAP.get(layer, layer) if layer != "all" else None

    if db_layer:
        try:
            sql = text(
                "SELECT id, layer, source, entity, label, raw, features, timestamp "
                "FROM log_events USE INDEX (idx_log_events_layer_label) "
                "WHERE layer = :ly AND label = :lb LIMIT :lim"
            )
            rows = conn.execute(sql, {"ly": db_layer, "lb": label, "lim": limit}).fetchall()
        except Exception:
            sql = text(
                "SELECT id, layer, source, entity, label, raw, features, timestamp "
                "FROM log_events WHERE layer = :ly AND label = :lb LIMIT :lim"
            )
            rows = conn.execute(sql, {"ly": db_layer, "lb": label, "lim": limit}).fetchall()
    else:
        sql = text(
            "SELECT id, layer, source, entity, label, raw, features, timestamp "
            "FROM log_events WHERE label = :lb LIMIT :lim"
        )
        rows = conn.execute(sql, {"lb": label, "lim": limit}).fetchall()

    return [
        {
            "layer":     r[1], "source": r[2], "entity": r[3],
            "label":     r[4], "raw":    r[5],  "features": r[6],
            "timestamp": r[7],
        }
        for r in rows
    ]

def _simulate_worker(
    layer: str,
    rate: float,
    max_events: int,
    only_anomalies: bool,
) -> None:
    from ..ws.realtime import manager
    from ..models.incidents import Incident
    from sqlalchemy import text
    import json

    _sim_status.update({
        "running": True, "sent": 0, "anomalies": 0,
        "started_at": datetime.utcnow().isoformat(), "finished_at": None, "error": None,
        "layer": layer, "rate": rate,
    })

    db: Session = SessionLocal()
    try:
        conn = db.connection()

        if only_anomalies:
            events = _fetch_events_fast(conn, layer, label=1, limit=max_events)
        else:
            n_anomaly = max(1, max_events // 3)
            n_normal  = max_events - n_anomaly
            anomalies = _fetch_events_fast(conn, layer, label=1, limit=n_anomaly)
            normals   = _fetch_events_fast(conn, layer, label=0, limit=n_normal)
            events    = anomalies + normals
            random.shuffle(events)

        if not events:
            _sim_status["error"] = (
                f"No events found for layer='{layer}'. "
                "Run Step 1 (Ingest) then 'Fix Anomaly Labels'."
            )
            return

        n_anom = sum(1 for e in events if (e["label"] or 0) == 1)
        logger.info("Simulator: %d events (%d anomalies) at %.1f/s layer=%s",
                    len(events), n_anom, rate, layer)
        if n_anom == 0:
            logger.warning("Simulator: no label=1 events — run 'Fix Labels' first.")

        sleep_between = 1.0 / max(rate, 0.1)

        FLUSH_EVERY   = 5
        pending_incs: list = []

        for ev in events:
            if _sim_stop_event.is_set():
                logger.info("Simulator: stopped by user")
                break

            ev_label   = int(ev["label"]) if ev["label"] is not None else 0
            confidence = 0.85 if ev_label == 1 else 0.1
            _sim_status["sent"] += 1

            if ev_label == 1:
                _sim_status["anomalies"] += 1

                now       = datetime.utcnow()
                severity  = "high" if confidence > 0.8 else "medium"
                ev_layer  = ev["layer"] or layer
                entity    = ev["entity"] or ev_layer

                manager.broadcast_sync({
                    "type":       "log_anomaly",
                    "layer":      ev_layer,
                    "entity":     entity,
                    "message":    (ev["raw"] or "")[:150],
                    "confidence": round(confidence, 4),
                    "severity":   severity,
                    "timestamp":  now.isoformat(),
                    "simulated":  True,
                })

                incident = Incident(
                    entity     = entity,
                    type       = f"Simulated {ev_layer.title()} Anomaly",
                    severity   = severity,
                    start_time = now,
                    end_time   = now,
                    events     = [],
                    attributes = {
                        "layer":      ev_layer,
                        "source":     ev["source"] or "",
                        "confidence": round(confidence, 4),
                        "simulated":  True,
                        "mode":       "simulation",
                    },
                )
                pending_incs.append(incident)

                if len(pending_incs) >= FLUSH_EVERY:
                    db.add_all(pending_incs)
                    db.commit()
                    manager.broadcast_sync({
                        "type":     "incident_batch",
                        "count":    len(pending_incs),
                        "severity": severity,
                        "layer":    ev_layer,
                        "simulated": True,
                    })
                    pending_incs = []

            time.sleep(sleep_between)

        if pending_incs:
            db.add_all(pending_incs)
            db.commit()
            manager.broadcast_sync({
                "type":     "incident_batch",
                "count":    len(pending_incs),
                "severity": "medium",
                "layer":    layer,
                "simulated": True,
            })

        logger.info("Simulator finished: %d sent, %d anomalies, %d incidents created",
                    _sim_status["sent"], _sim_status["anomalies"], _sim_status["anomalies"])

    except Exception as exc:
        logger.error("Simulator error: %s", exc, exc_info=True)
        _sim_status["error"] = str(exc)
    finally:
        db.close()
        _sim_status["running"]     = False
        _sim_status["finished_at"] = datetime.utcnow().isoformat()

@router.post("/simulate/start")
def start_simulation(payload: SimulateRequest):
    global _sim_thread

    if _sim_status["running"]:
        raise HTTPException(status_code=409, detail="Simulation already running. Stop it first.")

    valid_layers = {"bgl", "cicids", "tda", "all"}
    if payload.layer not in valid_layers:
        raise HTTPException(status_code=422, detail=f"layer must be one of: {', '.join(valid_layers)}")
    if payload.rate <= 0 or payload.rate > 1000:
        raise HTTPException(status_code=422, detail="rate must be between 0.1 and 1000 events/second")
    if payload.max_events < 1 or payload.max_events > 10000:
        raise HTTPException(status_code=422, detail="max_events must be between 1 and 10000")

    _sim_stop_event.clear()

    _sim_thread = threading.Thread(
        target=_simulate_worker,
        args=(payload.layer, payload.rate, payload.max_events, payload.only_anomalies),
        daemon=True,
    )
    _sim_thread.start()

    return {
        "status":     "started",
        "layer":      payload.layer,
        "rate":       payload.rate,
        "max_events": payload.max_events,
        "message":    f"Replaying up to {payload.max_events} events at {payload.rate}/s. Watch the dashboard for live anomalies.",
    }

@router.post("/simulate/stop")
def stop_simulation():
    if not _sim_status["running"]:
        raise HTTPException(status_code=409, detail="No simulation is currently running.")
    _sim_stop_event.set()
    return {"status": "stopping", "sent_so_far": _sim_status["sent"]}

@router.get("/simulate/status")
def simulation_status():
    elapsed = None
    if _sim_status["started_at"]:
        start = datetime.fromisoformat(_sim_status["started_at"])
        end   = datetime.fromisoformat(_sim_status["finished_at"]) if _sim_status["finished_at"] else datetime.utcnow()
        elapsed = round((end - start).total_seconds(), 1)

    return {
        **_sim_status,
        "elapsed_seconds": elapsed,
    }
