from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

COMBINE_THRESHOLD = 4
TOP_THRESHOLD     = 7
MAX_COMBINED      = 3

INTENTS: Dict[str, Dict] = {
    "metrics": {
        "keywords": {
            "precision": 4, "recall": 4, "f1 score": 5, "f1": 3,
            "false positive rate": 5, "false positive": 4, "fpr": 4,
            "false negative rate": 5, "false negative": 4, "fnr": 4,
            "confusion matrix": 5, "confusion": 3,
            "accuracy": 3, "auc": 4, "roc": 4,
            "tp": 2, "tn": 2, "fp": 2, "fn": 2,
            "true positive": 3, "true negative": 3,
            "metric": 3, "performance": 2, "score": 2, "measure": 2,
        },
        "threshold": 4, "db_needed": False,
    },
    "anomaly": {
        "keywords": {
            "anomal": 4, "attack": 3, "suspicious": 3, "threat": 3,
            "malicious": 3, "intrusion": 4, "breach": 4, "exploit": 3,
            "flag": 2, "label": 2, "detected": 2, "cyber": 3,
        },
        "threshold": 4, "db_needed": True,
    },
    "incident": {
        "keywords": {
            "incident": 5, "alert": 3, "event group": 5, "correlat": 4,
            "severity": 3, "critical": 3, "high severity": 4, "triage": 4,
        },
        "threshold": 4, "db_needed": True,
    },
    "model": {
        "keywords": {
            "random forest": 5, "xgboost": 5, "lgbm": 5, "lightgbm": 5,
            "isolation forest": 5, "svm": 4, "mlp": 4, "neural network": 5,
            "neural": 3, "algorithm": 3, "machine learning": 4,
            "model": 2, "train": 2, "classifier": 4,
        },
        "threshold": 4, "db_needed": False,
    },
    "reduce_fp": {
        "keywords": {
            "reduce false positive": 5, "lower false positive": 5,
            "fewer false alarm": 5, "alert fatigue": 5,
            "improve precision": 5, "threshold": 3,
            "reduce": 2, "lower": 2, "improve": 2, "better": 2,
            "false positive rate": 4, "high fpr": 5,
        },
        "threshold": 4, "db_needed": False,
    },
    "pipeline": {
        "keywords": {
            "pipeline": 4, "workflow": 4, "step": 3, "process": 3,
            "ingest": 4, "how does": 3, "how do": 3,
            "what happens": 3, "end to end": 4, "overview of": 3,
        },
        "threshold": 4, "db_needed": True,
    },
    "layers": {
        "keywords": {
            "layer": 4, "bgl": 3, "cicids": 3, "tda": 3,
            "system log": 5, "network layer": 5, "application layer": 5,
            "system layer": 5, "network flow": 4, "database access": 4,
            "what layer": 4, "which layer": 4,
        },
        "threshold": 4, "db_needed": True,
    },
    "cross_layer": {
        "keywords": {
            "cross-layer": 5, "cross layer": 5, "multi-layer": 5,
            "correlat": 4, "combine layer": 5, "across layer": 5,
            "entity": 3, "time window": 4, "co-occurrence": 4,
        },
        "threshold": 4, "db_needed": False,
    },
    "dataset": {
        "keywords": {
            "dataset": 4, "csv": 4, "file": 2, "data source": 5,
            "input data": 4, "what file": 4, "which file": 4,
            "bgl": 3, "cicids": 3, "tda": 3, "blue gene": 4,
        },
        "threshold": 4, "db_needed": True,
    },
    "stats": {
        "keywords": {
            "how many": 4, "count": 3, "total": 3, "statistic": 3,
            "summary": 3, "overview": 3, "number of": 4, "how much": 3,
            "current": 2, "live": 2, "right now": 3,
        },
        "threshold": 4, "db_needed": True,
    },
    "framing_high_fpr": {
        "keywords": {
            "high false positive": 6, "high fpr": 6, "too many alert": 6,
            "lots of false alarm": 6, "many false positive": 6,
            "false positive rate is high": 6, "fpr is high": 6,
        },
        "threshold": 5, "db_needed": False, "framing": True,
    },
    "framing_low_recall": {
        "keywords": {
            "low recall": 6, "missing attack": 6, "missed anomal": 6,
            "not catching": 5, "recall is low": 6, "miss threat": 5,
            "false negative rate is high": 6,
        },
        "threshold": 5, "db_needed": False, "framing": True,
    },
    "framing_low_f1": {
        "keywords": {
            "low f1": 6, "bad f1": 6, "f1 is low": 6, "poor f1": 6,
            "f1 score is low": 6, "f1 too low": 6,
        },
        "threshold": 5, "db_needed": False, "framing": True,
    },
    "framing_high_recall": {
        "keywords": {
            "high recall": 5, "catching everything": 5, "recall is high": 5,
            "recall too high": 4, "maximise recall": 4, "maximize recall": 4,
        },
        "threshold": 5, "db_needed": False, "framing": True,
    },
    "compare": {
        "keywords": {
            "difference between": 6, "compare": 5, "versus": 5, "vs ": 5,
            "vs.": 5, "better than": 5, "which is better": 6,
            "pros and cons": 6, "advantages": 4, "disadvantages": 4,
            "contrast": 5,
        },
        "threshold": 4, "db_needed": False, "comparison": True,
    },
}

