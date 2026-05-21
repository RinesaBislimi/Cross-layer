"""Cross-Layer API: public routes here; ingest/train/incident-generation in ``routers.admin``."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import json
import logging
import threading

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .db import Base, engine, get_db, SessionLocal
from .models import Incident, LogEvent  # noqa: F401 — register models on Base.metadata
from .models.alert_rule import AlertRule   # noqa: F401 — register AlertRule table
from .models.user import User              # noqa: F401 — register User table
from .models.feedback import IncidentFeedback  # noqa: F401
from .models.response_rule import ResponseRule  # noqa: F401
from .routers import admin, analytics, alert_rules
from .routers import auth, ingest, feedback, response_rules, simulate
from .schemas import IncidentSchema, LogEventSchema
from .services.correlation import correlate_entity_in_window
from .ws import realtime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Persistent file-based stats cache ────────────────────────────────────────
# Heavy GROUP BY queries on 56 M rows saturate MySQL and block all other
# connections.  We therefore NEVER run them at request time.  Instead:
#
#   • On startup: load a pre-computed JSON file (if it exists) — instant.
#   • POST /admin/compute-stats: runs the slow queries once, stores result.
#   • GET  /summary: returns the file cache + a few always-fast queries.
#
# Run /admin/compute-stats once after first ingest to populate layer data.

_STATS_DIR  = Path(__file__).resolve().parent.parent / "data"
_STATS_FILE = _STATS_DIR / "stats_cache.json"

_stats_cache: Optional[dict] = None   # loaded from file on startup
_stats_computing = False               # guard against concurrent /admin/compute-stats


def _load_stats_file() -> Optional[dict]:
    try:
        if _STATS_FILE.exists():
            return json.loads(_STATS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read stats cache file: %s", exc)
    return None


def _save_stats_file(data: dict) -> None:
    try:
        _STATS_DIR.mkdir(parents=True, exist_ok=True)
        _STATS_FILE.write_text(json.dumps(data, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write stats cache file: %s", exc)


def _compute_heavy_stats(db: Session) -> dict:
    """Run the slow GROUP BY queries on log_events.  May take minutes."""
    result: dict = {"logs_by_source": [], "logs_by_layer": [], "total_anomalies": 0}
    try:
        rows = db.execute(text(
            "SELECT source, COUNT(*) AS n, "
            "SUM(CASE WHEN label = 1 THEN 1 ELSE 0 END) AS a "
            "FROM log_events WHERE source IS NOT NULL GROUP BY source ORDER BY n DESC LIMIT 10"
        )).fetchall()
        result["logs_by_source"] = [
            {"name": str(r[0]), "count": int(r[1] or 0), "anomalies": int(r[2] or 0)}
            for r in rows
        ]
        result["total_anomalies"] = sum(s["anomalies"] for s in result["logs_by_source"])
    except Exception as e:
        logger.error("compute_stats logs_by_source failed: %s", e)

    try:
        rows = db.execute(text(
            "SELECT layer, COUNT(*) AS n, "
            "SUM(CASE WHEN label = 1 THEN 1 ELSE 0 END) AS a "
            "FROM log_events WHERE layer IS NOT NULL GROUP BY layer ORDER BY n DESC"
        )).fetchall()
        result["logs_by_layer"] = [
            {"name": str(r[0]), "count": int(r[1] or 0), "anomalies": int(r[2] or 0)}
            for r in rows
        ]
    except Exception as e:
        logger.error("compute_stats logs_by_layer failed: %s", e)

    return result


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(title="Cross-Layer Log Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    global _stats_cache
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified")
        tables = inspect(engine).get_table_names()
        logger.info("Available tables: %s", tables)
        if "incidents" not in tables:
            logger.warning("Incidents table not found — check model registration.")
        if "log_events" not in tables:
            logger.warning("log_events table not found — check model registration.")
    except Exception as e:
        logger.error("Error during startup: %s", e)
        raise

    # Load pre-computed heavy stats from file (instant if file exists)
    cached = _load_stats_file()
    if cached:
        _stats_cache = cached
        logger.info(
            "Stats cache loaded from file: %d layers, %d sources",
            len(cached.get("logs_by_layer", [])),
            len(cached.get("logs_by_source", [])),
        )
    else:
        logger.info(
            "No stats cache file found — layer breakdown unavailable until "
            "POST /admin/compute-stats is called."
        )


# ── Health / diagnostics ──────────────────────────────────────────────────────

@app.get("/debug/db", tags=["health"])
def debug_db(db: Session = Depends(get_db)) -> dict:
    """Diagnostic: fast DB checks only (no full-table scans)."""
    from .config import get_settings  # noqa
    s = get_settings()
    result: dict = {"database_url": s.DATABASE_URL[:40] + "…", "queries": {}}
    for label, sql in [
        ("log_events_approx", "SELECT TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_NAME='log_events' AND TABLE_SCHEMA=DATABASE()"),
        ("incidents_count",   "SELECT COUNT(*) FROM incidents"),
        ("anomalies_approx",  "SELECT COUNT(*) FROM log_events WHERE label = 1 LIMIT 1"),
    ]:
        try:
            rows = db.execute(text(sql)).fetchall()
            result["queries"][label] = [list(r) for r in rows]
        except Exception as e:
            result["queries"][label] = f"ERROR: {e}"
    return result


@app.get("/health", tags=["health"])
def health_check(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    return {"status": "ok", "database": db_status}


# ── Logs & incidents ──────────────────────────────────────────────────────────

@app.get("/logs", response_model=List[LogEventSchema], tags=["logs"])
def list_logs(
    layer: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[LogEventSchema]:
    query = db.query(LogEvent)
    if layer:
        query = query.filter(LogEvent.layer == layer)
    if source:
        query = query.filter(LogEvent.source == source)
    return query.order_by(LogEvent.timestamp.desc()).limit(limit).all()


@app.get("/incidents", response_model=List[IncidentSchema], tags=["incidents"])
def list_incidents(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[IncidentSchema]:
    return (
        db.query(Incident)
        .order_by(Incident.start_time.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@app.get("/incidents/{incident_id}/events", response_model=List[LogEventSchema], tags=["incidents"])
def get_incident_events(
    incident_id: int,
    db: Session = Depends(get_db),
) -> List[LogEventSchema]:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    event_ids = incident.events or []
    if not isinstance(event_ids, list) or not event_ids:
        if event_ids and not isinstance(event_ids, list):
            logger.warning("Events field is not a list for incident %s", incident_id)
        return []

    event_ids_int: List[int] = []
    for eid in event_ids:
        if isinstance(eid, str):
            try:
                event_ids_int.append(int(eid))
            except ValueError:
                logger.warning("Invalid event ID format: %s", eid)
        else:
            event_ids_int.append(eid)

    return (
        db.query(LogEvent)
        .filter(LogEvent.id.in_(event_ids_int))
        .order_by(LogEvent.timestamp)
        .all()
    )


@app.post("/correlate/{entity}", response_model=IncidentSchema, tags=["incidents"])
def correlate_entity(
    entity: str,
    minutes: int = 10,
    db: Session = Depends(get_db),
) -> IncidentSchema:
    end = datetime.utcnow()
    start = end - timedelta(minutes=minutes)
    incident = correlate_entity_in_window(db, entity=entity, start=start, end=end)
    if not incident:
        raise HTTPException(status_code=404, detail="No cross-layer incident found")
    return incident


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/summary", tags=["stats"])
def get_summary(db: Session = Depends(get_db)) -> dict:
    """Dashboard stats.

    Fast queries (information_schema + incidents table) run every time.
    Heavy layer/source breakdown comes from a pre-computed file cache.
    Run ``POST /admin/compute-stats`` once after first ingest to populate
    the layer cards.
    """
    result: dict = {
        "total_logs": 0,
        "total_anomalies": 0,
        "total_incidents": 0,
        "logs_by_source": [],
        "logs_by_layer": [],
        "incidents_by_severity": [],
        "incidents_by_mode": [],
    }

    # Overlay pre-computed heavy stats if available
    if _stats_cache:
        result["logs_by_layer"]   = _stats_cache.get("logs_by_layer",  [])
        result["logs_by_source"]  = _stats_cache.get("logs_by_source", [])
        result["total_anomalies"] = _stats_cache.get("total_anomalies", 0)

    # Approximate total — information_schema is instant even on 56 M rows
    try:
        approx = db.execute(text(
            "SELECT TABLE_ROWS FROM information_schema.TABLES "
            "WHERE TABLE_NAME='log_events' AND TABLE_SCHEMA=DATABASE()"
        )).scalar()
        result["total_logs"] = int(approx or 0)
    except Exception as e:
        logger.error("summary total_logs failed: %s", e)

    # Incidents table has ~206 rows — these three queries are fast
    try:
        result["total_incidents"] = int(
            db.execute(text("SELECT COUNT(*) FROM incidents")).scalar() or 0
        )
    except Exception as e:
        logger.error("summary total_incidents failed: %s", e)

    try:
        rows = db.execute(text(
            "SELECT COALESCE(severity, 'unknown'), COUNT(*) AS n "
            "FROM incidents GROUP BY severity ORDER BY n DESC"
        )).fetchall()
        result["incidents_by_severity"] = [
            {"name": str(r[0]), "count": int(r[1] or 0)} for r in rows
        ]
    except Exception as e:
        logger.error("summary incidents_by_severity failed: %s", e)

    try:
        rows = db.execute(text(
            "SELECT COALESCE(JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.generated_from')), 'unknown') AS mode, "
            "COUNT(*) AS n FROM incidents GROUP BY mode ORDER BY n DESC"
        )).fetchall()
        result["incidents_by_mode"] = [
            {"name": str(r[0]), "count": int(r[1] or 0)} for r in rows
        ]
    except Exception:
        if result["total_incidents"]:
            result["incidents_by_mode"] = [{"name": "generated", "count": result["total_incidents"]}]

    logger.info(
        "summary: logs≈%d anomalies=%d incidents=%d layers=%d",
        result["total_logs"], result["total_anomalies"],
        result["total_incidents"], len(result["logs_by_layer"]),
    )
    return result


@app.get("/stats", tags=["stats"])
def get_stats(db: Session = Depends(get_db)) -> dict:
    """Alias for /summary — kept for backwards compatibility."""
    return get_summary(db)


app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(admin.router)
app.include_router(analytics.router)
app.include_router(alert_rules.router)
app.include_router(feedback.router)
app.include_router(response_rules.router)
app.include_router(simulate.router)
app.include_router(realtime.router)
