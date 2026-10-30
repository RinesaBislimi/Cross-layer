"""Quantitative evaluation of the cross-layer correlation engine.

Why a controlled benchmark?  (answers R1.2, R2, R3, R4)
------------------------------------------------------------------
CICIDS2017 (network), BGL (system) and TDA (application) were captured in
different environments and years, so no event in one dataset shares a real
timestamp/identifier with an event in another.  There is therefore no public
ground truth of *true* cross-layer incidents on these three datasets.  To
evaluate the correlation engine quantitatively and honestly we use a
controlled attack-injection benchmark with a KNOWN ground truth:

  * We sample real per-layer anomalies from the three datasets (these are the
    alerts a deployed system would emit).
  * We PLANT ``n_incidents`` multi-stage incidents.  Each planted incident picks
    one shared identifier E (an IP/host/user surrogate) and emits a
    network -> system -> application alert chain whose events fall inside a span
    shorter than the window W.  This is the "synthetically constructed /
    temporally aligned" mapping R1.2 asks us to describe.
  * We add ``n_distractors`` independent single-layer alerts (background noise)
    that share identifiers by chance, to create opportunities for FALSE
    correlations.

We then run the correlation engine (a faithful reimplementation of Algorithm 1,
including the non-decreasing network->system->application layer-order
constraint) and measure, against the planted ground truth:

    alerts_before            -- total per-layer alerts fed in
    incidents_after          -- number of multi-stage incidents produced
    reduction_ratio          -- 1 - incidents_after / alerts_before (triage gain)
    reconstructed (TP)       -- planted incidents correctly recovered
    false_correlations (FP)  -- reported incidents that are not a planted chain
    missed (FN)              -- planted incidents not recovered
    incident precision/recall/F1

Finally we sweep W to give the sensitivity analysis R4 requests.

Run:  python experiments/correlation_eval.py
"""
from __future__ import annotations

import json
import logging
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("experiments.correlation_eval")

RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

LAYER_ORDER = {"network": 0, "system": 1, "application": 2}


@dataclass
class Event:
    t: datetime
    layer: str
    entity: str
    score: float
    gid: Optional[int] = None   # ground-truth incident id (None = distractor)


# --------------------------------------------------------------------------- #
# Correlation engine -- faithful reimplementation of Algorithm 1
# --------------------------------------------------------------------------- #
def correlate(events: List[Event], window_s: float,
              enforce_order: bool = True, min_layers: int = 2) -> List[List[int]]:
    """Group events sharing an identifier within W that span >= min_layers.

    Returns a list of incidents, each a sorted list of event indices.
    Deduplication: an event may seed a candidate, but identical event sets are
    merged (union-find on shared membership) so the result is transitive and
    duplicate-free, matching dedup(I) in the paper.
    """
    ev = sorted(range(len(events)), key=lambda i: events[i].t)
    W = timedelta(seconds=window_s)
    # index events by entity for near-linear lookup
    # identifier-indexed hash map -> time-sorted alert lists; the window
    # [t-W, t+W] is located by binary search so per-alert work is
    # O(log m + window occupancy), i.e. near-linear overall for sparse windows.
    by_entity: Dict[str, List[int]] = {}
    for i in ev:
        by_entity.setdefault(events[i].entity, []).append(i)
    by_time = {k: [events[j].t for j in v] for k, v in by_entity.items()}

    candidates: List[frozenset] = []
    for i in ev:
        e = events[i]
        same = by_entity.get(e.entity, [])
        times = by_time[e.entity]
        lo = bisect_left(times, e.t - W)
        hi = bisect_right(times, e.t + W)
        group = same[lo:hi]
        layers = {events[j].layer for j in group}
        if len(layers) < min_layers:
            continue
        if enforce_order:
            # keep only events that respect a non-decreasing layer order relative
            # to the earliest event in the group
            group_sorted = sorted(group, key=lambda j: events[j].t)
            kept, last = [], -1
            for j in group_sorted:
                lo = LAYER_ORDER.get(events[j].layer, 99)
                if lo >= last:
                    kept.append(j)
                    last = lo
            group = kept
            if len({events[j].layer for j in group}) < min_layers:
                continue
        candidates.append(frozenset(group))

    # dedup / merge overlapping candidates (union-find)
    parent: Dict[int, int] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    for cand in candidates:
        members = list(cand)
        for m in members:
            find(m)
        for m in members[1:]:
            union(members[0], m)

    groups: Dict[int, set] = {}
    for cand in candidates:
        for m in cand:
            groups.setdefault(find(m), set()).add(m)
    incidents = [sorted(g) for g in groups.values()
                 if len({events[j].layer for j in g}) >= min_layers]
    return incidents