ALGO_COMPARE: Dict[str, Dict[str, str]] = {
    "rf": {
        "name": "Random Forest",
        "speed": "Medium", "accuracy": "High", "fpr": "Medium",
        "large_data": "Good", "imbalanced": "Good with class_weight",
        "best_for": "General purpose, robust to noise",
    },
    "xgboost": {
        "name": "XGBoost",
        "speed": "Medium-Fast", "accuracy": "Very High", "fpr": "Low",
        "large_data": "Good", "imbalanced": "scale_pos_weight param",
        "best_for": "Highest accuracy on tabular data",
    },
    "lgbm": {
        "name": "LightGBM",
        "speed": "Fastest", "accuracy": "Very High", "fpr": "Low",
        "large_data": "Best", "imbalanced": "is_unbalance param",
        "best_for": "Large datasets, speed-critical tasks",
    },
    "svm": {
        "name": "SVM (Linear)",
        "speed": "Slow on large data", "accuracy": "Medium", "fpr": "Medium",
        "large_data": "Poor", "imbalanced": "class_weight param",
        "best_for": "High-dimensional sparse features",
    },
    "mlp": {
        "name": "Neural Network (MLP)",
        "speed": "Slow", "accuracy": "High", "fpr": "Medium",
        "large_data": "Good", "imbalanced": "Needs oversampling",
        "best_for": "Non-linear patterns, large datasets",
    },
    "isolation_forest": {
        "name": "Isolation Forest",
        "speed": "Fast", "accuracy": "Medium (unsupervised)", "fpr": "High if threshold not tuned",
        "large_data": "Good", "imbalanced": "N/A — no labels needed",
        "best_for": "No labeled anomalies available",
    },
}

METRIC_COMPARE: Dict[str, str] = {
    "precision": (
        "**Precision** = TP / (TP + FP)\n"
        "Of all events flagged as anomalies, what % were actual anomalies?\n"
        "→ High precision = few false alarms. Focus on this if alert fatigue is a problem."
    ),
    "recall": (
        "**Recall** = TP / (TP + FN)\n"
        "Of all real anomalies, what % did the model catch?\n"
        "→ High recall = few missed attacks. Critical for security where missing an attack is worse than a false alarm."
    ),
    "f1": (
        "**F1 Score** = 2 × (Precision × Recall) / (Precision + Recall)\n"
        "Harmonic mean — penalises extreme imbalance between precision and recall.\n"
        "→ Best single metric for imbalanced datasets (like anomaly detection)."
    ),
    "fpr": (
        "**FPR (False Positive Rate)** = FP / (FP + TN)\n"
        "Of all normal events, what % were wrongly flagged as anomalies?\n"
        "→ Keep this low to avoid alert fatigue. High FPR = analysts waste time on false alarms."
    ),
    "accuracy": (
        "**Accuracy** = (TP + TN) / Total\n"
        "% of all predictions that were correct.\n"
        "→ Misleading on imbalanced data! If 99% of events are normal, a model that predicts 'normal' for everything has 99% accuracy but catches no attacks."
    ),
}

def _word_match(text: str, keyword: str) -> bool:
    if len(keyword) <= 3:
        pattern = r'(?<![a-zA-Z])' + re.escape(keyword) + r'(?![a-zA-Z])'
        return bool(re.search(pattern, text))
    return keyword in text

def _score(q: str) -> Dict[str, int]:
    scores: Dict[str, int] = {}
    for intent_name, intent_def in INTENTS.items():
        total = 0
        for kw, weight in intent_def["keywords"].items():
            if _word_match(q, kw):
                total += weight
        if total >= intent_def["threshold"]:
            scores[intent_name] = total
    return scores

