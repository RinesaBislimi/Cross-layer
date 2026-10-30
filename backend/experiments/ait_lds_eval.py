"""End-to-end cross-layer evaluation on AIT Log Data Set V2 (answers R4's main request).

AIT-LDS v2 (Landauer et al., IEEE TDSC 2023; Zenodo 5789064) records, for a
simulated enterprise network, the logs of EVERY host over 4-6 days with a
scripted multi-step attack (scan -> web exploit -> credential theft -> login ->
privilege escalation / exfiltration) on the last day, and ships line-level
ground truth. The three layers of our pipeline are therefore GENUINELY LINKED:
the same attacker IP appears in Suricata / DNS logs (network), in auth.log and
syslog (system) and in Apache access logs (application).

Pipeline (mirrors Sections 4-6 of the paper):
  1. Parse one scenario zip: gather/<host>/logs/** with labels/<host>/logs/**
     (label files are JSON lines {"line": n, "labels": [...], "rules": {...}}).
  2. Map log files to layers:
        network     suricata fast.log / eve.json, dnsmasq.log
        system      auth.log, syslog, audit/audit.log
        application apache2 *access*.log, error.log, horde/exim logs
  3. Per line: timestamp, layer, canonical entity (first IPv4 in the line, else
     host), ten lexical features + per-layer numerics (status code, bytes,
     message length), label = 1 iff the line number appears in the label file.
  4. Per-layer detectors (LightGBM) under (a) stratified 70/15/15 and
     (b) a strict temporal split (train on everything before the attack day).
  5. Correlation (Algorithm 1, reference implementation from
     correlation_eval.py) over the per-layer alerts (predicted positives);
     ground truth incident = attack-labelled events sharing the attacker entity
     inside the attack window. Reports alerts before/after, whether the attack
     chain is reconstructed (layers covered), false correlations, incident P/R.

Usage:  python experiments/ait_lds_eval.py <scenario.zip> [--max-lines-per-file N]
Output: results/ait_lds_results.json
"""
from __future__ import annotations

import io
import json
import logging
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from correlation_eval import Event, correlate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("ait")
RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
LAYER_OF = [
    (re.compile(r"suricata/(fast\.log|eve\.json)$|dnsmasq\.log$|/vpn/|openvpn"), "network"),
    (re.compile(r"auth\.log$|syslog$|audit/audit\.log$|/kern\.log$"), "system"),
    (re.compile(r"apache2/.*access.*\.log$|apache2/.*error.*\.log$|horde|exim4/mainlog$"), "application"),
]
KW = ["error", "fail", "denied", "invalid", "refused", "unauthorized", "exploit", "shell",
      "sudo", "root", "scan", "alert", "attack", "404", "500", "post"]

# timestamp patterns seen in AIT-LDS v2 log families
TS_PATTERNS = [
    (re.compile(r"^(\d{2}/\d{2}/\d{4}-\d{2}:\d{2}:\d{2})"), "%m/%d/%Y-%H:%M:%S"),          # suricata fast
    (re.compile(r"\"timestamp\":\s*\"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"), "%Y-%m-%dT%H:%M:%S"),  # eve.json
    (re.compile(r"\[(\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2})"), "%d/%b/%Y:%H:%M:%S"),      # apache
    (re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"), "%Y-%m-%dT%H:%M:%S"),             # iso syslog
    (re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2} \d{2}:\d{2}:\d{2})"), "%b %d %H:%M:%S"),           # classic syslog
    (re.compile(r"\[[A-Za-z]{3} ([A-Za-z]{3} \d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)? \d{4})\]"), "%b %d %H:%M:%S %Y"),  # apache error
    (re.compile(r"msg=audit\((\d+)\."), "epoch"),                                                # audit
]


def parse_ts(line: str, year_hint: int) -> Optional[datetime]:
    for rx, fmt in TS_PATTERNS:
        m = rx.search(line)
        if not m:
            continue
        s = m.group(1)
        try:
            if fmt == "epoch":
                return datetime.utcfromtimestamp(int(s))
            s2 = re.sub(r"\.\d+", "", s)
            dt = datetime.strptime(s2, fmt.replace("%b %d %H:%M:%S %Y", "%b %d %H:%M:%S %Y"))
            if fmt == "%b %d %H:%M:%S":
                dt = dt.replace(year=year_hint)
            return dt
        except ValueError:
            continue
    return None


def layer_of(path: str) -> Optional[str]:
    for rx, layer in LAYER_OF:
        if rx.search(path):
            return layer
    return None


def featurize(line: str, layer: str) -> List[float]:
    low = line.lower()
    f = [len(line), line.count(" ")] + [int(k in low) for k in KW]
    status = re.search(r'" (\d{3}) (\d+|-)', line)             # apache: "GET ... HTTP/1.1" 200 1234
    f += [int(status.group(1)) if status else 0,
          int(status.group(2)) if status and status.group(2).isdigit() else 0]
    f += [len(IPV4.findall(line)), int("application" == layer), int("system" == layer)]
    return f


