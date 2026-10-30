
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Incident, LogEvent
from ..services.alert_service import evaluate_and_fire
from ..services.correlation import find_common_entities, generate_cross_layer_incidents
from ..services.ml_incidents import generate_ml_incidents
from ..services.ingestion import ingest_bgl_csv, ingest_cicids_csv, ingest_tda_csv, _backend_root
from ..services.training import train_bgl, train_cicids, train_cross_layer, train_tda
from ..services.ml_models import SUPPORTED_MODEL_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

_MODEL_TYPE_ERR = f"model_type must be one of: {', '.join(SUPPORTED_MODEL_TYPES)}"

def _broadcast_incident_batch(incidents: list) -> None:
    if not incidents:
        return
    try:
        import asyncio
        from ..ws.realtime import manager

        sev_counts: dict = {}
        for inc in incidents:
            s = (inc.severity or "unknown").lower()
            sev_counts[s] = sev_counts.get(s, 0) + 1

        sev_order = ["critical", "high", "medium", "low", "unknown"]
        sample = next(
            (i for s in sev_order for i in incidents if (i.severity or "").lower() == s),
            incidents[0],
        )

        msg = {
            "type":        "incident_batch",
            "count":       len(incidents),
            "severity_counts": sev_counts,
            "sample": {
                "id":       sample.id,
                "entity":   sample.entity,
                "severity": sample.severity,
                "type":     sample.type,
            },
        }

        loop = asyncio.new_event_loop()
        loop.run_until_complete(manager.broadcast(msg))
        loop.close()
    except Exception as exc:
        logger.debug("WS broadcast skipped: %s", exc)

@router.post("/admin/ingest/bgl")
def api_ingest_bgl(db: Session = Depends(get_db)) -> dict:
    try:
        count = ingest_bgl_csv(db)
        logger.info("Ingested %s BGL logs", count)
        return {"inserted": count}
    except Exception as e:
        logger.error("Error ingesting BGL: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/admin/ingest/cicids")
def api_ingest_cicids(db: Session = Depends(get_db)) -> dict:
    try:
        count = ingest_cicids_csv(db)
        logger.info("Ingested %s CICIDS logs", count)
        return {"inserted": count}
    except Exception as e:
        logger.error("Error ingesting CICIDS: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/admin/ingest/tda")
def api_ingest_tda(db: Session = Depends(get_db)) -> dict:
    try:
        count = ingest_tda_csv(db)
        logger.info("Ingested %s TDA logs", count)
        return {"inserted": count}
    except Exception as e:
        logger.error("Error ingesting TDA: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/admin/train/bgl")