def _extract_entities(q: str) -> Dict[str, Any]:
    datasets, layers, metrics, algorithms = [], [], [], []

    for name in ("bgl", "cicids", "tda"):
        if name in q:
            datasets.append(name)
    if "blue gene" in q:
        datasets.append("bgl")
    if "cicids-2017" in q or "cicids 2017" in q:
        datasets.append("cicids")
    if "network flow" in q or "network traffic" in q:
        datasets.append("cicids")
    if "database access" in q or "transaction log" in q:
        datasets.append("tda")
    if "kernel log" in q or "system log" in q:
        datasets.append("bgl")

    for lyr in ("system", "network", "application"):
        if lyr in q:
            layers.append(lyr)

    for m in ("f1 score", "f1", "precision", "recall", "fpr",
              "false positive rate", "false negative", "accuracy", "auc"):
        if m in q:
            metrics.append(m)

    algo_map = {
        "random forest": "rf", "xgboost": "xgboost", "lgbm": "lgbm",
        "lightgbm": "lgbm", "isolation forest": "isolation_forest",
        "neural network": "mlp", "neural": "mlp", "svm": "svm", "mlp": "mlp",
    }
    for phrase, key in algo_map.items():
        if phrase in q:
            if key not in algorithms:
                algorithms.append(key)

    question_type = "other"
    for qt in ("why", "how", "what", "which", "compare", "difference", "is it"):
        if q.startswith(qt) or f" {qt} " in q:
            question_type = qt
            break

    return {
        "datasets": list(dict.fromkeys(datasets)),
        "layers": list(dict.fromkeys(layers)),
        "metrics": list(dict.fromkeys(metrics)),
        "algorithms": list(dict.fromkeys(algorithms)),
        "question_type": question_type,
    }

def _db_stats(db) -> Dict[str, Any]:
    from sqlalchemy import text

    row = db.execute(text("""
        SELECT (SELECT COUNT(1) FROM log_events)               AS total_logs,
               (SELECT COUNT(1) FROM log_events WHERE label=1) AS anomaly_logs,
               (SELECT COUNT(1) FROM incidents)                AS total_inc
    """)).fetchone()

    total_logs   = int(row[0] or 0)
    anomaly_logs = int(row[1] or 0)
    total_inc    = int(row[2] or 0)

    sev_rows = db.execute(text(
        "SELECT severity, COUNT(1) FROM incidents GROUP BY severity ORDER BY COUNT(1) DESC"
    )).fetchall()
    by_sev = {str(r[0] or "unknown"): r[1] for r in sev_rows}

    by_source: Dict[str, int] = {"BGL": 0, "CICIDS": 0, "TDA": 0}
    by_layer:  Dict[str, int] = {"system": 0, "network": 0, "application": 0}

    return {
        "total_logs":      total_logs,
        "anomaly_logs":    anomaly_logs,
        "normal_logs":     total_logs - anomaly_logs,
        "anomaly_pct":     round(anomaly_logs / total_logs * 100, 1) if total_logs else 0,
        "total_incidents": total_inc,
        "by_layer":        by_layer,
        "by_source":       by_source,
        "by_severity":     by_sev,
    }

def _answer_metrics(entities: Dict, stats: Optional[Dict]) -> str:
    asked = entities.get("metrics", [])
    lines = ["**ML Metric Reference**\n"]

    covered = set()
    for m in asked:
        key = m.replace(" rate", "").replace(" score", "").strip()
        if key in METRIC_COMPARE:
            lines.append(METRIC_COMPARE[key])
            covered.add(key)

    lines.append("\n**Quick reference:**")
    lines.append("| Metric | Formula | Focus |")
    lines.append("|--------|---------|-------|")
    lines.append("| Precision | TP/(TP+FP) | Minimise false alarms |")
    lines.append("| Recall    | TP/(TP+FN) | Catch every real attack |")
    lines.append("| F1 Score  | 2×P×R/(P+R)| Balanced single score |")
    lines.append("| FPR       | FP/(FP+TN) | Alert fatigue control |")
    lines.append("| Accuracy  | (TP+TN)/N  | ⚠ Misleading if imbalanced |")
    lines.append("\n**For security:** prioritise **Recall** (catch all threats) and **F1** (balance). "
                 "Keep **FPR** low to avoid overwhelming analysts.")
    return "\n".join(lines)

