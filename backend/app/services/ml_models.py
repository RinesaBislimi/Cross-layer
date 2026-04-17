import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier

try:
    import lightgbm as lgb
    _LGBM_AVAILABLE = True
except ImportError:
    _LGBM_AVAILABLE = False

SUPPORTED_MODEL_TYPES = ("rf", "xgboost", "lgbm", "svm", "mlp", "isolation_forest")


class _IsolationForestWrapper:
    """Wraps IsolationForest to expose predict/predict_proba like a classifier."""

    def __init__(self, contamination: float = 0.1, random_state: int = 42, **kwargs):
        self._if = IsolationForest(
            contamination=contamination, random_state=random_state, **kwargs
        )

    def fit(self, X, y=None):  # noqa: N803
        self._if.fit(X)
        return self

    def predict(self, X):  # noqa: N803
        # IsolationForest: -1 = anomaly, 1 = normal → remap 1=anomaly, 0=normal
        raw = self._if.predict(X)
        return (raw == -1).astype(int)

    def predict_proba(self, X):  # noqa: N803
        scores = self._if.score_samples(X)  # log density: lower = more anomalous
        min_s, max_s = scores.min(), scores.max()
        if max_s == min_s:
            proba_anomaly = np.full(len(scores), 0.5)
        else:
            proba_anomaly = 1.0 - (scores - min_s) / (max_s - min_s)
        return np.column_stack([1.0 - proba_anomaly, proba_anomaly])


def train_rf_classifier(
    X, y, n_estimators: int = 100, random_state: int = 42
) -> RandomForestClassifier:
    model = RandomForestClassifier(
        n_estimators=n_estimators, random_state=random_state
    )
    model.fit(X, y)
    return model


def train_xgb_classifier(
    X, y, n_estimators: int = 100, random_state: int = 42, **kwargs: Any
) -> XGBClassifier:
    model = XGBClassifier(
        n_estimators=n_estimators,
        random_state=random_state,
        eval_metric="logloss",
        **kwargs,
    )
    model.fit(X, y)
    return model


def train_lgbm_classifier(X, y, n_estimators: int = 100, random_state: int = 42):
    if not _LGBM_AVAILABLE:
        raise RuntimeError(
            "LightGBM is not installed. Run: pip install lightgbm"
        )
    model = lgb.LGBMClassifier(
        n_estimators=n_estimators,
        random_state=random_state,
        verbose=-1,
    )
    model.fit(X, y)
    return model


def train_svm_classifier(X, y, random_state: int = 42):
    base = LinearSVC(random_state=random_state, max_iter=2000)
    model = CalibratedClassifierCV(base, cv=3)
    model.fit(X, y)
    return model


def train_mlp_classifier(X, y, random_state: int = 42):
    model = MLPClassifier(
        hidden_layer_sizes=(128, 64),
        max_iter=300,
        random_state=random_state,
        early_stopping=True,
        validation_fraction=0.1,
    )
    model.fit(X, y)
    return model


def train_isolation_forest(X, contamination: float = 0.1, random_state: int = 42):
    model = _IsolationForestWrapper(contamination=contamination, random_state=random_state)
    model.fit(X)
    return model


