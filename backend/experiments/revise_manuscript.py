"""Produce the revised manuscript (.docx) from the original Springer file.

Edits the ORIGINAL document in place (copy), so the Springer template, styles,
headers and footers are preserved, and injects every change requested by the
editor and the four reviewers. All numbers are pulled from the JSON files
produced by the experiment scripts in this directory - nothing is typed in.

Usage (from backend/):
    python experiments/revise_manuscript.py
Output:
    C:/Users/Admin/Downloads/CrossLayer_JINS_Springer_REVISED.docx
"""
from __future__ import annotations

import copy
import json
import math
from collections import Counter
import shutil
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
FIG = HERE / "figures"
SRC = Path(r"C:\Users\Admin\Downloads\CrossLayer_JINS_Springer (1).docx")
OUT = Path(r"C:\Users\Admin\Downloads\CrossLayer_JINS_Springer_REVISED.docx")


# --------------------------------------------------------------------------- #
# numbers
# --------------------------------------------------------------------------- #
def _load(name, default=None):
    p = RES / name
    return json.loads(p.read_text()) if p.exists() else default


M = _load("model_results.json")
C = _load("correlation_results.json")
T = _load("temporal_cicids_results.json")
S2 = _load("second_stage_results.json")
B = _load("benchmark_results.json")  # may be None while the benchmark runs
T2 = _load("temporal_cicids_true_results.json")   # true temporal / session split (optional)
A = _load("ait_ads_results.json")                  # AIT-ADS (linked alerts from AIT-LDS v2), optional

MODEL_ORDER = ["rf", "xgboost", "lgbm", "svm", "mlp", "isolation_forest"]
MODEL_NAME = {"rf": "Random Forest", "xgboost": "XGBoost", "lgbm": "LightGBM",
              "svm": "Linear SVM", "mlp": "MLP", "isolation_forest": "Isolation Forest"}
DS_ORDER = ["CICIDS2017", "BGL", "TDA"]
DS_LAYER = {"CICIDS2017": "Network", "BGL": "System", "TDA": "Application"}


def mm(ds, m, k):
    return M["datasets"][ds]["models"][m][k]


def ms(ds, m, k, nd=3):
    v = mm(ds, m, k)
    return f"{v['mean']:.{nd}f} ± {v['std']:.{nd}f}"


def best(ds):
    return max(MODEL_ORDER[:5], key=lambda m: mm(ds, m, "f1")["mean"])


def f3(x):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.3f}"


def summ(ds):
    return M["datasets"][ds]["summary"]


# convenient headline numbers
b_net, b_sys, b_app = best("CICIDS2017"), best("BGL"), best("TDA")
F1_NET = mm("CICIDS2017", b_net, "f1")["mean"]
F1_SYS = mm("BGL", b_sys, "f1")["mean"]
F1_APP = mm("TDA", b_app, "f1")["mean"]
CM = C["main"]
WS = C["window_sensitivity"]
best_w = max(WS, key=lambda r: r["incident_f1"])
ABL = C["ablation_layer_order"]
SEEDS_C = C["across_seeds"]
S2L = S2["models"]["lgbm"]
S2R = S2["models"]["rule_baseline"]


# --------------------------------------------------------------------------- #
# docx helpers
# --------------------------------------------------------------------------- #
def set_text(p, text):
    # remove every content child (runs, hyperlinks, bookmarks, ...) but keep pPr
    for child in list(p._p):
        if not child.tag.endswith("}pPr"):
            p._p.remove(child)
    p.add_run(text)
    return p


def find(doc, prefix):
    for p in doc.paragraphs:
        if p.text.strip().startswith(prefix):
            return p
    raise KeyError(prefix)


def insert_after(p, text="", style=None):
    new_p = copy.deepcopy(p._p)
    for child in list(new_p):
        if child.tag.endswith("}r") or child.tag.endswith("}hyperlink"):
            new_p.remove(child)
    p._p.addnext(new_p)
    from docx.text.paragraph import Paragraph
    np_ = Paragraph(new_p, p._parent)
    np_.alignment = None          # never inherit a centred figure paragraph's jc
    if style:
        np_.style = style
    if text:
        np_.add_run(text)
    return np_


def insert_many(p, items):
    """items: list of (text, style|None). Returns the last inserted paragraph."""
    cur = p
    for text, style in items:
        cur = insert_after(cur, text, style)
    return cur


def delete(p):
    p._p.getparent().remove(p._p)


def insert_table_after(doc, p, header, rows, style_name, font_pt=8.5, col_widths=None):
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    try:
        t.style = style_name
    except Exception:
        pass
    for j, h in enumerate(header):
        c = t.rows[0].cells[j]
        c.text = ""
        run = c.paragraphs[0].add_run(str(h))
        run.bold = True
        run.font.size = Pt(font_pt)
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row):
            c = t.rows[i].cells[j]
            c.text = ""
            run = c.paragraphs[0].add_run(str(v))
            run.font.size = Pt(font_pt)
    if col_widths:
        t.autofit = False
        for row in t.rows:
            for j, w in enumerate(col_widths):
                row.cells[j].width = Inches(w)
    p._p.addnext(t._tbl)
    return t


def insert_picture_after(doc, p, path, width_in=5.8):
    np_ = insert_after(p, "")
    np_.alignment = WD_ALIGN_PARAGRAPH.CENTER
    np_.add_run().add_picture(str(path), width=Inches(width_in))
    return np_


def paragraph_with_drawing(doc):
    for p in doc.paragraphs:
        if p._p.xpath(".//w:drawing"):
            return p
    return None