def _answer_anomaly(entities: Dict, stats: Optional[Dict]) -> str:
    ds = entities.get("datasets", [])
    lines = ["**Anomaly Detection Overview**\n"]

    if stats and stats["total_logs"] > 0:
        lines.append(
            f"**Live database:**\n"
            f"• Total events: {stats['total_logs']:,}\n"
            f"• Anomalous (label=1): {stats['anomaly_logs']:,} ({stats['anomaly_pct']}%)\n"
            f"• Normal (label=0): {stats['normal_logs']:,}\n"
        )
        if stats["by_layer"]:
            lines.append("**By layer:**")
            for lyr, cnt in stats["by_layer"].items():
                lines.append(f"  • {lyr}: {cnt:,} events")
    elif stats:
        lines.append("*No data ingested yet. Go to Analysis → Step 1.*\n")
    else:
        lines.append("Each log event gets a `label` (0 = normal, 1 = anomaly) during ingestion.")

    lines.append(
        "\n**How anomalies are detected:**\n"
        "1. **Ingestion** — CSV rows are labelled (BGL fault flags, CICIDS attack types, TDA access flags)\n"
        "2. **Training** — ML models learn the pattern of each layer's normal vs anomalous events\n"
        "3. **Scoring** — New events scored; high-probability anomalies flagged\n"
        "4. **Correlation** — Flagged events across layers grouped into incidents"
    )

    if "cicids" in ds or "network" in entities.get("layers", []):
        lines.append(
            "\n**CICIDS-2017 attacks include:** DoS, DDoS, PortScan, Brute Force, "
            "Web Attacks (SQLi, XSS), Botnet, Infiltration."
        )
    if "bgl" in ds or "system" in entities.get("layers", []):
        lines.append(
            "\n**BGL anomalies** = hardware/kernel faults: memory errors, node failures, I/O errors."
        )
    if "tda" in ds or "application" in entities.get("layers", []):
        lines.append(
            "\n**TDA anomalies** = suspicious database access: unusual query patterns, off-hours access."
        )
    return "\n".join(lines)

def _answer_incident(entities: Dict, stats: Optional[Dict]) -> str:
    lines = ["**Incident Management**\n"]
    if stats:
        total = stats["total_incidents"]
        sev_str = ", ".join(f"{k}: {v}" for k, v in stats["by_severity"].items()) or "none"
        lines.append(
            f"**Current incidents:** {total:,} total\n"
            f"**By severity:** {sev_str}\n"
        )
    lines.append(
        "**What is an incident?**\n"
        "A group of correlated anomalous events from the same entity across ≥2 layers "
        "within a time window. Single-layer anomalies may be false positives; "
        "multi-layer correlation is strong evidence of a real threat.\n\n"
        "**Severity rules:**\n"
        "• Critical — anomalies in all 3 layers, or high ML confidence\n"
        "• High — anomalies in 2 layers, significant event count\n"
        "• Medium — 2 layers, lower confidence\n"
        "• Low — 1 layer flagged but below threshold\n\n"
        "**Generation modes:**\n"
        "• **Cross-layer** — groups by entity + time window (fast, no model needed)\n"
        "• **ML-scored** — uses trained model probabilities (more precise)"
    )
    return "\n".join(lines)

def _answer_model(entities: Dict, stats: Optional[Dict]) -> str:
    asked_algos = entities.get("algorithms", [])
    lines = ["**Available ML Algorithms**\n"]
    lines.append(
        "| Algorithm | Speed | Accuracy | FPR | Best for |\n"
        "|-----------|-------|----------|-----|----------|\n"
        + "\n".join(
            f"| **{d['name']}** | {d['speed']} | {d['accuracy']} | {d['fpr']} | {d['best_for']} |"
            for d in ALGO_COMPARE.values()
        )
    )
    if asked_algos:
        lines.append("\n**Details on your algorithms:**")
        for a in asked_algos:
            d = ALGO_COMPARE.get(a, {})
            if d:
                lines.append(
                    f"\n**{d['name']}**\n"
                    f"• Speed: {d['speed']}\n"
                    f"• Imbalanced data handling: {d['imbalanced']}\n"
                    f"• Best for: {d['best_for']}"
                )
    lines.append(
        "\n**Recommendations:**\n"
        "• Start with **Random Forest** (robust, explainable)\n"
        "• Switch to **LightGBM** if training is slow on large CICIDS data\n"
        "• Use **XGBoost** for highest accuracy\n"
        "• Use **Isolation Forest** if you have no labeled anomalies"
    )
    return "\n".join(lines)

def _answer_reduce_fp(entities: Dict, stats: Optional[Dict]) -> str:
    return (
        "**How to Reduce False Positives**\n\n"
        "**1. Raise the probability threshold**\n"
        "In Generate ML incidents, increase `probability_threshold` (e.g. 0.7 instead of 0.5).\n"
        "Higher threshold = fewer but more confident alerts.\n\n"
        "**2. Choose a lower-FPR algorithm**\n"
        "XGBoost and LightGBM typically achieve lower FPR than Random Forest on security data.\n"
        "Switch algorithm in the Algorithm selector before retraining.\n\n"
        "**3. Increase min_layers requirement**\n"
        "Set `min_layers=3` — only create incidents when all 3 layers flag the same entity.\n"
        "This drastically cuts single-layer false positives.\n\n"
        "**4. Enable require_anomaly flag**\n"
        "In cross-layer generation, set `require_anomaly=true` to only correlate\n"
        "events already labelled as anomalies by the ML model.\n\n"
        "**5. Retrain with more data**\n"
        "More training examples (especially of normal events) give the model better\n"
        "decision boundaries. Re-ingest with a larger CSV if available.\n\n"
        "**Trade-off reminder:** Reducing FPR usually reduces Recall too (you catch fewer real attacks).\n"
        "Monitor both metrics together with the F1 score."
    )

