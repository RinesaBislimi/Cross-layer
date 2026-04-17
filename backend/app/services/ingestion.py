# services/ingestion.py
import codecs
import csv
import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LogEvent, RAW_MAX_LENGTH

logger = logging.getLogger(__name__)


def _backend_root() -> Path:
    """Parent of ``app/`` (the backend project directory that contains ``data/``)."""
    return Path(__file__).resolve().parent.parent.parent


def _resolve_csv_file(*candidates: str) -> Optional[str]:
    """
    Return the first path that exists. Tries, in order:
    absolute path, path relative to backend root, path relative to cwd.
    Matches ``config.Settings`` defaults like ``data/bgl/bgl.csv``.
    """
    for rel in candidates:
        if not rel or not str(rel).strip():
            continue
        rel = str(rel).strip()
        p = Path(rel)
        if p.is_file():
            return str(p.resolve())
        for base in (_backend_root(), Path.cwd()):
            q = (base / rel).resolve()
            if q.is_file():
                return str(q)
    return None


def _detect_encoding(path: str) -> str:
    """Detect file encoding by inspecting the first 4 bytes (BOM detection only)."""
    with open(path, "rb") as f:
        head = f.read(4)
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    return "utf-8"


def _csv_rows_from_path(path: str) -> Tuple[Iterator[Dict[str, Any]], str]:
    """
    Return (streaming iterator of row dicts, delimiter used).

    Opens the file as a *stream* so the entire CSV is never loaded into memory.
    Delimiter is detected from the first line only.
    """
    encoding = _detect_encoding(path)
    # Peek at the first line to detect delimiter without reading the whole file
    with open(path, encoding=encoding, errors="replace", newline="") as f:
        first_line = f.readline()
    delimiter = "," if "," in first_line else "\t" if "\t" in first_line else ";"

    # Return a live file handle wrapped in DictReader — caller iterates it
    # We use a generator so the file is closed after exhaustion
    def _stream():
        with open(path, encoding=encoding, errors="replace", newline="") as fh:
            # Strip NUL chars inline via a generator wrapper
            reader = csv.DictReader(
                (line.replace("\x00", "") for line in fh),
                delimiter=delimiter,
            )
            yield from reader

    return _stream(), delimiter


def _normalize_row_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """Strip CSV header whitespace so 'Label ' and 'Label' match."""
    return {str(k).strip(): v for k, v in row.items()}


def _row_lookup(row: Dict[str, Any], *names: str) -> Optional[Any]:
    """First non-empty value for any of the candidate column names (exact, after strip)."""
    for name in names:
        if name in row and row[name] is not None and str(row[name]).strip() != "":
            return row[name]
    return None


def _serialize_raw_row(row: Dict[str, Any]) -> str:
    """Stable JSON for DB `raw` (LogEvent.raw); never use invalid kwarg `raw_data`."""
    try:
        return json.dumps(row, default=str, ensure_ascii=False)[:RAW_MAX_LENGTH]
    except Exception:
        return str(row)[:RAW_MAX_LENGTH]


