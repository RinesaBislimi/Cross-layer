"""Learned second-stage cross-layer incident classifier (answers R4).

The production service already trains a second-stage model
(app/services/training.train_cross_layer) on per-(entity, window) aggregate
features. Here we evaluate that learned cross-layer component on the controlled
benchmark with KNOWN ground truth, so the claim "machine learning is applied
across layers" is backed by numbers.

Unit of classification: one candidate incident = all alerts sharing an entity
inside a W-second window (the output of Algorithm 1 *before* the layer-order
filter). Cross-layer features computed per candidate (formally defined in the
manuscript, Section 4.5):
    count_network, count_system, count_application  -- alerts per layer
    n_layers        -- number of distinct layers present
    span_s          -- time span of the candidate (seconds)
    max_score       -- max per-layer detector score
    mean_score      -- mean per-layer detector score
    order_ok        -- 1 if layer order is non-decreasing net->sys->app
Label: 1 if the candidate contains a complete planted multi-stage chain.

Run: python experiments/second_stage_eval.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
import lightgbm as lgb
sys.path.insert(0, str(Path(__file__).resolve().parent))
from correlation_eval import build_benchmark, correlate, LAYER_ORDER

RESULTS = Path(__file__).resolve().parent / "results"
FEATS = ["count_network","count_system","count_application","n_layers",
         "span_s","max_score","mean_score","order_ok"]

def candidates(events, truth, W=60.0):
    inc = correlate(events, window_s=W, enforce_order=False, min_layers=1)
    truth_sets = [set(t) for t in truth]
    X, y = [], []
    for c in inc:
        ev = [events[i] for i in c]
        cnt = {l: 0 for l in ("network","system","application")}
        for e in ev: cnt[e.layer] += 1
        ts = sorted(e.t for e in ev)
        ev_sorted = sorted(ev, key=lambda e: e.t)
        orders = [LAYER_ORDER[e.layer] for e in ev_sorted]
        order_ok = int(all(a <= b for a, b in zip(orders, orders[1:])))
        X.append([cnt["network"], cnt["system"], cnt["application"],
                  sum(v > 0 for v in cnt.values()),
                  (ts[-1]-ts[0]).total_seconds(),
                  max(e.score for e in ev), float(np.mean([e.score for e in ev])), order_ok])
        cs = set(c)
        y.append(int(any(t.issubset(cs) for t in truth_sets)))
    return np.array(X, float), np.array(y, int)

def main():
    out = {"features": FEATS, "models": {}}
    models = {
        "logreg": lambda s: LogisticRegression(max_iter=1000, random_state=s),
        "rf": lambda s: RandomForestClassifier(n_estimators=100, random_state=s, n_jobs=-1),
        "lgbm": lambda s: lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8,
                                             random_state=s, verbose=-1, n_jobs=-1),
    }
    # rule-based baseline = Algorithm 1 with layer-order filter (n_layers>=2 & order_ok)
    seeds = [42, 7, 13, 21, 2024]
    runs = {k: [] for k in list(models) + ["rule_baseline"]}
    n_cand = []
    for s in seeds:
        ev, tr = build_benchmark(seed=s)
        X, y = candidates(ev, tr)
        n_cand.append((len(y), int(y.sum())))
        Xtr, Xtmp, ytr, ytmp = train_test_split(X, y, test_size=0.3, random_state=s, stratify=y)
        Xva, Xte, yva, yte = train_test_split(Xtmp, ytmp, test_size=0.5, random_state=s, stratify=ytmp)
        rb = ((Xte[:,3] >= 2) & (Xte[:,7] == 1)).astype(int)
        runs["rule_baseline"].append(dict(precision=precision_score(yte, rb, zero_division=0),
            recall=recall_score(yte, rb, zero_division=0), f1=f1_score(yte, rb, zero_division=0), roc_auc=float("nan")))
        for k, mk in models.items():
            m = mk(s).fit(Xtr, ytr)
            p = m.predict(Xte); pr = m.predict_proba(Xte)[:,1]
            runs[k].append(dict(precision=precision_score(yte, p, zero_division=0),
                recall=recall_score(yte, p, zero_division=0), f1=f1_score(yte, p, zero_division=0),
                roc_auc=roc_auc_score(yte, pr)))
    for k, rs in runs.items():
        out["models"][k] = {m: {"mean": float(np.nanmean([r[m] for r in rs])),
                                "std": float(np.nanstd([r[m] for r in rs]))}
                            for m in ("precision","recall","f1","roc_auc")}
        s = out["models"][k]
        print(f"{k:14s} P={s['precision']['mean']:.3f}±{s['precision']['std']:.3f} "
              f"R={s['recall']['mean']:.3f}±{s['recall']['std']:.3f} F1={s['f1']['mean']:.3f}±{s['f1']['std']:.3f} "
              f"AUC={s['roc_auc']['mean']:.3f}")
    out["candidates_per_seed"] = n_cand
    (RESULTS / "second_stage_results.json").write_text(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