def _answer_pipeline(entities: Dict, stats: Optional[Dict]) -> str:
    lines = ["**ML Analysis Pipeline — Step by Step**\n"]
    lines.append(
        "**Step 1 — Ingest**\n"
        "CSV files are read and stored in the database as `log_events`.\n"
        "Each event gets: timestamp, layer, source, entity, label (0/1), features (JSON).\n"
        "Supported: BGL (system), CICIDS-2017 (network), TDA (application).\n"
    )
    lines.append(
        "**Step 2 — Train**\n"
        "Per-layer models are trained on the ingested data:\n"
        "• 70% train / 15% validation / 15% test split\n"
        "• Metrics reported: precision, recall, F1, FPR, confusion matrix\n"
        "• Cross-layer model learns from combined feature vectors across all sources.\n"
    )
    lines.append(
        "**Step 3 — Generate Incidents**\n"
        "Two modes:\n"
        "• Cross-layer: entity + time-window grouping of anomalous events\n"
        "• ML-scored: model probability threshold scoring per source\n"
        "Results stored as incidents with severity, entity, and detection metadata.\n"
    )
    if stats and stats["total_logs"] > 0:
        src_str = ", ".join(f"{k}: {v:,}" for k, v in stats["by_source"].items())
        lines.append(
            f"**Current pipeline state:**\n"
            f"• Logs ingested: {stats['total_logs']:,} ({src_str})\n"
            f"• Incidents generated: {stats['total_incidents']:,}"
        )
    elif stats:
        lines.append("*Pipeline is empty — start with Step 1 to ingest data.*")
    return "\n".join(lines)

def _answer_layers(entities: Dict, stats: Optional[Dict]) -> str:
    asked = entities.get("layers", []) or entities.get("datasets", [])
    lines = ["**The Three Monitoring Layers**\n"]

    layer_info = {
        "system": (
            "**System layer** — BGL dataset\n"
            "Blue Gene/L supercomputer kernel and hardware logs.\n"
            "Detects: node failures, memory errors, I/O faults, kernel panics.\n"
            "Entity = node ID / host name."
        ),
        "network": (
            "**Network layer** — CICIDS-2017 dataset\n"
            "Network flow traffic (src/dst IP, ports, packet stats, duration).\n"
            "Detects: DoS, DDoS, PortScan, Brute Force, Web Attacks, Botnet.\n"
            "Entity = source IP address."
        ),
        "application": (
            "**Application layer** — TDA dataset\n"
            "Database access and transaction logs.\n"
            "Detects: unusual query patterns, suspicious access, privilege abuse, off-hours activity.\n"
            "Entity = user ID / session ID."
        ),
    }

    if asked:
        for lyr in asked:
            if lyr in layer_info:
                lines.append(layer_info[lyr])
        remaining = [l for l in layer_info if l not in asked]
        if remaining:
            lines.append("\n**Other layers (summary):**")
            for lyr in remaining:
                brief = layer_info[lyr].split("\n")[0]
                lines.append(f"• {brief}")
    else:
        for info in layer_info.values():
            lines.append(info + "\n")

    if stats and stats["by_layer"]:
        lines.append("\n**Live layer counts:**")
        for lyr, cnt in stats["by_layer"].items():
            anom = round(cnt * stats["anomaly_pct"] / 100) if stats["total_logs"] else 0
            lines.append(f"  • {lyr}: {cnt:,} events")

    lines.append(
        "\n**Cross-layer insight:** An entity (IP/host/user) appearing anomalously in 2-3 layers "
        "simultaneously is a strong indicator of a coordinated attack or system compromise."
    )
    return "\n".join(lines)