def _downsample(arr: np.ndarray, max_pts: int = 200) -> List[float]:
    """Downsample a curve array to at most max_pts points for JSON transfer."""
    step = max(1, len(arr) // max_pts)
    return [round(float(v), 5) for v in arr[::step]]


def _compute_metrics(
    y_true,
    y_pred,
    y_proba: Optional[np.ndarray] = None,
    split_name: str = "",
) -> Tuple[Dict[str, Any], str]:
    """Compute full metrics including ROC/PR curves when probabilities available."""
    report_text = classification_report(y_true, y_pred, digits=4, zero_division=0)
    try:
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    except ValueError:
        tn = fp = fn = tp = 0

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr_val   = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    accuracy    = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0
    mcc_denom   = ((tp+fp)*(tp+fn)*(tn+fp)*(tn+fn)) ** 0.5
    mcc         = (tp*tn - fp*fn) / mcc_denom if mcc_denom > 0 else 0.0

    metrics: Dict[str, Any] = {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fpr_val,
        "specificity": specificity,
        "accuracy": accuracy,
        "mcc": mcc,
        "tp": float(tp), "tn": float(tn), "fp": float(fp), "fn": float(fn),
        # class balance in this split
        "n_positive": int(np.sum(y_true == 1)),
        "n_negative": int(np.sum(y_true == 0)),
        "n_total":    int(len(y_true)),
    }

    # ── Curve metrics (only when probabilities are available) ────────────────
    if y_proba is not None and len(np.unique(y_true)) > 1:
        try:
            roc_fpr, roc_tpr, roc_thresh = roc_curve(y_true, y_proba)
            roc_auc = float(roc_auc_score(y_true, y_proba))
            pr_prec, pr_rec, pr_thresh = precision_recall_curve(y_true, y_proba)
            ap_score = float(average_precision_score(y_true, y_proba))

            metrics["roc_auc"]    = round(roc_auc, 4)
            metrics["avg_precision"] = round(ap_score, 4)
            metrics["roc_curve"]  = {
                "fpr": _downsample(roc_fpr),
                "tpr": _downsample(roc_tpr),
            }
            metrics["pr_curve"] = {
                "precision": _downsample(pr_prec),
                "recall":    _downsample(pr_rec),
            }
            # Threshold analysis: metrics at 10 evenly-spaced probability thresholds
            thresholds = np.linspace(0.1, 0.9, 9)
            thresh_rows = []
            for thr in thresholds:
                y_t = (y_proba >= thr).astype(int)
                tn_t, fp_t, fn_t, tp_t = (0, 0, 0, 0)
                try:
                    tn_t, fp_t, fn_t, tp_t = confusion_matrix(y_true, y_t, labels=[0, 1]).ravel()
                except ValueError:
                    pass
                p_t = tp_t / (tp_t + fp_t) if (tp_t + fp_t) > 0 else 0.0
                r_t = tp_t / (tp_t + fn_t) if (tp_t + fn_t) > 0 else 0.0
                f_t = 2 * p_t * r_t / (p_t + r_t) if (p_t + r_t) > 0 else 0.0
                fpr_t = fp_t / (fp_t + tn_t) if (fp_t + tn_t) > 0 else 0.0
                thresh_rows.append({
                    "threshold": round(float(thr), 2),
                    "precision": round(p_t, 3),
                    "recall":    round(r_t, 3),
                    "f1":        round(f_t, 3),
                    "fpr":       round(fpr_t, 3),
                })
            metrics["threshold_analysis"] = thresh_rows
        except Exception:
            pass  # curves are bonus data — never fail the whole training

    return metrics, report_text


def _get_feature_importance(
    model: Any, feature_cols: List[str], top_n: int = 20
) -> Optional[Dict[str, List]]:
    """Extract feature importances from tree-based models."""
    importances = None
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "estimators_") and hasattr(model.estimators_[0], "feature_importances_"):
        importances = np.mean([e.feature_importances_ for e in model.estimators_], axis=0)

    if importances is None or len(importances) != len(feature_cols):
        return None

    indices = np.argsort(importances)[::-1][:top_n]
    return {
        "features":    [str(feature_cols[i]) for i in indices],
        "importances": [round(float(importances[i]), 5) for i in indices],
    }


def train_and_evaluate(
    df: pd.DataFrame,
    feature_cols: list,
    label_col: str = "label",
) -> Tuple[Any, Dict[str, float], str]:
    """Train on all data and return train metrics. Kept for backwards compatibility."""
    df = df.dropna(subset=[label_col])
    X = df[feature_cols]
    y = df[label_col]
    model = train_rf_classifier(X, y)
    y_pred = model.predict(X)
    metrics, report_text = _compute_metrics(y, y_pred)
    return model, metrics, report_text


