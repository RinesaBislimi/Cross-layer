"""Analytics endpoints: heatmap, entity risk, attack chains, report summary.

Schema notes (incidents table):
  - `type`       — incident type string  (NOT `incident_type`)
  - `severity`   — 'critical' | 'high' | 'medium' | 'low'
  - `attributes` — JSON blob with 'description', 'layers' (list), 'severity_score',
                   'anomaly_count', 'duration_minutes', 'generated_from', …
  - NO `risk_score` column — derived from severity in Python
  - NO top-level `layer` column — extracted from attributes->>'$.layers'
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Map severity string → 0-1 risk score
_SEV_SCORE = {"critical": 0.90, "high": 0.75, "medium": 0.50, "low": 0.25}


def _sev_score(sev):
    # type: (Optional[str]) -> float
    return _SEV_SCORE.get((sev or "").lower(), 0.25)


def _parse_layers(raw):
    # type: (Optional[str]) -> list
    if not raw:
        return []
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except Exception:
        return []


# ── Heatmap ───────────────────────────────────────────────────────────────────

@router.get("/heatmap")
def get_heatmap(db: Session = Depends(get_db)):
    """Anomaly counts by hour-of-day x day-of-week.
    Samples last 100 K rows via PK descending scan — safe on 56 M rows."""
    try:
        rows = db.execute(text("""
            SELECT
                HOUR(timestamp)      AS hr,
                DAYOFWEEK(timestamp) AS dow,
                COUNT(*)             AS total,
                SUM(CASE WHEN label = 1 THEN 1 ELSE 0 END) AS anomalies
            FROM (
                SELECT timestamp, label
                FROM log_events
                ORDER BY id DESC
                LIMIT 100000
            ) sub
            GROUP BY hr, dow
            ORDER BY dow, hr
        """)).fetchall()

        return {
            "data": [
                {
                    "hour":      int(r[0]),
                    "dow":       int(r[1]),
                    "total":     int(r[2] or 0),
                    "anomalies": int(r[3] or 0),
                }
                for r in rows
            ],
            "sample_size": 100000,
        }
    except Exception as exc:
        logger.error("heatmap failed: %s", exc)
        return {"data": [], "error": str(exc)}


# ── Entity risk profiler ──────────────────────────────────────────────────────

@router.get("/entities")
def get_entities(limit: int = 60, db: Session = Depends(get_db)):
    """Top entities ranked by risk (severity-derived). Incidents table only — fast."""
    try:
        rows = db.execute(text("""
            SELECT
                entity,
                COUNT(*)                                                                AS incident_count,
                MAX(start_time)                                                         AS last_seen,
                GROUP_CONCAT(DISTINCT severity  ORDER BY severity  SEPARATOR ',')      AS severities,
                GROUP_CONCAT(
                    COALESCE(
                        JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.layers[0]')),
                        'unknown'
                    )
                    SEPARATOR ','
                )                                                                       AS layer_samples
            FROM incidents
            WHERE entity IS NOT NULL AND entity != ''
            GROUP BY entity
            ORDER BY incident_count DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()

        entities = []
        for r in rows:
            sevs = [s for s in (r[3] or "").split(",") if s]
            max_sev = max(sevs, key=_sev_score, default="low")
            avg_risk = round(
                sum(_sev_score(s) for s in sevs) / max(len(sevs), 1), 3
            )
            layers = list(dict.fromkeys(
                lyr for lyr in (r[4] or "").split(",") if lyr and lyr != "unknown"
            ))
            entities.append({
                "entity":         str(r[0]),
                "incident_count": int(r[1] or 0),
                "max_risk":       _sev_score(max_sev),
                "avg_risk":       avg_risk,
                "last_seen":      str(r[2]) if r[2] else None,
                "severities":     list(dict.fromkeys(sevs)),
                "layers":         layers,
            })

        entities.sort(key=lambda e: -e["max_risk"])
        return {"entities": entities}
    except Exception as exc:
        logger.error("entities failed: %s", exc)
        return {"entities": [], "error": str(exc)}


@router.get("/entity/{entity_name:path}")
def get_entity_detail(entity_name: str, db: Session = Depends(get_db)):
    """All incidents for a specific entity."""
    try:
        rows = db.execute(text("""
            SELECT
                id,
                type,
                severity,
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.layers[0]'))   AS layer,
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.description'))  AS description,
                start_time
            FROM incidents
            WHERE entity = :ent
            ORDER BY start_time DESC
            LIMIT 200
        """), {"ent": entity_name}).fetchall()

        return {
            "entity": entity_name,
            "incidents": [
                {
                    "id":            int(r[0]),
                    "incident_type": str(r[1]) if r[1] else "",
                    "severity":      str(r[2]) if r[2] else "unknown",
                    "layer":         str(r[3]) if r[3] else "unknown",
                    "risk_score":    _sev_score(r[2]),
                    "start_time":    str(r[5]) if r[5] else None,
                    "description":   str(r[4]) if r[4] else "",
                }
                for r in rows
            ],
        }
    except Exception as exc:
        logger.error("entity detail failed: %s", exc)
        return {"entity": entity_name, "incidents": [], "error": str(exc)}


# ── Attack chains ─────────────────────────────────────────────────────────────

