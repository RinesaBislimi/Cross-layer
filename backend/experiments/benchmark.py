"""System-level throughput / latency / memory benchmark (answers R1.5, R3).

Measures, on this machine:
  1. Per-layer detection throughput: events/second and per-event latency
     (mean and p99) for feature-vector inference with the fitted model.
  2. Correlation-engine throughput and empirical scaling: events/second as the
     number of alerts grows (to support the near-linear O(n) claim).
  3. Peak Python memory (tracemalloc) and, if psutil is available, peak RSS.

Run:  python experiments/benchmark.py
"""
from __future__ import annotations

import json
import logging
import time
import tracemalloc
from pathlib import Path
from typing import Dict

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from datasets import load_cicids, load_bgl, load_tda
from correlation_eval import build_benchmark, correlate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("experiments.benchmark")

RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

try:
    import psutil  # type: ignore
    _PROC = psutil.Process()
except Exception:  # noqa: BLE001
    _PROC = None


def _rss_mb() -> float:
    if _PROC is None:
        return float("nan")
    return _PROC.memory_info().rss / 1e6


def bench_layer(name: str, loader, n: int) -> Dict:
    ds = loader(n)
    X = ds.X.to_numpy(dtype="float64")
    y = ds.y
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, random_state=42,
                                          stratify=y if len(np.unique(y)) > 1 else None)
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1).fit(Xtr, ytr)

    # warm up
    model.predict(Xte[:100])

    # batch throughput
    t0 = time.perf_counter()
    model.predict(Xte)
    batch_s = time.perf_counter() - t0
    eps = len(Xte) / batch_s if batch_s else float("nan")

    # per-event latency distribution (single-event scoring, as in streaming)
    sample = Xte[:2000]
    lat = np.empty(len(sample))
    for i, row in enumerate(sample):
        s = time.perf_counter()
        model.predict(row.reshape(1, -1))
        lat[i] = (time.perf_counter() - s) * 1e3  # ms
    return {
        "layer": ds.layer, "dataset": name, "n_test": int(len(Xte)),
        "batch_events_per_s": round(eps, 1),
        "latency_ms_mean": round(float(lat.mean()), 4),
        "latency_ms_p99": round(float(np.percentile(lat, 99)), 4),
    }


def bench_correlation() -> Dict:
    rows = []
    for n_distr in [2000, 8000, 20000, 50000, 100000]:
        events, _ = build_benchmark(n_incidents=max(50, n_distr // 100),
                                    n_distractors=n_distr, seed=42)
        n = len(events)
        t0 = time.perf_counter()
        correlate(events, window_s=60.0, enforce_order=True)
        dt = time.perf_counter() - t0
        rows.append({"n_events": n, "seconds": round(dt, 4),
                     "events_per_s": round(n / dt, 1) if dt else float("nan")})
        log.info("correlation n=%s  %.3fs  %.0f ev/s", n, dt, n / dt if dt else 0)
    # empirical scaling exponent: fit log(t) ~ a*log(n)+b  (1=linear, 2=quadratic)
    ns = np.log([r["n_events"] for r in rows])
    ts = np.log([max(r["seconds"], 1e-6) for r in rows])
    slope = float(np.polyfit(ns, ts, 1)[0])
    return {"scaling": rows, "empirical_exponent": round(slope, 3)}


def main():
    tracemalloc.start()
    rss0 = _rss_mb()
    out: Dict = {"layers": [], "correlation": {}, "host": {}}

    for name, loader, n in [("CICIDS2017", load_cicids, 150_000),
                            ("BGL", load_bgl, 150_000),
                            ("TDA", load_tda, 80_000)]:
        r = bench_layer(name, loader, n)
        out["layers"].append(r)
        log.info("%s: %.0f ev/s  latency mean=%.3fms p99=%.3fms",
                 name, r["batch_events_per_s"], r["latency_ms_mean"], r["latency_ms_p99"])

    out["correlation"] = bench_correlation()

    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    out["host"] = {
        "peak_python_mem_mb": round(peak / 1e6, 1),
        "rss_start_mb": round(rss0, 1) if not np.isnan(rss0) else None,
        "rss_end_mb": round(_rss_mb(), 1) if not np.isnan(_rss_mb()) else None,
        "psutil_available": _PROC is not None,
    }
    (RESULTS / "benchmark_results.json").write_text(json.dumps(out, indent=2))
    log.info("DONE -> %s", RESULTS / "benchmark_results.json")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