def _answer_cross_layer(entities: Dict, stats: Optional[Dict]) -> str:
    return (
        "**Cross-Layer Detection — How It Works**\n\n"
        "A single-layer anomaly has ~20-40% false positive rate. But if the **same entity** "
        "(IP, hostname, user) shows suspicious activity in 2 or 3 layers at the same time, "
        "confidence jumps to >90%.\n\n"
        "**Example attack scenario:**\n"
        "1. Network layer: IP 192.168.1.50 performs a port scan (CICIDS detects it)\n"
        "2. Application layer: same IP makes unusual DB queries 2 minutes later (TDA detects it)\n"
        "3. Cross-layer model correlates both → creates a Critical incident\n"
        "   → Likely: reconnaissance → exploitation attempt\n\n"
        "**Two correlation modes:**\n\n"
        "• **Time co-occurrence** *(recommended)*\n"
        "  Groups any multi-layer anomalies within the same time window (e.g. 24 hours).\n"
        "  Works even when entity IDs differ across datasets.\n\n"
        "• **Entity mode**\n"
        "  Groups events where the `entity` field exactly matches across layers.\n"
        "  Requires consistent entity naming (e.g. same IP format in all datasets).\n\n"
        "**Cross-layer model:**\n"
        "  Trains on combined feature vectors: count_*, burst_*, active_layers.\n"
        "  Learns which multi-layer co-occurrence patterns are truly malicious."
    )

def _answer_dataset(entities: Dict, stats: Optional[Dict]) -> str:
    from ..config import get_settings
    s = get_settings()
    lines = ["**Datasets Used in This Project**\n"]
    lines.append(
        f"• **BGL** (system layer)\n"
        f"  Path: `{s.BGL_PATH}`\n"
        f"  Blue Gene/L kernel logs. Label: 0=normal, 1=hardware fault.\n"
    )
    lines.append(
        f"• **CICIDS-2017** (network layer)\n"
        f"  Path: `{s.CICIDS_PATH}`\n"
        f"  Network flow traffic. Labels: 0=Benign, 1=Attack (15+ attack types).\n"
    )
    lines.append(
        f"• **TDA** (application layer)\n"
        f"  Path: `{s.TDA_PATH}`\n"
        f"  DB access logs. Label: 0=normal, 1=suspicious access.\n"
    )
    if stats and stats["total_logs"] > 0:
        lines.append("**Ingested so far:**")
        for src, cnt in stats["by_source"].items():
            lines.append(f"  • {src}: {cnt:,} events")
    elif stats:
        lines.append("*No data ingested yet. Go to Analysis → Step 1.*")
    return "\n".join(lines)

def _answer_stats(entities: Dict, stats: Optional[Dict]) -> str:
    if not stats:
        return (
            "I can show live statistics once data is ingested.\n"
            "Go to **Analysis → Step 1** to ingest your CSV files first."
        )
    if stats["total_logs"] == 0:
        return (
            "**The database is currently empty.**\n\n"
            "Go to **Analysis → Step 1** and click the Ingest buttons to load your CSV data.\n"
            "Supported datasets: BGL, CICIDS-2017, TDA."
        )
    sev_str = ", ".join(f"{k}: {v}" for k, v in stats["by_severity"].items()) or "none"
    layer_str = "\n".join(f"  • {k}: {v:,}" for k, v in stats["by_layer"].items())
    return (
        f"**System Overview (Live)**\n\n"
        f"**Log events:** {stats['total_logs']:,} total\n"
        f"  • Anomalies (label=1): {stats['anomaly_logs']:,} ({stats['anomaly_pct']}%)\n"
        f"  • Normal (label=0): {stats['normal_logs']:,}\n\n"
        f"**By layer:**\n{layer_str}\n\n"
        f"**Incidents:** {stats['total_incidents']:,} total\n"
        f"  • By severity: {sev_str}"
    )