FEAT_NAMES = ["len", "spaces"] + [f"kw_{k}" for k in KW] + ["http_status", "bytes", "n_ips", "is_app", "is_sys"]


def load_scenario(zip_path: Path, max_lines_per_file: int) -> Tuple[pd.DataFrame, Dict]:
    z = zipfile.ZipFile(zip_path)
    names = z.namelist()
    root = names[0].split("/")[0]
    gather = [n for n in names if f"{root}/gather/" in n and "/logs/" in n and not n.endswith("/")]
    label_set = set(n for n in names if f"{root}/labels/" in n)
    meta = {"scenario": root, "files_total": len(gather), "files_used": []}
    try:
        ds_yml = z.read(f"{root}/dataset.yml").decode("utf8", "ignore")
        meta["dataset_yml"] = ds_yml[:600]
        yrs = re.findall(r"(\d{4})-\d{2}-\d{2}", ds_yml)
        year_hint = int(yrs[0]) if yrs else 2022
    except KeyError:
        year_hint = 2022

    rows = []
    for n in gather:
        layer = layer_of(n)
        if layer is None:
            continue
        host = n.split("/gather/")[1].split("/")[0]
        lbl_name = n.replace("/gather/", "/labels/")
        labelled_lines: Dict[int, List[str]] = {}
        if lbl_name in label_set:
            for raw in z.read(lbl_name).decode("utf8", "ignore").splitlines():
                try:
                    j = json.loads(raw)
                    labelled_lines[int(j["line"])] = j.get("labels", [])
                except Exception:  # noqa: BLE001
                    pass
        data = z.read(n)
        if n.endswith(".gz"):
            import gzip
            data = gzip.decompress(data)
        text = data.decode("utf8", "ignore")
        n_lines = 0
        kept = 0
        for i, line in enumerate(text.splitlines(), start=1):
            n_lines += 1
            is_attack = i in labelled_lines
            # keep every attack line; subsample benign lines uniformly
            if not is_attack and kept >= max_lines_per_file:
                continue
            ts = parse_ts(line, year_hint)
            if ts is None:
                continue
            ips = IPV4.findall(line)
            entity = f"ip:{ips[0]}" if ips else f"host:{host}"
            rows.append({"ts": ts, "layer": layer, "host": host, "file": n.split("/logs/")[1],
                         "entity": entity, "y": int(is_attack),
                         "attack_labels": ",".join(labelled_lines.get(i, [])),
                         **dict(zip(FEAT_NAMES, featurize(line, layer)))})
            kept += 1
        meta["files_used"].append({"file": n.split(f"{root}/gather/")[1], "layer": layer,
                                   "lines": n_lines, "kept": kept, "attack_lines": len(labelled_lines)})
        log.info("%-60s %-11s lines=%-8d kept=%-7d attack=%d", n.split(f"{root}/gather/")[1], layer,
                 n_lines, kept, len(labelled_lines))
    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    return df, meta


def per_layer_detection(df: pd.DataFrame, attack_day: datetime.date) -> Dict:
    out = {}
    for layer in ["network", "system", "application"]:
        d = df[df.layer == layer]
        if d.empty or d.y.sum() < 5:
            out[layer] = {"note": "insufficient attack-labelled lines", "n": int(len(d)), "n_attack": int(d.y.sum())}
            continue
        X = d[FEAT_NAMES].to_numpy("float64"); y = d.y.to_numpy()
        res = {"n": int(len(d)), "n_attack": int(y.sum())}
        # (a) stratified random
        tr, te = train_test_split(np.arange(len(y)), test_size=0.30, random_state=42, stratify=y)
        m = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8, random_state=42,
                               verbose=-1, n_jobs=-1).fit(X[tr], y[tr])
        p = m.predict(X[te]); pr = m.predict_proba(X[te])[:, 1]
        res["random"] = {"precision": round(float(precision_score(y[te], p, zero_division=0)), 4),
                         "recall": round(float(recall_score(y[te], p, zero_division=0)), 4),
                         "f1": round(float(f1_score(y[te], p, zero_division=0)), 4),
                         "roc_auc": round(float(roc_auc_score(y[te], pr)), 4)}
        # (b) temporal: train strictly before the attack day (benign only) -> unsupervised fallback
        before = d.ts.dt.date < attack_day
        if y[before.to_numpy()].sum() == 0:
            from sklearn.ensemble import IsolationForest
            iso = IsolationForest(n_estimators=100, contamination=0.01, random_state=42, n_jobs=-1)
            iso.fit(X[before.to_numpy()])
            te_mask = ~before.to_numpy()
            p = (iso.predict(X[te_mask]) == -1).astype(int); sc = -iso.score_samples(X[te_mask])
            res["temporal_unsupervised"] = {
                "note": "no attack lines before the attack day: Isolation Forest trained on pre-attack days",
                "precision": round(float(precision_score(y[te_mask], p, zero_division=0)), 4),
                "recall": round(float(recall_score(y[te_mask], p, zero_division=0)), 4),
                "f1": round(float(f1_score(y[te_mask], p, zero_division=0)), 4),
                "roc_auc": round(float(roc_auc_score(y[te_mask], sc)), 4) if len(np.unique(y[te_mask])) > 1 else None}
        out[layer] = res
        log.info("%s: %s", layer, res)
    return out