@router.get("/attack-chains")
def get_attack_chains(db: Session = Depends(get_db)):
    """Return each incident as an attack chain, with one timeline event per layer.

    Each incident already encodes which layers were involved (attributes.layers).
    Cross-layer incidents (2+ layers) are flagged and sorted to the top.
    """
    try:
        rows = db.execute(text("""
            SELECT
                id,
                type,
                severity,
                entity,
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.layers'))           AS layers_json,
                JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.description'))       AS description,
                COALESCE(
                    JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.anomaly_count')), '0'
                )                                                              AS anomaly_count,
                start_time,
                end_time
            FROM incidents
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 0
                    WHEN 'high'     THEN 1
                    WHEN 'medium'   THEN 2
                    ELSE                 3
                END,
                start_time DESC
            LIMIT 100
        """)).fetchall()

        chains = []
        for r in rows:
            layers = _parse_layers(r[4])
            risk    = _sev_score(r[2])

            # Build one virtual "event" per layer for the timeline view
            events = [
                {
                    "id":            "%s-%s" % (r[0], lyr),
                    "incident_type": "%s layer" % lyr.capitalize(),
                    "severity":      str(r[2]) if r[2] else "unknown",
                    "layer":         lyr,
                    "entity":        str(r[3]) if r[3] else "",
                    "risk_score":    risk,
                    "start_time":    str(r[7]) if r[7] else "",
                }
                for lyr in (layers if layers else ["unknown"])
            ]

            chains.append({
                "id":           "chain-%s" % r[0],
                "events":       events,
                "layer_count":  len(layers),
                "layers":       layers,
                "max_risk":     risk,
                "start_time":   str(r[7]) if r[7] else "",
                "end_time":     str(r[8]) if r[8] else "",
                "cross_layer":  len(layers) > 1,
                "entity":       str(r[3]) if r[3] else "",
                "description":  str(r[5]) if r[5] else "",
                "anomaly_count": int(r[6] or 0),
                "severity":     str(r[2]) if r[2] else "unknown",
            })

        return {"chains": chains, "total": len(chains)}
    except Exception as exc:
        logger.error("attack-chains failed: %s", exc)
        return {"chains": [], "total": 0, "error": str(exc)}


# ── Report summary ────────────────────────────────────────────────────────────

@router.get("/report-summary")
def get_report_summary(db: Session = Depends(get_db)):
    """All data needed for the report generator. Incidents table only — fast."""
    try:
        inc_total = int(db.execute(text("SELECT COUNT(*) FROM incidents")).scalar() or 0)

        sev_rows = db.execute(text(
            "SELECT COALESCE(severity, 'unknown'), COUNT(*) "
            "FROM incidents GROUP BY severity ORDER BY COUNT(*) DESC"
        )).fetchall()

        layer_rows = db.execute(text(
            "SELECT "
            "  COALESCE(JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.layers[0]')), 'unknown') AS lyr, "
            "  COUNT(*) AS cnt, "
            "  GROUP_CONCAT(severity SEPARATOR ',') AS sevs "
            "FROM incidents "
            "GROUP BY lyr ORDER BY cnt DESC"
        )).fetchall()

        top_entities = db.execute(text(
            "SELECT entity, COUNT(*) AS cnt, "
            "  GROUP_CONCAT(severity SEPARATOR ',') AS sevs "
            "FROM incidents "
            "WHERE entity IS NOT NULL AND entity != '' "
            "GROUP BY entity ORDER BY cnt DESC LIMIT 10"
        )).fetchall()

        top_incidents = db.execute(text(
            "SELECT id, type, severity, entity, start_time, "
            "  COALESCE(JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.layers[0]')), 'unknown') AS lyr "
            "FROM incidents "
            "ORDER BY "
            "  CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "  WHEN 'medium' THEN 2 ELSE 3 END, "
            "  start_time DESC "
            "LIMIT 5"
        )).fetchall()

        trend = db.execute(text(
            "SELECT DATE(start_time) AS d, COUNT(*), "
            "  SUM(CASE WHEN severity IN ('critical','high') THEN 1 ELSE 0 END) "
            "FROM incidents "
            "WHERE start_time IS NOT NULL "
            "GROUP BY d ORDER BY d"
        )).fetchall()

        def _avg_risk(sevs_csv):
            if not sevs_csv:
                return 0.25
            parts = [s for s in sevs_csv.split(",") if s]
            return round(sum(_sev_score(s) for s in parts) / max(len(parts), 1), 3)

        def _max_risk(sevs_csv):
            parts = [s for s in (sevs_csv or "").split(",") if s]
            return _sev_score(max(parts, key=_sev_score, default="low"))

        return {
            "generated_at":    datetime.utcnow().isoformat(),
            "total_incidents": inc_total,
            "by_severity":     [{"name": str(r[0]), "count": int(r[1])} for r in sev_rows],
            "by_layer":        [
                {"name": str(r[0]), "count": int(r[1]), "avg_risk": _avg_risk(r[2])}
                for r in layer_rows
            ],
            "top_entities":    [
                {"entity": str(r[0]), "count": int(r[1]), "max_risk": _max_risk(r[2])}
                for r in top_entities
            ],
            "top_incidents":   [
                {
                    "id":       int(r[0]),
                    "type":     str(r[1] or ""),
                    "severity": str(r[2] or ""),
                    "layer":    str(r[5] or "unknown"),
                    "entity":   str(r[3] or ""),
                    "risk":     _sev_score(r[2]),
                    "time":     str(r[4] or ""),
                }
                for r in top_incidents
            ],
            "daily_trend": [
                {"date": str(r[0]), "total": int(r[1]), "high_critical": int(r[2] or 0)}
                for r in trend
            ],
        }
    except Exception as exc:
        logger.error("report-summary failed: %s", exc)
        return {"error": str(exc), "generated_at": datetime.utcnow().isoformat()}
