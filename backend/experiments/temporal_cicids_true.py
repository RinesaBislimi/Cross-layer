"""TRUE temporal and session-aware evaluation of CICIDS2017 (answers R2, R4).

Uses the original per-day *timestamped* flow files (GeneratedLabelledFlows.zip,
"TrafficLabelling" folder: Monday ... Friday, with Timestamp and Source IP),
not the consolidated label-grouped CSV. Four protocols, same 52 features and
cleaning as datasets.py, LightGBM and Random Forest:

  random        stratified random 70/15/15 (reference)
  within_day    chronological 70/15/15 inside every day, then pooled: the model
                is tested on flows that occur strictly after its training flows
                of the same day (attack types shared across partitions)
  cross_day     train on Mon-Wed, validate on the last 15% of Wed, test on Thu-Fri:
                strict forward-in-time split; Thu/Fri contain attack families
                (web attacks, infiltration, botnet, DDoS, port scan) that are
                absent from Mon-Wed, so this also measures generalisation to
                unseen attack types
  by_source_ip  session-aware GroupShuffleSplit on Source IP (no host appears in
                both train and test)

Known CICIDS2017 quirk handled: afternoon timestamps lack AM/PM; hours < 8 are
PM and are shifted by +12 h before sorting.

Usage:  python experiments/temporal_cicids_true.py <path-to-GeneratedLabelledFlows.zip>
"""
from __future__ import annotations

import io
import json
import logging
import sys
import zipfile
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
import lightgbm as lgb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datasets import CICIDS_ORIG_COLS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("temporal_true")
RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
PER_FILE_CAP = 120_000     # rows kept per daily file (uniform random, seed 42)


def load_all(zip_path: Path) -> pd.DataFrame:
    z = zipfile.ZipFile(zip_path)
    parts = []
    rng = np.random.RandomState(42)
    for info in z.infolist():
        if not info.filename.lower().endswith(".csv"):
            continue
        name = Path(info.filename).name
        day = next((d for d in DAY_ORDER if name.startswith(d)), None)
        if day is None:
            continue
        raw = z.read(info)
        df = pd.read_csv(io.BytesIO(raw), encoding="latin1", low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        need = ["Timestamp", "Source IP", "Destination IP", "Label"] + CICIDS_ORIG_COLS
        missing = [c for c in need if c not in df.columns]
        if missing:
            raise KeyError(f"{name}: missing {missing[:5]}")
        df = df[need]
        if len(df) > PER_FILE_CAP:
            df = df.iloc[rng.choice(len(df), PER_FILE_CAP, replace=False)]
        df["day"] = day
        df["file"] = name
        parts.append(df)
        log.info("%s: %s rows kept", name, len(df))
    df = pd.concat(parts, ignore_index=True)

    # day files mix "5/7/2017 8:42" and "03/07/2017 08:55:58" (Monday); pandas 2.x
    # infers one format from the first value unless format="mixed"
    ts = pd.to_datetime(df["Timestamp"].astype(str).str.strip(), dayfirst=True,
                        format="mixed", errors="coerce")
    # afternoon hours recorded without PM marker
    pm = ts.dt.hour < 8
    ts = ts + pd.to_timedelta(pm.astype(int) * 12, unit="h")
    df["ts"] = ts
    df = df[df["ts"].notna()]

    feat = df[CICIDS_ORIG_COLS].apply(pd.to_numeric, errors="coerce")
    feat = feat.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df[CICIDS_ORIG_COLS] = feat
    df["y"] = (df["Label"].astype(str).str.strip().str.upper() != "BENIGN").astype(int)
    df = df.drop_duplicates(subset=CICIDS_ORIG_COLS + ["y"])
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def fit_eval(name: str, Xtr, ytr, Xte, yte) -> Dict:
    out = {}
    for mname, model in [
        ("lgbm", lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8,
                                    random_state=42, verbose=-1, n_jobs=-1)),
        ("rf", RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)),
    ]:
        model.fit(Xtr, ytr)
        pred = model.predict(Xte)
        proba = model.predict_proba(Xte)[:, 1]
        out[mname] = {
            "precision": round(float(precision_score(yte, pred, zero_division=0)), 4),
            "recall": round(float(recall_score(yte, pred, zero_division=0)), 4),
            "f1": round(float(f1_score(yte, pred, zero_division=0)), 4),
            "roc_auc": round(float(roc_auc_score(yte, proba)), 4) if len(np.unique(yte)) > 1 else None,
        }
        log.info("%-14s %-5s P=%.3f R=%.3f F1=%.3f AUC=%s", name, mname, out[mname]["precision"],
                 out[mname]["recall"], out[mname]["f1"], out[mname]["roc_auc"])
    out["n_train"], out["n_test"] = int(len(ytr)), int(len(yte))
    out["train_attack_rate"] = round(float(np.mean(ytr)), 4)
    out["test_attack_rate"] = round(float(np.mean(yte)), 4)
    return out


