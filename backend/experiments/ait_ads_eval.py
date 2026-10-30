"""Cross-layer correlation on GENUINELY LINKED alerts: AIT Alert Data Set (AIT-ADS).

AIT-ADS (Landauer et al., CSET 2024; Zenodo 8263181) contains the alerts that
three IDSs - Suricata (network traffic), Wazuh (host rules on auth/syslog/web/
mail logs) and AMiner (log anomaly detection) - raise on the eight AIT-LDS v2
enterprise testbeds, in which every host is logged simultaneously while a
scripted multi-step attack (scans -> WordPress/dirb -> webshell -> cracking ->
reverse shell -> privilege escalation -> service stop / DNS exfiltration) runs.
Labels are attack-phase time intervals per scenario.

This is exactly the input of our correlation engine (per-layer alerts with
timestamp, layer, identifiers, score) with the three layers captured on the SAME
hosts, so it answers Reviewer 4's main request on real data without the 7-26 GB
raw log download.

Layer mapping (deterministic, from the IDS and the Wazuh rule groups / AMiner
log source):
  network      Suricata alerts (any IDS: rule group 'ids', 'suricata', 'firewall', 'dns')
  system       Wazuh/AMiner on auth.log, syslog, audit, sshd, pam, sudo, systemd,
               rootcheck, syscheck, ossec
  application  Wazuh/AMiner on apache/web/wordpress/exim/horde/mail/php

Entity: the attacker/target IP found in the alert (srcip, dstip, or the first
IPv4 in the raw log), else the agent host. Score: Wazuh rule level / 15,
Suricata severity mapped to [0.5, 1], AMiner 0.7.

Evaluation per scenario (then mean +/- SD over the eight scenarios):
  alerts_before, incidents_after, reduction, incident precision (incidents
  whose alerts are majority attack-labelled), attack-alert recall (attack
  alerts absorbed into some multi-layer incident), the number of attack phases
  and layers covered by the best attacker incident, false correlations, and a
  sweep over W. Also a leave-one-scenario-out second-stage classifier.

Usage: python experiments/ait_ads_eval.py <dir containing ait_ads.zip and labels.csv>
"""
from __future__ import annotations

import io
import json
import logging
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from correlation_eval import Event, correlate_fast as correlate, LAYER_ORDER  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("ait_ads")
RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SYS_KW = ("auth", "sshd", "pam", "sudo", "syslog", "audit", "systemd", "rootcheck", "syscheck",
          "ossec", "login", "authentication", "kernel", "cron", "user", "account")
APP_KW = ("apache", "web", "wordpress", "exim", "horde", "mail", "php", "http", "attack", "sql",
          "xss", "webshell", "dovecot", "roundcube", "cms")
NET_KW = ("suricata", "ids", "firewall", "dns", "dnsmasq", "openvpn", "vpn", "netflow", "network")


def _get(d: dict, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _ts(v) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v), tz=timezone.utc).replace(tzinfo=None)
    s = str(v).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    if s.isdigit():
        return datetime.fromtimestamp(int(s), tz=timezone.utc).replace(tzinfo=None)
    return None


def layer_from_text(txt: str, ids: str) -> str:
    t = txt.lower()
    if ids == "suricata" or any(k in t for k in ("suricata", "ids alert", "eve.json")):
        return "network"
    if any(k in t for k in APP_KW):
        return "application"
    if any(k in t for k in SYS_KW):
        return "system"
    if any(k in t for k in NET_KW):
        return "network"
    return "system"


def parse_wazuh(obj: dict) -> Optional[dict]:
    src = obj.get("_source", obj)
    ts = _ts(src.get("timestamp") or src.get("@timestamp"))
    if ts is None:
        return None
    rule = src.get("rule", {}) or {}
    groups = " ".join(rule.get("groups", []) or [])
    desc = str(rule.get("description", ""))
    location = str(src.get("location", ""))
    data = src.get("data", {}) or {}
    full = str(src.get("full_log", ""))
    is_suricata = "suricata" in groups.lower() or "suricata" in location.lower() or "alert" in data and isinstance(data.get("alert"), dict)
    ids = "suricata" if is_suricata else "wazuh"
    layer = layer_from_text(" ".join([groups, location, desc]), ids)
    ips = [v for v in (data.get("srcip"), data.get("src_ip"), data.get("dstip"), data.get("dest_ip"))
           if isinstance(v, str) and IPV4.fullmatch(v)]
    if not ips:
        ips = IPV4.findall(full) or IPV4.findall(desc)
    agent = _get(src, "agent", "name", default="") or ""
    agent_ip = _get(src, "agent", "ip", default="") or ""
    entity = f"ip:{ips[0]}" if ips else (f"ip:{agent_ip}" if agent_ip else f"host:{agent}")
    level = rule.get("level", 5)
    try:
        score = min(1.0, max(0.1, float(level) / 15.0))
    except (TypeError, ValueError):
        score = 0.5
    if ids == "suricata":
        sev = _get(data, "alert", "severity", default=2)
        try:
            score = {1: 1.0, 2: 0.75, 3: 0.5}.get(int(sev), 0.6)
        except (TypeError, ValueError):
            score = 0.6
    return {"t": ts, "ids": ids, "layer": layer, "entity": entity, "host": agent,
            "score": score, "name": desc[:80], "all_ips": ips}