def _parse_datetime_general(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in ("-", "NaN", "nan", "None"):
        return None
    fmts = (
        "%Y%m%d%H%M%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
    )
    for fmt in fmts:
        try:
            return datetime.strptime(s.replace("Z", ""), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bgl_timestamp_from_log_text(text: str) -> Optional[datetime]:
    """Parse BGL-style timestamps embedded in log lines."""
    if not text:
        return None
    # e.g. 2005-06-03-15.42.50.363779
    m = re.search(
        r"(\d{4})-(\d{2})-(\d{2})-(\d{2})\.(\d{2})\.(\d{2})\.(\d+)",
        text,
    )
    if m:
        y, mo, d, h, mi, s, _frac = m.groups()
        return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    # e.g. 2005.06.03 at start
    m2 = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", text)
    if m2:
        y, mo, d = m2.groups()
        return datetime(int(y), int(mo), int(d))
    return None


def _infer_cicids_label(row: Dict[str, Any]) -> int:
    """0 = benign/normal, 1 = attack / anomaly (handles Label, Attack Type, etc.)."""
    for key in ("Label", "label", "Attack Type", "attack_type", "Label "):
        if key not in row or row[key] is None:
            continue
        v = str(row[key]).strip()
        if not v:
            continue
        u = v.upper()
        if u in (
            "BENIGN",
            "NORMAL TRAFFIC",
            "NORMAL",
            "BENIGN TRAFFIC",
            "WHITE",
        ):
            return 0
        try:
            return int(v)
        except ValueError:
            return 1
    return 0

def extract_entity_from_bgl(message: str, row: dict) -> Optional[str]:
    """
    Extract entity (IP, hostname, node ID) from BGL logs
    BGL logs often contain node names, IPs, or hostnames
    """
    # CSV exports often use node_id (see scripts/bgl_log_to_csv.py)
    if "node_id" in row and row["node_id"]:
        return str(row["node_id"]).strip()
    # Try common BGL fields
    if 'node' in row and row['node']:
        return row['node']
    if 'host' in row and row['host']:
        return row['host']
    if 'ip' in row and row['ip']:
        return row['ip']
    
    # Try to extract from message
    if message:
        # Look for IP addresses
        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
        ip_match = re.search(ip_pattern, message)
        if ip_match:
            return ip_match.group()
        
        # Look for hostnames (simplified)
        hostname_pattern = r'\b[a-zA-Z0-9][a-zA-Z0-9\-]{1,62}\.(?:com|org|net|local|edu|gov)\b'
        hostname_match = re.search(hostname_pattern, message)
        if hostname_match:
            return hostname_match.group()
        
        # Look for node IDs (e.g., node001, server-01, etc.)
        node_pattern = r'\b(?:node|server|host|vm)[\-_]?[0-9]+\b'
        node_match = re.search(node_pattern, message, re.IGNORECASE)
        if node_match:
            return node_match.group()
    
    return None


def extract_entity_from_cicids(row: dict) -> Optional[str]:
    """
    Extract entity from CICIDS network logs
    Usually source IP or destination IP
    """
    # Try different field names that might contain IPs
    for field in ['Src IP', 'Source IP', 'src_ip', 'source_ip', 'Source']:
        if field in row and row[field]:
            return str(row[field]).strip()
    
    for field in ['Dst IP', 'Dest IP', 'dst_ip', 'dest_ip', 'Destination']:
        if field in row and row[field]:
            return str(row[field]).strip()
    
    # Look for entity field
    if 'entity' in row and row['entity']:
        return str(row['entity']).strip()

    # Reduced exports may omit IPs; weak correlation key for cross-layer demos
    dp = _row_lookup(row, "Destination Port", "destination port")
    if dp is not None and str(dp).strip():
        return f"dst-port:{str(dp).strip()}"

    return None


def extract_entity_from_tda(row: dict) -> Optional[str]:
    """
    Extract entity from TDA application logs
    Usually user ID, session ID, or application name
    """
    # Try common fields
    for field in ['user_id', 'user', 'username', 'uid', 'userid']:
        if field in row and row[field]:
            return row[field]
    
    for field in ['session_id', 'session', 'sid']:
        if field in row and row[field]:
            return row[field]
    
    for field in ['app_id', 'app_name', 'application', 'service']:
        if field in row and row[field]:
            return row[field]
    
    # Look for entity field
    if 'entity' in row and row['entity']:
        return row['entity']
    
    return None


def ingest_bgl_csv(db: Session, csv_path: Optional[str] = None) -> int:
    """Ingest BGL logs with entity extraction"""
    if csv_path is None:
        s = get_settings()
        csv_path = _resolve_csv_file(
            s.BGL_PATH,
            "data/bgl/bgl.csv",
            "data/bgl_logs.csv",
            "../data/bgl_logs.csv",
            "bgl_logs.csv",
        )
        if not csv_path:
            raise FileNotFoundError(
                "BGL CSV file not found. Set BGL_PATH in .env or place a file at "
                "backend/data/bgl/bgl.csv (see config.Settings)."
            )
    
    count = 0
    BATCH = 5000
    batch = []

    try:
        reader, _ = _csv_rows_from_path(csv_path)
        for row in reader:
            row = _normalize_row_keys(row)
            # Extract timestamp
            timestamp = None
            for ts_field in ('timestamp', 'time', 'date', 'datetime', 'log_time'):
                v = row.get(ts_field)
                if v:
                    timestamp = _parse_datetime_general(v)
                    if timestamp:
                        break

            # Extract message (BGL exports use log_message — see data/bgl/bgl.csv)
            message = ""
            for msg_field in ("log_message", "message", "msg", "log", "content", "text"):
                v = row.get(msg_field)
                if v:
                    message = str(v)
                    break

            if not timestamp:
                timestamp = _bgl_timestamp_from_log_text(message)
            if not timestamp:
                timestamp = datetime.utcnow()

            entity = extract_entity_from_bgl(message, row)

            # In the existing bgl.csv the 'timestamp' column holds the BGL alert flag:
            # '-' = normal (0), anything else = anomaly type (1).
            label = 0
            raw_ts_field = row.get("timestamp", "").strip()
            if raw_ts_field and raw_ts_field != "-" and _parse_datetime_general(raw_ts_field) is None:
                label = 1
            for label_field in ('label', 'anomaly', 'is_anomaly', 'class'):
                v = row.get(label_field)
                if v not in (None, ""):
                    try:
                        label = int(str(v).strip())
                        break
                    except ValueError:
                        if str(v).lower() in ('anomaly', 'true', '1', 'yes'):
                            label = 1
                            break

            msg_stored = message.strip()[:1000] or None
            features: Dict[str, Any] = {"source": "BGL"}
            nid = row.get("node_id")
            if nid is not None and str(nid).strip():
                features["node_id"] = str(nid).strip()

            batch.append(LogEvent(
                timestamp=timestamp,
                layer="system",
                source="BGL",
                message=msg_stored,
                entity=entity,
                label=label,
                raw=_serialize_raw_row(row),
                features=features,
            ))
            count += 1

            if len(batch) >= BATCH:
                db.bulk_save_objects(batch)
                db.commit()
                logger.info("BGL ingested %d rows so far", count)
                batch = []

        if batch:
            db.bulk_save_objects(batch)
            db.commit()

        logger.info("BGL ingestion complete: %d rows", count)
        return count

    except Exception as e:
        logger.error("Error ingesting BGL logs: %s", e)
        db.rollback()
        raise


def ingest_cicids_csv(db: Session, csv_path: Optional[str] = None) -> int:
    """Ingest CICIDS logs with entity extraction"""
    if csv_path is None:
        s = get_settings()
        csv_path = _resolve_csv_file(
            s.CICIDS_PATH,
            "data/cicids/cicids.csv",
            "data/cicids_logs.csv",
            "../data/cicids_logs.csv",
            "cicids_logs.csv",
        )
        if not csv_path:
            raise FileNotFoundError(
                "CICIDS CSV file not found. Set CICIDS_PATH in .env or place a file at "
                "backend/data/cicids/cicids.csv (see config.Settings)."
            )
    
    _CICIDS_NUM_COLS = (
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
    )

    count = 0
    BATCH = 5000
    batch = []
    _now = datetime.utcnow  # local alias avoids global lookup in hot loop

    try:
        reader, _ = _csv_rows_from_path(csv_path)
        for row in reader:
            row = _normalize_row_keys(row)

            timestamp = None
            for ts_field in ('Timestamp', 'timestamp', 'time', 'datetime'):
                v = row.get(ts_field)
                if v:
                    ts_str = str(v).strip()
                    if '/' in ts_str:
                        try:
                            timestamp = datetime.strptime(ts_str, '%d/%m/%Y %H:%M:%S')
                            break
                        except ValueError:
                            pass
                    timestamp = _parse_datetime_general(ts_str)
                    if timestamp:
                        break
            if not timestamp:
                timestamp = _now()

            entity = extract_entity_from_cicids(row)

            sip = _row_lookup(row, "Src IP", "Source IP", "src_ip")
            dip = _row_lookup(row, "Dst IP", "Dest IP", "dst_ip")
            parts = []
            if sip or dip:
                parts.append("Flow:")
                if sip:
                    parts.append(str(sip))
                if dip:
                    parts.append("->" + str(dip))
            proto = _row_lookup(row, "Protocol", "protocol")
            if proto:
                parts.append("[" + str(proto) + "]")
            atk = _row_lookup(row, "Attack Type", "Label", "label")
            if atk:
                parts.append("attack=" + str(atk))
            dp = _row_lookup(row, "Destination Port", "destination port")
            if dp is not None:
                parts.append("dst_port=" + str(dp))
            message = " ".join(parts) if parts else "CICIDS flow"

            label = _infer_cicids_label(row)

            num_feats: Dict[str, Any] = {"source": "CICIDS2017"}
            for col in _CICIDS_NUM_COLS:
                v = row.get(col)
                if v is not None and str(v).strip() not in ("", "nan", "inf", "-inf"):
                    try:
                        num_feats[col] = float(v)
                    except (ValueError, TypeError):
                        pass
            num_feats["attack_type"] = atk

            batch.append(LogEvent(
                timestamp=timestamp,
                layer="network",
                source="CICIDS2017",
                message=message[:1000],
                entity=entity,
                label=label,
                raw=_serialize_raw_row(row),
                features=num_feats,
            ))
            count += 1

            if len(batch) >= BATCH:
                db.bulk_save_objects(batch)
                db.commit()
                logger.info("CICIDS ingested %d rows so far", count)
                batch = []

        if batch:
            db.bulk_save_objects(batch)
            db.commit()

        logger.info("CICIDS ingestion complete: %d rows", count)
        return count

    except Exception as e:
        logger.error("Error ingesting CICIDS logs: %s", e)
        db.rollback()
        raise


def ingest_tda_csv(db: Session, csv_path: Optional[str] = None) -> int:
    """Ingest TDA logs with entity extraction"""
    if csv_path is None:
        s = get_settings()
        csv_path = _resolve_csv_file(
            s.TDA_PATH,
            "data/tda/tda.csv",
            "data/tda_logs.csv",
            "../data/tda_logs.csv",
            "tda_logs.csv",
        )
        if not csv_path:
            raise FileNotFoundError(
                "TDA CSV file not found. Set TDA_PATH in .env or place a file at "
                "backend/data/tda/tda.csv (see config.Settings)."
            )
    
    count = 0
    BATCH = 5000
    batch = []
    _now = datetime.utcnow

    try:
        reader, _ = _csv_rows_from_path(csv_path)
        for row in reader:
            row = _normalize_row_keys(row)

            timestamp = None
            for ts_field in ('timestamp', 'time', 'date', 'datetime', 'log_time'):
                v = row.get(ts_field)
                if v:
                    timestamp = _parse_datetime_general(v)
                    if timestamp:
                        break
            if not timestamp:
                timestamp = _now()

            message = ""
            for msg_field in ("message", "msg", "log", "content", "text", "description"):
                v = row.get(msg_field)
                if v:
                    message = str(v)
                    break
            if not message.strip():
                u = _row_lookup(row, "user", "user_id", "username")
                tbl = _row_lookup(row, "table", "table_id", "resource")
                bits = []
                if u is not None:
                    bits.append(f"user={u}")
                if tbl is not None:
                    bits.append(f"table={tbl}")
                message = " ".join(bits)

            entity = extract_entity_from_tda(row)

            label = 0
            for label_field in ('label', 'anomaly', 'is_anomaly', 'class', 'attack'):
                v = row.get(label_field)
                if v not in (None, ""):
                    try:
                        label = int(str(v).strip())
                        break
                    except ValueError:
                        if str(v).lower() in ('anomaly', 'true', '1', 'yes', 'attack'):
                            label = 1
                            break

            features: Dict[str, Any] = {"source": "TDA"}
            for k in ("user", "table", "user_id", "table_id"):
                v = row.get(k)
                if v is not None and str(v).strip():
                    features[k] = str(v).strip()

            batch.append(LogEvent(
                timestamp=timestamp,
                layer="application",
                source="TDA",
                message=message.strip()[:1000] or None,
                entity=entity,
                label=label,
                raw=_serialize_raw_row(row),
                features=features,
            ))
            count += 1

            if len(batch) >= BATCH:
                db.bulk_save_objects(batch)
                db.commit()
                logger.info("TDA ingested %d rows so far", count)
                batch = []

        if batch:
            db.bulk_save_objects(batch)
            db.commit()

        logger.info("TDA ingestion complete: %d rows", count)
        return count

    except Exception as e:
        logger.error("Error ingesting TDA logs: %s", e)
        db.rollback()
        raise