def correlation_on_alerts(df: pd.DataFrame, attack_start: datetime, attack_end: datetime,
                          window_s: float = 60.0) -> Dict:
    """Run Algorithm 1 over the per-layer alerts of a detector trained per layer
    (stratified split, predictions on the WHOLE layer via 5-fold out-of-fold)."""
    from sklearn.model_selection import StratifiedKFold
    alerts: List[Event] = []
    is_attack: List[int] = []
    for layer in ["network", "system", "application"]:
        d = df[df.layer == layer]
        if d.empty or d.y.sum() < 5:
            continue
        X = d[FEAT_NAMES].to_numpy("float64"); y = d.y.to_numpy()
        oof = np.zeros(len(y));
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=42).split(X, y):
            m = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8, random_state=42,
                                   verbose=-1, n_jobs=-1).fit(X[tr], y[tr])
            oof[te] = m.predict_proba(X[te])[:, 1]
        for (ts, ent, yy), sc in zip(d[["ts", "entity", "y"]].itertuples(index=False), oof):
            if sc >= 0.5:
                alerts.append(Event(ts.to_pydatetime(), layer, ent, float(sc), gid=(0 if yy == 1 else None)))
                is_attack.append(int(yy))
    n_alerts = len(alerts)
    n_attack_alerts = int(sum(is_attack))
    incidents = correlate(alerts, window_s=window_s, enforce_order=True)
    inc_rows = []
    for inc in incidents:
        ev = [alerts[i] for i in inc]
        attack_frac = float(np.mean([e.gid == 0 for e in ev]))
        layers = sorted({e.layer for e in ev})
        t0, t1 = min(e.t for e in ev), max(e.t for e in ev)
        in_window = attack_start - timedelta(minutes=5) <= t0 <= attack_end + timedelta(minutes=5)
        inc_rows.append({"entity": ev[0].entity, "layers": layers, "n": len(ev),
                         "attack_fraction": round(attack_frac, 3), "start": t0.isoformat(),
                         "end": t1.isoformat(), "in_attack_window": bool(in_window)})
    true_inc = [r for r in inc_rows if r["attack_fraction"] >= 0.5]
    false_inc = [r for r in inc_rows if r["attack_fraction"] < 0.5]
    attacker_layers = sorted(set(l for r in true_inc for l in r["layers"]))
    attack_alert_covered = 0
    covered = set()
    for inc in incidents:
        for i in inc:
            if alerts[i].gid == 0:
                covered.add(i)
    attack_alert_covered = len(covered)
    return {
        "window_s": window_s,
        "alerts_before": n_alerts, "attack_alerts": n_attack_alerts,
        "incidents_after": len(incidents),
        "reduction_ratio": round(1 - len(incidents) / n_alerts, 4) if n_alerts else None,
        "true_incidents": len(true_inc), "false_correlations": len(false_inc),
        "incident_precision": round(len(true_inc) / len(incidents), 4) if incidents else None,
        "attack_alert_recall": round(attack_alert_covered / n_attack_alerts, 4) if n_attack_alerts else None,
        "attack_chain_layers_reconstructed": attacker_layers,
        "multi_stage_attack_reconstructed": len(attacker_layers) >= 2,
        "incidents": sorted(inc_rows, key=lambda r: -r["n"])[:25],
    }


def main():
    zip_path = Path(sys.argv[1])
    max_lines = int(sys.argv[sys.argv.index("--max-lines-per-file") + 1]) if "--max-lines-per-file" in sys.argv else 60_000
    df, meta = load_scenario(zip_path, max_lines)
    # attack window from dataset.yml if present, else from labelled lines
    att = df[df.y == 1]
    attack_start, attack_end = att.ts.min().to_pydatetime(), att.ts.max().to_pydatetime()
    meta.update({"rows": int(len(df)), "rows_per_layer": df.layer.value_counts().to_dict(),
                 "attack_rows_per_layer": df[df.y == 1].layer.value_counts().to_dict(),
                 "attack_window": [attack_start.isoformat(), attack_end.isoformat()],
                 "attack_labels": Counter(l for s in att.attack_labels for l in s.split(",") if l).most_common(20),
                 "distinct_entities": int(df.entity.nunique()),
                 "entities_in_2plus_layers": int((df.groupby("entity").layer.nunique() >= 2).sum())})
    out = {"meta": meta}
    out["per_layer"] = per_layer_detection(df, attack_start.date())
    out["correlation"] = {}
    for W in [30, 60, 300]:
        out["correlation"][f"W={W}"] = correlation_on_alerts(df, attack_start, attack_end, window_s=float(W))
        log.info("W=%s -> %s", W, {k: v for k, v in out["correlation"][f"W={W}"].items() if k != "incidents"})
    (RESULTS / "ait_lds_results.json").write_text(json.dumps(out, indent=2, default=str))
    log.info("DONE -> %s", RESULTS / "ait_lds_results.json")


if __name__ == "__main__":
    main()