def api_train_bgl(
    db: Session = Depends(get_db),
    model_type: str = "rf",
) -> dict:
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise HTTPException(status_code=400, detail=_MODEL_TYPE_ERR)
    try:
        result = train_bgl(db, model_type=model_type)
        logger.info("BGL training completed: %s", result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        logger.error("Error training BGL: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/admin/train/cicids")
def api_train_cicids(
    db: Session = Depends(get_db),
    model_type: str = "rf",
) -> dict:
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise HTTPException(status_code=400, detail=_MODEL_TYPE_ERR)
    try:
        result = train_cicids(db, model_type=model_type)
        logger.info("CICIDS training completed: %s", result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        logger.error("Error training CICIDS: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/admin/train/tda")
def api_train_tda(
    db: Session = Depends(get_db),
    model_type: str = "rf",
) -> dict:
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise HTTPException(status_code=400, detail=_MODEL_TYPE_ERR)
    try:
        result = train_tda(db, model_type=model_type)
        logger.info("TDA training completed: %s", result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        logger.error("Error training TDA: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/admin/train/cross-layer")
def api_train_cross_layer(
    db: Session = Depends(get_db),
    model_type: str = "rf",
    window_minutes: int = 10,
    min_layers: int = 2,
) -> dict:
    if model_type not in SUPPORTED_MODEL_TYPES:
        raise HTTPException(status_code=400, detail=_MODEL_TYPE_ERR)
    try:
        result = train_cross_layer(
            db,
            window_minutes=window_minutes,
            min_layers=min_layers,
            model_type=model_type,
        )
        logger.info("Cross-layer training completed: %s", result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as e:
        logger.error("Error training cross-layer: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.get("/admin/common-entities")
def api_common_entities(
    min_layers: int = 2,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> List[dict]:
    try:
        return find_common_entities(db, min_layers=min_layers, limit=limit)
    except Exception as e:
        logger.error("Error finding common entities: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/admin/incidents/generate")
def api_generate_incidents(
    window_minutes: int = 10,
    min_layers: int = 2,
    lookback_hours: int = 24,
    require_anomaly: bool = False,
    max_entities: int = 5000,
    sliding_window: bool = True,
    correlation_mode: str = "time_cooccurrence",
    max_events_per_incident: int = 2000,
    enforce_layer_order: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    if correlation_mode not in ("entity", "time_cooccurrence"):
        raise HTTPException(
            status_code=400,
            detail="correlation_mode must be 'entity' or 'time_cooccurrence'",
        )
    try:
        total_logs = db.query(func.count(LogEvent.id)).scalar() or 0
        if total_logs == 0:
            raise HTTPException(
                status_code=400,
                detail="No log events found in database. Please ingest data first.",
            )

        logger.info(
            "Generating incidents: mode=%s window=%s min_layers=%s lookback=%s "
            "require_anomaly=%s sliding=%s",
            correlation_mode,
            window_minutes,
            min_layers,
            lookback_hours,
            require_anomaly,
            sliding_window,
        )
        result = generate_cross_layer_incidents(
            db,
            window_minutes=window_minutes,
            min_layers=min_layers,
            lookback_hours=lookback_hours,
            require_anomaly=require_anomaly,
            max_entities=max_entities,
            sliding_window=sliding_window,
            correlation_mode=correlation_mode,
            max_events_per_incident=max_events_per_incident,
            enforce_layer_order=enforce_layer_order,
        )
        logger.info("Generated incidents: %s", result)

        try:
            created_count = result.get("created", 0) if isinstance(result, dict) else 0
            if created_count > 0:
                recent = (
                    db.query(Incident)
                    .order_by(Incident.id.desc())
                    .limit(min(created_count, 500))
                    .all()
                )
                fired = evaluate_and_fire(db, recent)
                if fired:
                    logger.info("Alert rules fired: %d rule(s) triggered", fired)

                try:
                    from ..services.response_service import evaluate_and_respond
                    resp_fired = evaluate_and_respond(db, recent)
                    if resp_fired:
                        logger.info("Response rules fired: %d rule(s)", resp_fired)
                except Exception as _re:
                    logger.warning("Response rule evaluation failed: %s", _re)

                _broadcast_incident_batch(recent)
        except Exception as _ae:
            logger.warning("Alert evaluation failed (non-fatal): %s", _ae)

        return result
    except HTTPException:
        raise
    except ValueError as exc:
        logger.error("Value error generating incidents: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected error generating incidents: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(exc)}") from exc

@router.post("/admin/incidents/generate-ml")
def api_generate_incidents_ml(
    lookback_hours: int = 168,
    probability_threshold: float = 0.5,
    batch_size: int = 4000,
    max_events_per_source: int = 80_000,
    merge_window_minutes: int = 15,
    fallback_to_label: bool = True,
    db: Session = Depends(get_db),
) -> dict:
    total_logs = db.query(func.count(LogEvent.id)).scalar() or 0
    if total_logs == 0:
        raise HTTPException(
            status_code=400,
            detail="No log events found in database. Please ingest data first.",
        )
    try:
        result = generate_ml_incidents(
            db,
            lookback_hours=lookback_hours,
            probability_threshold=probability_threshold,
            batch_size=batch_size,
            max_events_per_source=max_events_per_source,
            merge_window_minutes=merge_window_minutes,
            fallback_to_label=fallback_to_label,
        )
        logger.info("ML incidents: %s", result.get("created"))

        try:
            created_count = result.get("created", 0) if isinstance(result, dict) else 0
            if created_count > 0:
                recent = (
                    db.query(Incident)
                    .order_by(Incident.id.desc())
                    .limit(min(created_count, 500))
                    .all()
                )
                fired = evaluate_and_fire(db, recent)
                if fired:
                    logger.info("Alert rules fired: %d rule(s) triggered", fired)

                try:
                    from ..services.response_service import evaluate_and_respond
                    evaluate_and_respond(db, recent)
                except Exception as _re:
                    logger.warning("Response rule evaluation failed: %s", _re)

                _broadcast_incident_batch(recent)
        except Exception as _ae:
            logger.warning("Alert evaluation failed (non-fatal): %s", _ae)

        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("ML incident generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.get("/admin/debug/paths")
def api_debug_paths() -> dict:
    from ..services.training import _resolve_model_path
    import os

    settings = get_settings()
    br = _backend_root()

    def status(rel: str) -> dict:
        expected = (br / rel).resolve()
        saved_to = Path(_resolve_model_path(rel))
        return {
            "config_value": rel,
            "status_checks_at": str(expected),
            "training_saves_to": str(saved_to),
            "paths_match": str(expected) == str(saved_to),
            "file_exists": saved_to.is_file(),
        }

    return {
        "backend_root": str(br),
        "cwd": os.getcwd(),
        "models": {
            "bgl":         status(settings.BGL_MODEL_PATH),
            "cicids":      status(settings.CICIDS_MODEL_PATH),
            "tda":         status(settings.TDA_MODEL_PATH),
            "cross_layer": status(settings.CROSS_LAYER_MODEL_PATH),
        },
    }

@router.get("/admin/model-status")
def api_model_status() -> List[dict]:
    settings = get_settings()
    backend_root = _backend_root()

    def _resolve(rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (backend_root / p).resolve()

    models = [
        {"name": "BGL", "layer": "system", "path": settings.BGL_MODEL_PATH},
        {"name": "CICIDS2017", "layer": "network", "path": settings.CICIDS_MODEL_PATH},
        {"name": "TDA", "layer": "application", "path": settings.TDA_MODEL_PATH},
        {"name": "Cross-Layer", "layer": "cross", "path": settings.CROSS_LAYER_MODEL_PATH},
    ]
    result = []
    for m in models:
        p = _resolve(m["path"])
        trained = p.is_file()
        result.append({
            "name": m["name"],
            "layer": m["layer"],
            "trained": trained,
            "size_kb": round(p.stat().st_size / 1024, 1) if trained else None,
            "path": str(p),
        })
    return result

@router.post("/admin/analyze/incident/{incident_id}")
def api_analyze_incident(
    incident_id: int,
    db: Session = Depends(get_db),
) -> dict:
    from ..services.llm_service import explain_incident

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    events_q = (
        db.query(LogEvent)
        .filter(LogEvent.timestamp >= incident.start_time, LogEvent.timestamp <= incident.end_time)
    )
    if incident.entity:
        events_q = events_q.filter(LogEvent.entity == incident.entity)
    events = events_q.limit(50).all()

    incident_data = {
        "severity": incident.severity,
        "entity": incident.entity,
        "sources": incident.sources if hasattr(incident, "sources") else [],
        "start_time": str(incident.start_time),
        "end_time": str(incident.end_time),
        "event_count": incident.event_count if hasattr(incident, "event_count") else len(events),
        "anomaly_count": incident.anomaly_count if hasattr(incident, "anomaly_count") else None,
        "description": incident.description if hasattr(incident, "description") else None,
    }
    events_data = [
        {
            "layer": e.layer,
            "source": e.source,
            "timestamp": str(e.timestamp),
            "entity": e.entity,
            "label": e.label,
            "message": e.message,
            "features": e.features,
        }
        for e in events
    ]

    try:
        explanation = explain_incident(incident_data, events_data, db=db)
        return {"incident_id": incident_id, "explanation": explanation}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("LLM incident analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.post("/admin/analyze/log/{log_id}")
def api_analyze_log(
    log_id: int,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
) -> dict:
    from ..services.llm_service import explain_log_event

    log = db.query(LogEvent).filter(LogEvent.id == log_id).first()
    if log is None:
        raise HTTPException(status_code=404, detail=f"Log event {log_id} not found")

    extra_signals: list = body.get("signals") or []

    log_data = {
        "id":         log.id,
        "layer":      log.layer,
        "source":     log.source,
        "timestamp":  str(log.timestamp),
        "entity":     log.entity,
        "label":      log.label,
        "confidence": log.confidence,
        "message":    log.message,
        "features":   log.features,
        "raw":        log.raw or "",
    }

    try:
        explanation = explain_log_event(log_data, db=db, extra_signals=extra_signals)
        return {"log_id": log_id, "explanation": explanation}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("LLM log analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.post("/admin/chat/stream")
def api_chat_stream(
    body: dict = Body(...),
    db: Session = Depends(get_db),
):
    import json as _json
    from fastapi.responses import StreamingResponse
    from ..services.llm_service import stream_chat
    from ..config import get_settings

    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="'question' field is required")
    if len(question) > 4000:
        raise HTTPException(status_code=400, detail="Question too long (max 4000 chars)")

    provider = get_settings().LLM_PROVIDER

    def generate():
        try:
            for token in stream_chat(question, db=db):
                yield f"data: {_json.dumps({'token': token})}\n\n"
        except Exception as exc:
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
        yield f"data: {_json.dumps({'done': True, 'provider': provider})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )

@router.post("/admin/enrich-entities")
def api_enrich_entities(
    limit: int = 10000,
    db: Session = Depends(get_db),
) -> dict:
    import re

    ip_pattern       = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
    hostname_pattern = re.compile(r"\b([a-zA-Z][a-zA-Z0-9\-]{2,30}\.[a-zA-Z]{2,6})\b")
    user_pattern     = re.compile(r"(?:user[=: ]+|uid[=: ]+|username[=: ]+|USER[=: ]+)([a-zA-Z0-9_\-\.@]{3,40})", re.I)

    events = (
        db.query(LogEvent)
        .filter(
            (LogEvent.entity.is_(None)) | (LogEvent.entity == "")
        )
        .limit(limit)
        .all()
    )

    updated   = 0
    ip_found  = 0
    usr_found = 0
    host_found = 0

    for event in events:
        raw = event.raw or event.message or ""
        if not raw:
            continue

        entity = None

        m = user_pattern.search(raw)
        if m:
            entity = m.group(1)
            usr_found += 1

        if not entity:
            for ip_match in ip_pattern.findall(raw):
                parts = ip_match.split(".")
                if len(parts) == 4:
                    first = int(parts[0])
                    if first not in (10, 127) and not (first == 172 and 16 <= int(parts[1]) <= 31) and not (first == 192 and int(parts[1]) == 168):
                        entity = ip_match
                        ip_found += 1
                        break

        if not entity:
            m = hostname_pattern.search(raw)
            if m:
                entity = m.group(1)
                host_found += 1

        if entity:
            event.entity = entity[:200]
            updated += 1

    try:
        db.commit()
    except Exception as exc:
        logger.error("enrich-entities commit failed: %s", exc)
        raise HTTPException(status_code=500, detail="DB commit failed") from exc

    return {
        "total_processed": len(events),
        "updated":         updated,
        "ip_extracted":    ip_found,
        "user_extracted":  usr_found,
        "hostname_extracted": host_found,
    }

@router.post("/admin/fix-labels")
def api_fix_labels(db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import text

    results: dict = {}

    cicids_rows = db.execute(
        text("""
            UPDATE log_events
            SET label = CASE
                WHEN INSTR(raw, 'Normal Traffic') > 0 THEN 0
                ELSE 1
            END
            WHERE layer = 'network'
        """)
    ).rowcount
    results["cicids_updated"] = cicids_rows
    logger.info("fix-labels: CICIDS → %d rows updated", cicids_rows)

    bgl_rows = db.execute(
        text("""
            UPDATE log_events
            SET label = CASE
                WHEN UPPER(raw) LIKE '%FATAL%'         THEN 1
                WHEN UPPER(raw) LIKE '%FAILURE%'       THEN 1
                WHEN UPPER(raw) LIKE '%machine check%' THEN 1
                ELSE 0
            END
            WHERE layer = 'system'
        """)
    ).rowcount
    results["bgl_updated"] = bgl_rows
    results["bgl_note"] = "BGL labels derived from FATAL/FAILURE/machine-check keywords in raw log text"
    logger.info("fix-labels: BGL → %d rows updated", bgl_rows)

    tda_rows = db.execute(
        text("""
            UPDATE log_events
            SET label = CASE WHEN id % 7 = 0 THEN 1 ELSE 0 END
            WHERE layer = 'application'
        """)
    ).rowcount
    results["tda_updated"] = tda_rows
    results["tda_note"] = "TDA labels are synthetic (~14% anomaly rate via id%7) — no ground-truth labels exist in the TDA CSV"
    logger.info("fix-labels: TDA → %d rows updated with synthetic labels", tda_rows)

    db.commit()

    dist = db.execute(
        text("SELECT layer, label, COUNT(*) FROM log_events GROUP BY layer, label ORDER BY layer, label")
    ).fetchall()
    results["distribution"] = [
        {"layer": r[0], "label": r[1], "count": r[2]} for r in dist
    ]

    return {"status": "done", **results}

@router.delete("/admin/incidents/clear-simulated")
def api_clear_simulated_incidents(db: Session = Depends(get_db)) -> dict:
    from sqlalchemy import text

    try:
        result = db.execute(
            text("""
                DELETE FROM incidents
                WHERE type LIKE 'Simulated %'
                   OR JSON_EXTRACT(attributes, '$.simulated') = true
            """)
        )
        deleted = result.rowcount
    except Exception:
        result = db.execute(
            text("""
                DELETE FROM incidents
                WHERE type LIKE 'Simulated %'
                   OR attributes LIKE '%"simulated": true%'
                   OR attributes LIKE '%"simulated":true%'
            """)
        )
        deleted = result.rowcount

    db.commit()
    logger.info("clear-simulated-incidents: deleted %d rows", deleted)
    return {"status": "ok", "deleted": deleted}

@router.post("/admin/compute-stats")
def api_compute_stats(db: Session = Depends(get_db)) -> dict:
    from ..main import _compute_heavy_stats, _save_stats_file
    import main as _main_mod
    import time

    logger.info("compute-stats: starting (may take several minutes)…")
    t0 = time.time()
    try:
        heavy = _compute_heavy_stats(db)
        _save_stats_file(heavy)
        try:
            import app.main as _m
            _m._stats_cache = heavy
        except Exception:
            pass
        elapsed = round(time.time() - t0, 1)
        logger.info("compute-stats: done in %.1f s", elapsed)
        return {
            "status": "ok",
            "elapsed_seconds": elapsed,
            "layers": len(heavy.get("logs_by_layer", [])),
            "sources": len(heavy.get("logs_by_source", [])),
            "total_anomalies": heavy.get("total_anomalies", 0),
        }
    except Exception as exc:
        logger.error("compute-stats failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@router.post("/admin/chat")
def api_chat(
    body: dict = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    from ..services.llm_service import chat

    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="'question' field is required")
    if len(question) > 4000:
        raise HTTPException(status_code=400, detail="Question too long (max 4000 chars)")

    try:
        answer = chat(question, db=db)
        from ..config import get_settings
        return {"question": question, "answer": answer, "provider": get_settings().LLM_PROVIDER}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("LLM chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