def parse_aminer(obj: dict) -> Optional[dict]:
    ld = obj.get("LogData", {}) or {}
    tss = ld.get("Timestamps") or []
    ts = _ts(tss[0]) if tss else _ts(obj.get("timestamp"))
    if ts is None:
        return None
    raw = " ".join(str(x) for x in (ld.get("RawLogData") or [])[:3])
    res = " ".join(str(x) for x in (ld.get("LogResources") or []))
    comp = str(_get(obj, "AnalysisComponent", "AnalysisComponentName", default=""))
    layer = layer_from_text(" ".join([res, raw[:200], comp]), "aminer")
    ips = IPV4.findall(raw)
    host = re.search(r"/([a-z0-9_]+)/", res)
    entity = f"ip:{ips[0]}" if ips else f"host:{host.group(1) if host else 'aminer'}"
    return {"t": ts, "ids": "aminer", "layer": layer, "entity": entity,
            "host": host.group(1) if host else "", "score": 0.7, "name": comp[:80], "all_ips": ips}


def load_json_any(raw: bytes) -> List[dict]:
    txt = raw.decode("utf8", "ignore").strip()
    if not txt:
        return []
    if txt[0] == "[":
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            pass
    out = []
    for line in txt.splitlines():
        line = line.strip().rstrip(",")
        if not line or line in ("[", "]"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_labels(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    # expected columns like: scenario, phase/label, start, end (epoch or iso)
    scol = next(c for c in df.columns if "scen" in c or "dataset" in c or c == "name")
    pcol = next(c for c in df.columns if "phase" in c or "label" in c or "step" in c or "attack" in c)
    st = next(c for c in df.columns if c.startswith("start") or c == "from" or c == "begin")
    en = next(c for c in df.columns if c.startswith("end") or c == "to" or c == "stop")
    df = df.rename(columns={scol: "scenario", pcol: "phase", st: "start", en: "end"})
    df["start"] = df["start"].map(_ts); df["end"] = df["end"].map(_ts)
    return df[["scenario", "phase", "start", "end"]].dropna()


def label_alert(t: datetime, phases: pd.DataFrame) -> Optional[str]:
    m = phases[(phases.start <= t) & (t <= phases.end)]
    return None if m.empty else str(m.iloc[0]["phase"])


def evaluate_scenario(name: str, alerts: List[dict], phases: pd.DataFrame, Ws=(30, 60, 300)) -> Dict:
    # vectorised interval labelling (phases are consecutive, non-overlapping)
    ph = phases.sort_values("start")
    starts = np.array([x.timestamp() for x in ph["start"]]); ends = np.array([x.timestamp() for x in ph["end"]])
    names = ph["phase"].astype(str).to_numpy()
    ts = np.array([a["t"].replace(tzinfo=timezone.utc).timestamp() for a in alerts])
    idx = np.searchsorted(starts, ts, side="right") - 1
    for a, i, t in zip(alerts, idx, ts):
        hit = i >= 0 and t <= ends[i]
        a["phase"] = names[i] if hit else None
        a["y"] = int(hit and "false_positive" not in names[i])
    attack_ips = Counter(ip for a in alerts if a["y"] for ip in a["all_ips"])
    attacker = attack_ips.most_common(1)[0][0] if attack_ips else None
    events = [Event(a["t"], a["layer"], a["entity"], a["score"], gid=(0 if a["y"] else None)) for a in alerts]
    n_attack = sum(a["y"] for a in alerts)
    res = {"scenario": name, "alerts": len(alerts), "attack_alerts": n_attack,
           "alerts_per_layer": Counter(a["layer"] for a in alerts),
           "attack_alerts_per_layer": Counter(a["layer"] for a in alerts if a["y"]),
           "alerts_per_ids": Counter(a["ids"] for a in alerts),
           "attack_phases": sorted(set(a["phase"] for a in alerts if a["y"])),
           "attacker_ip": attacker, "windows": {}}
    for W, enforce in [(W, e) for W in Ws for e in (False, True)]:
        # On real IDS streams the network and application detectors fire in an
        # interleaved order, so the strict outside-in constraint is reported as an
        # ablation ("W=..,order") and the unordered variant is the primary result.
        incidents = correlate(events, window_s=float(W), enforce_order=enforce)
        rows = []
        covered = set()
        for inc in incidents:
            ev = [alerts[i] for i in inc]
            frac = float(np.mean([e["y"] for e in ev]))
            layers = sorted({e["layer"] for e in ev})
            ph = sorted({e["phase"] for e in ev if e["y"]})
            rows.append({"entity": ev[0]["entity"], "n": len(ev), "layers": layers,
                         "attack_fraction": round(frac, 3), "phases": ph,
                         "start": min(e["t"] for e in ev).isoformat()})
            if frac >= 0.5:
                covered.update(i for i in inc if alerts[i]["y"])
        true_inc = [r for r in rows if r["attack_fraction"] >= 0.5]
        false_inc = [r for r in rows if r["attack_fraction"] < 0.5]
        best = max(true_inc, key=lambda r: (len(r["phases"]), len(r["layers"]), r["n"]), default=None)
        key = f"W={W}" + (",order" if enforce else "")
        res["windows"][key] = {
            "layer_order_enforced": enforce,
            "incidents_after": len(incidents),
            "reduction_ratio": round(1 - len(incidents) / len(alerts), 4) if alerts else None,
            "true_incidents": len(true_inc), "false_correlations": len(false_inc),
            "incident_precision": round(len(true_inc) / len(incidents), 4) if incidents else None,
            "attack_alert_recall": round(len(covered) / n_attack, 4) if n_attack else None,
            "best_attack_incident": best,
            "max_layers_in_attack_incident": max((len(r["layers"]) for r in true_inc), default=0),
            "max_phases_in_attack_incident": max((len(r["phases"]) for r in true_inc), default=0),
            "attack_incidents_multilayer": sum(1 for r in true_inc if len(r["layers"]) >= 2),
        }
        w = res["windows"][key]
        log.info("%-15s %-12s alerts=%-7d inc=%-5d P=%.3f R=%.3f layers=%d phases=%d FP=%d",
                 name, key, len(alerts), len(incidents), w["incident_precision"] or 0,
                 w["attack_alert_recall"] or 0, w["max_layers_in_attack_incident"],
                 w["max_phases_in_attack_incident"], w["false_correlations"])
    return res


def candidate_features(alerts: List[dict], W: float) -> Tuple[np.ndarray, np.ndarray]:
    events = [Event(a["t"], a["layer"], a["entity"], a["score"]) for a in alerts]
    cands = correlate(events, window_s=W, enforce_order=False, min_layers=1)
    X, y = [], []
    for c in cands:
        ev = [alerts[i] for i in c]
        cnt = Counter(e["layer"] for e in ev)
        evs = sorted(ev, key=lambda e: e["t"])
        orders = [LAYER_ORDER[e["layer"]] for e in evs]
        X.append([cnt["network"], cnt["system"], cnt["application"], len(cnt),
                  (evs[-1]["t"] - evs[0]["t"]).total_seconds(),
                  max(e["score"] for e in ev), float(np.mean([e["score"] for e in ev])),
                  int(all(a <= b for a, b in zip(orders, orders[1:])))])
        y.append(int(np.mean([e["y"] for e in ev]) >= 0.5))
    return np.array(X, float), np.array(y, int)


def main(data_dir: str):
    d = Path(data_dir)
    z = zipfile.ZipFile(d / "ait_ads.zip")
    labels = load_labels(d / "labels.csv")
    scen_files: Dict[str, List[str]] = defaultdict(list)
    for n in z.namelist():
        if n.endswith("/") or not n.lower().endswith(".json"):
            continue
        base = Path(n).name
        scen = base.split("_")[0]
        scen_files[scen].append(n)
    out = {"scenarios": {}, "label_columns": list(labels.columns), "n_label_rows": int(len(labels))}
    per_scen_alerts: Dict[str, List[dict]] = {}
    for scen, files in sorted(scen_files.items()):
        phases = labels[labels.scenario.astype(str).str.lower() == scen.lower()]
        alerts: List[dict] = []
        for n in files:
            parser = parse_aminer if "aminer" in n.lower() else parse_wazuh
            n_in = 0
            with z.open(n) as fh:
                first = fh.read(1)
            if first == b"[":                       # small JSON array (AMiner)
                objs = load_json_any(z.read(n))
                for o in objs:
                    a = parser(o)
                    if a:
                        alerts.append(a)
                    n_in += 1
            else:                                   # JSON lines: stream, keep compact dicts only
                with z.open(n) as fh:
                    for raw in io.TextIOWrapper(fh, encoding="utf8", errors="ignore"):
                        line = raw.strip().rstrip(",")
                        if not line or line in ("[", "]"):
                            continue
                        try:
                            o = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        n_in += 1
                        a = parser(o)
                        if a:
                            alerts.append(a)
            log.info("%s: %s records -> %s alerts so far", Path(n).name, n_in, len(alerts))
        if not alerts or phases.empty:
            log.warning("%s: alerts=%d phases=%d -> skipped", scen, len(alerts), len(phases))
            continue
        alerts.sort(key=lambda a: a["t"])
        per_scen_alerts[scen] = alerts
        out["scenarios"][scen] = evaluate_scenario(scen, alerts, phases)

    # aggregate across scenarios
    agg = {}
    keys = list(next(iter(out["scenarios"].values()))["windows"].keys()) if out["scenarios"] else []
    for key in keys:
        vals = defaultdict(list)
        for r in out["scenarios"].values():
            w = r["windows"][key]
            for k in ("reduction_ratio", "incident_precision", "attack_alert_recall",
                      "max_layers_in_attack_incident", "max_phases_in_attack_incident", "false_correlations"):
                if w[k] is not None:
                    vals[k].append(w[k])
        agg[key] = {k: {"mean": round(float(np.mean(v)), 4), "std": round(float(np.std(v)), 4)} for k, v in vals.items()}
        agg[key]["scenarios_with_multilayer_attack_incident"] = sum(
            1 for r in out["scenarios"].values() if r["windows"][key]["max_layers_in_attack_incident"] >= 2)
    out["aggregate"] = agg

    # leave-one-scenario-out second-stage classifier at W=60
    try:
        import lightgbm as lgb
        from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
        feats = {s: candidate_features(a, 60.0) for s, a in per_scen_alerts.items()}
        loso = []
        for s in feats:
            Xtr = np.vstack([feats[o][0] for o in feats if o != s]); ytr = np.concatenate([feats[o][1] for o in feats if o != s])
            Xte, yte = feats[s]
            if yte.sum() == 0 or ytr.sum() == 0:
                continue
            m = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8, random_state=42, verbose=-1, n_jobs=-1).fit(Xtr, ytr)
            p = m.predict(Xte); pr = m.predict_proba(Xte)[:, 1]
            rule = ((Xte[:, 3] >= 2) & (Xte[:, 7] == 1)).astype(int)
            loso.append({"held_out": s, "n_candidates": int(len(yte)), "n_attack_candidates": int(yte.sum()),
                         "lgbm": {"precision": round(float(precision_score(yte, p, zero_division=0)), 4),
                                  "recall": round(float(recall_score(yte, p, zero_division=0)), 4),
                                  "f1": round(float(f1_score(yte, p, zero_division=0)), 4),
                                  "roc_auc": round(float(roc_auc_score(yte, pr)), 4)},
                         "rule": {"precision": round(float(precision_score(yte, rule, zero_division=0)), 4),
                                  "recall": round(float(recall_score(yte, rule, zero_division=0)), 4),
                                  "f1": round(float(f1_score(yte, rule, zero_division=0)), 4)}})
        out["second_stage_loso"] = loso
        if loso:
            out["second_stage_loso_mean"] = {m: {k: round(float(np.mean([r[m][k] for r in loso])), 4)
                                                 for k in ("precision", "recall", "f1")} for m in ("lgbm", "rule")}
            log.info("LOSO second stage: %s", out["second_stage_loso_mean"])
    except Exception as e:  # noqa: BLE001
        log.warning("second stage skipped: %s", e)

    (RESULTS / "ait_ads_results.json").write_text(json.dumps(out, indent=2, default=str))
    log.info("DONE -> %s", RESULTS / "ait_ads_results.json")
    print(json.dumps(out["aggregate"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
