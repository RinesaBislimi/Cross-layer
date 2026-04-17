from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from .feature_engineering import (
    BGL_FEATURE_COLS,
    CICIDS_FEATURE_COLS,
    TDA_FEATURE_COLS,
    build_bgl_features,
    build_cicids_features,
    build_cross_layer_features,
    build_cross_layer_time_features,
    build_tda_features,
)
from .ingestion import _backend_root
from .ml_models import (
    save_model,
    train_and_evaluate_with_split,
)

settings = get_settings()


def _resolve_model_path(rel: str) -> str:
    """Always resolve model paths relative to the backend root directory.

    This ensures save_model() and api_model_status() agree on the location
    regardless of which directory uvicorn is launched from.
    """
    p = Path(rel)
    if p.is_absolute():
        return str(p)
    resolved = (_backend_root() / p).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


def _ensure_labels(df, dataset_name: str) -> None:
    if df is None or df.empty:
        raise ValueError(
            f"No data found for {dataset_name}. Did you run the /admin/ingest endpoint?"
        )
    if "label" not in df.columns:
        raise ValueError(
            f"No 'label' column found for {dataset_name}. "
            f"Make sure the dataset has labels and ingestion maps them to LogEvent.label."
        )


def _train_layer(
    db: Session,
    dataset_name: str,
    get_features_fn,
    feature_cols: list,
    model_path: str,
    model_type: str = "rf",
) -> dict:
    df = get_features_fn(db)
    _ensure_labels(df, dataset_name)
    model, train_m, val_m, test_m, report = train_and_evaluate_with_split(
        df, feature_cols, model_type=model_type
    )
    save_model(model, _resolve_model_path(model_path))
    return {
        "train_metrics": train_m,
        "val_metrics":   val_m,
        "test_metrics":  test_m,
        "report":        report,
        "feature_cols":  feature_cols,
        "dataset":       dataset_name,
        "model_type":    model_type,
    }


def train_bgl(db: Session, model_type: str = "rf") -> dict:
    return _train_layer(
        db,
        "BGL",
        build_bgl_features,
        BGL_FEATURE_COLS,
        settings.BGL_MODEL_PATH,
        model_type=model_type,
    )


def train_cicids(db: Session, model_type: str = "rf") -> dict:
    df = build_cicids_features(db)
    _ensure_labels(df, "CICIDS2017")
    # Use proper numerical features when available; fall back to text_len
    feature_cols = [c for c in CICIDS_FEATURE_COLS if c in df.columns and df[c].sum() != 0]
    if not feature_cols:
        feature_cols = ["text_len"] if "text_len" in df.columns else CICIDS_FEATURE_COLS
    model, train_m, val_m, test_m, report = train_and_evaluate_with_split(
        df, feature_cols, model_type=model_type
    )
    save_model(model, _resolve_model_path(settings.CICIDS_MODEL_PATH))
    return {
        "train_metrics": train_m,
        "val_metrics":   val_m,
        "test_metrics":  test_m,
        "report":        report,
        "feature_cols":  feature_cols,
        "dataset":       "CICIDS2017",
        "model_type":    model_type,
    }


def train_tda(db: Session, model_type: str = "rf") -> dict:
    return _train_layer(
        db,
        "TDA",
        build_tda_features,
        TDA_FEATURE_COLS,
        settings.TDA_MODEL_PATH,
        model_type=model_type,
    )


def train_cross_layer(
    db: Session,
    window_minutes: int = 10,
    min_layers: int = 2,
    model_type: str = "rf",
) -> dict:
    """
    Train the cross-layer model on (entity × time-window) features.

    Falls back to time co-occurrence windows (no entity requirement) when
    entity-based overlap across layers is too sparse to produce a training set.
    This is common because BGL uses node names, CICIDS uses IPs, and TDA uses
    user IDs — they rarely share the same entity string.
    """
    mode = "entity"
    df = build_cross_layer_features(db, window_minutes=window_minutes, min_layers=min_layers)

    feature_cols = [c for c in (df.columns if df is not None else []) if c.startswith("count_")]
    if df is None or df.empty or len(df) < 10 or not feature_cols:
        # Fallback: sequential bucket approach — always produces training data
        mode = "time_cooccurrence"
        df = build_cross_layer_time_features(db, window_minutes=window_minutes)
        feature_cols = [
            c for c in (df.columns if df is not None else [])
            if c.startswith("count_") or c.startswith("burst_") or c == "active_layers"
        ]

    if df is None or df.empty:
        raise ValueError(
            "No cross-layer data found. Ingest at least two datasets first "
            "(e.g. BGL + CICIDS via Step 1)."
        )
    if not feature_cols:
        raise ValueError("No layer count features found in cross-layer DataFrame.")
    if len(df) < 10:
        raise ValueError(
            f"Not enough cross-layer windows to train ({len(df)} rows, need ≥ 10). "
            "Ingest more data or reduce window_minutes."
        )

    model, train_m, val_m, test_m, report = train_and_evaluate_with_split(
        df, feature_cols, label_col="label", model_type=model_type
    )
    model_path = _resolve_model_path(settings.CROSS_LAYER_MODEL_PATH)
    save_model(model, model_path)

    # Verify the file was actually written
    saved_ok = Path(model_path).is_file()
    if not saved_ok:
        raise RuntimeError(
            f"Model trained but file was NOT saved at: {model_path}. "
            "Check write permissions on that directory."
        )

    return {
        "mode":          mode,
        "rows_used":     len(df),
        "saved_to":      model_path,
        "train_metrics": train_m,
        "val_metrics":   val_m,
        "test_metrics":  test_m,
        "report":        report,
        "feature_cols":  feature_cols,
        "dataset":       "Cross-Layer",
        "model_type":    model_type,
    }
