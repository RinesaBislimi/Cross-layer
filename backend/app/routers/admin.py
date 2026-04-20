"""Operational endpoints: ingest datasets, train models, incident generation, AI analysis."""

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
    """Entities that appear in multiple layers (candidates for correlation)."""
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
    db: Session = Depends(get_db),
) -> dict:
    """Generate cross-layer incidents from log_events.

    ``correlation_mode``: ``entity`` (same ``entity`` across layers) or ``time_cooccurrence``
    (multi-layer activity in the same time bucket; ``entity`` on the incident is null).
    """
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
        )
        logger.info("Generated incidents: %s", result)

        # Evaluate alert rules against newly created incidents
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
    """
    Generate incidents using trained layer models (``models/*.pkl``) and batched scoring.

    Much faster than pure rule correlation on huge tables: scans each source with a row limit
    and keyset pagination. If a model file is missing, uses ``LogEvent.label == 1`` when
    ``fallback_to_label`` is true.

    Train first: ``POST /admin/train/bgl``, ``/admin/train/cicids``, ``/admin/train/tda``.
    """
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

        # Evaluate alert rules against newly created incidents
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
    """Show exactly where each model is expected and where training saves files."""
    from ..services.training import _resolve_model_path  # noqa: PLC0415
    import os  # noqa: PLC0415

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
    """Return which trained model files exist and their sizes."""
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


# ── AI / LLM endpoints ────────────────────────────────────────────────────────

@router.post("/admin/analyze/incident/{incident_id}")
def api_analyze_incident(
    incident_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Use Claude to explain a cross-layer incident in natural language.

    Requires ANTHROPIC_API_KEY set in environment / .env file.
    """
    from ..services.llm_service import explain_incident  # lazy import

    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    # Collect associated log events (capped to avoid huge prompts)
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
    """Use the LLM to explain why a specific log event was flagged as anomalous.

    Accepts an optional JSON body: {"signals": ["SYN flood indicator: 72 SYN flags", ...]}
    These pre-detected heuristic signals are forwarded to the LLM prompt so the
    explanation is pinned to the exact indicators already shown in the UI.
    """
    from ..services.llm_service import explain_log_event  # lazy import

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
        # Send full raw text — the LLM prompt already caps it at 800 chars
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
    """Streaming SSE endpoint — yields tokens as they are generated."""
    import json as _json  # noqa: PLC0415
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from ..services.llm_service import stream_chat  # noqa: PLC0415
    from ..config import get_settings  # noqa: PLC0415

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


@router.post("/admin/compute-stats")
def api_compute_stats(db: Session = Depends(get_db)) -> dict:
    """Pre-compute slow GROUP BY stats on log_events and save to disk.

    This endpoint may run for several minutes on large tables (56 M rows).
    Call it once after ingest to populate the layer/source breakdown on the
    dashboard.  Results are stored in ``data/stats_cache.json`` and loaded
    automatically on the next server startup.
    """
    from ..main import _compute_heavy_stats, _save_stats_file  # noqa: PLC0415
    import main as _main_mod  # noqa — update the in-process cache too  # noqa: PLC0415
    import time  # noqa: PLC0415

    logger.info("compute-stats: starting (may take several minutes)…")
    t0 = time.time()
    try:
        heavy = _compute_heavy_stats(db)
        _save_stats_file(heavy)
        # Update the in-process cache so the current server instance picks it up
        try:
            import app.main as _m  # noqa: PLC0415
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
    """AI assistant Q&A about the cross-layer detection system.

    Body: {"question": "..."}.
    Provider is controlled by LLM_PROVIDER in backend/.env:
      local     — embedded, zero keys (default)
      gemini    — free Google Gemini Flash (GEMINI_API_KEY)
      groq      — free Groq cloud (GROQ_API_KEY)
      ollama    — local LLM via Ollama
      anthropic — Anthropic Claude (ANTHROPIC_API_KEY)
    """
    from ..services.llm_service import chat  # lazy import

    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="'question' field is required")
    if len(question) > 4000:
        raise HTTPException(status_code=400, detail="Question too long (max 4000 chars)")

    try:
        answer = chat(question, db=db)
        from ..config import get_settings  # noqa: PLC0415
        return {"question": question, "answer": answer, "provider": get_settings().LLM_PROVIDER}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("LLM chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
