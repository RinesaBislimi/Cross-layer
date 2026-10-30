"""Generate publication figures for the revised manuscript.

Figures:
  Fig 1  Multi-stage attack scenario (timeline across the three layers, shared
         identifier, correlation window)          -> fig1_attack_scenario.png
  Fig 2  Overall system architecture (accurate: per-layer detectors + learned
         cross-layer second-stage model)          -> fig2_architecture.png
  Fig 3  Correlation-engine window (W) sensitivity -> fig3_window_sensitivity.png
  Fig 4  Per-model F1 across the three layers      -> fig4_model_comparison.png

Colorblind-safe Okabe-Ito palette, assigned in fixed order.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

# Okabe-Ito colorblind-safe palette (fixed order)
OI = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
      "vermillion": "#D55E00", "purple": "#CC79A7", "sky": "#56B4E9",
      "yellow": "#F0E442", "grey": "#4D4D4D"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.6,
    "figure.dpi": 300,
})


def _box(ax, x, y, w, h, text, fc, ec):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                linewidth=1.5, edgecolor=ec, facecolor=fc, mutation_aspect=1))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9.5)


def _arrow(ax, p0, p1, color=OI["grey"]):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=12,
                                 lw=1.4, color=color, shrinkA=2, shrinkB=2))


# --------------------------------------------------------------------------- #
# Fig 1: multi-stage attack scenario
# --------------------------------------------------------------------------- #
def fig1():
    fig, ax = plt.subplots(figsize=(8.2, 4.3))
    ax.set_xlim(0, 10); ax.set_ylim(-0.8, 6.9); ax.axis("off")
    lanes = [("Application layer (TDA)", 4.6, OI["green"]),
             ("System layer (BGL)", 3.0, OI["orange"]),
             ("Network layer (CICIDS2017)", 1.4, OI["blue"])]
    for name, y, c in lanes:
        ax.axhline(y, 0.06, 0.97, color=c, lw=1.0, alpha=0.5, zorder=0)
        ax.text(0.1, y + 0.45, name, fontsize=9, color=c, fontweight="bold")

    steps = [
        (1.6, 1.4, OI["blue"], "1. Port scan /\nrecon"),
        (4.0, 3.0, OI["orange"], "2. Failed auth /\nprivilege attempt"),
        (6.4, 3.0, OI["orange"], "3. Kernel / RAS\nanomaly"),
        (8.6, 4.6, OI["green"], "4. Abnormal DB\naccess (exfil)"),
    ]
    prev = None
    for x, y, c, label in steps:
        ax.scatter([x], [y], s=240, color=c, edgecolor="white", linewidth=1.5, zorder=3)
        ax.text(x, y - 0.95, label, ha="center", va="top", fontsize=8.3)
        if prev is not None:
            _arrow(ax, (prev[0] + 0.18, prev[1]), (x - 0.18, y), color=OI["grey"])
        prev = (x, y)

    # shared identifier + correlation window annotation
    ax.annotate("shared identifier  E = 10.0.0.7  (host / user / IP)",
                xy=(5.1, 6.45), ha="center", fontsize=8.6, color=OI["purple"],
                fontweight="bold")
    ax.annotate("", xy=(1.6, 5.75), xytext=(8.6, 5.75),
                arrowprops=dict(arrowstyle="<->", color=OI["purple"], lw=1.2))
    ax.text(5.1, 5.88, "correlation window  W", ha="center", fontsize=8.2, color=OI["purple"])
    ax.text(9.55, -0.25, "time", fontsize=8.5, style="italic", color=OI["grey"])
    _arrow(ax, (0.3, -0.25), (9.4, -0.25))
    fig.tight_layout()
    fig.savefig(FIG / "fig1_attack_scenario.png", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Fig 2: architecture (accurate)
# --------------------------------------------------------------------------- #
def fig2():
    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    ax.set_xlim(0, 12); ax.set_ylim(0, 12); ax.axis("off")
    g = ("#eaf4ec", OI["green"]); b = ("#e8f0f8", OI["blue"])
    o = ("#fdf1e3", OI["orange"]); p = ("#f6ecf3", OI["purple"])

    _box(ax, 0.3, 10.4, 3.5, 1.2, "Network layer\nCICIDS2017 (flows)", *g)
    _box(ax, 4.25, 10.4, 3.5, 1.2, "System layer\nBGL logs", *g)
    _box(ax, 8.2, 10.4, 3.5, 1.2, "Application layer\nTDA access logs", *g)
    _box(ax, 1.5, 8.7, 9.0, 1.0, "Ingestion & normalisation  (unified event schema)", *b)
    _box(ax, 1.5, 7.0, 9.0, 1.0, "Feature engineering  (52 / 10 / 6 per-layer features)", *b)
    _box(ax, 0.6, 5.0, 5.2, 1.3, "Per-layer detectors\nRF · XGBoost · LightGBM · SVM · MLP · IsoForest", *o)
    _box(ax, 6.2, 5.0, 5.2, 1.3, "Per-layer anomaly alerts\n(label, score, identifiers, timestamp)", *o)
    _box(ax, 1.3, 3.0, 9.4, 1.2, "Cross-layer correlation engine (Algorithm 1)\n+ learned second-stage incident classifier", *p)
    _box(ax, 2.6, 1.1, 6.8, 1.0, "REST / WebSocket API  →  Angular 17 dashboard", *b)

    for x in (2.05, 6.0, 9.95):
        _arrow(ax, (x, 10.4), (x, 9.75))
    _arrow(ax, (6, 8.7), (6, 8.05))
    _arrow(ax, (3.2, 7.0), (3.2, 6.35)); _arrow(ax, (3.2, 5.0), (6.0, 4.25))
    _arrow(ax, (8.8, 7.0), (8.8, 6.35)); _arrow(ax, (8.8, 5.0), (6.0, 4.25))
    _arrow(ax, (6, 3.0), (6, 2.15))
    fig.tight_layout()
    fig.savefig(FIG / "fig2_architecture.png", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Fig 3: window sensitivity
# --------------------------------------------------------------------------- #
def fig3():
    d = json.load(open(RES / "correlation_results.json"))
    rows = d["window_sensitivity"]
    W = [r["window_s"] for r in rows]
    P = [r["incident_precision"] for r in rows]
    R = [r["incident_recall"] for r in rows]
    F = [r["incident_f1"] for r in rows]
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.plot(W, P, "-o", color=OI["blue"], lw=2, ms=6, label="Incident precision")
    ax.plot(W, R, "-s", color=OI["orange"], lw=2, ms=6, label="Incident recall")
    ax.plot(W, F, "-^", color=OI["green"], lw=2, ms=6, label="Incident F1")
    ax.axvline(60, color=OI["grey"], ls="--", lw=1, alpha=0.7)
    ax.text(62, 0.30, "default W = 60 s", fontsize=8, color=OI["grey"])
    ax.set_xscale("log")
    ax.set_xticks(W); ax.set_xticklabels([str(w) for w in W])
    ax.set_xlabel("Correlation window  W  (seconds, log scale)")
    ax.set_ylabel("Incident-level score")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    fig.savefig(FIG / "fig3_window_sensitivity.png", bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Fig 4: per-model F1 across layers
# --------------------------------------------------------------------------- #
def fig4():
    path = RES / "model_results.json"
    d = json.load(open(path))
    order = ["rf", "xgboost", "lgbm", "svm", "mlp", "isolation_forest"]
    names = {"rf": "RF", "xgboost": "XGBoost", "lgbm": "LightGBM", "svm": "SVM",
             "mlp": "MLP", "isolation_forest": "IsoForest"}
    datasets = [k for k in ["CICIDS2017", "BGL", "TDA"] if k in d["datasets"]]
    colors = [OI["blue"], OI["orange"], OI["green"]]
    import numpy as np
    x = np.arange(len(order)); width = 0.26
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    for i, ds in enumerate(datasets):
        models = d["datasets"][ds]["models"]
        f1 = [models.get(m, {}).get("f1", {}).get("mean", 0) for m in order]
        sd = [models.get(m, {}).get("f1", {}).get("std", 0) for m in order]
        ax.bar(x + (i - 1) * width, f1, width, yerr=sd, capsize=2.5,
               color=colors[i], label=ds, edgecolor="white", linewidth=0.5)
    ax.set_xticks(x); ax.set_xticklabels([names[m] for m in order])
    ax.set_ylabel("Test F1 (mean ± SD, 5 seeds)")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.01))
    fig.tight_layout()
    fig.savefig(FIG / "fig4_model_comparison.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    import sys
    which = sys.argv[1:] or ["1", "2", "3", "4"]
    if "1" in which: fig1()
    if "2" in which: fig2()
    if "3" in which: fig3()
    if "4" in which:
        try: fig4()
        except Exception as e: print("fig4 skipped:", e)
    print("figures ->", FIG)