def main(zip_path: str):
    df = load_all(Path(zip_path))
    X = df[CICIDS_ORIG_COLS].to_numpy("float64")
    y = df["y"].to_numpy()
    res: Dict = {"n_rows": int(len(df)),
                 "rows_per_day": df["day"].value_counts().reindex(DAY_ORDER).fillna(0).astype(int).to_dict(),
                 "attack_rate_per_day": df.groupby("day")["y"].mean().reindex(DAY_ORDER).round(4).to_dict(),
                 "attack_types_per_day": {d: sorted(set(df.loc[df.day == d, "Label"].str.strip()) - {"BENIGN"})
                                          for d in DAY_ORDER}}

    # random
    tr, tmp = train_test_split(np.arange(len(y)), test_size=0.3, random_state=42, stratify=y)
    va, te = train_test_split(tmp, test_size=0.5, random_state=42, stratify=y[tmp])
    res["random"] = fit_eval("random", X[tr], y[tr], X[te], y[te])

    # within-day chronological
    tr_idx, te_idx = [], []
    for d in DAY_ORDER:
        idx = np.where(df["day"].to_numpy() == d)[0]           # already time-sorted
        n = len(idx)
        tr_idx.append(idx[: int(0.70 * n)]); te_idx.append(idx[int(0.85 * n):])
    tr_idx, te_idx = np.concatenate(tr_idx), np.concatenate(te_idx)
    res["within_day"] = fit_eval("within_day", X[tr_idx], y[tr_idx], X[te_idx], y[te_idx])

    # cross-day (strict forward in time)
    train_days = {"Monday", "Tuesday", "Wednesday"}
    tr_idx = np.where(df["day"].isin(train_days).to_numpy())[0]
    te_idx = np.where(df["day"].isin({"Thursday", "Friday"}).to_numpy())[0]
    res["cross_day"] = fit_eval("cross_day", X[tr_idx], y[tr_idx], X[te_idx], y[te_idx])
    # per-attack-family recall on the unseen days (diagnostic)
    model = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1, max_depth=8,
                               random_state=42, verbose=-1, n_jobs=-1).fit(X[tr_idx], y[tr_idx])
    pred = model.predict(X[te_idx])
    lab = df["Label"].str.strip().to_numpy()[te_idx]
    fam = {}
    for a in sorted(set(lab)):
        m = lab == a
        fam[a] = {"n": int(m.sum()),
                  ("recall" if a != "BENIGN" else "specificity"):
                  round(float((pred[m] == 1).mean() if a != "BENIGN" else (pred[m] == 0).mean()), 4)}
    res["cross_day"]["per_label_on_test"] = fam

    # session-aware: StratifiedGroupKFold so that no host (or session) appears in
    # both partitions while every test fold still contains attack flows. CICIDS2017
    # attacks originate from only a handful of source IPs, so a single
    # GroupShuffleSplit on Source IP can leave the test fold without any attack;
    # 5-fold StratifiedGroupKFold with mean +/- SD over folds avoids that.
    from sklearn.model_selection import StratifiedGroupKFold
    for key, grp in [("by_source_ip", df["Source IP"].astype(str).to_numpy()),
                     ("by_session", (df["Source IP"].astype(str) + ">" +
                                     df["Destination IP"].astype(str)).to_numpy())]:
        folds = []
        sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
        for tr_idx, te_idx in sgkf.split(X, y, grp):
            if y[te_idx].sum() == 0 or y[tr_idx].sum() == 0:
                continue
            r = fit_eval(f"{key}/fold", X[tr_idx], y[tr_idx], X[te_idx], y[te_idx])
            r["n_groups_train"], r["n_groups_test"] = int(len(set(grp[tr_idx]))), int(len(set(grp[te_idx])))
            folds.append(r)
        agg = {"n_folds_with_attacks": len(folds), "folds": folds,
               "n_groups_total": int(len(set(grp)))}
        for m in ("lgbm", "rf"):
            agg[m] = {k: round(float(np.mean([f[m][k] for f in folds if f[m][k] is not None])), 4)
                      for k in ("precision", "recall", "f1", "roc_auc")}
            agg[m]["f1_std"] = round(float(np.std([f[m]["f1"] for f in folds])), 4)
        agg["n_train"] = int(np.mean([f["n_train"] for f in folds])); agg["n_test"] = int(np.mean([f["n_test"] for f in folds]))
        agg["test_attack_rate"] = round(float(np.mean([f["test_attack_rate"] for f in folds])), 4)
        agg["n_source_ips_train"] = int(np.mean([f["n_groups_train"] for f in folds]))
        agg["n_source_ips_test"] = int(np.mean([f["n_groups_test"] for f in folds]))
        res[key] = agg
        log.info("%s: %d folds, lgbm F1=%.3f±%.3f rf F1=%.3f±%.3f", key, len(folds),
                 agg["lgbm"]["f1"], agg["lgbm"]["f1_std"], agg["rf"]["f1"], agg["rf"]["f1_std"])

    (RESULTS / "temporal_cicids_true_results.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "attack_types_per_day"}, indent=1)[:3000])


if __name__ == "__main__":
    main(sys.argv[1])
