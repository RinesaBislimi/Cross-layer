from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Incident, LogEvent

def _generate_incidents_time_cooccurrence(
    db: Session,
    *,
    window_minutes: int,
    min_layers: int,
    lookback_hours: int,
    require_anomaly: bool,
    max_events_per_incident: int,
    logger: logging.Logger,
) -> Dict[str, Any]:
    utc_now = datetime.utcnow()
    period_end = utc_now
    period_start = period_end - timedelta(hours=lookback_hours)
    time_anchor = "utc_now"
    window = timedelta(minutes=window_minutes)

    logs_in_window = (
        db.query(func.count(LogEvent.id))
        .filter(
            LogEvent.timestamp >= period_start,
            LogEvent.timestamp <= period_end,
        )
        .scalar()
        or 0
    )
    if logs_in_window == 0:
        max_ts = db.query(func.max(LogEvent.timestamp)).scalar()
        if max_ts is not None:
            period_end = max_ts
            period_start = period_end - timedelta(hours=lookback_hours)
            min_ts = db.query(func.min(LogEvent.timestamp)).scalar()
            if min_ts is not None and period_start < min_ts:
                period_start = min_ts
            time_anchor = "latest_log"
            logs_in_window = (
                db.query(func.count(LogEvent.id))
                .filter(
                    LogEvent.timestamp >= period_start,
                    LogEvent.timestamp <= period_end,
                )
                .scalar()
                or 0
            )

    logs_with_entity_in_window = (
        db.query(func.count(LogEvent.id))
        .filter(
            LogEvent.entity.isnot(None),
            LogEvent.entity != "",
            LogEvent.timestamp >= period_start,
            LogEvent.timestamp <= period_end,
        )
        .scalar()
        or 0
    )
    logs_with_entity_total = (
        db.query(func.count(LogEvent.id))
        .filter(LogEvent.entity.isnot(None), LogEvent.entity != "")
        .scalar()
        or 0
    )

    if period_start >= period_end:
        period_start = period_end - window

    created = 0
    skipped = 0
    time_cells_scanned = 0
    t = period_start

    while t < period_end:
        t_end = min(t + window, period_end)
        if t_end <= t:
            break
        time_cells_scanned += 1

        if t_end < period_end:
            time_upper = LogEvent.timestamp < t_end
        else:
            time_upper = LogEvent.timestamp <= period_end

        cell_filters = [
            LogEvent.timestamp >= t,
            time_upper,
            LogEvent.layer.isnot(None),
            LogEvent.layer != "",
        ]
        layer_cnt = (
            db.query(func.count(func.distinct(LogEvent.layer)))
            .filter(*cell_filters)
            .scalar()
            or 0
        )
        if layer_cnt < min_layers:
            t = t_end
            continue

        if require_anomaly:
            has_anomaly = (
                db.query(LogEvent.id)
                .filter(*cell_filters, LogEvent.label == 1)
                .limit(1)
                .first()
            )
            if not has_anomaly:
                t = t_end
                continue

        total_in_cell = (
            db.query(func.count(LogEvent.id)).filter(*cell_filters).scalar() or 0
        )
        anomaly_count = (
            db.query(func.count(LogEvent.id))
            .filter(*cell_filters, LogEvent.label == 1)
            .scalar()
            or 0
        )

        events = (
            db.query(LogEvent)
            .filter(*cell_filters)
            .order_by(LogEvent.timestamp)
            .limit(max_events_per_incident)
            .all()
        )
        if not events:
            t = t_end
            continue

        layers = sorted({e.layer for e in events if e.layer})
        if len(layers) < min_layers:
            t = t_end
            continue

        duration_minutes = max(
            0.0,
            (events[-1].timestamp - events[0].timestamp).total_seconds() / 60.0,
        )
        severity_score = (
            25 * len(layers)
            + 15 * min(anomaly_count, 50)
            + min(duration_minutes, 30)
        )
        if severity_score >= 80:
            severity = "critical"
        elif severity_score >= 60:
            severity = "high"
        elif severity_score >= 40:
            severity = "medium"
        else:
            severity = "low"

        incident_type = f"Cross-layer time window: {' + '.join(layers)}"
        existing = (
            db.query(Incident.id)
            .filter(
                Incident.entity.is_(None),
                Incident.start_time == t,
                Incident.end_time == t_end,
                Incident.type == incident_type,
            )
            .first()
        )
        if existing:
            skipped += 1
            t = t_end
            continue

        layer_str = " + ".join(l.capitalize() for l in layers)
        _desc = (
            f"Multi-layer activity spike: {layer_str} layers were active in the same "
            f"{window_minutes}-minute window "
            f"({anomaly_count} anomalous event{'s' if anomaly_count != 1 else ''} out of {total_in_cell} total). "
            f"Severity score: {severity_score:.0f}."
        )
        attrs: Dict[str, object] = {
            "description": _desc,
            "layers": layers,
            "num_events_stored": len(events),
            "num_events_in_cell": total_in_cell,
            "events_truncated": total_in_cell > len(events),
            "window_minutes": window_minutes,
            "generated_from": "time_cooccurrence",
            "correlation_mode": "time_cooccurrence",
            "require_anomaly": require_anomaly,
            "anomaly_count_in_cell": anomaly_count,
            "severity_score": severity_score,
            "duration_minutes": duration_minutes,
        }

        incident = Incident(
            entity=None,
            type=incident_type,
            severity=severity,
            start_time=t,
            end_time=t_end,
            events=[e.id for e in events],
            attributes=attrs,
        )
        db.add(incident)
        created += 1
        if created % 200 == 0:
            db.commit()
            logger.info("Committed %s time-cooccurrence incidents so far", created)

        t = t_end

    db.commit()
    logger.info(
        "Time cooccurrence: created=%s skipped=%s cells=%s anchor=%s",
        created,
        skipped,
        time_cells_scanned,
        time_anchor,
    )

    hint: Optional[str] = None
    if created == 0:
        hint = (
            f"No {window_minutes}-minute bucket contained {min_layers}+ distinct layers. "
            "The datasets likely span different calendar years (e.g. BGL=2006, CICIDS=2017) "
            "so no single time window contains events from multiple layers. "
            "Use 'Generate ML incidents' instead — it scores each dataset within its own time range."
        )

    return {
        "created": created,
        "skipped": skipped,
        "entities_scanned": 0,
        "multi_layer_entities_in_window": 0,
        "sliding_window": False,
        "correlation_mode": "time_cooccurrence",
        "time_cells_scanned": time_cells_scanned,
        "time_anchor": time_anchor,
        "window_start": period_start,
        "window_end": period_end,
        "logs_in_window": logs_in_window,
        "logs_with_entity_in_window": logs_with_entity_in_window,
        "logs_with_entity_total": logs_with_entity_total,
        "hint": hint,
    }

