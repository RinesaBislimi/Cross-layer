"""Generate the point-by-point response to the editor and reviewers (.docx).

Reads the same JSON result files as revise_manuscript.py so every number
quoted in the response matches the revised manuscript.

Usage (from backend/):  python experiments/write_response.py
Output: C:/Users/Admin/Downloads/Response_to_Reviewers_CrossLayer.docx
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import revise_manuscript as R  # noqa: E402  (loads M, C, T, S2, B and helpers)

OUT = Path(r"C:\Users\Admin\Downloads\Response_to_Reviewers_CrossLayer.docx")

M, C, T, S2, B = R.M, R.C, R.T, R.S2, R.B
T2, A = R.T2, R.A
CM, WS, ABL, SC = R.CM, R.WS, R.ABL, R.SEEDS_C
S2L, S2R = R.S2L, R.S2R
mm, ms, MODEL_NAME = R.mm, R.ms, R.MODEL_NAME
lay = {r["dataset"]: r for r in B["layers"]}
corr = B["correlation"]
best_w = R.best_w
tt, tr = T["temporal"], T["random"]
s_net, s_sys, s_app = R.summ("CICIDS2017"), R.summ("BGL"), R.summ("TDA")


def main():
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)

    d.add_heading("Point-by-point response to the Editor and Reviewers", 0)
    d.add_paragraph(
        'Manuscript: "A Cross-Layer Log Monitoring and Analysis System Using Machine Learning" — '
        "Journal on Information Security (Springer). Submission ID 230ca5f3-0951-47a3-898e-7c64c243c4a9.")
    d.add_paragraph(
        "We thank the Editor and the four Reviewers for their careful and constructive reading. We have "
        "undertaken a comprehensive revision. In summary, the revised manuscript (i) evaluates the cross-layer "
        "correlation engine quantitatively on a controlled benchmark with known ground truth, including a "
        "window sensitivity analysis and an ablation; (ii) adds a learned second-stage incident classifier so "
        "that machine learning operates across layers, and evaluates it; (iii) reports all six algorithms on "
        "all three datasets with mean ± SD over five seeds, training/inference time, an order-preserving split, "
        "and complete hyperparameters; (iv) documents every feature, the cleaning and labelling of each dataset, "
        "the scaling (fitted on training data only) and the handling of imbalance; (v) adds system-level "
        "throughput, latency and memory measurements; (vi) adds a privacy/GDPR section, a SIEM/HERCULE "
        "comparison and a refreshed related-work section with DOIs; (vii) separates the two figures that shared "
        "the label Figure 1; (viii) strongly re-frames the pseudo-labelled application layer; and (ix) ships "
        "scripted experiments that regenerate every table and figure. Every number in the revised paper was "
        "produced by these scripts; where the new, more rigorous protocol changed a previously reported value "
        "(notably the BGL and CICIDS2017 scores), we say so explicitly in the paper. Section, table and figure "
        "numbers below refer to the revised manuscript.")

    def comment(txt):
        p = d.add_paragraph()
        r = p.add_run("Comment. ")
        r.bold = True
        p.add_run(txt).italic = True

    def response(txt):
        p = d.add_paragraph()
        r = p.add_run("Response. ")
        r.bold = True
        r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        p.add_run(txt)

    def changes(txt):
        p = d.add_paragraph()
        r = p.add_run("Changes. ")
        r.bold = True
        p.add_run(txt)

    # ------------------------------------------------------------------ #
    d.add_heading("Editor", 1)
    comment("The reviewers have identified significant shortcomings ... all the comments and concerns must be "
            "addressed carefully and thoroughly ... ensure the results are accurately reported, any overstated "
            "conclusions are rewritten and the limitations of the work fully explained.")
    response("We have addressed every comment below. Results are now reported with variance and were regenerated "
             "from scripted, deterministic experiments; overstated statements (perfect F1, 'scalable' without "
             "evidence, 'cross-layer ML' without a learned cross-layer component) were either backed by new "
             "evidence or rewritten; and the limitations are consolidated in Sections 7.3–7.5 and in the "
             "Conclusions.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 1", 1)
    comment("1. The central cross-layer contribution should be evaluated quantitatively ... number of alerts "
            "before and after correlation, correctly reconstructed multi-stage incidents, false correlations, "
            "incident-level precision/recall.")
    response(f"We agree. New Section 6.3 reports exactly these quantities on a benchmark with known ground truth "
             f"(200 planted multi-stage chains, 12,000 distractor alerts). At the default W = 60 s the engine "
             f"compresses {CM['alerts_before']:,} alerts into {CM['incidents_after']} incidents "
             f"({100*CM['reduction_ratio']:.1f}% reduction), reconstructs {CM['tp']}/200 incidents, produces "
             f"{CM['fp']} false correlations and misses {CM['fn']}, i.e. incident precision {CM['incident_precision']:.3f}, "
             f"recall {CM['incident_recall']:.3f}, F1 {CM['incident_f1']:.3f}; across five benchmark seeds "
             f"P = {SC['incident_precision']['mean']:.3f} ± {SC['incident_precision']['std']:.3f}, "
             f"R = {SC['incident_recall']['mean']:.3f} ± {SC['incident_recall']['std']:.3f}. We also add a sensitivity "
             f"analysis over W (Table 10, Fig. 4) and an ablation of the layer-ordering constraint "
             f"(FP {ABL['without_order']['fp']} → {ABL['with_order']['fp']} when the constraint is enabled).")
    changes("Sections 6.3.1–6.3.2, Tables 9–10, Fig. 4; Section 7.2 rewritten; new script correlation_eval.py.")

    comment("2. The cross-layer use of the three independent datasets requires much clearer explanation ... "
            "whether cross-layer incidents were synthetically constructed, temporally aligned, or otherwise mapped.")
    response("The reviewer is right that this was not explicit. The three datasets are not linked at the event "
             "level and cannot be: they were captured in different environments and years. The revised paper "
             "states this plainly (Sections 6.3.1 and 7.5). Cross-layer incidents for evaluating the correlation "
             "engine are therefore synthetically constructed and temporally aligned in a controlled "
             "attack-injection benchmark whose construction is described step by step in Section 6.3.1 (shared "
             "entity pool, planted network→system→application chains within a 40 s span, dense independent "
             "distractors from the same pool). The per-layer detectors are still trained and evaluated on the real "
             "datasets. We also explain how heterogeneous identifiers are canonicalised and matched in a real "
             "deployment (Section 4.4, 'Identifier matching').")
    changes("Sections 4.4, 6.3.1, 7.2, 7.5.")

    comment("3. The evaluation of the TDA application layer should be interpreted more cautiously ... reported "
            "MLP performance mainly reflects agreement with the pseudo-labeling procedure.")
    response("We fully agree and now say so in the strongest terms. A dedicated Section 7.3 ('The application "
             "layer: agreement with pseudo-labels, not verified accuracy') states that the TDA scores measure "
             "reproduction of the Isolation Forest labelling, that they must not be compared with the other "
             "layers, that the supervised Isolation Forest row is the natural reference point, and that any blind "
             "spot of the pseudo-labeller is inherited. The abstract, Section 4.2, Table 2, Section 6.1 and the "
             "Conclusions carry the same caveat. During the revision we also found and corrected a discrepancy "
             "between the service code and the paper: the ingestion code had been assigning placeholder random "
             "labels to TDA instead of Isolation Forest labels; the code now matches the paper and all TDA numbers "
             "were regenerated with Isolation Forest pseudo-labels (contamination 0.05, 100 trees).")
    changes("Section 7.3 (new), Section 4.2, Table 2, Abstract, Conclusions; backend code ingestion.py / "
            "feature_engineering.py.")

    comment("4. The influence of experimental randomness on the reported deep-learning results should be examined "
            "more carefully ... cite empirical studies on randomness, data partitioning and experimental settings "
            "(five AHU AFDD papers listed).")
    response("All per-layer metrics are now means ± SD over five seeds that control both the data partition and "
             "the learner initialisation (Table 7), five-fold CV on the training partition is reported as an "
             "independent variance estimate, and the correlation benchmark is repeated over five seeds. A new "
             "Section 7.4 discusses the sources of randomness and the observed variance (largest for the MLP/SVM "
             "and on the pseudo-labelled layer). Regarding the suggested citations: we located and cite three of "
             "the listed works — 'Fault-class coverage-aligned combined training for AFDD of AHUs across multiple "
             "buildings' (Sci. Rep. 2025, ref [40]), the attention-based cross-building AHU study (Build. Environ., "
             "ref [41]) and 'Class-aware temporal and contextual contrastive framework for semi-supervised AFDD in "
             "AHUs' (Energy Build. 2026, ref [46]) — together with general variance studies [38, 39] and Le & Zhang "
             "[16]. For 'Automated fault detection and diagnosis of AHUs via tabular-based methods using operational "
             "data from a large office building', 'Empirical comparison of sequence-aware augmentation strategies "
             "...' and 'Coverage-aware multi-head TabNet ...' we could not retrieve a venue or DOI from any index "
             "available to us (only an unindexed ResearchGate listing for the first); we would gladly add them if "
             "the reviewer can provide the references.")
    changes("Section 3 (paragraph on randomness), Section 7.4 (new), Table 7, refs [38–41].")

    comment("5. The claims of scalability and real-time applicability should be supported by empirical "
            "system-level measurements ... throughput, processing latency, memory usage, events-per-second.")
    response(f"New Section 6.4 and Table 12 report, on a single workstation: batch detection throughput of "
             f"{lay['CICIDS2017']['batch_events_per_s']:,.0f} / {lay['BGL']['batch_events_per_s']:,.0f} / "
             f"{lay['TDA']['batch_events_per_s']:,.0f} events/s for the network/system/application detectors; "
             f"single-event latency (mean and p99); correlation-engine throughput of "
             f"{corr['scaling'][-1]['events_per_s']:,.0f} alerts/s at {corr['scaling'][-1]['n_events']:,} alerts with an "
             f"empirical scaling exponent of {corr['empirical_exponent']:.2f} (1 = linear); and peak memory "
             f"({B['host']['peak_python_mem_mb']:.0f} MB Python heap). The abstract and conclusions now claim only what "
             "these measurements support (single-node operation at ~10⁵ events/s after feature extraction) and "
             "state what is excluded (network and storage I/O).")
    changes("Section 6.4, Table 12; Abstract and Section 8 reworded; script benchmark.py.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 2", 1)
    comment("The number of references is not sufficient; many are old; many lack DOI/URL. Update references, "
            "rework SOTA (Sections 1, 2, 3).")
    response("The reference list grew from 29 to 48 entries; every entry now carries a DOI or a stable URL. "
             "Added works include HERCULE (ACSAC 2016), DBD-Guardian (IEEE Access 2024), the SIEM and big-data "
             "security-analytics literature (Marchal 2014, Rassam 2017, Sun 2019, González-Granadillo 2021), the "
             "AIT Log Data Set (TDSC 2023), GDPR, variance studies (ASE 2020, MLSys 2021), two 2025 AHU AFDD "
             "studies, a 2023 deep-learning-for-logs survey, LogGPT (2023), a multi-step attack detection survey "
             "and a provenance-based IDS survey. Sections 1, 2 (with new 2.4 'SIEM and big-data security "
             "analytics' and 2.5 'Positioning') and 3 were rewritten accordingly, and Table 1 now includes "
             "HERCULE, Marchal et al. and DBD-Guardian with a 'correlation evaluated' column. The older "
             "references that remain are foundational (Random Forest, XGBoost, Isolation Forest, the dataset "
             "papers, Chandola's survey).")
    changes("Sections 1–3, Table 1, References.")

    comment("The novel element — cross-layer correlation into multi-stage incidents — is supported mainly by "
            "description rather than a controlled quantitative experiment.")
    response("Addressed by the new controlled experiment of Section 6.3 (see Reviewer 1, point 1) and by the "
             "learned second-stage classifier of Sections 4.5 and 6.3.3.")

    comment("Complete all missing Table 3 metrics.")
    response("The old Table 3 (and its internal 'n.r.' note) is replaced by Table 7, which reports precision, "
             "recall, F1, ROC-AUC, CV F1, training time and inference throughput for all 18 model–dataset pairs.")

    comment("Report all six models, not just winners, preferably mean ± SD.")
    response("Done: Table 7 and Fig. 3 report all six models on all three datasets as mean ± SD over five seeds.")

    comment("Add temporal/session-aware evaluation for CICIDS2017.")
    if T2:
        c_, g_, w_, r_, s_ = T2["cross_day"], T2["by_source_ip"], T2["within_day"], T2["random"], T2["by_session"]
        response(f"New Section 6.2 and Table 8 evaluate CICIDS2017 on the original timestamped per-day flow files "
                 f"under four protocols: within-day chronological (LightGBM F1 = {w_['lgbm']['f1']:.3f}, random split "
                 f"on the same rows {r_['lgbm']['f1']:.3f}); strict cross-day Monday-Wednesday -> Thursday-Friday "
                 f"(F1 = {c_['lgbm']['f1']:.3f} LightGBM / {c_['rf']['f1']:.3f} Random Forest, with a per-attack-family "
                 f"diagnostic); host-disjoint StratifiedGroupKFold on source IP (F1 = {g_['lgbm']['f1']:.3f} ± "
                 f"{g_['lgbm']['f1_std']:.3f} / {g_['rf']['f1']:.3f} ± {g_['rf']['f1_std']:.3f}); and session-disjoint "
                 f"by (source, destination) pair (F1 = {s_['lgbm']['f1']:.3f} ± {s_['lgbm']['f1_std']:.3f} / "
                 f"{s_['rf']['f1']:.3f} ± {s_['rf']['f1_std']:.3f}). The paper now states plainly that the near-perfect "
                 "random-split score is conditional on the attacking hosts and attack families being represented in "
                 "training, that the earlier version overstated the generality of the network layer, and that this "
                 "strengthens the case for cross-layer correlation (Sections 6.2, 7.1, 7.5).")

    else:
        response(f"New Section 6.2 and Table 8 add an order-preserving 70/15/15 split: LightGBM F1 = {tt['f1']:.3f} versus "
                 f"{tr['f1']:.3f} under the random split; we are explicit that this is a block split on the consolidated CSV.")

    comment("Clarify exactly how 70/15/15 and five-fold CV interact.")
    response("Section 4.3 ('Evaluation protocol') now states it precisely: per seed, a stratified 70/15/15 split; "
             "five-fold stratified CV on the 70% training partition only (variance estimate/model selection); the "
             "15% validation partition for MLP early stopping; all headline metrics on the untouched 15% test "
             "partition; repeated over five seeds and averaged.")

    comment("Complete the TDA URL and preferably release the cross-layer implementation.")
    response("The TDA dataset is now identified as the Binary Access Traffic Matrices dataset of Gutflaish et al. (AAAI-19, new ref [48]) and its URL is given in the 'Availability of data and materials' statement and in Section 4.1 (https://www.kaggle.com/datasets/eyalgut/binary-traffic-matrices). The "
             "cross-layer implementation, including the experiments package that regenerates every table and "
             "figure, is referenced at https://github.com/RinesaBislimi/Cross-layer in the same statement and in "
             "Section 5.3.")

    comment("Precision = Recall = F1 = ROC-AUC = 1.000 can indicate overfitting.")
    response(f"We agree that an exact 1.000 deserved scrutiny. Under the new protocol (stratified random sample over "
             f"the whole file, five seeds, train-only scaling) the CICIDS2017 scores are {R.F1_NET:.4f} ± "
             f"{mm('CICIDS2017', R.b_net, 'f1')['std']:.4f} F1 for LightGBM — high but not perfect, with non-zero variance. "
             "Section 7.1 explains why the earlier 1.000 arose (single run on a non-random prefix), why the data "
             "are not an imbalance artefact, why the benchmark is highly separable, and what the order-preserving "
             "split does and does not rule out.")

    comment("TDA has no verified ground truth; Isolation Forest labels; MLP F1 = 0.848 / ROC-AUC = 0.993 against "
            "generated labels.")
    response("See Reviewer 1, point 3: Section 7.3 is devoted to this limitation and the values are now reported "
             "as agreement with pseudo-labels, with the supervised Isolation Forest as the reference row.")

    comment("How can an event in CICIDS2017 genuinely correspond to an event in BGL or TDA? This is the fundamental "
            "dataset/correlation problem.")
    response("It cannot, and the revised paper says so (Sections 6.3.1 and 7.5). The correlation engine is "
             "therefore evaluated on a documented controlled benchmark, and evaluation on a dataset whose layers are "
             "genuinely linked (AIT Log Data Set V2) is identified as the first priority of future work; the "
             "experiments package accepts any source providing (timestamp, layer, entity, label, score) tuples.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 3", 1)
    comment("It is not clear what rationale is used for correlating the events.")
    response("Section 4.4 now opens with the rationale (same actor, same target, bounded dwell time, outside-in "
             "progression), defines the three criteria (window, shared canonical identifier, layer ordering), "
             "explains identifier matching, transitivity and deduplication, and gives a step-by-step worked example "
             "with six concrete alerts.")

    comment("Privacy-related concerns; GDPR.")
    response("New Section 4.6 'Privacy and regulatory considerations' describes pseudonymisation of identifiers "
             "with a keyed hash (HMAC-SHA-256) at ingestion, data minimisation (identifiers are never model "
             "features), storage limitation and purpose limitation/access control, relates them to GDPR Articles "
             "5, 25 and 32 and Recital 49, and notes that a deployment-specific impact assessment is still required. "
             "The dashboard displays pseudonyms only (Section 5.4).")

    comment("No evidence for 'a scalable and practical basis for real-world, high-volume environments'.")
    response("See Reviewer 1, point 5: Section 6.4 provides measured throughput, latency, scaling exponent and "
             "memory, and the claim is reworded to match the evidence.")

    comment("Background and related work must be improved; compare with SIEMs; consider Frade et al., Marchal et "
            "al., Rassam et al., Sun et al.")
    response("All four suggested works are cited and discussed in the new Section 2.4, which also contrasts the "
             "proposal with SIEM platforms along three axes (learned per-event alerts, a single characterised "
             "correlation rule instead of rule libraries, learned incident scoring) and states what a SIEM offers "
             "that our prototype does not; Table 1 includes Marchal et al. and DBD-Guardian.")

    comment("The methodology is typical; the contribution is not clear.")
    response("Section 1.2 restates the four contributions so that each is tied to new evidence: the unified "
             "pipeline; the correlation engine with a learned second stage, quantitatively evaluated; the complete "
             "six-model comparison with variance, timing and an order-preserving split; and the system-level "
             "evidence, privacy design and reproducible scripts. We do not claim novelty in the per-layer "
             "ingestion/feature/training stages themselves.")

    comment("Feature engineering: identify the features, the rationale, and the preprocessing.")
    response("Tables 3, 4 and 5 list all 52 CICIDS2017, 10 BGL and 6 TDA predictors with their meaning and "
             "rationale; Section 4.2 explains which 26 CICFlowMeter columns were excluded and why; Section 4.1 "
             "documents cleaning (infinite values, NaN, duplicates, with counts) and sampling; Section 4.3 "
             "documents z-scoring fitted on the training partition only.")

    comment("Are the data balanced? Is there any bias that led to the perfect F1?")
    response(f"Table 2 reports class proportions ({100*s_net['positive_rate']:.1f}% attack in CICIDS2017, "
             f"{100*s_sys['positive_rate']:.1f}% anomalous in BGL, 5% by construction in TDA). Section 7.1 discusses "
             "the near-perfect score: it is not an imbalance artefact (precision and recall are both > 0.99), it "
             "reflects the strong separability of several attack classes, and under the new protocol it is no "
             "longer exactly 1.000.")

    comment("How does the inter-layer correlation affect the results? Different solutions at each layer? Ablation?")
    response("Per-layer detection and cross-layer correlation are evaluated separately by design: Table 7 reports "
             "six alternative detectors for every layer (not one), and Section 6.3 evaluates the correlation stage "
             "on its own with an ablation of the layer-ordering constraint and a comparison of the fixed rule "
             f"against learned second-stage classifiers (F1 {S2R['f1']['mean']:.3f} → {S2L['f1']['mean']:.3f}).")

    comment("Reproducibility: make the proposal openly available.")
    response("The repository is referenced in the Availability statement and Section 5.3 lists the scripts that "
             "regenerate every table and figure from the raw CSV files without the database or API.")

    comment("The frontend module is not described in sufficient detail.")
    response("New Section 5.4 describes the eleven dashboard modules (Dashboard, Logs, Incidents with analyst "
             "confirm/dismiss feeding the second-stage model, Attack chains, Entities, Heatmap, Analysis, Alert "
             "rules, Response rules, Statistics, Reports), the REST/WebSocket plumbing and the pseudonymised display.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 4", 1)
    comment("The source code of the cross-layer platform is not publicly available.")
    response("The repository (including the experiments package) is referenced in the Availability statement and "
             "Section 5.3.")

    comment("The work does not deliver what its title promises: the ML is not cross-layer and the cross-layer "
            "part is not ML. Either tone down the title and claims or introduce a learned component operating "
            "across layers (cf. HERCULE).")
    response("We took the second route and also tempered the claims. The system already contained a second-stage "
             "model trained on aggregate cross-layer features; it was not described or evaluated in the original "
             "submission. Section 4.5 now defines it formally (eight features per candidate incident: per-layer "
             "counts, number of layers, span, max/mean score, order flag), Section 6.3.3 and Table 11 evaluate it on "
             f"the benchmark (fixed rule F1 {S2R['f1']['mean']:.3f} → LightGBM {S2L['f1']['mean']:.3f} ± "
             f"{S2L['f1']['std']:.3f}), and Fig. 2 shows it in the architecture. Section 7.2 states explicitly that "
             "learning happens per layer and then on incident features (late fusion), that early fusion/multimodal "
             "or graph models (HERCULE) are an alternative, and that we do not claim to outperform HERCULE. The "
             "title is retained because machine learning is now applied both within and across layers; the "
             "abstract and Section 1 describe the two levels precisely.")

    comment("A list of the predictors for each layer is missing; features removed from CICIDS2017; BGL's ten "
            "features; TDA's six; a table per dataset with features, samples and class proportions.")
    response("Tables 2–5 provide exactly this (see Reviewer 3, feature engineering).")

    comment("Normalisation method and whether the scaler was fitted on the training set only; cleaning of "
            "CICIDS2017; parser/classification unit for BGL; handling of class imbalance.")
    response("Section 4.3: z-scoring inside a scikit-learn Pipeline, fitted on the training partition only and "
             "refitted within CV folds (the service code was changed accordingly). Section 4.1: CICIDS2017 cleaning "
             "with counts; BGL needs no template parser because the alert flag in the first field is the label and "
             "the unit is one log line, with lexical features from the raw message; imbalance is handled by "
             "stratification, by metric choice and by contamination = positive rate for Isolation Forest, with no "
             "resampling.")

    comment("Not compared with any multi-source correlation approach, e.g. HERCULE.")
    response("HERCULE is now discussed in Section 2.3, included in Table 1 and contrasted in Section 7.2; a direct "
             "empirical comparison requires jointly captured logs and is part of the AIT-LDS future work.")

    comment("Six algorithms are compared yet Table 3 reports one model per dataset; hyperparameters not reported; "
            "remove the internal 'n.r.' note.")
    response("Table 7 reports all algorithms on all datasets with precision, recall, F1, ROC-AUC (mean ± SD), CV "
             "F1, training and inference time; Table 6 lists all hyperparameters; the 'n.r.' note is removed.")

    comment("The datasets do not originate from a single real system; repeat the evaluation on datasets whose "
            "layers are genuinely linked, e.g. AIT Log Data Set V2.")
    if A and A.get("scenarios"):
        ag = A["aggregate"]["W=60"]; n_scen = len(A["scenarios"]); ms_ = A.get("second_stage_loso_mean", {})
        response(f"We agree and have added Section 6.5 and Table 13: the correlation engine was run on the AIT Alert "
                 f"Data Set (alerts from Suricata, Wazuh and AMiner on all {n_scen} AIT-LDS v2 testbeds, where network, "
                 f"system and application logs of the same hosts are captured together with attack-phase ground truth). "
                 f"Averaged over scenarios the engine reduces triage volume by {100*ag['reduction_ratio']['mean']:.1f}%, "
                 f"with incident precision {ag['incident_precision']['mean']:.3f} ± {ag['incident_precision']['std']:.3f} and "
                 f"attack-alert recall {ag['attack_alert_recall']['mean']:.3f} ± {ag['attack_alert_recall']['std']:.3f}, and in "
                 f"{ag['scenarios_with_multilayer_attack_incident']} of {n_scen} scenarios the attack is reconstructed as a "
                 f"cross-layer incident"
                 + (f"; a leave-one-scenario-out second-stage classifier on the eight generic features is precise "
                    f"({ms_['lgbm']['precision']:.3f}) but recovers only {100*ms_['lgbm']['recall']:.1f}% of attack candidates "
                    f"(F1 {ms_['lgbm']['f1']:.3f} vs {ms_['rule']['f1']:.3f} for the rule), a negative transfer result that "
                    "the paper reports as such" if ms_ else "")
                 + ". Because the alerts come from third-party detectors, the end-to-end run of our own per-layer detectors "
                 "on the raw AIT-LDS v2 logs (7-26 GB per scenario) remains future work; the experiments package ships a "
                 "ready-to-run harness for it (experiments/ait_lds_eval.py). Sections 6.3.1, 7.5 and 8 keep the limitation explicit.")
    else:
        response("We agree this is the most important remaining limitation and state it in Sections 6.3.1, 7.5 and 8. "
                 "Within the revision period we could not complete a full AIT-LDS v2 evaluation (the smallest scenario "
                 "is 7 GB and the download could not be completed in time); the experiments package now contains a "
                 "ready-to-run AIT-LDS v2 harness (experiments/ait_lds_eval.py) that parses a scenario, maps its logs "
                 "to the three layers, trains per-layer detectors and runs Algorithm 1 against the line-level ground "
                 "truth, and we list this evaluation as the first priority of future work.")

    comment("Section 4.2's 'four aggregate cross-layer features' are undefined and contradict the per-layer "
            "design; remove them or define them and use them in a second-stage model.")
    response("Done: Section 4.2 now states that these features are not inputs to the per-layer detectors, and "
             "Section 4.5 defines the aggregate cross-layer features formally and uses them in the learned "
             "second-stage classifier evaluated in Section 6.3.3.")

    comment("The correlation engine is described only by pseudocode; how are heterogeneous identifiers matched, is "
            "correlation transitive, how does deduplication work, why W = 60 s; the layer-ordering constraint is "
            "missing from Algorithm 1; a step-by-step example and a sensitivity analysis on W are requested.")
    response(f"Section 4.4 now covers identifier canonicalisation and exact matching, transitivity via union–find "
             f"merging, deduplication, and the choice of W; Algorithm 1 is rewritten with the hash-map lookup, the "
             f"order filter (line 4) and the union–find merge (line 7); a worked example with six concrete alerts "
             f"follows the algorithm; Table 10 and Fig. 4 sweep W from 5 s to 600 s (incident F1 peaks at "
             f"W = {best_w['window_s']} s on the benchmark; 60 s is kept as a recall-favouring default and justified).")

    comment("Code available only 'on reasonable request'.")
    response("See the Availability statement and Section 5.3.")

    comment("The TDA URL is missing, and Figure 1 is used to illustrate two different things.")
    response("The TDA dataset is identified and linked (Binary Access Traffic Matrices, Gutflaish et al. [48], https://www.kaggle.com/datasets/eyalgut/binary-traffic-matrices). The figures are separated: Fig. 1 is a new multi-stage attack "
             "scenario figure (Introduction) and Fig. 2 is the architecture (Section 4), which also shows the "
             "second-stage classifier.")

    # ------------------------------------------------------------------ #
    d.add_heading("Summary of other changes", 1)
    for t in [
        "Abstract and Section 1.2 rewritten to state the two levels of learning, the quantitative correlation "
        "results, the variance reporting and the pseudo-label caveat.",
        "Section 3 adds a paragraph on experimental randomness with citations.",
        "Section 5.2 documents that scaling is implemented as a train-only Pipeline; Section 5.3 lists the "
        "reproducibility scripts.",
        f"Previously reported values superseded by the new protocol: CICIDS2017 LightGBM F1 1.000 → "
        f"{R.F1_NET:.3f} ± {mm('CICIDS2017', R.b_net, 'f1')['std']:.3f}; BGL Random Forest F1 0.910 → "
        f"{mm('BGL','rf','f1')['mean']:.3f} ± {mm('BGL','rf','f1')['std']:.3f} (stratified random sample over the whole "
        f"file instead of a non-random prefix); TDA MLP F1 0.848 → {mm('TDA','mlp','f1')['mean']:.3f} ± "
        f"{mm('TDA','mlp','f1')['std']:.3f} (Isolation Forest pseudo-labels regenerated; see Reviewer 1, point 3). "
        "The paper states these changes explicitly (Sections 6.1 and 7.1).",
        "Abbreviations list extended (CV, GDPR, HMAC, SD, SIEM, TP/FP/FN).",
        "Backend code changes: TDA ingestion no longer assigns placeholder random labels; StandardScaler moved "
        "inside the SVM/MLP pipelines; Isolation Forest pseudo-labeller uses 100 trees; a reference "
        "implementation of Algorithm 1 with binary-searched windows and union–find merging ships in "
        "experiments/correlation_eval.py.",
    ]:
        d.add_paragraph(t, style="List Bullet")

    d.save(OUT)
    print("saved ->", OUT)


if __name__ == "__main__":
    main()