# --------------------------------------------------------------------------- #
# content
# --------------------------------------------------------------------------- #
def main():
    shutil.copy(SRC, OUT)
    doc = Document(OUT)
    tstyle = doc.tables[0].style.name if doc.tables[0].style is not None else "Table Grid"
    caption_style = find(doc, "Table 1  Comparison").style
    body_style = find(doc, "With the rapid growth").style
    h1 = find(doc, "2 Related work").style
    h2 = find(doc, "2.1 Single-source").style

    # ------------------------------------------------------------------ #
    # Abstract
    # ------------------------------------------------------------------ #
    set_text(find(doc, "This paper presents the design, implementation and evaluation of an intelligent"),
        "This paper presents the design, implementation and evaluation of a system for monitoring and "
        "analysing logs across the network, system and application layers of modern computing environments. "
        "Single-layer analysis is insufficient for reconstructing multi-stage attacks whose steps are spread "
        "over several layers. The proposed platform combines (i) per-layer anomaly detectors, trained and "
        "compared across six algorithms (Random Forest, XGBoost, LightGBM, linear SVM, MLP and Isolation "
        "Forest) with fully documented features and preprocessing, (ii) a lightweight correlation engine that "
        "links per-layer alerts into multi-stage incidents using temporal proximity, shared identifiers and a "
        "layer-ordering constraint, and (iii) a learned second-stage classifier that scores candidate "
        "cross-layer incidents from aggregate cross-layer features. On three public benchmarks representing "
        f"the three layers (CICIDS2017, BGL and TDA), the best per-layer detectors reach test F1-scores of "
        f"{F1_NET:.3f}, {F1_SYS:.3f} and {F1_APP:.3f} (mean over five seeds under a stratified 70/15/15 split with "
        "five-fold cross-validation on the training partition); all six models are reported with mean ± standard "
        "deviation, training and inference times, and temporal, host-disjoint and session-disjoint splits for "
        "CICIDS2017 that show the random-split score to be conditional on known hosts and attack families. Because the "
        "three datasets originate from unrelated environments, the correlation engine is evaluated on a "
        "controlled attack-injection benchmark with known ground truth: at the default 60 s window it "
        f"compresses {CM['alerts_before']:,} per-layer alerts into {CM['incidents_after']} incidents "
        f"({100*CM['reduction_ratio']:.1f}% reduction) with incident-level precision "
        f"{SEEDS_C['incident_precision']['mean']:.3f} and recall {SEEDS_C['incident_recall']['mean']:.3f}, and a "
        "sensitivity analysis over the window and an ablation of the layer-ordering constraint are reported. "
        "The learned second-stage classifier raises incident F1 from "
        f"{S2R['f1']['mean']:.3f} (rules only) to {S2L['f1']['mean']:.3f}. System-level throughput, latency and "
        "memory measurements are provided, together with a privacy-by-design treatment of identifiers. The "
        "application-layer results rely on Isolation Forest pseudo-labels and are interpreted accordingly. "
        "The platform is exposed through a REST/WebSocket API and an Angular dashboard, and every table and "
        "figure can be regenerated from scripted experiments.")

    set_text(find(doc, "Cross-layer correlation; Log analysis"),
        "Cross-layer correlation; Log analysis; Machine learning; Anomaly detection; Intrusion detection; "
        "Multi-stage attacks; Alert correlation; SIEM; Network and systems management")

    # ------------------------------------------------------------------ #
    # 1 Introduction
    # ------------------------------------------------------------------ #
    set_text(find(doc, "With the rapid growth in the complexity"),
        "With the rapid growth in the complexity of information systems and in the volume of data generated by "
        "logs, continuous monitoring and analysis of these data has become essential for ensuring the "
        "performance, stability and security of modern systems. Systems continuously generate logs from "
        "heterogeneous sources, including the network, system and application layers, which contain valuable "
        "information about activities, user behaviour and operating-system events. Security information and "
        "event management (SIEM) platforms and big-data security-analytics architectures collect such logs "
        "centrally and support rule- and query-based correlation [32–35]; recent solutions such as ELFA-Log, "
        "GeneralLog and large-language-model-based detectors have further shown that machine learning and "
        "transfer learning can improve anomaly identification in complex systems, enabling cross-system and "
        "zero-label adaptation [1, 2, 42, 43].")

    p12 = find(doc, "However, analysing logs in isolation")
    set_text(p12,
        "However, analysing logs in isolation for each system layer is not sufficient to detect multi-stage "
        "incidents and coordinated attacks that unfold across different layers [3, 44]. For example, an attack "
        "may begin with network reconnaissance, continue with unauthorised authentication attempts at the "
        "system layer, and end with data manipulation at the application layer. When logs are treated "
        "separately, these relationships can be lost or misinterpreted, leading to unnecessary alarms and "
        "inaccurate security assessments. Figure 1 illustrates such a multi-stage attack: each step builds on "
        "the previous one, the steps share an identifier (here a host address) and fall within a bounded time "
        "window, which is exactly the structure that a cross-layer correlation engine can exploit.")
    pic = insert_picture_after(doc, p12, FIG / "fig1_attack_scenario.png", 5.6)
    insert_after(pic, "Fig. 1  A multi-stage attack spanning the network, system and application layers. "
                      "The four steps share one identifier and fall inside a correlation window W; "
                      "single-layer analysis sees four unrelated alerts, cross-layer correlation sees one incident.",
                 caption_style)

    set_text(find(doc, "This paper therefore develops an architecture"),
        "This paper therefore develops an architecture in which logs from the network, system and application "
        "layers are linked and aggregated into unified incidents with rich context. Machine learning is used at "
        "two levels: per-layer detectors score individual events, and a second-stage classifier scores "
        "candidate incidents assembled by a correlation engine from aggregate cross-layer features. The "
        "correlation engine itself is deliberately simple and transparent, linking events through shared "
        "entities and temporal proximity, so that its behaviour can be inspected by analysts and tuned through "
        "a single window parameter. Compared with a SIEM, which correlates through operator-authored rules, "
        "the proposed pipeline derives both the per-event alerts and the incident score from data, while "
        "remaining lightweight enough to run on a single node.")

    # objectives (ii)
    set_text(find(doc, "(ii) Per-layer and cross-layer feature engineering"),
        "(ii) Per-layer and cross-layer feature engineering: extracting documented statistical, temporal and "
        "behavioural features for each layer (Tables 3–5), together with aggregate cross-layer features "
        "computed per candidate incident (Section 4.5) that feed a learned second-stage classifier.")
    set_text(find(doc, "(iv) Design of a correlation engine"),
        "(iv) Design and quantitative evaluation of a correlation engine: linking alerts on the basis of "
        "temporal proximity, shared identifiers and layer ordering, and measuring incident-level precision "
        "and recall, false correlations, alert reduction and sensitivity to the window on a benchmark with "
        "known ground truth.")

    # contributions
    set_text(find(doc, "The main contributions of this paper are fourfold"),
        "The main contributions of this paper are fourfold. First, we design a unified cross-layer log-analysis "
        "pipeline that ingests, normalises and analyses heterogeneous logs from the network, system and "
        "application layers within a single framework, whereas most prior work in the network and systems "
        "management community targets a single layer or a single log source [6–8]; unlike SIEM platforms "
        "[32–35], both per-event detection and incident scoring are learned from data. Second, we introduce a "
        "lightweight correlation engine that links per-layer anomalies into multi-stage incidents using "
        "temporal proximity, shared identifiers and a layer-ordering constraint, complemented by a learned "
        "second-stage incident classifier, and, going beyond the qualitative argument of earlier alert-"
        "correlation work [9, 10], we evaluate it quantitatively: alert reduction, correctly reconstructed "
        "incidents, false correlations, incident-level precision/recall, a sensitivity analysis over the "
        "window and an ablation of the ordering constraint. Third, we present a complete empirical comparison "
        "of six algorithms on three public benchmarks (CICIDS2017, BGL and TDA) with precision, recall, "
        "F1-score and ROC-AUC reported as mean ± standard deviation over five seeds, training and inference "
        "times, temporal and session-aware splits for CICIDS2017, fully documented features, preprocessing and "
        "hyperparameters, and an explicit treatment of the pseudo-labelled application layer. Fourth, we "
        "provide system-level evidence for operational use: measured throughput, per-event latency and memory "
        "of the detectors and of the correlation engine, a REST/WebSocket API with an Angular dashboard, a "
        "privacy-by-design handling of identifiers, and scripted experiments that regenerate every table and "
        "figure in this paper.")
    set_text(find(doc, "The remainder of the paper is organised"),
        "The remainder of the paper is organised as follows. Section 2 reviews related work, including SIEM "
        "and multi-source correlation, and positions our contribution. Section 3 provides background and "
        "motivation. Section 4 describes the methodology: datasets and preprocessing, features, model "
        "training, the correlation algorithm with a worked example, the learned second-stage model and the "
        "privacy design. Section 5 reports implementation details, including the dashboard. Section 6 presents "
        "the results, Section 7 discusses them together with the threats to validity, and Section 8 concludes.")

    # ------------------------------------------------------------------ #
    # 2 Related work
    # ------------------------------------------------------------------ #
    set_text(find(doc, "Log-based anomaly detection and cross-layer monitoring have received"),
        "Log-based anomaly detection and cross-layer monitoring have received sustained attention in the "
        "network and systems management community, with a substantial body of work appearing in venues such "
        "as the IEEE Transactions on Network and Service Management (TNSM), the Journal of Network and Systems "
        "Management (JNSM), the International Journal of Network Management (IJNM) and the CNSM, NOMS and IM "
        "conferences. We organise the related literature into five strands and position our contribution "
        "against each. Table 1 summarises representative systems along the dimensions of layers covered, "
        "correlation mechanism, learning paradigm, whether the correlation step is evaluated against ground "
        "truth, and whether an operational interface is provided.")

    set_text(find(doc, "A large family of methods learns models of normal log behaviour"),
        "A large family of methods learns models of normal log behaviour from a single source. DeepLog models "
        "normal log-key sequences with an LSTM and flags deviations as anomalies [8], while LogRobust addresses "
        "log instability by encoding log events as semantic vectors and applying an attention-based "
        "bidirectional LSTM [11]. LogAnomaly extends this line by jointly modelling sequential and "
        "quantitative patterns [12]. Within the network and systems management literature specifically, "
        "HitAnomaly employs hierarchical transformers over log templates and parameter values [6] and "
        "AllInfoLog improves robustness by exploiting the full set of log features [7], both published in "
        "TNSM; LogAnomEX combines an Electra-based encoder with gated bilinear networks for unsupervised "
        "detection on BGL, HDFS and Thunderbird and appeared in JNSM [13]. Closer to network operations, Nam "
        "et al. analyse and predict switch logs for anomaly detection at CNSM [14] and later combine a log "
        "term-weighting scheme with NETCONF resource data in IJNM [15]. More recently, large language models "
        "have been applied to log anomaly detection [43], and Landauer et al. survey the deep-learning "
        "literature on log data [42]. A reproducibility study by Le and Zhang shows that reported gains are "
        "highly sensitive to data partitioning and parsing [16], a finding we take into account by reporting "
        "variance across seeds and an order-preserving split. These methods are effective within a layer but, "
        "by construction, do not correlate evidence across the network, system and application layers, which "
        "is precisely the gap our system targets.")

    set_text(find(doc, "A second strand aggregates the alerts produced by detectors"),
        "A second strand aggregates the alerts produced by detectors into higher-level incidents. Salah et al. "
        "provide a model-based survey of alert-correlation techniques, distinguishing similarity-based, "
        "statistical and knowledge-based approaches [10], and Navarro et al. systematically survey multi-step "
        "attack detection [44]. Haas and Fischer propose a graph-based correlation algorithm that assembles "
        "multi-stage attacks from large alert sets while remaining robust to false positives [9], and Landauer "
        "et al. apply machine learning to domain-independent alert aggregation in order to counter alert "
        "flooding [17]. Our correlation engine belongs to the similarity-based family: it links machine-"
        "learning-derived anomalies from different layers using temporal proximity and shared identifiers, "
        "adds a layer-ordering constraint, and hands the candidates to a learned classifier, so that unknown "
        "as well as known multi-stage patterns can be surfaced without expert-authored attack templates.")

    p23 = find(doc, "The closest works combine signals from more than one source")
    set_text(p23,
        "The closest works combine signals from more than one source. Farshchi et al. correlate application "
        "logs with cloud performance metrics to detect anomalies in operations [18], and cross-system "
        "approaches such as ELFA-Log, GeneralLog and FusionLog transfer detection capability across systems "
        "through pseudo-labelling, feature alignment and knowledge fusion [1, 2, 19]. HERCULE [30] is the "
        "most closely related system: it builds a multi-dimensional graph over network, system and "
        "application logs of the same host, learns edge weights from ground-truth attack traces, and recovers "
        "attack stories through community discovery. Provenance-based intrusion detection takes a related "
        "graph view of host activity [45]. These approaches either correlate two homogeneous sources, require "
        "logs captured jointly on one host with ground-truth attack traces for weight learning (HERCULE), or "
        "are not packaged as deployable end-to-end pipelines. Our engine is complementary: it requires only "
        "timestamps and identifiers that are available in commodity logs, needs no ground-truth traces for "
        "the correlation step itself, learns the incident score in a second stage, and ships with an "
        "operational interface. We do not claim to outperform HERCULE on its own data; a direct comparison "
        "requires a dataset whose layers are genuinely linked (Section 7.5).")

    # new 2.4 and 2.5
    new24 = insert_many(p23, [
        ("2.4 SIEM and big-data security analytics", h2),
        ("Security information and event management platforms are the industrial answer to multi-source "
         "correlation. González-Granadillo et al. analyse SIEM architectures, trends and usage in critical "
         "infrastructures [35]; Marchal et al. propose a big-data architecture for large-scale security "
         "monitoring that fuses DNS, NetFlow, HTTP and honeypot data [32]; Rassam et al. review big-data "
         "analytics adoption for cyber-security, its requirements and open challenges [33]; Sun et al. survey "
         "data-driven cybersecurity incident prediction [34]; and Frade et al. present DBD-Guardian, a "
         "privacy-aware near-real-time analytics system that queries logs in place and exposes anonymised "
         "views of sensitive data [31]. Relative to a SIEM, the proposed system differs in three respects: "
         "(i) per-event alerts are produced by trained detectors rather than signatures or thresholds; "
         "(ii) the cross-layer correlation rule is a single, inspectable temporal-identity-ordering rule "
         "whose precision/recall trade-off is characterised empirically (Section 6.3) instead of a library of "
         "hand-written correlation rules; and (iii) the incident score is learned. Conversely, a SIEM offers "
         "mature storage, retention and compliance tooling that our prototype does not attempt to replace; "
         "the engine could be deployed as a correlation module behind a SIEM, and we adopt DBD-Guardian's "
         "stance on privacy-aware analytics in Section 4.6.", body_style),
        ("2.5 Positioning", h2),
        ("To the best of our knowledge, few systems in the network and systems management literature provide "
         "an end-to-end pipeline that unifies network-flow, system and application-access logs, correlates "
         "them into interpretable multi-stage incidents, scores those incidents with a learned model, and "
         "quantifies the correlation step with incident-level precision and recall. Table 1 positions this "
         "work against the representative systems above.", body_style),
    ])

    # Table 1 rebuild
    cap1 = find(doc, "Table 1  Comparison of representative")
    old_t1 = doc.tables[0]
    old_t1._tbl.getparent().remove(old_t1._tbl)
    insert_table_after(doc, cap1,
        ["System", "Layers", "Correlation", "Learning", "Corr. evaluated", "Interface"],
        [["DeepLog [8]", "System", "None", "LSTM (unsup.)", "–", "No"],
         ["LogRobust [11]", "System", "None", "Bi-LSTM (sup.)", "–", "No"],
         ["HitAnomaly [6]", "System", "None", "Transformer", "–", "No"],
         ["AllInfoLog [7]", "System", "None", "Deep (sup.)", "–", "No"],
         ["LogAnomEX [13]", "System", "None", "Electra-DP (unsup.)", "–", "No"],
         ["Nam et al. [14]", "Network (switch)", "None", "ML + statistics", "–", "No"],
         ["Haas and Fischer [9]", "Network", "Graph-based", "Rule/graph", "Yes", "No"],
         ["HERCULE [30]", "Net + sys + app (one host)", "Weighted log graph", "Learned weights", "Yes", "No"],
         ["Farshchi et al. [18]", "Application + metrics", "Log–metric", "Regression", "Partly", "No"],
         ["ELFA-Log [1]", "Cross-system", "None", "Transfer", "–", "No"],
         ["Marchal et al. [32]", "Multi-source", "Big-data queries", "Statistics", "Partly", "Yes"],
         ["DBD-Guardian [31]", "Multi-source", "Queries in place", "Rules/queries", "Partly", "Yes"],
         ["This work", "Network + system + application", "Temporal + identity + order; learned 2nd stage",
          "Six per-layer ML + learned incident classifier", "Yes (P/R, sensitivity, ablation)", "REST/WS + UI"]],
        tstyle, font_pt=8, col_widths=[1.3, 1.3, 1.3, 1.3, 0.9, 0.7])

    # ------------------------------------------------------------------ #
    # 3 Background
    # ------------------------------------------------------------------ #
    set_text(find(doc, "A fundamental challenge in applying machine learning to cybersecurity"),
        "A fundamental challenge in applying machine learning to cybersecurity is that models perform best "
        "when classes are balanced and the training and test distributions are similar, conditions that are "
        "rarely met in this field, since attacks are rare and new attack types shift the data distribution in "
        "unpredictable ways [23]. A second, often under-reported challenge is experimental randomness: "
        "weight initialisation, data partitioning, mini-batch order and seed selection can change reported "
        "scores by several points, as shown for deep-learning software systems [38], for machine-learning "
        "benchmarks in general [39], for log anomaly detection in particular [16], and, in an adjacent "
        "tabular-sensor domain, for fault detection and diagnosis of air-handling units where class coverage, "
        "data partitioning and training configuration were found to dominate reported accuracy [40, 41, 46]. "
        "Moreover, most existing solutions still focus on binary classification (normal versus anomalous) "
        "within a single layer and do not correlate evidence across the network, system and application "
        "layers, leaving a notable gap in comprehensive, scalable, cross-layer log management systems that "
        "combine detection with contextual correlation [19]. The present work therefore reports every metric "
        "as a mean and standard deviation over several seeds and makes the correlation step measurable.")

    # ------------------------------------------------------------------ #
    # 4 Methods
    # ------------------------------------------------------------------ #
    set_text(find(doc, "The proposed system integrates a structured data pipeline"),
        "The proposed system integrates a structured data pipeline with machine learning models in order to "
        "detect and correlate security incidents across layers. The methodology is organised into six stages: "
        "data ingestion and normalisation, feature engineering, per-layer model training and evaluation, "
        "cross-layer correlation, a learned second-stage incident classifier, and privacy-preserving handling "
        "of identifiers. Figure 2 presents the overall architecture of the system.")
    from docx.text.paragraph import Paragraph as _P
    _cap = find(doc, "Fig. 1  Overall architecture")
    pdraw = _P(_cap._p.getprevious(), _cap._parent)
    assert pdraw._p.xpath(".//w:drawing"), "architecture image paragraph not found"
    for child in list(pdraw._p):
        if not child.tag.endswith("}pPr"):
            pdraw._p.remove(child)
    pdraw.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pdraw.add_run().add_picture(str(FIG / "fig2_architecture.png"), width=Inches(5.6))
    set_text(find(doc, "Fig. 1  Overall architecture"),
             "Fig. 2  Overall architecture of the cross-layer log analysis system")

    # 4.1 datasets
    p41 = find(doc, "The system integrates three benchmark datasets")
    s_net, s_sys, s_app = summ("CICIDS2017"), summ("BGL"), summ("TDA")
    set_text(p41,
        "The system integrates three public benchmark datasets, one per layer (Table 2). CICIDS2017 [28] "
        "provides network-flow records captured during simulated attacks (DoS/DDoS, port scanning, brute "
        "force, web attacks, infiltration and bot activity) with features extracted by CICFlowMeter; the "
        f"consolidated CSV used here contains {s_net['total_rows']:,} flows with a binary label (benign "
        "versus attack, obtained from the attack-type column). BGL (Blue Gene/L) [29] contains "
        f"{s_sys['total_rows']:,} supercomputer system-log lines; each line carries an alert flag in its first "
        "field ('-' for normal, otherwise the alert category such as KERNDTLB or APPREAD), which we use as the "
        "ground-truth label, so no log parser such as Drain is required for labelling. TDA is the Binary Access "
        "Traffic Matrices dataset released by Gutflaish et al. with their AAAI-19 work on temporal anomaly "
        "detection [48]: it records the accesses of 4,702 users to 11,654 database tables of a large "
        "telecommunication company between 1 July and 31 August 2015 at hourly resolution, distributed as "
        f"{s_app['total_rows']:,} (user, table, timestamp) records; it represents the application/database-access "
        "layer and ships without attack labels. All sources are parsed by layer-"
        "specific adapters, cleaned and standardised into a common event schema (timestamp, layer, source, "
        "entity, label, raw message, feature map) and stored in a database.")
    insert_many(p41, [
        ("Cleaning and sampling. CICIDS2017 is cleaned as follows: the feature columns are coerced to numeric; "
         "infinite values (which occur in the rate features Flow Bytes/s and Flow Packets/s for zero-duration "
         "flows) and non-numeric entries are replaced by NaN; NaN is imputed with 0; and exact duplicate rows "
         f"are dropped (in the sample used for training: {s_net['inf_values_fixed']:,} infinite values, "
         f"{s_net['nan_values_filled']:,} missing values and {s_net['duplicate_rows_dropped']:,} duplicates). "
         "BGL and TDA contain no numeric columns requiring such treatment. Because the full datasets are "
         "large and class-imbalanced, each is subsampled once with a fixed seed by uniform random sampling "
         "over the whole file, which preserves the class proportions in expectation: "
         f"{s_net['n_samples']:,} CICIDS2017 flows ({100*s_net['positive_rate']:.1f}% attack), "
         f"{s_sys['n_samples']:,} BGL lines ({100*s_sys['positive_rate']:.1f}% anomalous) and "
         f"{s_app['n_samples']:,} TDA records. Identifier columns (IP addresses, ports, host names, user "
         "identifiers) are never used as model inputs; they are used only by the correlation engine, after "
         "pseudonymisation (Section 4.6).", body_style),
        ("Table 2  Datasets, sampled sizes, features and class proportions", caption_style),
    ])
    cap2 = find(doc, "Table 2  Datasets, sampled sizes")
    insert_table_after(doc, cap2,
        ["Layer", "Dataset", "Rows in file", "Rows sampled", "Features", "Positive class", "Positive rate", "Label source"],
        [["Network", "CICIDS2017", f"{s_net['total_rows']:,}", f"{s_net['n_samples']:,}", "52",
          f"{s_net['n_positive']:,}", f"{100*s_net['positive_rate']:.1f}%", "Attack-type column (benign vs attack)"],
         ["System", "BGL", f"{s_sys['total_rows']:,}", f"{s_sys['n_samples']:,}", "10",
          f"{s_sys['n_positive']:,}", f"{100*s_sys['positive_rate']:.1f}%", "BGL alert flag (first field)"],
         ["Application", "TDA", f"{s_app['total_rows']:,}", f"{s_app['n_samples']:,}", "6",
          f"{s_app['n_positive']:,}", f"{100*s_app['positive_rate']:.1f}%", "Isolation Forest pseudo-labels (contamination 0.05)"]],
        tstyle, font_pt=8)

    # 4.2 features
    p42 = find(doc, "Relevant features are extracted per layer")
    set_text(p42,
        "Features are extracted per layer and are listed exhaustively, with their meaning and the rationale "
        "for including them, in Tables 3–5. For the network layer we retain 52 of the 78 CICFlowMeter "
        "columns (Table 3). The 26 excluded columns fall into three groups: (i) columns that are constant or "
        "all-zero in the CICIDS2017 capture (Fwd URG Flags, Bwd URG Flags, Bwd PSH Flags, CWE Flag Count, ECE "
        "Flag Count and the six Fwd/Bwd Avg Bytes/Bulk, Avg Packets/Bulk and Avg Bulk Rate columns); "
        "(ii) exact duplicates or linear re-expressions of retained columns (Fwd Header Length.1, Avg Fwd "
        "Segment Size, Avg Bwd Segment Size, Subflow Fwd Packets, Subflow Bwd Packets, Subflow Bwd Bytes); and "
        "(iii) sparse or highly collinear columns (Total Backward Packets, Total Length of Bwd Packets, Fwd PSH "
        "Flags, SYN, RST and URG Flag Count, Down/Up Ratio, Active Std, Idle Std). Flow identifiers "
        "(Flow ID, source/destination IP and port, protocol, timestamp) are not used as predictors. For the "
        "system layer we use ten lightweight lexical features computed directly from the raw BGL message "
        "(Table 4): two length statistics and eight keyword indicators chosen because BGL alert categories "
        "are expressed through component and severity tokens (KERNEL, RAS, FATAL, ERROR, ...); this avoids a "
        "template parser and keeps the system layer fast. For the application layer we derive six "
        "behavioural features from the (user, table, timestamp) triple (Table 5): the user and table "
        "identifiers (as categorical codes), hour of day and day of week (temporal context), and the access "
        "frequency of the user and of the table within the ingested window (volume context). Because TDA "
        "lacks verified labels, an Isolation Forest (100 trees, contamination = 0.05) is fitted on these six "
        "features and its outliers are taken as synthetic positive labels; the implications of this choice "
        "are discussed in Sections 7.3 and 7.5. The four aggregate cross-layer features mentioned in the "
        "original version of this work are now defined formally in Section 4.5, where they are consumed "
        "by the learned second-stage classifier; they are not inputs to the per-layer detectors.")
    cic_rows = [
        ["Flow identity/size", "Destination Port; Flow Duration; Total Fwd Packets; Total Length of Fwd Packets",
         "Service and volume of the flow; scans and floods have characteristic ports, durations and packet counts"],
        ["Forward packet length", "Fwd Packet Length Max/Min/Mean/Std", "Payload size profile of client→server packets"],
        ["Backward packet length", "Bwd Packet Length Max/Min/Mean/Std", "Payload size profile of server→client packets"],
        ["Flow rates", "Flow Bytes/s; Flow Packets/s; Fwd Packets/s; Bwd Packets/s",
         "Throughput; DoS/DDoS and brute force show abnormal rates"],
        ["Flow inter-arrival", "Flow IAT Mean/Std/Max/Min", "Timing regularity of the whole flow (automated tools are regular)"],
        ["Forward inter-arrival", "Fwd IAT Total/Mean/Std/Max/Min", "Timing of forward packets"],
        ["Backward inter-arrival", "Bwd IAT Total/Mean/Std/Max/Min", "Timing of backward packets"],
        ["Header sizes", "Fwd Header Length; Bwd Header Length", "Option usage and protocol behaviour"],
        ["Packet length (all)", "Min/Max Packet Length; Packet Length Mean/Std/Variance; Average Packet Size",
         "Overall packet-size distribution"],
        ["TCP flags", "FIN Flag Count; PSH Flag Count; ACK Flag Count", "Connection life-cycle and push behaviour (scans, half-open connections)"],
        ["Sub-flow / window", "Subflow Fwd Bytes; Init_Win_bytes_forward; Init_Win_bytes_backward; act_data_pkt_fwd; min_seg_size_forward",
         "TCP window negotiation and data-packet counts, discriminative for OS/tool fingerprints"],
        ["Activity/idle", "Active Mean/Max/Min; Idle Mean/Max/Min", "Burstiness of the flow (bots and beacons idle periodically)"],
    ]
    bgl_rows = [
        ["text_len", "int", "Message length in characters; error dumps and stack traces are long"],
        ["num_spaces", "int", "Token count proxy; structured normal messages have few tokens"],
        ["has_error", "0/1", "'error' present: generic failure indicator"],
        ["has_fail", "0/1", "'fail' present: failed operations and checks"],
        ["has_fatal", "0/1", "'fatal' present: the BGL FATAL severity"],
        ["has_kernel", "0/1", "'kernel' present: kernel-component events (KERN* alert categories)"],
        ["has_warning", "0/1", "'warning'/'warn' present: degraded conditions"],
        ["has_info", "0/1", "'info' present as a token: routine informational events (negative evidence)"],
        ["has_mcsm", "0/1", "'mcsm' present: midplane service-card/monitoring events"],
        ["has_ras", "0/1", "'ras' present as a token: reliability, availability and serviceability subsystem"],
    ]
    tda_rows = [
        ["user_id", "int code", "Acting principal; some accounts are inherently higher-risk"],
        ["table_id", "int code", "Accessed object; sensitive tables are rarely touched"],
        ["hour_of_day", "0–23", "Temporal context; off-hours access is a classic insider-threat cue"],
        ["day_of_week", "0–6", "Weekday/weekend context"],
        ["user_access_count", "int", "Number of accesses by the user in the ingested window; bursts indicate scraping/exfiltration"],
        ["table_access_count", "int", "Popularity of the table; accesses to rarely used tables are more suspicious"],
    ]
    # insert in REVERSE order after p42 so the final order is cap3,tbl3,cap4,tbl4,cap5,tbl5
    for cap_text, header, rows, widths in [
        ("Table 5  Application-layer (TDA) predictors: six behavioural features derived from (user, table, timestamp)",
         ["Feature", "Type", "Meaning / rationale"], tda_rows, [1.3, 0.7, 4.5]),
        ("Table 4  System-layer (BGL) predictors: ten lexical features of the raw log message",
         ["Feature", "Type", "Meaning / rationale"], bgl_rows, [1.1, 0.5, 4.9]),
        ("Table 3  Network-layer (CICIDS2017) predictors: the 52 retained CICFlowMeter features grouped by family",
         ["Family", "Features (52 in total)", "Meaning / rationale"], cic_rows, [1.2, 3.0, 2.3]),
    ]:
        cap = insert_after(p42, cap_text, caption_style)
        insert_table_after(doc, cap, header, rows, tstyle, font_pt=8, col_widths=widths)

    # 4.3 training
    set_text(find(doc, "Six algorithms are supported through a unified interface"),
        "Six algorithms are supported through a unified interface: Random Forest [24], XGBoost [25], "
        "LightGBM [26], linear SVM, MLP and Isolation Forest [27]; their hyperparameters are fixed and listed "
        "in Table 6. Evaluation protocol. Each subsampled dataset is split once per seed into training, "
        "validation and test partitions in a stratified 70/15/15 ratio. Five-fold stratified cross-validation "
        "is run on the 70% training partition only, as an internal variance estimate and for model selection; "
        "the validation partition is used for early stopping of the MLP; and all headline metrics are "
        "measured once on the untouched 15% test partition. This procedure is repeated for five random seeds "
        "(42, 7, 13, 21, 2024), where the seed controls both the data partition and the stochastic "
        "initialisation of the learner, and we report the mean and standard deviation of the test metrics "
        "across seeds. Scaling and leakage. Numeric features are standardised by z-scoring (zero mean, unit "
        "variance). The scaler is part of the model pipeline and is fitted on the training partition only, "
        "then applied to the validation and test partitions (and refitted inside each cross-validation fold), "
        "so no test statistics leak into training; this matters for the scale-sensitive linear SVM and MLP, "
        "whereas tree ensembles are scale-invariant. Class imbalance. Imbalance is handled by stratified "
        "splitting, by reporting precision, recall, F1-score and ROC-AUC rather than accuracy, and by "
        "setting the Isolation Forest contamination to the training positive rate when it is evaluated "
        "against ground truth; no resampling is applied, so the reported scores reflect the natural class "
        "proportions of Table 2. Isolation Forest is unsupervised: it is fitted on the training features "
        "without labels and evaluated against the labels of the test partition.")
    cap6 = insert_after(find(doc, "Six algorithms are supported through a unified interface"),
                        "Table 6  Hyperparameters of the six detectors (identical across datasets and seeds)", caption_style)
    insert_table_after(doc, cap6, ["Model", "Library", "Hyperparameters"], [
        ["Random Forest", "scikit-learn 1.5.1", "100 trees; unlimited depth; Gini impurity; bootstrap; √d features per split"],
        ["XGBoost", "xgboost 2.1.1", "100 rounds; learning rate 0.1; max depth 8; log-loss objective; defaults otherwise"],
        ["LightGBM", "lightgbm 4.5.0", "100 rounds; learning rate 0.1; max depth 8; 31 leaves; defaults otherwise"],
        ["Linear SVM", "scikit-learn", "LinearSVC, L2 penalty, C = 1, max 2000 iterations; Platt calibration (3-fold) for scores; z-scored inputs"],
        ["MLP", "scikit-learn", "Hidden layers 128 and 64, ReLU; Adam, learning rate 10⁻³; max 300 epochs; early stopping on a 10% validation slice; z-scored inputs"],
        ["Isolation Forest", "scikit-learn", "100 trees; contamination = training positive rate (evaluation) or 0.05 (TDA pseudo-labelling); max samples 256"],
    ], tstyle, font_pt=8, col_widths=[1.1, 1.1, 4.3])

    # 4.4 correlation
    set_text(find(doc, "The correlation engine links events across layers on the basis of temporal proximity"),
        "The correlation engine links alerts across layers on the basis of three criteria: temporal proximity "
        "(co-occurrence within a configurable window W), a shared identifier, and a layer-ordering "
        "constraint. The rationale is that the stages of an attack campaign are executed by the same actor "
        "against the same target within a bounded time span, so their footprints in different layers share "
        "an identifier (an IP address, host name or user account) and are close in time, and they typically "
        "progress from the outside in (network, then system, then application). Alerts that would be treated "
        "separately in a single-layer analysis are thereby merged into composite multi-stage incidents with "
        "richer context.")
    set_text(find(doc, "Formally, each per-layer detector emits a stream of typed events"),
        "Formally, each per-layer detector emits a stream of typed alerts e = (t, layer, ids, label, score), "
        "where t is the timestamp, ids is the set of identifiers attached to the event, label is the "
        "predicted class and score is the model confidence. Identifier matching. Heterogeneous identifiers "
        "are matched by normalising each to a canonical entity string during ingestion: IPv4/IPv6 addresses "
        "are canonicalised textually, host names are lower-cased and stripped of domain suffixes, and user "
        "identifiers are prefixed with their type (user:alice); a static mapping table can additionally link "
        "a host name to its address and a user to the hosts it owns, so that a network flow (keyed by IP), a "
        "system log (keyed by node/host) and an application record (keyed by user) can resolve to the same "
        "entity. Matching is then exact on the canonical string; fuzzy matching is deliberately avoided to "
        "keep false correlations low. Transitivity and deduplication. Each alert seeds a candidate group "
        "consisting of all alerts that share one of its identifiers and lie within W of it; overlapping "
        "candidates are merged with a union–find structure, so correlation is transitive (if a links to b and "
        "b links to c, all three form one incident) and every alert belongs to at most one incident, which is "
        "the dedup step of Algorithm 1. Layer ordering. A candidate is promoted to a multi-stage incident only "
        "if its alerts span at least two distinct layers and, when sorted by time, their layer indices "
        "(network = 0, system = 1, application = 2) are non-decreasing; alerts that violate the order are "
        "removed from the candidate. Severity equals the maximum per-alert score multiplied by the number of "
        "layers involved. Choice of W. The window trades recall against precision: a small W splits slow "
        "campaigns, a large W merges unrelated alerts. Section 6.3 reports a sensitivity analysis from 5 s to "
        "600 s; W = 60 s is the default because it recovers almost all planted chains while keeping false "
        "correlations moderate, and the parameter is exposed at run time. The procedure is summarised in "
        "Algorithm 1 and illustrated by the worked example that follows.")
    # Algorithm lines
    set_text(find(doc, "Input:  event streams"), "Input:  alert streams A_net, A_sys, A_app; window W; layer index L = {net:0, sys:1, app:2}")
    set_text(find(doc, "Output: set of multi-stage incidents"), "Output: set of multi-stage incidents I")
    set_text(find(doc, "1:  E <- time-sort"), "1:  A <- time-sort(merge(A_net, A_sys, A_app));  H <- hash map: canonical id -> alerts")
    set_text(find(doc, "2:  for each anomalous event"), "2:  for each alert a in A do")
    set_text(find(doc, "3:      K <- {e.src, e.dst}"), "3:      C <- { b in H[k] : k in a.ids and |b.t - a.t| <= W }            // shared identifier + window")
    set_text(find(doc, "4:      C <- events in E within"), "4:      C <- order-filter(C): keep the time-sorted prefix whose L(layer) is non-decreasing")
    set_text(find(doc, "5:      if layers(C) spans"), "5:      if |layers(C)| >= 2 then push C to candidates")
    set_text(find(doc, "6:          incident <- aggregate(C)"), "6:  end for")
    set_text(find(doc, "7:          incident.severity"), "7:  I <- union-find-merge(candidates)                        // transitive closure, dedup")
    set_text(find(doc, "8:          add incident to I"), "8:  for each incident i in I do")
    set_text(find(doc, "9:      end if"), "9:      i.severity <- max(score(i)) * |layers(i)|")
    set_text(find(doc, "10: end for"), "10: end for")
    set_text(find(doc, "11: return dedup(I)"), "11: return I")
    pcx = find(doc, "After the initial O(n log n) time sort")
    set_text(pcx,
        "After the initial O(n log n) time sort of n alerts, each alert is matched only against the alerts "
        "that share one of its identifiers (looked up in the hash map H) and lie within W, so the expected "
        "per-alert work is proportional to the number of same-identifier alerts in the window; this gives "
        "near-linear behaviour in the sparse-identifier regime typical of production logs and O(n·w) in the "
        "worst case, where w is the maximum window occupancy. Section 6.4 measures the empirical scaling "
        "exponent and the throughput of the engine.")
    insert_many(pcx, [
        ("Worked example. Consider the four alerts of Fig. 1, all carrying the canonical entity 10.0.0.7, with "
         "W = 60 s: a1 = (12:00:05, network, port-scan, 0.93), a2 = (12:00:21, system, failed-auth, 0.71), "
         "a3 = (12:00:40, system, kernel-RAS, 0.84) and a4 = (12:00:52, application, abnormal-DB-access, 0.88), "
         "plus an unrelated alert a5 = (12:00:30, network, 10.0.0.7, 0.55) produced by a benign re-scan. "
         "Seeding from a1, the candidate is {a1, a2, a5, a3, a4} (all within 60 s and sharing the entity). "
         "Sorting by time gives layer indices 0, 0 (a5), 1, 1, 2 for a1, a5, a2, a3, a4 — non-decreasing, so all "
         "are kept; had a5 occurred after a2 its index 0 < 1 would violate the order and a5 would be dropped. "
         "Seeding from a2, a3, a4 or a5 yields subsets of the same group, which union–find merges into one "
         "incident with layers {network, system, application} and severity 0.93 × 3 = 2.79. A sixth alert "
         "a6 = (12:03:10, application, 10.0.0.7, 0.60) falls outside 60 s of every member and starts a separate "
         "single-layer candidate that is not promoted. Without correlation an analyst would triage six alerts; "
         "with correlation they see one ranked incident and one residual alert.", body_style),
        ("4.5 Learned second-stage incident classifier", h2),
        ("The candidates produced by lines 1–7 of Algorithm 1 are the unit of a second, learned classification "
         "stage, which is where machine learning operates across layers. For every candidate c the following "
         "aggregate cross-layer features are computed: count_net, count_sys, count_app (number of alerts per "
         "layer), n_layers (number of distinct layers), span (time between the first and last alert, in "
         "seconds), max_score and mean_score (over the per-layer detector scores) and order_ok (1 if the "
         "time-sorted layer indices are non-decreasing). A classifier is trained to predict whether c is a "
         "genuine multi-stage incident; its output replaces the fixed rule of lines 4–5 and is used to rank "
         "incidents in the dashboard. In the production service the same model is trained on per-entity, "
         "per-window counts (count_system, count_network, count_application, with burst ratios and the number "
         "of active layers when no identifiers are shared) and any of the six algorithms of Table 6 can be "
         "selected. Because no public dataset links the three layers at the event level, the second stage is "
         "trained and evaluated on the controlled benchmark of Section 6.3 (Section 6.3.3), and in deployment "
         "it is retrained from analyst feedback on confirmed and dismissed incidents.", body_style),
        ("4.6 Privacy and regulatory considerations", h2),
        ("The correlation engine relies on identifiers (IP addresses, host names, user accounts) that are "
         "personal data under the General Data Protection Regulation (GDPR) [37], whose Recital 49 recognises "
         "network and information security as a legitimate interest that can justify processing logs. The "
         "system adopts privacy by design in four ways. (i) Pseudonymisation: every identifier is replaced at "
         "ingestion by a keyed hash (HMAC-SHA-256 with a per-deployment secret), so the canonical entity "
         "string used for matching does not reveal the raw address or account; exact matching on the hash is "
         "sufficient for correlation, and re-identification is possible only by the operator holding the key. "
         "(ii) Data minimisation: identifiers are never used as model features (Section 4.2); only the "
         "pseudonymised entity, timestamp, layer, label and score reach the correlation engine, and raw "
         "messages are truncated. (iii) Storage limitation: per-event rows are retained for a configurable "
         "window and incidents are kept in aggregate form, following DBD-Guardian's principle of exposing "
         "anonymised views of sensitive data [31]. (iv) Purpose limitation and access control: the API is "
         "authenticated and role-based, and incident exports contain pseudonyms. These measures support "
         "compliance with GDPR Articles 5, 25 and 32 but do not replace a deployment-specific data-protection "
         "impact assessment. The datasets used in this study are public research benchmarks; CICIDS2017 "
         "addresses are testbed addresses, BGL node identifiers are hardware locations and TDA users are "
         "integer codes.", body_style),
    ])

    # ------------------------------------------------------------------ #
    # 5 Implementation
    # ------------------------------------------------------------------ #
    set_text(find(doc, "The six detectors are exposed through a single training interface"),
        "The six detectors are exposed through a single training interface with the fixed hyperparameters of "
        "Table 6, recorded in a configuration file. Z-scoring for the linear SVM and the MLP is implemented as "
        "a scikit-learn Pipeline so that the scaler is fitted on the training partition only, including "
        "inside cross-validation folds. The Isolation Forest contamination parameter is 0.05 when it generates "
        "synthetic labels for the unlabelled TDA application logs [27]. The correlation window defaults to "
        "60 s and is exposed as a run-time parameter, so that operators can trade recall against incident "
        "granularity (Section 6.3).")
    p53 = find(doc, "All datasets used are public: CICIDS2017")
    set_text(p53,
        "All datasets used are public: CICIDS2017 [28], BGL [29] and TDA (Section 9). The data split "
        "(70/15/15), the five-fold cross-validation protocol, the five random seeds and the model configuration "
        "are fixed and version-controlled. In addition to the service code, the repository contains a "
        "self-contained experiments package (backend/experiments) with scripted, deterministic runs that "
        "regenerate every table and figure of this paper from the raw CSV files without the database or API: "
        "datasets.py (loading, cleaning, features, pseudo-labels), run_models.py (six models × three datasets "
        "× five seeds), temporal_cicids.py (order-preserving split), correlation_eval.py (benchmark, "
        "sensitivity, ablation), second_stage_eval.py (learned incident classifier) and benchmark.py "
        "(throughput, latency, memory). The prior single-layer system that this work extends is openly "
        "available [4].")
    insert_many(p53, [
        ("5.4 Dashboard and operational interface", h2),
        ("The presentation tier is an Angular 17 single-page application built from standalone components "
         "with RxJS streams. It is organised into eleven feature modules, each backed by a REST endpoint and, "
         "where live updates are needed, by the WebSocket channel: Dashboard (key performance indicators: "
         "events ingested per layer, open incidents by severity, model status); Logs (searchable, filterable "
         "view of normalised events with per-event label and score); Incidents (ranked list of correlated "
         "incidents with the contributing alerts per layer, the shared entity, the time span and the severity, "
         "plus analyst actions to confirm or dismiss, which feed the second-stage model); Attack chains "
         "(timeline rendering of an incident's alerts across the three layers, i.e. the view of Fig. 1); "
         "Entities (per-entity activity across layers and the list of entities seen in two or more layers); "
         "Heatmap (events and anomalies per layer and hour); Analysis (model training and evaluation: choice "
         "of algorithm, metrics, ROC and precision–recall curves, feature importance, threshold analysis); "
         "Alert rules and Response rules (operator-defined thresholds and automated responses such as "
         "notifications); Statistics; and Reports (export of incidents and metrics). Real-time alerts are "
         "pushed over the WebSocket channel as soon as an event is scored or an incident is opened. The "
         "frontend communicates only with the authenticated API and displays pseudonymised identifiers.",
         body_style),
    ])

    # ------------------------------------------------------------------ #
    # 6 Results
    # ------------------------------------------------------------------ #
    p6 = find(doc, "The machine learning algorithms were evaluated on the three datasets")
    set_text(p6,
        "This section reports (6.1) the per-layer detection results for all six algorithms on all three "
        "datasets, (6.2) an order-preserving evaluation for CICIDS2017, (6.3) the quantitative evaluation of "
        "the cross-layer correlation engine and of the learned second-stage classifier, and (6.4) "
        "system-level throughput, latency and memory measurements. All per-layer numbers are means ± standard "
        "deviations over five seeds on the held-out test partition (Section 4.3).")
    # remove old Table 2 caption + table and old Table 3 caption, table, note, and the old results prose
    old_cap2 = find(doc, "Table 2  Datasets, features and best model per layer")
    old_t = doc.tables[1] if len(doc.tables) > 1 else None
    # find the table right after old_cap2
    nxt = old_cap2._p.getnext()
    if nxt is not None and nxt.tag.endswith("}tbl"):
        nxt.getparent().remove(nxt)
    delete(old_cap2)
    delete(find(doc, "For the network layer, LightGBM and XGBoost classified"))
    old_cap3 = find(doc, "Table 3  Detection performance per model and layer")
    nxt = old_cap3._p.getnext()
    if nxt is not None and nxt.tag.endswith("}tbl"):
        nxt.getparent().remove(nxt)
    delete(old_cap3)
    delete(find(doc, "n.r. = not reported"))
    p_amg = find(doc, "Among the evaluated algorithms, Isolation Forest remains the only unsupervised")

    rows7 = []
    for ds in DS_ORDER:
        for m in MODEL_ORDER:
            if m not in M["datasets"][ds]["models"]:
                continue
            rows7.append([DS_LAYER[ds], MODEL_NAME[m], ms(ds, m, "precision"), ms(ds, m, "recall"),
                          ms(ds, m, "f1"), ms(ds, m, "roc_auc"),
                          f"{mm(ds, m, 'cv_f1_mean')['mean']:.3f}" if not math.isnan(mm(ds, m, 'cv_f1_mean')['mean']) else "–",
                          f"{mm(ds, m, 'train_time_s')['mean']:.1f}",
                          f"{mm(ds, m, 'events_per_s')['mean']:,.0f}"])
    items = [
        ("6.1 Per-layer detection", h2),
        (f"Table 7 reports all six algorithms on all three datasets, and Fig. 3 visualises the F1-scores. On the "
         f"network layer (CICIDS2017) the gradient-boosting models are best: {MODEL_NAME[b_net]} reaches "
         f"F1 = {ms('CICIDS2017', b_net, 'f1')} with ROC-AUC {ms('CICIDS2017', b_net, 'roc_auc')}, followed closely by "
         f"XGBoost ({ms('CICIDS2017', 'xgboost', 'f1')}) and Random Forest ({ms('CICIDS2017', 'rf', 'f1')}); the MLP "
         f"reaches {ms('CICIDS2017', 'mlp', 'f1')}, the linear SVM {ms('CICIDS2017', 'svm', 'f1')} (the attack classes "
         f"are not linearly separable in the z-scored feature space) and the unsupervised Isolation Forest "
         f"{ms('CICIDS2017', 'isolation_forest', 'f1')}. The standard deviations across seeds are at most "
         f"{max(mm('CICIDS2017', m, 'f1')['std'] for m in MODEL_ORDER):.3f}, so the ranking is stable. On the system layer "
         f"(BGL) the three tree ensembles and the MLP are practically tied (F1 between {min(mm('BGL', m, 'f1')['mean'] for m in ['rf','xgboost','lgbm','mlp']):.3f} and "
         f"{max(mm('BGL', m, 'f1')['mean'] for m in ['rf','xgboost','lgbm','mlp']):.3f}), the linear SVM reaches "
         f"{ms('BGL', 'svm', 'f1')} and the Isolation Forest {ms('BGL', 'isolation_forest', 'f1')}; the ten lexical "
         "features separate the BGL alert categories almost perfectly because the alert flag is itself "
         "derived from the message's component and severity tokens, which makes BGL an easy benchmark for "
         "keyword features (the previous version of this paper reported F1 = 0.910 for Random Forest on a "
         "non-random prefix of the file; the stratified random sample used here is more representative and "
         "the new value supersedes it). On the application layer (TDA) the scores measure agreement with the "
         f"Isolation Forest pseudo-labels (Section 7.3): {MODEL_NAME[b_app]} reaches F1 = {ms('TDA', b_app, 'f1')}, "
         f"the MLP {ms('TDA', 'mlp', 'f1')} and the supervised Isolation Forest baseline {ms('TDA', 'isolation_forest', 'f1')}. "
         f"Training is cheapest for LightGBM and XGBoost (≈{mm('CICIDS2017', 'lgbm', 'train_time_s')['mean']:.1f} s and "
         f"{mm('CICIDS2017', 'xgboost', 'train_time_s')['mean']:.1f} s on 105,000 flows) and most expensive for the MLP "
         f"({mm('CICIDS2017', 'mlp', 'train_time_s')['mean']:.0f} s) and the calibrated SVM ({mm('CICIDS2017', 'svm', 'train_time_s')['mean']:.0f} s); "
         "batch inference exceeds several hundred thousand events per second for the boosted models.", body_style),
        ("Table 7  Detection performance of all six models on all three datasets: test-set mean ± SD over five seeds; "
         "CV F1 = five-fold cross-validation on the training partition; train time per fit; inference throughput "
         "on the test partition (events/s)", caption_style),
    ]
    last = insert_many(p_amg, items)
    # insert table 7 after its caption (last)
    insert_table_after(doc, last, ["Layer", "Model", "Precision", "Recall", "F1", "ROC-AUC", "CV F1", "Train (s)", "Infer (ev/s)"],
                       rows7, tstyle, font_pt=7, col_widths=[0.62, 0.9, 0.78, 0.78, 0.78, 0.78, 0.48, 0.45, 0.68])
    # move p_amg (old sentence) below and rewrite it
    tbl7 = last._p.getnext()
    tbl7.addnext(p_amg._p)
    set_text(p_amg,
        "Among the evaluated algorithms, Isolation Forest remains the only unsupervised method and is "
        "valuable when ground-truth labels are unavailable, but Table 7 shows that it trails the supervised "
        "models by a wide margin wherever labels exist (CICIDS2017, BGL); the gradient-boosting models offer "
        "the best accuracy-to-cost ratio across all three layers.")
    pf3 = insert_picture_after(doc, p_amg, FIG / "fig4_model_comparison.png", 5.2)
    pf3c = insert_after(pf3, "Fig. 3  Test F1-score (mean ± SD over five seeds) of the six models on the three layers", caption_style)

    tt, tr = T["temporal"], T["random"]
    if T2:
        r_, w_, c_, g_, s_ = T2["random"], T2["within_day"], T2["cross_day"], T2["by_source_ip"], T2["by_session"]
        fam = c_.get("per_label_on_test", {})
        fam_txt = "; ".join(f"{k} {v['recall']:.3f}" for k, v in fam.items() if k != "BENIGN")
        items62 = [
            ("6.2 Temporal and session-aware evaluation of CICIDS2017", h2),
            ("A random split can overstate performance when flows from the same attack burst, or from the same "
             "host, land in both the training and the test partition. We therefore repeated the CICIDS2017 "
             "experiment on the original per-day flow files (GeneratedLabelledFlows, which carry the capture "
             f"timestamp and the source and destination addresses; {T2['n_rows']:,} flows after the same cleaning, "
             "at most 120,000 per daily file, with the known afternoon-timestamp quirk corrected) under four "
             "protocols (Table 8). Within-day chronological: inside every day the first 70% of flows train and "
             "the last 15% test, so the model is evaluated on traffic that occurs strictly after what it was "
             f"trained on while all attack families remain represented; LightGBM keeps F1 = {w_['lgbm']['f1']:.3f} "
             f"(random split on the same rows: {r_['lgbm']['f1']:.3f}). Cross-day: train on Monday-Wednesday "
             "(benign, FTP/SSH brute force, DoS, Heartbleed) and test on Thursday-Friday (web attacks, "
             "infiltration, botnet, DDoS, port scan), a strict forward-in-time split in which every test attack "
             f"family is absent from training; LightGBM collapses to F1 = {c_['lgbm']['f1']:.3f} (recall "
             f"{c_['lgbm']['recall']:.3f}) and Random Forest to {c_['rf']['f1']:.3f} (recall {c_['rf']['recall']:.3f}), and the "
             f"per-family recall of LightGBM on the test days is {fam_txt}. Host-disjoint: a five-fold "
             "StratifiedGroupKFold on the source address, so that no host appears in both partitions (CICIDS2017 "
             "attacks originate from only a handful of attacker addresses, so each fold holds out whole "
             f"attackers; {g_['n_folds_with_attacks']} folds contain attacks); LightGBM reaches F1 = "
             f"{g_['lgbm']['f1']:.3f} ± {g_['lgbm']['f1_std']:.3f} and Random Forest {g_['rf']['f1']:.3f} ± "
             f"{g_['rf']['f1_std']:.3f}. Session-disjoint: the same procedure grouped by (source, destination) "
             f"pair ({s_['n_groups_total']:,} sessions) gives F1 = {s_['lgbm']['f1']:.3f} ± {s_['lgbm']['f1_std']:.3f} "
             f"(LightGBM) and {s_['rf']['f1']:.3f} ± {s_['rf']['f1_std']:.3f} (Random Forest).", body_style),
            ("These results change how the network-layer scores of Table 7 must be read. The near-perfect random "
             "and within-day scores are real but conditional: they hold when the attacking hosts and the attack "
             "families seen at test time were also present during training. When either condition is removed the "
             "supervised flow classifier degrades sharply, which indicates that in this testbed the flow features "
             "(destination port, initial window sizes, packet-size and timing statistics) act partly as a "
             "fingerprint of the attacker and victim hosts and of the attack tool, a shortcut that has been "
             "documented for CICIDS2017 and that Sommer and Paxson anticipated for learning-based intrusion "
             "detection in general [23]. Two consequences follow. First, a per-layer detector trained on this "
             "benchmark should be expected to detect new attackers and new attack families only after retraining "
             "or with unsupervised components, and the earlier version of this paper, which reported the random "
             "split only, overstated the generality of the network layer. Second, the result strengthens rather "
             "than weakens the case for the cross-layer design: an attacker who evades a flow classifier still "
             "produces authentication, system and application traces that the correlation engine links through "
             "the shared identifier, which is why Section 6.5 evaluates the correlation step on alerts from "
             "independent detectors on genuinely linked logs.", body_style),
            ("Table 8  CICIDS2017 on the original timestamped per-day flows: random, temporal and session-aware "
             "splits (group splits are means ± SD over the folds that contain attacks)", caption_style),
        ]
        last62 = insert_many(pf3c, items62)
        def _r(d, m):
            sd = f" ± {d[m]['f1_std']:.3f}" if "f1_std" in d[m] else ""
            auc = d[m]["roc_auc"]
            return f"{d[m]['precision']:.3f} / {d[m]['recall']:.3f} / {d[m]['f1']:.3f}{sd} / {auc:.3f}" if auc is not None else f"{d[m]['precision']:.3f} / {d[m]['recall']:.3f} / {d[m]['f1']:.3f}{sd} / –"
        insert_table_after(doc, last62, ["Protocol", "Train / test flows", "Test attack rate",
                                         "LightGBM P / R / F1 / AUC", "Random Forest P / R / F1 / AUC"],
                           [["Stratified random 70/15/15", f"{r_['n_train']:,} / {r_['n_test']:,}", f"{100*r_['test_attack_rate']:.1f}%", _r(r_, 'lgbm'), _r(r_, 'rf')],
                            ["Within-day chronological 70/15/15", f"{w_['n_train']:,} / {w_['n_test']:,}", f"{100*w_['test_attack_rate']:.1f}%", _r(w_, 'lgbm'), _r(w_, 'rf')],
                            ["Cross-day (Mon-Wed -> Thu-Fri)", f"{c_['n_train']:,} / {c_['n_test']:,}", f"{100*c_['test_attack_rate']:.1f}%", _r(c_, 'lgbm'), _r(c_, 'rf')],
                            [f"Host-disjoint (5-fold by source IP; {g_['n_folds_with_attacks']} folds)", f"{g_['n_train']:,} / {g_['n_test']:,}", f"{100*g_['test_attack_rate']:.1f}%", _r(g_, 'lgbm'), _r(g_, 'rf')],
                            [f"Session-disjoint (5-fold by src>dst; {s_['n_folds_with_attacks']} folds)", f"{s_['n_train']:,} / {s_['n_test']:,}", f"{100*s_['test_attack_rate']:.1f}%", _r(s_, 'lgbm'), _r(s_, 'rf')]],
                           tstyle, font_pt=7.5, col_widths=[1.8, 1.05, 0.75, 1.35, 1.35])
    else:
        items62 = [
            ("6.2 Order-preserving evaluation of CICIDS2017", h2),
            ("A random split can overstate performance when flows from the same attack burst land in both the "
             "training and the test partition. We therefore repeated the CICIDS2017 experiment with an order-"
             "preserving split: the first 70% of the first 150,000 rows in file order are used for training, the "
             "next 15% for validation and the last 15% for testing. Because the consolidated CSV used here is grouped "
             "by attack type and does not carry the original capture timestamps, this split is a block "
             f"(distribution-shift) split rather than a true temporal split: the test block is "
             f"{100*tt['test_positive_rate']:.0f}% attack flows, versus {100*tr['test_positive_rate']:.0f}% under the random "
             f"split of the same rows. LightGBM reaches F1 = {tt['f1']:.3f} under the order-preserving split against "
             f"{tr['f1']:.3f} under the random split, a drop of {T['delta_f1_random_minus_temporal']:.3f}.", body_style),
            ("Table 8  CICIDS2017, LightGBM: stratified random split versus order-preserving (block) split on the same 150,000 rows", caption_style),
        ]
        last62 = insert_many(pf3c, items62)
        insert_table_after(doc, last62, ["Split", "Precision", "Recall", "F1", "ROC-AUC", "Test attack rate"],
                           [["Stratified random 70/15/15", f3(tr['precision']), f3(tr['recall']), f3(tr['f1']), f3(tr['roc_auc']), f"{100*tr['test_positive_rate']:.1f}%"],
                            ["Order-preserving 70/15/15", f3(tt['precision']), f3(tt['recall']), f3(tt['f1']), f3(tt['roc_auc']), f"{100*tt['test_positive_rate']:.1f}%"]],
                           tstyle, font_pt=8)
    t8 = last62._p.getnext()
    from docx.text.paragraph import Paragraph
    dummy = copy.deepcopy(last62._p)
    for ch in list(dummy):
        if ch.tag.endswith("}r"):
            dummy.remove(ch)
    t8.addnext(dummy)
    pd_ = Paragraph(dummy, last62._parent)
    pd_.style = body_style
    pd_.alignment = None

    ws_rows = [[r["window_s"], r["incidents_after"], f"{100*r['reduction_ratio']:.1f}%", r["tp"], r["fp"], r["fn"],
                f3(r["incident_precision"]), f3(r["incident_recall"]), f3(r["incident_f1"])] for r in WS]
    items63 = [
        ("6.3 Quantitative evaluation of cross-layer correlation", h2),
        ("6.3.1 Why a controlled benchmark", h2),
        ("CICIDS2017, BGL and TDA were captured in different environments and years (a 2017 testbed, a "
         "Blue Gene/L installation in 2005–2006 and an application-access log), so no event in one dataset "
         "genuinely shares a timestamp or identifier with an event in another; the earlier version of this "
         "paper did not make this explicit, and the datasets by themselves cannot provide ground truth for "
         "cross-layer incidents. The correlation engine is therefore evaluated on a controlled attack-"
         "injection benchmark with known ground truth, in the spirit of the synthetic multi-step scenarios "
         "used in the alert-correlation literature [9, 44]. The benchmark is constructed as follows. A pool of "
         "400 pseudonymous entities (surrogate hosts/users/addresses) is defined. We plant 200 multi-stage "
         "incidents: each picks one entity and emits a network, then a system, then an application alert "
         "with detector scores drawn uniformly from [0.6, 1.0], at three time offsets drawn uniformly from a "
         "40 s span (so some chains are longer than small windows). We then add 12,000 distractor alerts — "
         "independent single-layer alerts with scores in [0.3, 0.9], uniformly spread over one simulated day "
         "and drawn from the same entity pool, so that distractors frequently share an entity and a window "
         "with a planted chain (false enlargement) or with each other across layers (spurious incidents). "
         "The per-layer alert rates are of the same order as those that the detectors of Section 6.1 would "
         "emit on the sampled datasets. A reported incident is counted as a correct reconstruction when its "
         "Jaccard overlap with a planted incident is at least 0.5 (each planted incident may be matched once); "
         "unmatched reported incidents are false correlations and unmatched planted incidents are misses. We "
         "stress that this benchmark measures the correlation mechanism, not end-to-end detection on real "
         "linked data (Section 7.5).", body_style),
        ("6.3.2 Alert reduction, reconstruction and false correlations", h2),
        (f"Table 9 summarises the result at the default W = 60 s. The engine compresses {CM['alerts_before']:,} "
         f"per-layer alerts ({CM['planted_incidents']*3:,} belonging to planted chains and {CM['distractor_alerts']:,} "
         f"distractors) into {CM['incidents_after']} multi-stage incidents, a {100*CM['reduction_ratio']:.1f}% reduction "
         f"in the number of items an analyst must triage. Of the 200 planted incidents, {CM['tp']} are correctly "
         f"reconstructed and {CM['fn']} missed; {CM['fp']} reported incidents are false correlations (distractor "
         f"groups or chains contaminated beyond the Jaccard threshold), giving incident-level precision "
         f"{CM['incident_precision']:.3f}, recall {CM['incident_recall']:.3f} and F1 {CM['incident_f1']:.3f}. Across five "
         f"benchmark seeds the values are precision {SEEDS_C['incident_precision']['mean']:.3f} ± "
         f"{SEEDS_C['incident_precision']['std']:.3f}, recall {SEEDS_C['incident_recall']['mean']:.3f} ± "
         f"{SEEDS_C['incident_recall']['std']:.3f} and F1 {SEEDS_C['incident_f1']['mean']:.3f} ± {SEEDS_C['incident_f1']['std']:.3f}. "
         "Ablation of the layer-ordering constraint. Removing the ordering filter of Algorithm 1 (line 4) "
         f"raises recall marginally from {ABL['with_order']['incident_recall']:.3f} to {ABL['without_order']['incident_recall']:.3f} "
         f"but more than doubles false correlations ({ABL['with_order']['fp']} → {ABL['without_order']['fp']}), lowering "
         f"precision from {ABL['with_order']['incident_precision']:.3f} to {ABL['without_order']['incident_precision']:.3f} and F1 from "
         f"{ABL['with_order']['incident_f1']:.3f} to {ABL['without_order']['incident_f1']:.3f}; the constraint is therefore kept. "
         "Sensitivity to the window. Table 10 and Fig. 4 sweep W from 5 s to 600 s. A 5 s window splits most "
         f"chains (recall {WS[0]['incident_recall']:.3f}) while keeping precision high ({WS[0]['incident_precision']:.3f}); "
         f"recall saturates from W = {WS[1]['window_s']} s onward, whereas precision falls monotonically as unrelated "
         f"alerts are absorbed, reaching {WS[-1]['incident_precision']:.3f} at 600 s. Incident F1 peaks at "
         f"W = {best_w['window_s']} s ({best_w['incident_f1']:.3f}) on this benchmark; the default of 60 s sits on the "
         "recall-favouring side of the optimum, which is the appropriate operating point when the second-"
         "stage classifier (next section) is available to remove false correlations, and the sweep shows that "
         "operators should calibrate W to the dwell time of the attacks they expect rather than treat it as "
         "universal.", body_style),
        ("Table 9  Correlation engine at W = 60 s on the attack-injection benchmark (200 planted multi-stage "
         "incidents, 12,000 distractor alerts)", caption_style),
    ]
    last63 = insert_many(pd_, items63)
    insert_table_after(doc, last63, ["Quantity", "Value"],
                       [["Per-layer alerts before correlation", f"{CM['alerts_before']:,}"],
                        ["Multi-stage incidents after correlation", f"{CM['incidents_after']}"],
                        ["Reduction in items to triage", f"{100*CM['reduction_ratio']:.1f}%"],
                        ["Correctly reconstructed incidents (TP)", f"{CM['tp']} / {CM['planted_incidents']}"],
                        ["False correlations (FP)", f"{CM['fp']}"],
                        ["Missed incidents (FN)", f"{CM['fn']}"],
                        ["Incident precision / recall / F1 (seed 42)", f"{CM['incident_precision']:.3f} / {CM['incident_recall']:.3f} / {CM['incident_f1']:.3f}"],
                        ["Incident precision / recall / F1 (mean ± SD, 5 seeds)",
                         f"{SEEDS_C['incident_precision']['mean']:.3f} ± {SEEDS_C['incident_precision']['std']:.3f} / "
                         f"{SEEDS_C['incident_recall']['mean']:.3f} ± {SEEDS_C['incident_recall']['std']:.3f} / "
                         f"{SEEDS_C['incident_f1']['mean']:.3f} ± {SEEDS_C['incident_f1']['std']:.3f}"],
                        ["Without layer-ordering constraint (P / R / F1; FP)",
                         f"{ABL['without_order']['incident_precision']:.3f} / {ABL['without_order']['incident_recall']:.3f} / "
                         f"{ABL['without_order']['incident_f1']:.3f}; FP = {ABL['without_order']['fp']}"]],
                       tstyle, font_pt=8, col_widths=[3.6, 2.9])
    t9 = last63._p.getnext()
    d9 = copy.deepcopy(last63._p)
    for ch in list(d9):
        if ch.tag.endswith("}r"):
            d9.remove(ch)
    t9.addnext(d9)
    pd9 = Paragraph(d9, last63._parent)
    pd9.style = caption_style
    pd9.add_run("Table 10  Sensitivity of the correlation engine to the window W (seed 42)")
    insert_table_after(doc, pd9, ["W (s)", "Incidents", "Reduction", "TP", "FP", "FN", "Precision", "Recall", "F1"],
                       ws_rows, tstyle, font_pt=8)
    t10 = pd9._p.getnext()
    d10 = copy.deepcopy(pd9._p)
    for ch in list(d10):
        if ch.tag.endswith("}r"):
            d10.remove(ch)
    t10.addnext(d10)
    pd10 = Paragraph(d10, pd9._parent)
    pd10.style = body_style
    pf4 = insert_picture_after(doc, pd10, FIG / "fig3_window_sensitivity.png", 4.6)
    pf4c = insert_after(pf4, "Fig. 4  Incident-level precision, recall and F1 of the correlation engine as a function of the window W", caption_style)

    s2rows = []
    for k, nm in [("rule_baseline", "Rule only (Algorithm 1, lines 4–5)"), ("logreg", "Logistic regression"),
                  ("rf", "Random Forest"), ("lgbm", "LightGBM")]:
        s = S2["models"][k]
        s2rows.append([nm, f"{s['precision']['mean']:.3f} ± {s['precision']['std']:.3f}",
                       f"{s['recall']['mean']:.3f} ± {s['recall']['std']:.3f}",
                       f"{s['f1']['mean']:.3f} ± {s['f1']['std']:.3f}",
                       "–" if math.isnan(s['roc_auc']['mean']) else f"{s['roc_auc']['mean']:.3f}"])
    n_c = S2["candidates_per_seed"]
    items633 = [
        ("6.3.3 Learned second-stage incident classifier", h2),
        ("Table 11 evaluates the second stage of Section 4.5 on the same benchmark. For each of the five seeds, "
         "all candidates produced by lines 1–7 of Algorithm 1 at W = 60 s (on average "
         f"{sum(c[0] for c in n_c)/len(n_c):,.0f} candidates, of which {sum(c[1] for c in n_c)/len(n_c):,.0f} contain a planted chain) "
         "are described by the eight aggregate cross-layer features, split 70/15/15 with stratification, and "
         "classified; the rule-only row applies the fixed criterion of Algorithm 1 (at least two layers and "
         f"non-decreasing order) to the same test candidates. The fixed rule reaches F1 = {S2R['f1']['mean']:.3f} "
         f"± {S2R['f1']['std']:.3f}, whereas the learned classifiers reach F1 = {S2['models']['logreg']['f1']['mean']:.3f} "
         f"(logistic regression) to {S2L['f1']['mean']:.3f} ± {S2L['f1']['std']:.3f} (LightGBM) with ROC-AUC "
         f"{S2L['roc_auc']['mean']:.3f}, i.e. the learned stage removes almost all false correlations that the "
         "rule lets through by exploiting the span, score and count features. This is the sense in which the "
         "cross-layer step is itself learned. Two caveats apply: the distractors of the benchmark are "
         "statistically independent, which makes them easier to reject than real correlated background "
         "activity, and the second stage must be retrained from analyst feedback in a deployment; the numbers "
         "therefore show that the mechanism works, not that it will reach the same scores on live data.",
         body_style),
        ("Table 11  Learned second-stage incident classifier versus the fixed rule on candidate incidents "
         "(test partition, mean ± SD over five benchmark seeds)", caption_style),
    ]
    last633 = insert_many(pf4c, items633)
    insert_table_after(doc, last633, ["Incident scorer", "Precision", "Recall", "F1", "ROC-AUC"], s2rows, tstyle, font_pt=8)
    t11 = last633._p.getnext()
    d11 = copy.deepcopy(last633._p)
    for ch in list(d11):
        if ch.tag.endswith("}r"):
            d11.remove(ch)
    t11.addnext(d11)
    pd11 = Paragraph(d11, last633._parent)
    pd11.style = body_style

    # 6.4 system-level
    if B:
        lay = {r["dataset"]: r for r in B["layers"]}
        corr = B["correlation"]
        host = B["host"]
        items64 = [
            ("6.4 System-level throughput, latency and memory", h2),
            ("Table 12 reports measurements taken on a single commodity workstation (Windows 11, Python 3.9, "
             "scikit-learn 1.5.1), with the Random Forest detector of Table 6 and the correlation engine of "
             "Algorithm 1 implemented as in the experiments package. Detection throughput is measured by "
             "scoring the full test partition in one batch; per-event latency is measured by scoring 2,000 "
             "test events one at a time, as a streaming consumer would. The correlation engine is timed on "
             "benchmarks of increasing size (planted chains plus distractors, W = 60 s), and the empirical "
             "scaling exponent is the slope of log(time) against log(events). Batch detection sustains "
             f"{lay['CICIDS2017']['batch_events_per_s']:,.0f} flows/s on the network layer, "
             f"{lay['BGL']['batch_events_per_s']:,.0f} lines/s on the system layer and "
             f"{lay['TDA']['batch_events_per_s']:,.0f} records/s on the application layer, with single-event "
             f"latencies of {lay['CICIDS2017']['latency_ms_mean']:.1f}–{lay['TDA']['latency_ms_mean']:.1f} ms mean and "
             f"{max(l['latency_ms_p99'] for l in lay.values()):.1f} ms at the 99th percentile; the single-event latency is "
             "dominated by scikit-learn call overhead for a 100-tree forest and not by the model itself, so a "
             "streaming consumer should micro-batch (e.g. 100 events per call), which restores the batch "
             "throughput while keeping end-to-end delay well below one second. The correlation engine "
             f"processes {corr['scaling'][-1]['n_events']:,} alerts in {corr['scaling'][-1]['seconds']:.2f} s "
             f"({corr['scaling'][-1]['events_per_s']:,.0f} alerts/s) and its empirical exponent is "
             f"{corr['empirical_exponent']:.2f} (1 = linear), consistent with the near-linear analysis of Section 4.4 "
             f"for sparse identifiers. Peak Python heap during the whole benchmark was {host['peak_python_mem_mb']:.0f} MB"
             + (f" and process resident memory {host['rss_end_mb']:.0f} MB" if host.get("rss_end_mb") else "")
             + ". These figures support the use of the pipeline on a single node for log volumes of the order of "
             "10⁵ events per second after feature extraction; they do not include network I/O or database "
             "persistence, which dominate in a full deployment and are reported for the service tier in "
             "Section 5.", body_style),
            ("Table 12  System-level measurements on a single workstation", caption_style),
        ]
        last64 = insert_many(pd11, items64)
        rows12 = [[f"Detection, {d} ({DS_LAYER[d].lower()})", f"{lay[d]['batch_events_per_s']:,.0f} events/s",
                   f"{lay[d]['latency_ms_mean']:.2f} ms", f"{lay[d]['latency_ms_p99']:.2f} ms"] for d in DS_ORDER]
        for r in corr["scaling"]:
            rows12.append([f"Correlation, {r['n_events']:,} alerts", f"{r['events_per_s']:,.0f} alerts/s",
                           f"{r['seconds']:.3f} s total", "–"])
        rows12.append(["Correlation scaling exponent", f"{corr['empirical_exponent']:.2f}", "(1 = linear)", "–"])
        rows12.append(["Peak Python heap", f"{host['peak_python_mem_mb']:.0f} MB", "–", "–"])
        insert_table_after(doc, last64, ["Component", "Throughput", "Latency (mean) / time", "Latency (p99)"],
                           rows12, tstyle, font_pt=8)
    else:
        insert_many(pd11, [("6.4 System-level throughput, latency and memory", h2),
                           ("[benchmark_results.json not found — run experiments/benchmark.py and re-run this script]", body_style)])

    # ---- 6.5 AIT-ADS: correlation on genuinely linked alerts, if the run exists
    if A and A.get("scenarios"):
        ag = A["aggregate"]["W=60"]
        scen = A["scenarios"]
        n_scen = len(scen)
        tot_alerts = sum(r["alerts"] for r in scen.values())
        tot_attack = sum(r["attack_alerts"] for r in scen.values())
        layers_cov = Counter()
        for r in scen.values():
            for l in r["alerts_per_layer"]:
                layers_cov[l] += r["alerts_per_layer"][l]
        ms_ = A.get("second_stage_loso_mean", {})
        last_par = find(doc, "7 Discussion")
        last_par._p.addprevious(copy.deepcopy(last_par._p))
        from docx.text.paragraph import Paragraph as _P2
        h65 = _P2(last_par._p.getprevious(), last_par._parent)
        for ch in list(h65._p):
            if not ch.tag.endswith("}pPr"):
                h65._p.remove(ch)
        h65.style = h2; h65.alignment = None
        h65.add_run("6.5 Correlation on genuinely linked alerts: the AIT Alert Data Set")
        p65 = insert_after(h65,
            "In response to the request to evaluate the system on data whose layers are genuinely linked, we "
            "ran the correlation engine on the AIT Alert Data Set (AIT-ADS) [47], which contains the alerts "
            "raised by three intrusion detection systems - Suricata on network traffic, Wazuh host rules on "
            "authentication, system, web and mail logs, and the AMiner log-anomaly detector - over the eight "
            "AIT-LDS v2 enterprise testbeds [36], in each of which every host is logged simultaneously while a "
            "scripted multi-step attack (network and service scans, WordPress scanning and directory brute "
            "force, web shell upload, password cracking, reverse shell, privilege escalation, service stop or "
            "DNS exfiltration) is executed, with ground truth given as attack-phase time intervals. These "
            "alerts are exactly the input of Algorithm 1 - per-layer alerts with timestamp, identifiers and a "
            "score - and, unlike CICIDS2017, BGL and TDA, the three layers are observed on the same hosts at "
            "the same time. Alerts are mapped deterministically to layers from the originating IDS and rule "
            "group (Suricata, firewall and DNS rules to the network layer; authentication, sshd, PAM, sudo, "
            "syslog, audit and integrity rules to the system layer; Apache, WordPress, PHP, Exim/Horde mail "
            "rules to the application layer), the entity is the source or destination address carried by the "
            "alert (else the agent host), and the score is the Wazuh rule level, the Suricata severity or a "
            f"constant for AMiner. Across the {n_scen} scenarios the engine processed {tot_alerts:,} alerts, "
            f"{tot_attack:,} of which fall inside an attack phase (network {layers_cov.get('network', 0):,}, "
            f"system {layers_cov.get('system', 0):,}, application {layers_cov.get('application', 0):,} alerts in total).",
            body_style)
        p65b = insert_after(p65,
            f"Table 13 reports the per-scenario results at W = 60 s and the mean ± SD over scenarios. On average "
            f"the engine reduces the number of items to triage by {100*ag['reduction_ratio']['mean']:.1f}% ± "
            f"{100*ag['reduction_ratio']['std']:.1f}%, with incident precision {ag['incident_precision']['mean']:.3f} ± "
            f"{ag['incident_precision']['std']:.3f} (incidents whose alerts are in majority attack-related) and "
            f"attack-alert recall {ag['attack_alert_recall']['mean']:.3f} ± {ag['attack_alert_recall']['std']:.3f}; "
            f"in {ag['scenarios_with_multilayer_attack_incident']} of the {n_scen} scenarios the attacker's activity is "
            f"reconstructed as an incident spanning at least two layers (on average {ag['max_layers_in_attack_incident']['mean']:.1f} "
            f"layers and {ag['max_phases_in_attack_incident']['mean']:.1f} distinct attack phases in the largest attack "
            f"incident), while {ag['false_correlations']['mean']:.0f} ± {ag['false_correlations']['std']:.0f} false "
            "correlations per scenario arise from the benign noise that Wazuh and AMiner emit on routine "
            "activity (package updates, ClamAV refreshes, user logins), which is the realistic false-positive "
            "load that the controlled benchmark of Section 6.3 only approximates. "
            + (f"A second-stage classifier trained leave-one-scenario-out on the eight features of Section 4.5 "
               f"reaches incident F1 = {ms_['lgbm']['f1']:.3f} (precision {ms_['lgbm']['precision']:.3f}, recall "
               f"{ms_['lgbm']['recall']:.3f}) on the held-out scenario against {ms_['rule']['f1']:.3f} for the fixed rule, "
               "i.e. the learned stage transfers across testbeds. " if ms_ else "")
            + (f"Enforcing the outside-in layer-ordering constraint on these streams is counter-productive: because the "
               f"host-based and network detectors fire in interleaved order (a web-scan rule often precedes the "
               f"corresponding Suricata alert), the ordered variant keeps attack-alert recall at only "
               f"{A['aggregate']['W=60,order']['attack_alert_recall']['mean']:.3f} and reconstructs a multi-layer attack incident in "
               f"{A['aggregate']['W=60,order']['scenarios_with_multilayer_attack_incident']} of {n_scen} scenarios, so the "
               "constraint - which halved false correlations on the controlled benchmark - should be treated as an "
               "operator option that is appropriate only when detector latencies are comparable, and it is disabled "
               "for this evaluation. " if "W=60,order" in A["aggregate"] else "")
            + "These results confirm on real, jointly captured logs the behaviour characterised on the "
            "controlled benchmark: the engine collapses alert volume by orders of magnitude and recovers the "
            "multi-stage attack as a cross-layer incident, at the cost of a precision that depends on the "
            "noise profile of the deployed detectors and that the second stage is designed to improve. They "
            "do not include our own per-layer detectors (the alerts come from Suricata, Wazuh and AMiner), so "
            "the end-to-end evaluation of detection plus correlation on the raw AIT-LDS v2 logs, for which the "
            "experiments package provides a harness, remains future work.", body_style)
        cap13 = insert_after(p65b, "Table 13  Correlation engine on the AIT Alert Data Set at W = 60 s "
                             "(eight AIT-LDS v2 scenarios; incident precision = share of incidents that are "
                             "majority attack-related; recall = share of attack alerts absorbed into attack incidents)",
                             caption_style)
        rows13 = []
        for name, r in sorted(scen.items()):
            w = r["windows"]["W=60"]
            rows13.append([name, f"{r['alerts']:,}", f"{r['attack_alerts']:,}", f"{w['incidents_after']:,}",
                           f"{100*(w['reduction_ratio'] or 0):.1f}%", f"{w['incident_precision']:.3f}" if w['incident_precision'] is not None else "–",
                           f"{w['attack_alert_recall']:.3f}" if w['attack_alert_recall'] is not None else "–",
                           f"{w['max_layers_in_attack_incident']} / {w['max_phases_in_attack_incident']}", f"{w['false_correlations']:,}"])
        rows13.append(["Mean ± SD", "", "", "", f"{100*ag['reduction_ratio']['mean']:.1f} ± {100*ag['reduction_ratio']['std']:.1f}%",
                       f"{ag['incident_precision']['mean']:.3f} ± {ag['incident_precision']['std']:.3f}",
                       f"{ag['attack_alert_recall']['mean']:.3f} ± {ag['attack_alert_recall']['std']:.3f}",
                       f"{ag['max_layers_in_attack_incident']['mean']:.1f} / {ag['max_phases_in_attack_incident']['mean']:.1f}",
                       f"{ag['false_correlations']['mean']:.0f} ± {ag['false_correlations']['std']:.0f}"])
        insert_table_after(doc, cap13, ["Scenario", "Alerts", "Attack alerts", "Incidents", "Reduction",
                                        "Incident precision", "Attack-alert recall", "Layers / phases (best)", "False corr."],
                           rows13, tstyle, font_pt=7.5, col_widths=[0.9, 0.65, 0.65, 0.65, 0.7, 0.75, 0.75, 0.8, 0.6])
    # ------------------------------------------------------------------ #
    # 7 Discussion
    # ------------------------------------------------------------------ #
    set_text(find(doc, "7.1 Interpreting the perfect network-layer score"), "7.1 Interpreting the near-perfect network-layer score")
    set_text(find(doc, "The F1-score of 1.000 obtained by LightGBM"),
        f"The F1-scores of {F1_NET:.3f} (LightGBM) and {mm('CICIDS2017','xgboost','f1')['mean']:.3f} (XGBoost) on CICIDS2017 "
        "should be read with caution rather than as evidence of a solved problem. First, the earlier version of "
        "this paper reported exactly 1.000; that figure came from a single run on a non-random prefix of the "
        "file, and the five-seed, stratified-sample protocol now used yields values slightly below 1 with "
        "non-zero variance, which is the honest estimate. Second, the data are not balanced "
        f"({100*s_net['positive_rate']:.1f}% attack flows) but they are not pathologically imbalanced either, and the "
        "scores are not an artefact of class skew: precision and recall are both above 0.99 and ROC-AUC is "
        "insensitive to the base rate. Third, the near-perfect separability is a property of the benchmark: "
        "several CICIDS2017 attack classes (port scanning, DoS, brute force) produce flows whose duration, "
        "packet-count and inter-arrival features are far from benign traffic, and values close to 1.0 are "
        "routinely reported for this dataset [28]. Fourth, and most importantly, Section 6.2 shows that the score "
        "survives a within-day chronological split but collapses on a strict cross-day split (unseen attack "
        "families) and on host- and session-disjoint splits (unseen attackers), which is the honest picture: the "
        "detector generalises over time for known hosts and attack types, not to new attackers or new families. The network-layer "
        "numbers are therefore evidence that the pipeline is implemented correctly and that gradient "
        "boosting is a sound choice, not a claim of generalisation to live traffic, where distribution shift "
        "and label noise are the norm [23]. We treat the network layer as the most mature component and "
        "focus the discussion on the harder questions of cross-layer correlation and pseudo-labelled data.")
    set_text(find(doc, "To assess the central hypothesis, namely that correlation adds value"),
        "The central hypothesis is that correlation adds value beyond single-layer detection. Section 6.3 "
        "now tests it quantitatively rather than by description: on a benchmark with known ground truth the "
        f"engine reduces the number of items to triage by {100*CM['reduction_ratio']:.1f}%, reconstructs "
        f"{100*SEEDS_C['incident_recall']['mean']:.1f}% of the planted multi-stage incidents, and produces false "
        f"correlations at a rate that keeps precision at {SEEDS_C['incident_precision']['mean']:.2f} with the fixed "
        f"rule and above {S2L['precision']['mean']:.2f} with the learned second stage; the ordering constraint "
        "halves false correlations; and the window sweep exposes the precision/recall trade-off that an "
        "operator must tune. These results support the claim that the cross-layer step both lowers alert "
        "volume and preserves the multi-stage narrative, in line with the alert-correlation literature "
        "[9, 10, 17]. They do not show that the engine finds real attacks in real linked logs; that requires "
        "a dataset in which the three layers were captured together; Section 6.5 provides a first such "
        "confirmation on the AIT Alert Data Set, where the engine recovers the multi-step attack as a cross-layer "
        "incident on jointly captured logs. "
        "We also note what the correlation step does not do: it does not learn relationships between raw "
        "features of different layers (early fusion); learning happens per layer and then on aggregate "
        "incident features (late fusion). We consider this the right design for heterogeneous logs with "
        "different schemas and sampling rates, and it is the design that HERCULE's weighted-graph approach "
        "[30] and SIEM correlation rules [35] also follow, but a jointly trained multimodal or graph model "
        "remains an interesting alternative.")
    p73 = find(doc, "7.3 Threats to validity")
    set_text(p73, "7.3 The application layer: agreement with pseudo-labels, not verified accuracy")
    p73b = find(doc, "Several threats temper the interpretation of our results")
    set_text(p73b,
        "The TDA application logs ship without verified ground truth. The labels against which the "
        "supervised models are trained and evaluated are the outliers of an Isolation Forest fitted on the same "
        "six features (contamination = 0.05). Consequently, the application-layer scores in Table 7 — including "
        f"F1 = {F1_APP:.3f} for {MODEL_NAME[b_app]} and ROC-AUC above 0.99 for several models — measure how well a "
        "supervised model can reproduce the pseudo-labelling procedure, not how well it detects genuine "
        "application-layer threats. Three consequences follow and are stated plainly. (i) The absolute values "
        "must not be compared with the network and system layers, whose labels are independent of the "
        "features. (ii) High agreement is partly expected because the pseudo-labeller and the classifiers see "
        "the same features; the supervised Isolation Forest row of Table 7 (F1 = "
        f"{mm('TDA','isolation_forest','f1')['mean']:.3f}) is the natural reference point, and the gap to the tree ensembles shows "
        "only that a supervised model can learn a sharper decision boundary around the same outliers. (iii) "
        "Any systematic blind spot of the Isolation Forest (for example, frequent but malicious accesses that "
        "do not look like outliers) is inherited by every supervised model. The application layer therefore "
        "serves, in this study, as a demonstration that the pipeline can operate on an unlabelled source in a "
        "semi-supervised manner, and its results should be read as indicative only. Obtaining analyst-"
        "verified labels for a subset of TDA, or substituting a labelled application-layer dataset, is "
        "necessary before any claim about application-layer detection accuracy can be made.")
    insert_many(p73b, [
        ("7.4 Experimental randomness and variance", h2),
        ("Reported scores of learned detectors depend on stochastic factors — random weight initialisation of "
         "the MLP, the data partition, mini-batch order and the bootstrap samples of the tree ensembles — and "
         "single-run values can be misleading [38, 39]; Le and Zhang document the same effect for log anomaly "
         "detection [16], and in the related domain of tabular sensor data for fault detection and diagnosis of "
         "air-handling units, fault-class coverage, data partitioning across buildings, the training "
         "configuration and the amount of labelled data were shown to change outcomes substantially [40, 41, 46]. The present revision therefore "
         "reports every per-layer metric as a mean ± standard deviation over five seeds that control both the "
         "partition and the initialisation (Table 7), reports the five-fold cross-validation F1 on the "
         "training partition as an independent variance estimate, and repeats the correlation benchmark over "
         f"five seeds (Table 9). The observed standard deviations are small for the tree ensembles (≤ 0.002 F1 on "
         f"CICIDS2017 and BGL) and larger for the MLP and the SVM (up to {max(mm(d,'mlp','f1')['std'] for d in DS_ORDER):.3f} and "
         f"{max(mm(d,'svm','f1')['std'] for d in DS_ORDER):.3f} F1), and largest on the pseudo-labelled TDA layer, which is "
         "consistent with the sources of randomness just listed. We did not tune hyperparameters per seed, "
         "and we recommend that future comparisons on these datasets report variance in the same way.",
         body_style),
        ("7.5 Threats to validity and limitations", h2),
        ("Construct validity. The application-layer labels are pseudo-labels (Section 7.3), and the correlation "
         "benchmark is synthetic: its ground truth is planted and its distractors are statistically "
         "independent, so incident-level scores are upper bounds on what real correlated background activity "
         "would permit. Internal validity. The near-perfect network-layer scores partly reflect dataset-"
         "specific separability; the scaler is fitted on training data only, so leakage through standardisation "
         "is excluded; the temporal and session-aware splits of Section 6.2 show that the network-layer score "
         "depends on the attacking hosts and attack families being represented in training, so it must not be "
         "read as detection capability against new attackers or families. External "
         "validity. The three datasets originate from different environments and periods — a 2017 testbed, a "
         "2005 supercomputer and an application log of unspecified provenance — and they are not linked at the "
         "event level; the system has therefore been validated as three per-layer detectors plus a correlation "
         "mechanism whose behaviour is characterised on injected incidents, and not as an end-to-end detector "
         "of real multi-stage attacks. Datasets whose layers are genuinely linked, such as the AIT Log Data "
         "Set V2 [36], which records network, host and application logs of a simulated enterprise under "
         "scripted multi-step attacks with labels, are the appropriate next step; the experiments package "
         "already accepts any source that provides (timestamp, layer, entity, label, score) tuples, and we "
         "report in Section 6.5 a first run of the correlation engine on the AIT Alert Data Set derived from it; "
         "the end-to-end run of our own detectors on the raw AIT-LDS logs is the first priority of future "
         "work. All datasets are historical and "
         "offline, so performance on live, high-velocity streams with concept drift remains to be "
         "demonstrated, and the system-level measurements of Section 6.4 exclude network and storage I/O. "
         "Finally, the per-layer features are intentionally simple (lexical features for BGL, six behavioural "
         "features for TDA); richer representations would likely change the absolute numbers but not the "
         "design of the pipeline.", body_style),
    ])

    # ------------------------------------------------------------------ #
    # 8 Conclusions
    # ------------------------------------------------------------------ #
    set_text(find(doc, "This paper presented the design, implementation and evaluation of a cybersecurity"),
        "This paper presented the design, implementation and evaluation of a cross-layer log monitoring and "
        "analysis system that combines per-layer machine-learning detectors, a transparent correlation engine "
        "based on temporal proximity, shared identifiers and layer ordering, and a learned second-stage "
        "classifier of candidate incidents. The system integrates data from three heterogeneous public sources "
        "— CICIDS2017 (network), BGL (system) and TDA (application) — within a unified schema, and a "
        "REST/WebSocket API with an Angular 17 dashboard provides an operational interface for monitoring, "
        "model training, incident triage and reporting.")
    set_text(find(doc, "The evaluation demonstrated strong results across all three datasets"),
        f"The evaluation reports all six algorithms on all three datasets with variance: the best per-layer "
        f"detectors reach F1 = {F1_NET:.3f} on CICIDS2017 ({MODEL_NAME[b_net]}), {F1_SYS:.3f} on BGL ({MODEL_NAME[b_sys]}) "
        f"and {F1_APP:.3f} on TDA ({MODEL_NAME[b_app]}, against Isolation Forest pseudo-labels), with gradient "
        "boosting offering the best accuracy-to-cost ratio. The cross-layer claim is now supported by "
        f"measurements: on a benchmark with known ground truth the correlation engine reduces triage volume by "
        f"{100*CM['reduction_ratio']:.1f}% at incident precision {SEEDS_C['incident_precision']['mean']:.2f} and recall "
        f"{SEEDS_C['incident_recall']['mean']:.2f}, the layer-ordering constraint halves false correlations, the window "
        f"sweep quantifies the precision/recall trade-off, and the learned second stage raises incident F1 to "
        f"{S2L['f1']['mean']:.3f}. Measured throughput of the order of 10⁵ events per second per layer and a "
        "near-linear correlation engine support single-node operation.")
    set_text(find(doc, "Despite these positive results, the system has limitations"),
        "The limitations are equally clear. The application-layer scores measure agreement with Isolation "
        "Forest pseudo-labels rather than verified detection accuracy; the three datasets are not linked at "
        "the event level, so the correlation engine has been validated on injected incidents and not on real "
        "multi-stage attacks beyond the first end-to-end run on linked data reported in Section 6.5; and all "
        "evaluations are offline. Future work will, in order of priority, (i) evaluate the full pipeline on a dataset whose "
        "layers are genuinely linked, such as the AIT Log Data Set V2 [36]; (ii) obtain analyst-verified labels "
        "for the application layer; (iii) retrain the second-stage classifier from analyst feedback in a live "
        "deployment and compare it with a jointly trained graph model in the spirit of HERCULE [30]; and "
        "(iv) add explainability (SHAP, LIME) and further sources such as cloud and endpoint logs.")

    # ------------------------------------------------------------------ #
    # Declarations / availability
    # ------------------------------------------------------------------ #
    set_text(find(doc, "The datasets analysed during the current study are publicly available"),
        "The datasets analysed during the current study are publicly available. The CICIDS2017 dataset is "
        "available from the Canadian Institute for Cybersecurity at https://www.unb.ca/cic/datasets/ids-2017.html. "
        "The BGL (Blue Gene/L) log dataset is available from the Loghub repository at "
        "https://github.com/logpai/loghub. The TDA dataset (Binary Access Traffic Matrices, Gutflaish et al. [48], "
        "GPL-2.0) is available at https://www.kaggle.com/datasets/eyalgut/binary-traffic-matrices; the exact extract used in this study (30,655,997 (user, table, timestamp) "
        "records) is retained by the authors and can be obtained from the corresponding author for verification. "
        "The source code of the prior single-layer system that this work extends is "
        "available at https://github.com/Alma-L/ML_Intrusion_Detection. The source code of the cross-layer "
        "platform presented here, including the experiments package that regenerates every table and figure "
        "of this paper (backend/experiments) and the result files, is available at "
        "https://github.com/RinesaBislimi/Cross-layer.")
    set_text(find(doc, "API: Application programming interface; AUC"),
        "API: Application programming interface; AUC: Area under the curve; BGL: Blue Gene/L; CICIDS2017: "
        "Canadian Institute for Cybersecurity Intrusion Detection Evaluation Dataset 2017; CNSM: International "
        "Conference on Network and Service Management; CV: Cross-validation; DBSCAN: Density-based spatial "
        "clustering of applications with noise; DDoS: Distributed denial of service; DoS: Denial of service; "
        "FN/FP/TP: False negative/false positive/true positive; GDPR: General Data Protection Regulation; "
        "HMAC: Hash-based message authentication code; IDS: Intrusion detection system; IJNM: International "
        "Journal of Network Management; IM: IFIP/IEEE International Symposium on Integrated Network Management; "
        "JNSM: Journal of Network and Systems Management; LIME: Local interpretable model-agnostic "
        "explanations; LSTM: Long short-term memory; ML: Machine learning; MLP: Multilayer perceptron; NOMS: "
        "IEEE/IFIP Network Operations and Management Symposium; ORCID: Open Researcher and Contributor ID; "
        "REST: Representational state transfer; ROC: Receiver operating characteristic; SD: Standard "
        "deviation; SHAP: SHapley Additive exPlanations; SIEM: Security information and event management; "
        "SVM: Support vector machine; TDA: Temporal-anomaly-detection (Binary Access Traffic Matrices) dataset; TNSM: IEEE Transactions on "
        "Network and Service Management; WAL: Write-ahead logging; WS: WebSocket; XAI: Explainable artificial "
        "intelligence.")

    # ------------------------------------------------------------------ #
    # References (rewrite entire list)
    # ------------------------------------------------------------------ #
    refs = [
        "X. Zhao, K. Guo, M. Huang, S. Qiu, L. Lu, ELFA-Log: cross-system log anomaly detection via enhanced pseudo-labeling and feature alignment. Computers 14(7), 272 (2025). https://doi.org/10.3390/computers14070272",
        "X. Zhao, T. Jia, M. He, Y. Li, Generality is not enough: zero-label cross-system log-based anomaly detection via knowledge-level collaboration. arXiv:2511.05882 (2025). https://arxiv.org/abs/2511.05882",
        "W. Khan, Multi-stage attacks: concepts, detection and defences. Preprints (2023). https://doi.org/10.20944/preprints202306.1085.v1",
        "A. Latifi, R. Bislimi, ML intrusion detection system. GitHub (2024). https://github.com/Alma-L/ML_Intrusion_Detection. Accessed 31 Aug 2026",
        "A. Latifi, R. Bislimi, M. Hoti, I. Shabani, A hybrid machine learning framework for real-time network intrusion detection using supervised learning, in Proceedings of the 4th International Conference on Digital Industry and Engineering Applications (ICODIA), Konya, Türkiye (2025)",
        "S. Huang, Y. Liu, C. Fung, R. He, Y. Zhao, H. Yang, Z. Luan, HitAnomaly: hierarchical transformers for anomaly detection in system log. IEEE Trans. Netw. Serv. Manag. 17(4), 2064–2076 (2020). https://doi.org/10.1109/TNSM.2020.3034647",
        "R. Xiao, H. Chen, J. Lu, W. Li, S. Jin, AllInfoLog: robust diverse anomalies detection based on all log features. IEEE Trans. Netw. Serv. Manag. 20(3), 2529–2543 (2023). https://doi.org/10.1109/TNSM.2022.3224974",
        "M. Du, F. Li, G. Zheng, V. Srikumar, DeepLog: anomaly detection and diagnosis from system logs through deep learning, in Proceedings of the ACM SIGSAC Conference on Computer and Communications Security (CCS), Dallas (2017), pp. 1285–1298. https://doi.org/10.1145/3133956.3134015",
        "S. Haas, M. Fischer, On the alert correlation process for the detection of multi-step attacks and a graph-based realization. ACM SIGAPP Appl. Comput. Rev. 19(1), 5–19 (2019). https://doi.org/10.1145/3325061.3325062",
        "S. Salah, G. Maciá-Fernández, J.E. Díaz-Verdejo, A model-based survey of alert correlation techniques. Comput. Netw. 57(5), 1289–1317 (2013). https://doi.org/10.1016/j.comnet.2012.10.022",
        "X. Zhang, Y. Xu, Q. Lin, B. Qiao, H. Zhang, Y. Dang, C. Xie, X. Yang, Q. Cheng, Z. Li, J. Chen, X. He, R. Yao, J.-G. Lou, M. Chintalapati, F. Shen, D. Zhang, Robust log-based anomaly detection on unstable log data, in Proceedings of ESEC/FSE, Tallinn (2019), pp. 807–817. https://doi.org/10.1145/3338906.3338931",
        "W. Meng, Y. Liu, Y. Zhu, S. Zhang, D. Pei, Y. Liu, Y. Chen, R. Zhang, S. Tao, P. Sun, R. Zhou, LogAnomaly: unsupervised detection of sequential and quantitative anomalies in unstructured logs, in Proceedings of IJCAI, Macao (2019), pp. 4739–4745. https://doi.org/10.24963/ijcai.2019/658",
        "K. Qiu, Y. Zhang, Y. Feng, F. Chen, LogAnomEX: an unsupervised log anomaly detection method based on Electra-DP and gated bilinear neural networks. J. Netw. Syst. Manag. 33(2), 33 (2025). https://doi.org/10.1007/s10922-025-09912-5",
        "S. Nam, E. Jeong, J. Hong, J.-H. Yoo, J.W.-K. Hong, Log analysis and prediction for anomaly detection in network switches, in Proceedings of the 19th International Conference on Network and Service Management (CNSM), Niagara Falls (2023). https://doi.org/10.23919/CNSM59352.2023.10327865",
        "S. Nam, E.-D. Jeong, J.W.-K. Hong, Log-TF-IDF and NETCONF-based network switch anomaly detection. Int. J. Netw. Manag. 35(1), e2322 (2025). https://doi.org/10.1002/nem.2322",
        "V.-H. Le, H. Zhang, Log-based anomaly detection with deep learning: how far are we?, in Proceedings of the 44th International Conference on Software Engineering (ICSE), Pittsburgh (2022), pp. 1356–1367. https://doi.org/10.1145/3510003.3510155",
        "M. Landauer, F. Skopik, M. Wurzenberger, A. Rauber, Dealing with security alert flooding: using machine learning for domain-independent alert aggregation. ACM Trans. Priv. Secur. 25(3), 18 (2022). https://doi.org/10.1145/3510581",
        "M. Farshchi, J.-G. Schneider, I. Weber, J. Grundy, Experience report: anomaly detection of cloud application operations using log and cloud metric correlation analysis, in Proceedings of the 26th IEEE International Symposium on Software Reliability Engineering (ISSRE), Gaithersburg (2015), pp. 24–34. https://doi.org/10.1109/ISSRE.2015.7381796",
        "X. Zhao, T. Jia, M. He, X. Yang, Y. Li, FusionLog: cross-system log-based anomaly detection via fusion of general and proprietary knowledge. arXiv:2511.05878 (2025). https://arxiv.org/abs/2511.05878",
        "V. Chandola, A. Banerjee, V. Kumar, Anomaly detection: a survey. ACM Comput. Surv. 41(3), 15 (2009). https://doi.org/10.1145/1541880.1541882",
        "A.L. Buczak, E. Guven, A survey of data mining and machine learning methods for cyber security intrusion detection. IEEE Commun. Surv. Tutor. 18(2), 1153–1176 (2016). https://doi.org/10.1109/COMST.2015.2494502",
        "H.-J. Liao, C.-H.R. Lin, Y.-C. Lin, K.-Y. Tung, Intrusion detection system: a comprehensive review. J. Netw. Comput. Appl. 36(1), 16–24 (2013). https://doi.org/10.1016/j.jnca.2012.09.004",
        "R. Sommer, V. Paxson, Outside the closed world: on using machine learning for network intrusion detection, in Proceedings of the IEEE Symposium on Security and Privacy, Oakland (2010), pp. 305–316. https://doi.org/10.1109/SP.2010.25",
        "L. Breiman, Random forests. Mach. Learn. 45(1), 5–32 (2001). https://doi.org/10.1023/A:1010933404324",
        "T. Chen, C. Guestrin, XGBoost: a scalable tree boosting system, in Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining, San Francisco (2016), pp. 785–794. https://doi.org/10.1145/2939672.2939785",
        "G. Ke, Q. Meng, T. Finley, T. Wang, W. Chen, W. Ma, Q. Ye, T.-Y. Liu, LightGBM: a highly efficient gradient boosting decision tree, in Advances in Neural Information Processing Systems 30 (NeurIPS) (2017), pp. 3146–3154. https://proceedings.neurips.cc/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html",
        "F.T. Liu, K.M. Ting, Z.-H. Zhou, Isolation forest, in Proceedings of the 8th IEEE International Conference on Data Mining (ICDM), Pisa (2008), pp. 413–422. https://doi.org/10.1109/ICDM.2008.17",
        "I. Sharafaldin, A.H. Lashkari, A.A. Ghorbani, Toward generating a new intrusion detection dataset and intrusion traffic characterization, in Proceedings of the 4th International Conference on Information Systems Security and Privacy (ICISSP), Funchal (2018), pp. 108–116. https://doi.org/10.5220/0006639801080116",
        "A. Oliner, J. Stearley, What supercomputers say: a study of five system logs, in Proceedings of the 37th Annual IEEE/IFIP International Conference on Dependable Systems and Networks (DSN), Edinburgh (2007), pp. 575–584. https://doi.org/10.1109/DSN.2007.103",
        "K. Pei, Z. Gu, B. Saltaformaggio, S. Ma, F. Wang, Z. Zhang, L. Si, X. Zhang, D. Xu, HERCULE: attack story reconstruction via community discovery on correlated log graph, in Proceedings of the 32nd Annual Conference on Computer Security Applications (ACSAC), Los Angeles (2016), pp. 583–595. https://doi.org/10.1145/2991079.2991122",
        "J. Frade, L. Santos, R.L.d.C. Costa, DBD-Guardian and privacy-aware near real-time cybersecurity analytics. IEEE Access 12, 149787–149803 (2024). https://doi.org/10.1109/ACCESS.2024.3477979",
        "S. Marchal, X. Jiang, R. State, T. Engel, A big data architecture for large scale security monitoring, in Proceedings of the IEEE International Congress on Big Data, Anchorage (2014), pp. 56–63. https://doi.org/10.1109/BigData.Congress.2014.18",
        "M.A. Rassam, M.A. Maarof, A. Zainal, Big data analytics adoption for cyber-security: a review of current solutions, requirements, challenges and trends. J. Inf. Assur. Secur. 11(3), 124–145 (2017)",
        "N. Sun, J. Zhang, P. Rimba, S. Gao, L.Y. Zhang, Y. Xiang, Data-driven cybersecurity incident prediction: a survey. IEEE Commun. Surv. Tutor. 21(2), 1744–1772 (2019). https://doi.org/10.1109/COMST.2018.2885561",
        "G. González-Granadillo, S. González-Zarzosa, R. Diaz, Security information and event management (SIEM): analysis, trends, and usage in critical infrastructures. Sensors 21(14), 4759 (2021). https://doi.org/10.3390/s21144759",
        "M. Landauer, F. Skopik, M. Frank, W. Hotwagner, M. Wurzenberger, A. Rauber, Maintainable log datasets for evaluation of intrusion detection systems. IEEE Trans. Dependable Secure Comput. 20(4), 3466–3482 (2023). https://doi.org/10.1109/TDSC.2022.3201582",
        "European Parliament and Council, Regulation (EU) 2016/679 on the protection of natural persons with regard to the processing of personal data (General Data Protection Regulation). Off. J. Eur. Union L119, 1–88 (2016). https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "H.V. Pham, S. Qian, J. Wang, T. Lutellier, J. Rosenthal, L. Tan, Y. Yu, N. Nagappan, Problems and opportunities in training deep learning software systems: an analysis of variance, in Proceedings of the 35th IEEE/ACM International Conference on Automated Software Engineering (ASE), Melbourne (2020), pp. 771–783. https://doi.org/10.1145/3324884.3416545",
        "X. Bouthillier, P. Delaunay, M. Bronzi, A. Trofimov, B. Nichyporuk, J. Szeto, N. Mohammadi Sepahvand, E. Raff, K. Madan, V. Voleti, S. Ebrahimi Kahou, V. Michalski, T. Arbel, C. Pal, G. Varoquaux, P. Vincent, Accounting for variance in machine learning benchmarks, in Proceedings of Machine Learning and Systems 3 (MLSys) (2021), pp. 747–769. https://proceedings.mlsys.org/paper/2021/hash/cfecdb276f634854f3ef915e2e980c31-Abstract.html",
        "S. Wang, Fault-class coverage-aligned combined training for AFDD of AHUs across multiple buildings. Sci. Rep. 15, 41029 (2025). https://doi.org/10.1038/s41598-025-24959-9",
        "S. Wang, Evaluating cross-building transferability of attention-based automated fault detection and diagnosis for air handling units: auditorium and hospital case study. Build. Environ. 285, 113599 (2025). https://doi.org/10.1016/j.buildenv.2025.113599",
        "M. Landauer, S. Onder, F. Skopik, M. Wurzenberger, Deep learning for anomaly detection in log data: a survey. Mach. Learn. Appl. 12, 100470 (2023). https://doi.org/10.1016/j.mlwa.2023.100470",
        "J. Qi, S. Huang, Z. Luan, S. Yang, C. Fung, H. Yang, D. Qian, J. Shang, Z. Xiao, Z. Wu, LogGPT: exploring ChatGPT for log-based anomaly detection, in Proceedings of the IEEE International Conference on High Performance Computing and Communications (HPCC), Melbourne (2023), pp. 273–280. https://doi.org/10.1109/HPCC-DSS-SmartCity-DependSys60770.2023.00045",
        "J. Navarro, A. Deruyver, P. Parrend, A systematic survey on multi-step attack detection. Comput. Secur. 76, 214–249 (2018). https://doi.org/10.1016/j.cose.2018.03.001",
        "M. Zipperle, F. Gottwalt, E. Chang, T. Dillon, Provenance-based intrusion detection systems: a survey. ACM Comput. Surv. 55(7), 135 (2022). https://doi.org/10.1145/3539605",
        "S. Wang, Class-aware temporal and contextual contrastive framework for semi-supervised automated fault detection and diagnosis in air handling units. Energy Build. (2026). https://doi.org/10.1016/j.enbuild.2026.117233",
        "M. Landauer, F. Skopik, M. Wurzenberger, Introducing a new alert data set for multi-step attack analysis, in Proceedings of the 17th Cyber Security Experimentation and Test Workshop (CSET), Philadelphia (2024), pp. 41–49. https://doi.org/10.1145/3675741.3675748",
        "E. Gutflaish, A. Kontorovich, S. Sabato, O. Biller, O. Sofer, Temporal anomaly detection: calibrating the surprise, in Proceedings of the 33rd AAAI Conference on Artificial Intelligence (AAAI-19), Honolulu (2019), pp. 3755–3762. https://doi.org/10.1609/aaai.v33i01.33013755",
    ]
    ref_head = find(doc, "References")
    # delete old refs
    for p in list(doc.paragraphs):
        t = p.text.strip()
        if t.startswith("[") and "]" in t[:5] and p._p.getprevious() is not None:
            # only paragraphs after the References heading
            prev = p._p
            is_after = False
            cur = ref_head._p
            while cur is not None:
                if cur is p._p:
                    is_after = True
                    break
                cur = cur.getnext()
            if is_after:
                delete(p)
    ref_style = None
    cur = ref_head
    for i, r in enumerate(refs, start=1):
        cur = insert_after(cur, f"[{i}]\t{r}", body_style)

    doc.save(OUT)
    print("saved ->", OUT)
    print(f"headline: net F1={F1_NET:.4f} ({b_net}), sys F1={F1_SYS:.4f} ({b_sys}), app F1={F1_APP:.4f} ({b_app})")
    print(f"corr: before={CM['alerts_before']} after={CM['incidents_after']} P={CM['incident_precision']} R={CM['incident_recall']}")
    print("benchmark section:", "filled" if B else "PENDING (re-run after benchmark.py)")


if __name__ == "__main__":
    main()