def correlate_entity_in_window(
    db: Session,
    entity: str,
    start: datetime,
    end: Optional[datetime] = None,
) -> Optional[Incident]:
    if end is None:
        end = start + timedelta(minutes=10)

    events: List[LogEvent] = (
        db.query(LogEvent)
        .filter(
            LogEvent.entity == entity,
            LogEvent.timestamp >= start,
            LogEvent.timestamp <= end,
        )
        .order_by(LogEvent.timestamp)
        .all()
    )

    if not events:
        return None

    has_network = any(e.layer == "network" for e in events)
    has_system = any(e.layer == "system" for e in events)
    has_application = any(e.layer == "application" for e in events)

    if has_network and has_system and has_application:
        description = "Cross-layer incident: network + system + application activity"
        severity = "high"
    elif has_network and has_system:
        description = "Cross-layer incident: network + system activity"
        severity = "medium"
    elif has_network and has_application:
        description = "Cross-layer incident: network + application activity"
        severity = "medium"
    elif has_system and has_application:
        description = "Cross-layer incident: system + application activity"
        severity = "medium"
    else:
        return None

    incident = Incident(
        entity=entity,
        type=description,
        severity=severity,
        start_time=start,
        end_time=end,
        events=[e.id for e in events],
        attributes={"layers": list({e.layer for e in events})},
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident

def find_common_entities(
    db: Session, min_layers: int = 2, limit: int = 50
) -> List[Dict[str, object]]:
    rows = (
        db.query(LogEvent.entity, LogEvent.layer)
        .filter(LogEvent.entity.isnot(None), LogEvent.entity != "")
        .distinct()
        .all()
    )

    layers_by_entity: Dict[str, set] = {}
    for entity, layer in rows:
        if entity:
            layers_by_entity.setdefault(entity, set()).add(layer)

    result: List[Dict[str, object]] = []
    for entity, layers in layers_by_entity.items():
        if len(layers) >= min_layers:
            result.append(
                {"entity": entity, "layers": sorted(layers), "num_layers": len(layers)}
            )

    result.sort(key=lambda x: x["num_layers"], reverse=True)
    return result[:limit]

def generate_cross_layer_incidents(
    db: Session,
    window_minutes: int = 10,
    min_layers: int = 2,
    lookback_hours: int = 24,
    require_anomaly: bool = False,
    max_entities: int = 5000,
    sliding_window: bool = True,
    correlation_mode: str = "entity",
    max_events_per_incident: int = 2000,
) -> Dict[str, Any]:
    logger = logging.getLogger(__name__)

    if window_minutes <= 0:
        raise ValueError("window_minutes must be > 0")
    if min_layers <= 1:
        raise ValueError("min_layers must be >= 2")
    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be > 0")
    if correlation_mode not in ("entity", "time_cooccurrence"):
        raise ValueError("correlation_mode must be 'entity' or 'time_cooccurrence'")
    if max_events_per_incident < 1:
        raise ValueError("max_events_per_incident must be >= 1")

    if correlation_mode == "time_cooccurrence":
        return _generate_incidents_time_cooccurrence(
            db,
            window_minutes=window_minutes,
            min_layers=min_layers,
            lookback_hours=lookback_hours,
            require_anomaly=require_anomaly,
            max_events_per_incident=max_events_per_incident,
            logger=logger,
        )

    utc_now = datetime.utcnow()
    period_end = utc_now
    period_start = period_end - timedelta(hours=lookback_hours)
    time_anchor = "utc_now"
    window = timedelta(minutes=window_minutes)

    def _multi_layer_entity_ids(
        p_start: datetime,
        p_end: datetime,
        *,
        min_distinct_layers: int,
        limit: int,
    ) -> List[str]:
        rows = (
            db.query(LogEvent.entity)
            .filter(
                LogEvent.entity.isnot(None),
                LogEvent.entity != "",
                LogEvent.layer.isnot(None),
                LogEvent.layer != "",
                LogEvent.timestamp >= p_start,
                LogEvent.timestamp <= p_end,
            )
            .group_by(LogEvent.entity)
            .having(func.count(func.distinct(LogEvent.layer)) >= min_distinct_layers)
            .order_by(func.count(LogEvent.id).desc())
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows if r and r[0]]

    def _count_multi_layer_entities(
        p_start: datetime,
        p_end: datetime,
        *,
        min_distinct_layers: int,
    ) -> int:
        subq = (
            db.query(LogEvent.entity)
            .filter(
                LogEvent.entity.isnot(None),
                LogEvent.entity != "",
                LogEvent.layer.isnot(None),
                LogEvent.layer != "",
                LogEvent.timestamp >= p_start,
                LogEvent.timestamp <= p_end,
            )
            .group_by(LogEvent.entity)
            .having(func.count(func.distinct(LogEvent.layer)) >= min_distinct_layers)
        ).subquery()
        return db.query(func.count()).select_from(subq).scalar() or 0

    entities = _multi_layer_entity_ids(
        period_start,
        period_end,
        min_distinct_layers=min_layers,
        limit=max_entities,
    )
    multi_layer_entity_total = _count_multi_layer_entities(
        period_start,
        period_end,
        min_distinct_layers=min_layers,
    )

    logs_with_entity_total = (
        db.query(func.count(LogEvent.id))
        .filter(LogEvent.entity.isnot(None), LogEvent.entity != "")
        .scalar()
        or 0
    )

    if not entities and logs_with_entity_total > 0:
        max_ts_with_entity = (
            db.query(func.max(LogEvent.timestamp))
            .filter(LogEvent.entity.isnot(None), LogEvent.entity != "")
            .scalar()
        )
        min_ts_with_entity = (
            db.query(func.min(LogEvent.timestamp))
            .filter(LogEvent.entity.isnot(None), LogEvent.entity != "")
            .scalar()
        )
        if max_ts_with_entity is not None:
            period_end = max_ts_with_entity
            period_start = period_end - timedelta(hours=lookback_hours)
            if min_ts_with_entity is not None and period_start < min_ts_with_entity:
                period_start = min_ts_with_entity
            time_anchor = "latest_log_with_entity"
            entities = _multi_layer_entity_ids(
                period_start,
                period_end,
                min_distinct_layers=min_layers,
                limit=max_entities,
            )
            multi_layer_entity_total = _count_multi_layer_entities(
                period_start,
                period_end,
                min_distinct_layers=min_layers,
            )
            logger.info(
                "No multi-layer entities in UTC-now window; anchor=%s, window [%s, %s], "
                "candidates=%s (total_multi_layer=%s)",
                time_anchor,
                period_start,
                period_end,
                len(entities),
                multi_layer_entity_total,
            )

    logs_in_window = (
        db.query(func.count(LogEvent.id))
        .filter(
            LogEvent.timestamp >= period_start,
            LogEvent.timestamp <= period_end,
        )
        .scalar()
        or 0
    )
    logs_with_entity_in_window = (
        db.query(func.count(LogEvent.id))
        .filter(
            LogEvent.entity.isnot(None),
            LogEvent.entity != "",
            LogEvent.timestamp >= period_start,
            LogEvent.timestamp <= period_end,
        )
        .scalar()
        or 0
    )

    logger.info("Found %s entities to process (anchor=%s)", len(entities), time_anchor)

    created = 0
    skipped = 0

    def process_bucket(
        ent: str,
        bucket: List[LogEvent],
        w_start: datetime,
        w_end: datetime,
    ) -> None:
        nonlocal created, skipped
        if not bucket:
            return
        layers = sorted({e.layer for e in bucket if e.layer})
        if len(layers) < min_layers:
            return

        anomaly_count = sum(1 for e in bucket if e.label == 1)
        if require_anomaly and anomaly_count == 0:
            return

        duration_minutes = max(
            0.0,
            (bucket[-1].timestamp - bucket[0].timestamp).total_seconds() / 60.0,
        )
        severity_score = (
            25 * len(layers)
            + 15 * anomaly_count
            + min(duration_minutes, 30)
        )
        if severity_score >= 80:
            severity = "critical"
        elif severity_score >= 60:
            severity = "high"
        elif severity_score >= 40:
            severity = "medium"
        else:
            severity = "low"

        incident_type = f"Cross-layer incident: {' + '.join(layers)}"
        pattern = None
        has_net = any(e.layer == "network" and e.label == 1 for e in bucket)
        has_app = any(e.layer == "application" and e.label == 1 for e in bucket)
        has_sys = any(e.layer == "system" and e.label == 1 for e in bucket)
        if has_net and has_app and has_sys:
            pattern = "network-application-system-escalation"

        existing = (
            db.query(Incident.id)
            .filter(
                Incident.entity == ent,
                Incident.start_time == w_start,
                Incident.end_time == w_end,
                Incident.type == incident_type,
            )
            .first()
        )
        if existing:
            skipped += 1
            return

        layer_str = " + ".join(l.capitalize() for l in layers)
        _ent_label = f'Entity "{ent}"' if ent else "Unknown entity"
        _pattern_note = (
            " Pattern: full network-application-system escalation chain detected."
            if pattern == "network-application-system-escalation" else ""
        )
        _desc = (
            f"{_ent_label} triggered alerts across {layer_str} layers "
            f"({anomaly_count} anomalous event{'s' if anomaly_count != 1 else ''} "
            f"in {len(bucket)} total, over {duration_minutes:.1f} minutes).{_pattern_note}"
        )
        attrs: Dict[str, object] = {
            "description": _desc,
            "layers": layers,
            "num_events": len(bucket),
            "anomaly_count": anomaly_count,
            "window_minutes": window_minutes,
            "generated_from": "log_events",
            "require_anomaly": require_anomaly,
            "severity_score": severity_score,
            "duration_minutes": duration_minutes,
            "sliding_window": sliding_window,
        }
        if pattern:
            attrs["correlation_pattern"] = pattern

        incident = Incident(
            entity=ent,
            type=incident_type,
            severity=severity,
            start_time=w_start,
            end_time=w_end,
            events=[e.id for e in bucket],
            attributes=attrs,
        )
        db.add(incident)
        created += 1
        if created % 100 == 0:
            logger.info("Created %s incidents so far", created)

    for entity in entities:
        events: List[LogEvent] = (
            db.query(LogEvent)
            .filter(
                LogEvent.entity == entity,
                LogEvent.timestamp >= period_start,
                LogEvent.timestamp <= period_end,
            )
            .order_by(LogEvent.timestamp)
            .all()
        )

        if not events:
            continue

        if sliding_window:
            right = 0
            n = len(events)
            for left in range(n):
                if right < left:
                    right = left
                w_start = events[left].timestamp
                w_end = w_start + window
                while right < n and events[right].timestamp <= w_end:
                    right += 1
                process_bucket(entity, events[left:right], w_start, w_end)
        else:
            i = 0
            while i < len(events):
                w_start = events[i].timestamp
                w_end = w_start + window
                bucket: List[LogEvent] = []
                while i < len(events) and events[i].timestamp <= w_end:
                    bucket.append(events[i])
                    i += 1
                process_bucket(entity, bucket, w_start, w_end)

    db.commit()
    logger.info(
        "Completed: created=%s skipped=%s entities_scanned=%s anchor=%s",
        created,
        skipped,
        len(entities),
        time_anchor,
    )

    probe_window_hours = 0
    multi_layer_entities_in_probe_window = 0
    if multi_layer_entity_total == 0 and logs_with_entity_total > 0:
        probe_window_hours = int(min(max(168, lookback_hours * 7), 720))
        probe_start = period_end - timedelta(hours=probe_window_hours)
        multi_layer_entities_in_probe_window = _count_multi_layer_entities(
            probe_start,
            period_end,
            min_distinct_layers=min_layers,
        )

    hint: Optional[str] = None
    if not entities:
        if logs_with_entity_total == 0:
            hint = (
                "No rows have a non-empty `entity` field. Populate `entity` (IPs, host ids, users) "
                "on log_events so the same value can appear across layers."
            )
        elif multi_layer_entities_in_probe_window > 0:
            hint = (
                f"No entity spans {min_layers}+ layers in the last {lookback_hours}h ending at "
                f"`window_end`, but `{multi_layer_entities_in_probe_window}` do in the last "
                f"{probe_window_hours}h. Call generate again with "
                f"`lookback_hours={probe_window_hours}` or higher so those entities are included."
            )
        else:
            hint = (
                f"No entity spans {min_layers}+ distinct layers in the last {probe_window_hours}h "
                f"ending at `window_end` either. Layer-specific identifiers probably differ — map the "
                f"same host/user/IP into `entity` during ingestion, and check "
                f"`GET /admin/common-entities?min_layers={min_layers}` (empty = no shared IDs "
                f"across layers in the dataset). "
                f"Alternatively use `correlation_mode=time_cooccurrence` to open incidents from "
                f"time buckets that contain multiple layers without a shared `entity`."
            )
    elif created == 0 and skipped == 0:
        hint = (
            f"Each scanned entity has {min_layers}+ layers in the window, but no single "
            f"`window_minutes`={window_minutes} slice contained that many layers at once. "
            "Increase `window_minutes` (e.g. 60–120) so separated layer signals can overlap, "
            "or verify timestamps align so correlation windows can include them."
        )

    out: Dict[str, Any] = {
        "created": created,
        "skipped": skipped,
        "entities_scanned": len(entities),
        "multi_layer_entities_in_window": multi_layer_entity_total,
        "correlation_mode": "entity",
        "sliding_window": sliding_window,
        "time_anchor": time_anchor,
        "window_start": period_start,
        "window_end": period_end,
        "logs_in_window": logs_in_window,
        "logs_with_entity_in_window": logs_with_entity_in_window,
        "logs_with_entity_total": logs_with_entity_total,
        "hint": hint,
    }
    if multi_layer_entity_total == 0 and logs_with_entity_total > 0:
        out["probe_window_hours"] = probe_window_hours
        out["multi_layer_entities_in_probe_window"] = multi_layer_entities_in_probe_window
    return out