def _answer_framing(framing_intent: str, entities: Dict, stats: Optional[Dict]) -> str:
    if framing_intent == "framing_high_fpr":
        return (
            "**High False Positive Rate — What It Means & How to Fix It**\n\n"
            "**Why it's a problem:**\n"
            "FPR = FP / (FP + TN) — the % of normal events wrongly flagged as threats.\n"
            "High FPR = analysts spend most of their time on false alarms → alert fatigue → real attacks get missed.\n\n"
            "**Common causes:**\n"
            "• Probability threshold too low (e.g. 0.3 flags too aggressively)\n"
            "• Imbalanced training data (too few normal examples)\n"
            "• Weak algorithm (SVM/MLP without proper tuning)\n"
            "• Features contain noise correlated with the positive class\n\n"
            "**Fixes (in order of impact):**\n"
            "1. Raise `probability_threshold` in Generate ML incidents (try 0.65–0.75)\n"
            "2. Switch to **XGBoost** or **LightGBM** — lower FPR than RF on security data\n"
            "3. Increase `min_layers` to 2 or 3 — require multi-layer confirmation\n"
            "4. Add more normal-event training samples\n"
            "5. Review features: remove timestamp-derived or entity-ID features\n\n"
            "**Trade-off:** Raising threshold reduces FPR but also reduces Recall. Monitor F1."
        )
    elif framing_intent == "framing_low_recall":
        return (
            "**Low Recall — Missing Real Attacks**\n\n"
            "**Why it's dangerous:**\n"
            "Recall = TP / (TP + FN) — the % of real anomalies your model catches.\n"
            "Low recall = attacks slip through undetected. In security, this is usually worse than false alarms.\n\n"
            "**Common causes:**\n"
            "• Probability threshold too high (model too conservative)\n"
            "• Insufficient training data for rare attack types\n"
            "• Class imbalance: model biased toward predicting 'normal'\n"
            "• Important features missing from feature engineering\n\n"
            "**Fixes:**\n"
            "1. Lower `probability_threshold` (try 0.35–0.45)\n"
            "2. Use `class_weight='balanced'` (Random Forest supports this)\n"
            "3. Try **Isolation Forest** — unsupervised, not biased by class imbalance\n"
            "4. Add SMOTE oversampling for rare attack types (requires scikit-imbalanced-learn)\n"
            "5. Check that anomaly labels in CSV are correct\n\n"
            "**Goal:** In most security systems, target Recall > 0.85 and tune FPR from there."
        )
    elif framing_intent == "framing_low_f1":
        return (
            "**Low F1 Score — Balancing Precision and Recall**\n\n"
            "F1 = 2 × Precision × Recall / (Precision + Recall)\n"
            "Low F1 means the model is failing on at least one of: catching attacks or avoiding false alarms.\n\n"
            "**Diagnose first:**\n"
            "• Is Precision low (high FPR)? → Too many false alarms → raise threshold\n"
            "• Is Recall low? → Missing attacks → lower threshold, check labels, rebalance\n"
            "• Both low? → Model is fundamentally wrong for the data → change algorithm\n\n"
            "**Steps to improve F1:**\n"
            "1. Check the confusion matrix — identify which class is failing\n"
            "2. Try **XGBoost** or **LightGBM** — consistently best F1 on tabular security data\n"
            "3. Tune `probability_threshold` using the validation set F1\n"
            "4. Ensure feature engineering captures the right signals\n"
            "5. If F1 < 0.5, check data quality — mislabeled events, missing features\n\n"
            "**Good F1 targets:** > 0.80 is good, > 0.90 is excellent for anomaly detection."
        )
    elif framing_intent == "framing_high_recall":
        return (
            "**High Recall — Maximising Attack Detection**\n\n"
            "Recall = TP / (TP + FN) — catching every real attack.\n\n"
            "**When to prioritise high Recall:**\n"
            "• You have SOC analysts who can handle false positives\n"
            "• Missing an attack is catastrophic (financial, regulatory, safety)\n"
            "• Initial deployment phase — cast wide net, tune precision later\n\n"
            "**How to maximise Recall:**\n"
            "1. Lower `probability_threshold` (0.3–0.4)\n"
            "2. Use `class_weight='balanced'` in training\n"
            "3. Prefer Isolation Forest for unknown attack types\n"
            "4. Set `min_layers=1` — generate incidents from single-layer anomalies too\n\n"
            "**Watch out:** Very high Recall (>0.97) usually comes with high FPR.\n"
            "Monitor analyst workload — alert fatigue leads to real threats being ignored."
        )
    return _answer_metrics(entities, stats)

def _answer_comparison(entities: Dict, scores: Dict[str, int]) -> str:
    algos   = entities.get("algorithms", [])
    metrics = entities.get("metrics", [])

    if len(algos) >= 2:
        a, b = algos[0], algos[1]
        da, db_ = ALGO_COMPARE.get(a, {}), ALGO_COMPARE.get(b, {})
        if da and db_:
            return (
                f"**{da['name']} vs {db_['name']}**\n\n"
                f"| Property | {da['name']} | {db_['name']} |\n"
                f"|----------|{'—'*len(da['name'])}|{'—'*len(db_['name'])}|\n"
                f"| Speed | {da['speed']} | {db_['speed']} |\n"
                f"| Accuracy | {da['accuracy']} | {db_['accuracy']} |\n"
                f"| FPR | {da['fpr']} | {db_['fpr']} |\n"
                f"| Large datasets | {da['large_data']} | {db_['large_data']} |\n"
                f"| Imbalanced data | {da['imbalanced']} | {db_['imbalanced']} |\n"
                f"| Best for | {da['best_for']} | {db_['best_for']} |\n\n"
                f"**Recommendation:** "
                + (f"Use {db_['name']} if speed matters on large data, {da['name']} for interpretability."
                   if a == "rf" and b in ("lgbm", "xgboost") else
                   f"Both are strong — try both and compare F1 on your validation set.")
            )

    if len(metrics) >= 2:
        m_a, m_b = metrics[0], metrics[1]
        ka = m_a.replace(" rate", "").replace(" score", "").strip()
        kb = m_b.replace(" rate", "").replace(" score", "").strip()
        block_a = METRIC_COMPARE.get(ka, f"**{m_a}**: no detail available")
        block_b = METRIC_COMPARE.get(kb, f"**{m_b}**: no detail available")
        return (
            f"**{m_a.title()} vs {m_b.title()}**\n\n"
            f"{block_a}\n\n---\n\n{block_b}\n\n"
            "**Key insight:** Precision and Recall trade off against each other. "
            "F1 is the best single metric when both matter equally."
        )

    return (
        "**Algorithm Comparison — All Models**\n\n"
        "| Algorithm | Speed | Accuracy | FPR | Best for |\n"
        "|-----------|-------|----------|-----|----------|\n"
        + "\n".join(
            f"| **{d['name']}** | {d['speed']} | {d['accuracy']} | {d['fpr']} | {d['best_for']} |"
            for d in ALGO_COMPARE.values()
        )
        + "\n\n**Metric comparison:**\n\n"
        + "\n\n".join(METRIC_COMPARE.values())
    )