def train_and_evaluate_with_split(
    df: pd.DataFrame,
    feature_cols: list,
    label_col: str = "label",
    test_size: float = 0.15,
    val_size: float = 0.15,
    random_state: int = 42,
    model_type: str = "rf",
) -> Tuple[Any, Dict[str, Any], Dict[str, Any], Dict[str, Any], str]:
    """
    Train/validation/test split, train on train, evaluate on all splits.
    Returns extended metrics including ROC/PR curves, feature importance, CV scores.
    model_type: 'rf' | 'xgboost' | 'lgbm' | 'svm' | 'mlp' | 'isolation_forest'
    Returns: (model, train_metrics, val_metrics, test_metrics, report_text).
    """
    df = df.dropna(subset=[label_col])
    if len(df) < 10:
        raise ValueError("Not enough labeled rows for train/val/test split (need at least 10).")

    X = df[feature_cols].values
    y = df[label_col].values
    feature_names = list(feature_cols)

    stratify = y if len(np.unique(y)) > 1 else None

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=(test_size + val_size), random_state=random_state, stratify=stratify
    )
    val_ratio = val_size / (test_size + val_size)
    stratify_temp = y_temp if len(np.unique(y_temp)) > 1 else None
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=(1 - val_ratio), random_state=random_state, stratify=stratify_temp
    )

    # ── Train with timing ────────────────────────────────────────────────────
    t0 = time.perf_counter()
    if model_type == "xgboost":
        model = train_xgb_classifier(X_train, y_train, random_state=random_state)
    elif model_type == "lgbm":
        model = train_lgbm_classifier(X_train, y_train, random_state=random_state)
    elif model_type == "svm":
        model = train_svm_classifier(X_train, y_train, random_state=random_state)
    elif model_type == "mlp":
        model = train_mlp_classifier(X_train, y_train, random_state=random_state)
    elif model_type == "isolation_forest":
        model = train_isolation_forest(X_train, random_state=random_state)
    else:
        model = train_rf_classifier(X_train, y_train, random_state=random_state)
    train_time = round(time.perf_counter() - t0, 3)

    # ── Probabilities for curves ─────────────────────────────────────────────
    def _proba(X_arr):
        if hasattr(model, "predict_proba"):
            try:
                return model.predict_proba(X_arr)[:, 1]
            except Exception:
                return None
        return None

    train_metrics, _ = _compute_metrics(y_train, model.predict(X_train), _proba(X_train), "Train")
    val_metrics,   _ = _compute_metrics(y_val,   model.predict(X_val),   _proba(X_val),   "Val")
    test_metrics, report_text = _compute_metrics(y_test, model.predict(X_test), _proba(X_test), "Test")

    # ── Training metadata ────────────────────────────────────────────────────
    train_metrics["train_time_s"] = train_time
    train_metrics["n_features"]   = len(feature_names)
    train_metrics["n_train"]      = int(len(X_train))
    train_metrics["model_type"]   = model_type

    # ── Cross-validation (5-fold on training data, F1 + AUC) ────────────────
    # Only run when dataset is large enough and model supports probabilities
    if len(X_train) >= 50 and model_type not in ("isolation_forest",):
        try:
            cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
            scoring = {"f1": "f1", "roc_auc": "roc_auc", "precision": "precision", "recall": "recall"}
            cv_results = cross_validate(model, X_train, y_train, cv=cv, scoring=scoring, n_jobs=-1)
            train_metrics["cv_scores"] = {
                "f1_mean":        round(float(cv_results["test_f1"].mean()), 4),
                "f1_std":         round(float(cv_results["test_f1"].std()), 4),
                "auc_mean":       round(float(cv_results["test_roc_auc"].mean()), 4),
                "auc_std":        round(float(cv_results["test_roc_auc"].std()), 4),
                "precision_mean": round(float(cv_results["test_precision"].mean()), 4),
                "recall_mean":    round(float(cv_results["test_recall"].mean()), 4),
                "folds":          5,
            }
        except Exception:
            pass  # CV is bonus — never block training

    # ── Feature importance ───────────────────────────────────────────────────
    fi = _get_feature_importance(model, feature_names)
    if fi:
        train_metrics["feature_importance"] = fi

    return model, train_metrics, val_metrics, test_metrics, report_text


def save_model(model: Any, path: str) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_path)


def load_model(path: str) -> Any:
    return joblib.load(path)