def correlate_fast(events: List[Event], window_s: float,
                   enforce_order: bool = True, min_layers: int = 2) -> List[List[int]]:
    """O(n log n) implementation of Algorithm 1 for large alert streams.

    Observation: under "share an identifier and lie within W of each other",
    the transitive closure of a time-sorted per-entity list is the set of
    maximal chains of consecutive alerts whose gaps are <= W.  So it suffices to
    walk each entity's alerts in time order and union each alert with the
    current chain when its gap to the last accepted alert is <= W.  The
    layer-order constraint is applied as in the reference implementation: an
    alert whose layer index is lower than the running maximum of the chain is
    dropped (left as a singleton) instead of breaking the chain.
    """
    from collections import defaultdict
    order = sorted(range(len(events)), key=lambda i: events[i].t)
    W = timedelta(seconds=window_s)
    by_entity: Dict[str, List[int]] = defaultdict(list)
    for i in order:
        by_entity[events[i].entity].append(i)
    parent = list(range(len(events)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for idxs in by_entity.values():
        root = None
        last_t = None
        max_layer = -1
        for i in idxs:
            e = events[i]
            lo = LAYER_ORDER.get(e.layer)
            if root is not None and e.t - last_t <= W:
                if enforce_order and lo is not None and lo < max_layer:
                    continue                      # out-of-order alert dropped
                parent[find(i)] = find(root)
                last_t = e.t
                if lo is not None:
                    max_layer = max(max_layer, lo)
            else:
                root, last_t = i, e.t
                max_layer = lo if lo is not None else -1
    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(len(events)):
        groups[find(i)].append(i)
    return [sorted(g) for g in groups.values()
            if len({events[j].layer for j in g}) >= min_layers]


# --------------------------------------------------------------------------- #
# Controlled benchmark generator
# --------------------------------------------------------------------------- #
def build_benchmark(n_incidents: int = 200, n_distractors: int = 12000,
                    chain_span_s: float = 40.0, n_entities: int = 400,
                    seed: int = 42) -> Tuple[List[Event], List[set]]:
    """A deliberately *hard* benchmark.

    Planted chains and distractors draw their identifiers from the SAME pool of
    ``n_entities`` surrogate IPs/hosts/users, and the distractors are temporally
    dense, so distractor alerts frequently share an identifier and fall inside a
    window with a planted chain (false enlargement) or with each other across
    layers (spurious incidents).  This is what makes incident precision < 1 and
    exposes the real recall/precision trade-off as W grows.
    """
    rng = np.random.RandomState(seed)
    base = datetime(2025, 1, 1)
    events: List[Event] = []
    truth: List[set] = []

    horizon_s = 24 * 3600  # one day of simulated time (dense)
    pool = [f"H{e:04d}" for e in range(n_entities)]

    # planted multi-stage incidents: network -> system -> application on shared E
    for g in range(n_incidents):
        start = base + timedelta(seconds=float(rng.uniform(0, horizon_s)))
        entity = pool[rng.randint(0, n_entities)]
        idxs = set()
        offs = sorted(rng.uniform(0, chain_span_s, size=3))
        for layer, off in zip(("network", "system", "application"), offs):
            idxs.add(len(events))
            events.append(Event(start + timedelta(seconds=float(off)), layer,
                                 entity, float(rng.uniform(0.6, 1.0)), gid=g))
        truth.append(idxs)

    # dense independent single-layer distractors drawn from the SAME id pool
    layers = ("network", "system", "application")
    for _ in range(n_distractors):
        t = base + timedelta(seconds=float(rng.uniform(0, horizon_s)))
        entity = pool[rng.randint(0, n_entities)]
        events.append(Event(t, layers[rng.randint(0, 3)], entity,
                            float(rng.uniform(0.3, 0.9)), gid=None))
    return events, truth


def score_incidents(incidents: List[List[int]], events: List[Event],
                    truth: List[set], jaccard_thr: float = 0.5) -> Dict:
    """Match predicted incidents to planted ones by Jaccard overlap (standard
    for event correlation).  Each planted incident may be matched at most once;
    leftover predictions are false correlations; unmatched plants are misses."""
    truth_sets = [set(s) for s in truth]
    used = set()
    tp = 0
    fp = 0
    for inc in incidents:
        inc_set = set(inc)
        best_j, best_g = 0.0, -1
        for g, ts in enumerate(truth_sets):
            if g in used:
                continue
            inter = len(inc_set & ts)
            if inter == 0:
                continue
            j = inter / len(inc_set | ts)
            if j > best_j:
                best_j, best_g = j, g
        if best_g >= 0 and best_j >= jaccard_thr:
            tp += 1
            used.add(best_g)
        else:
            fp += 1
    fn = len(truth_sets) - len(used)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "incident_precision": round(precision, 4),
            "incident_recall": round(recall, 4),
            "incident_f1": round(f1, 4)}


def main():
    out: Dict = {}

    # --- main result at the default window W = 60 s -------------------------- #
    events, truth = build_benchmark()
    alerts_before = len(events)
    incidents = correlate(events, window_s=60.0, enforce_order=True)
    sc = score_incidents(incidents, events, truth)
    out["main"] = {
        "window_s": 60,
        "alerts_before": alerts_before,
        "planted_incidents": len(truth),
        "distractor_alerts": alerts_before - 3 * len(truth),
        "incidents_after": len(incidents),
        "reduction_ratio": round(1 - len(incidents) / alerts_before, 4),
        **sc,
    }
    log.info("MAIN  before=%s after=%s  P=%.3f R=%.3f F1=%.3f  (TP=%s FP=%s FN=%s)",
             alerts_before, len(incidents), sc["incident_precision"],
             sc["incident_recall"], sc["incident_f1"], sc["tp"], sc["fp"], sc["fn"])

    # --- sensitivity to window W ------------------------------------------- #
    out["window_sensitivity"] = []
    for W in [5, 15, 30, 60, 120, 300, 600]:
        inc = correlate(events, window_s=float(W), enforce_order=True)
        s = score_incidents(inc, events, truth)
        row = {"window_s": W, "incidents_after": len(inc),
               "reduction_ratio": round(1 - len(inc) / alerts_before, 4), **s}
        out["window_sensitivity"].append(row)
        log.info("W=%4ds  incidents=%-5s P=%.3f R=%.3f F1=%.3f",
                 W, len(inc), s["incident_precision"], s["incident_recall"], s["incident_f1"])

    # --- ablation: layer-order constraint on vs off ------------------------ #
    inc_no_order = correlate(events, window_s=60.0, enforce_order=False)
    out["ablation_layer_order"] = {
        "with_order": score_incidents(correlate(events, 60.0, True), events, truth),
        "without_order": score_incidents(inc_no_order, events, truth),
    }

    # --- robustness across seeds ------------------------------------------- #
    seeds_res = []
    for seed in [42, 7, 13, 21, 2024]:
        ev, tr = build_benchmark(seed=seed)
        inc = correlate(ev, window_s=60.0, enforce_order=True)
        seeds_res.append(score_incidents(inc, ev, tr))
    for k in ["incident_precision", "incident_recall", "incident_f1"]:
        vals = np.array([r[k] for r in seeds_res])
        out.setdefault("across_seeds", {})[k] = {
            "mean": round(float(vals.mean()), 4), "std": round(float(vals.std()), 4)}

    (RESULTS / "correlation_results.json").write_text(json.dumps(out, indent=2))
    log.info("DONE -> %s", RESULTS / "correlation_results.json")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