def _dispatch(intent: str, entities: Dict, stats: Optional[Dict], scores: Dict) -> str:
    dispatch_map = {
        "metrics":      lambda: _answer_metrics(entities, stats),
        "anomaly":      lambda: _answer_anomaly(entities, stats),
        "incident":     lambda: _answer_incident(entities, stats),
        "model":        lambda: _answer_model(entities, stats),
        "reduce_fp":    lambda: _answer_reduce_fp(entities, stats),
        "pipeline":     lambda: _answer_pipeline(entities, stats),
        "layers":       lambda: _answer_layers(entities, stats),
        "cross_layer":  lambda: _answer_cross_layer(entities, stats),
        "dataset":      lambda: _answer_dataset(entities, stats),
        "stats":        lambda: _answer_stats(entities, stats),
        "compare":      lambda: _answer_comparison(entities, scores),
    }
    if intent.startswith("framing_"):
        return _answer_framing(intent, entities, stats)
    fn = dispatch_map.get(intent)
    return fn() if fn else ""

def _generic_fallback(question: str, scored: List[Tuple[str, int]]) -> str:
    hints = "\n".join(
        f"• Ask about **{name.replace('_', ' ')}** (I have detailed knowledge on this)"
        for name, _ in scored[:4]
    ) if scored else (
        "• ML metrics (precision, recall, F1, FPR)\n"
        "• Anomaly detection and datasets\n"
        "• Algorithms and model comparison\n"
        "• Pipeline workflow\n"
        "• How to reduce false positives"
    )
    return (
        f"I'm not sure exactly what you meant by: *\"{question[:80]}\"*\n\n"
        f"Here are some related topics I can help with:\n{hints}\n\n"
        "Try rephrasing, e.g.:\n"
        "• \"What does a high false positive rate mean?\"\n"
        "• \"Compare XGBoost vs LightGBM\"\n"
        "• \"How many anomalies are in the database?\"\n"
        "• \"How does cross-layer correlation work?\""
    )

def answer(question: str, db=None) -> str:
    q = question.lower().strip()

    scores = _score(q)

    entities = _extract_entities(q)

    needs_db = any(INTENTS[n].get("db_needed") for n in scores if n in INTENTS)
    stats: Optional[Dict] = None
    if db and needs_db:
        try:
            stats = _db_stats(db)
        except Exception:
            stats = None

    ranked = sorted(scores.items(), key=lambda x: -x[1])

    if not ranked:
        return _generic_fallback(question, [])

    framing = [n for n, _ in ranked if INTENTS.get(n, {}).get("framing")]
    if framing:
        return _answer_framing(framing[0], entities, stats)

    if "compare" in scores:
        return _answer_comparison(entities, scores)

    top_name, top_score = ranked[0]
    if top_score >= TOP_THRESHOLD or len(ranked) == 1:
        return _dispatch(top_name, entities, stats, scores)

    active = [(n, s) for n, s in ranked if s >= COMBINE_THRESHOLD][:MAX_COMBINED]

    intent_names = [n for n, _ in active]
    if "anomaly" in intent_names and "stats" in intent_names:
        active = [(n, s) for n, s in active if n != "stats"]

    if len(active) == 1:
        return _dispatch(active[0][0], entities, stats, scores)

    parts = [_dispatch(n, entities, stats, scores) for n, _ in active]
    separator = "\n\n" + "─" * 40 + "\n\n"
    header = "**Covering: " + " + ".join(n.replace("_", " ") for n, _ in active) + "**\n\n"
    return header + separator.join(p for p in parts if p)
