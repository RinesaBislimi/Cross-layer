"""Generate the point-by-point response to the editor and reviewers (.docx).

Reads the same JSON result files as revise_manuscript.py, so every number quoted
here is the one that appears in the revised manuscript.

Usage (from backend/):  python experiments/write_response.py
Output: C:/Users/Admin/Downloads/Response_to_Reviewers_CrossLayer.docx
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import revise_manuscript as R  # noqa: E402

OUT = Path(r"C:\Users\Admin\Downloads\Response_to_Reviewers_CrossLayer.docx")

M, C, T, S2, B, T2, A = R.M, R.C, R.T, R.S2, R.B, R.T2, R.A
CM, WS, ABL, SC = R.CM, R.WS, R.ABL, R.SEEDS_C
S2L, S2R = R.S2L, R.S2R
mm, ms, MODEL_NAME = R.mm, R.ms, R.MODEL_NAME
lay = {r["dataset"]: r for r in B["layers"]}
corr = B["correlation"]
best_w = R.best_w
tt, tr = T["temporal"], T["random"]
s_net, s_sys, s_app = R.summ("CICIDS2017"), R.summ("BGL"), R.summ("TDA")
BLACK = RGBColor(0, 0, 0)


def main():
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    st.font.color.rgb = BLACK
    for name in ("Heading 1", "Heading 2", "Title"):
        try:
            d.styles[name].font.color.rgb = BLACK
        except KeyError:
            pass

    def para(text, bold_prefix=None, italic=False):
        p = d.add_paragraph()
        if bold_prefix:
            r = p.add_run(bold_prefix)
            r.bold = True
            r.font.color.rgb = BLACK
        r = p.add_run(text)
        r.italic = italic
        r.font.color.rgb = BLACK
        return p

    def comment(txt):
        para(txt, "Reviewer's comment. ", italic=True)

    def reply(txt):
        para(txt, "Our response. ")

    h = d.add_heading("Response to the Editor and the Reviewers", 0)
    for r in h.runs:
        r.font.color.rgb = BLACK
    para('Manuscript: "A Cross-Layer Log Monitoring and Analysis System Using Machine Learning", '
         "Journal on Information Security (Springer), submission 230ca5f3-0951-47a3-898e-7c64c243c4a9.")

    para("Dear Editor, dear Reviewers,")
    para("Thank you for the time you spent on our manuscript and for the detail of the comments. They pointed "
         "at real weaknesses, and working through them has changed the paper in substance rather than in "
         "wording. The most important changes are these. The cross-layer correlation step, which the first "
         "version only described, is now measured: on a benchmark with planted ground truth we report how many "
         "alerts go in, how many incidents come out, how many of the planted multi-stage incidents are "
         "recovered, how many false correlations appear, and how all of this moves with the window. We then "
         "repeated the exercise on the AIT Alert Data Set, where network, system and application alerts really "
         "do come from the same hosts. We added a learned second-stage classifier so that machine learning "
         "operates across layers and not only inside them, and we evaluated it. All six algorithms are now "
         "reported on all three datasets with means and standard deviations over five seeds, together with "
         "training and inference times. For CICIDS2017 we went back to the original timestamped flow files and "
         "ran temporal, host-disjoint and session-disjoint splits; the outcome is sobering and we say so. "
         "Every feature, every preprocessing step, the scaling, the handling of imbalance and the "
         "hyperparameters are documented. We added system-level measurements, a privacy section, a comparison "
         "with SIEM platforms and HERCULE, and a refreshed bibliography in which every entry carries a DOI or a "
         "stable link. The TDA dataset is now identified and linked. The two figures that shared one caption "
         "have been separated. Finally, the whole evaluation is scripted: every table and figure in the paper "
         "can be regenerated from the raw CSV files with the scripts in the public repository.")
    para("Two things deserve to be said up front. First, while re-running everything under a stricter "
         "protocol we found that the service code had been assigning placeholder random labels to the "
         "unlabelled TDA data instead of the Isolation Forest labels the paper described. We fixed the code, "
         "regenerated the TDA results and state this openly in the paper. Second, several headline numbers "
         "changed, mostly because the first version used a single run on a non-random prefix of each file; "
         "the new values are given below and the paper names the old ones next to them. Section, table and "
         "figure numbers in this letter refer to the revised manuscript.")

    # ------------------------------------------------------------------ #
    d.add_heading("Editor", 1)
    comment("The reviewers have identified significant shortcomings in the manuscript ... please ensure the "
            "results are accurately reported, any overstated conclusions are rewritten and the limitations of "
            "the work fully explained.")
    reply("We have tried to do exactly that. Results were regenerated from deterministic scripts and are "
          "reported with variance. Where the first version made a claim it could not support - a perfect "
          "F1-score, scalability without measurements, 'cross-layer machine learning' without a learned "
          "cross-layer component - we either produced the evidence or rewrote the claim. The limitations are "
          "collected in Sections 7.3 to 7.5 and repeated in the Conclusions, including the ones we discovered "
          "ourselves during the revision.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 1", 1)
    comment("The central cross-layer contribution should be evaluated quantitatively: number of alerts before "
            "and after correlation, correctly reconstructed multi-stage incidents, false correlations, "
            "incident-level precision and recall.")
    reply(f"This was the gap we were most concerned about, and Section 6.3 now reports precisely these "
          f"quantities. We built a benchmark with 200 planted three-stage incidents and 12,000 distractor alerts "
          f"drawn from the same pool of identifiers, so that false correlations are actually possible. At the "
          f"default window of 60 s the engine turns {CM['alerts_before']:,} alerts into {CM['incidents_after']} "
          f"incidents ({100*CM['reduction_ratio']:.1f}% fewer items to look at), recovers {CM['tp']} of the 200 "
          f"planted incidents, misses {CM['fn']} and produces {CM['fp']} false correlations, which gives an "
          f"incident-level precision of {CM['incident_precision']:.3f} and recall of {CM['incident_recall']:.3f}. "
          f"Over five benchmark seeds the precision is {SC['incident_precision']['mean']:.3f} ± "
          f"{SC['incident_precision']['std']:.3f} and the recall {SC['incident_recall']['mean']:.3f} ± "
          f"{SC['incident_recall']['std']:.3f}. Table 10 and Fig. 4 sweep the window from 5 s to 600 s, and we "
          f"ablate the layer-ordering constraint, which on this benchmark halves the number of false "
          f"correlations ({ABL['without_order']['fp']} to {ABL['with_order']['fp']}). Section 6.5 then repeats the "
          "evaluation on real, jointly captured alerts (see our reply to Reviewer 4 below).")

    comment("The cross-layer use of the three independent datasets requires much clearer explanation: how can "
            "timestamps, addresses or hosts correspond across CICIDS2017, BGL and TDA? Were the incidents "
            "synthetically constructed, temporally aligned, or otherwise mapped?")
    reply("You are right that the first version left this implicit, and we should have been explicit. The three "
          "datasets were recorded in different places and years, and nothing in one of them corresponds to "
          "anything in another. The paper now says so plainly in Sections 6.3.1 and 7.5. The per-layer detectors "
          "are still trained and tested on the real data, but the incidents used to evaluate the correlation "
          "engine are constructed and temporally aligned in a controlled benchmark whose construction is "
          "described step by step in Section 6.3.1. Because this is only a benchmark, we added Section 6.5, "
          "where the engine runs on the AIT Alert Data Set and the layers are genuinely linked. Section 4.4 "
          "also explains how heterogeneous identifiers are canonicalised and matched in a real deployment.")

    comment("The TDA application-layer results should be interpreted more cautiously, since the reported MLP "
            "performance mainly reflects agreement with the pseudo-labelling procedure.")
    reply("We agree without reservation and have given this its own section. Section 7.3 states that the TDA "
          "scores measure how well a supervised model reproduces the Isolation Forest labelling, that they must "
          "not be compared with the other two layers, that the supervised Isolation Forest row in Table 7 is the "
          "natural reference, and that any blind spot of the pseudo-labeller is inherited by every model trained "
          "on it. The same caveat appears in the abstract, in Section 4.2, in Table 2 and in the Conclusions. As "
          "mentioned above, we also found and corrected a discrepancy between the code and the paper: the "
          "ingestion code had been assigning random placeholder labels to TDA. The code now does what the paper "
          "describes, and all TDA numbers were regenerated with Isolation Forest labels (contamination 0.05, "
          "100 trees).")

    comment("The influence of experimental randomness on the reported deep-learning results should be examined "
            "more carefully; the authors may cite empirical studies on randomness and data partitioning, "
            "including five studies on fault detection in air-handling units.")
    reply("Every per-layer metric is now a mean and standard deviation over five seeds that control both the "
          "data partition and the initialisation of the learner (Table 7); the five-fold cross-validation score "
          "on the training partition is reported alongside as an independent estimate; and the correlation "
          "benchmark is repeated over five seeds as well. Section 7.4 discusses where the variance comes from "
          "and where it is largest, namely the MLP, the SVM and the pseudo-labelled layer. Regarding the "
          "suggested references: we were able to locate and now cite three of the five - the Scientific Reports "
          "paper on coverage-aligned combined training across buildings [40], the Building and Environment "
          "study on cross-building transferability [41], and the Energy and Buildings paper on the class-aware "
          "temporal and contextual contrastive framework [46] - together with the general variance studies of "
          "Pham et al. [38] and Bouthillier et al. [39] and the reproducibility study of Le and Zhang [16]. For "
          "the remaining two titles (the tabular-methods study on a large office building and the sequence-"
          "aware augmentation comparison, as well as the coverage-aware multi-head TabNet paper) we could not "
          "find a venue or DOI in any index available to us; we would be glad to add them if you can point us "
          "to the records.")

    comment("The claims of scalability and real-time applicability should be supported by empirical "
            "system-level measurements: throughput, latency, memory, events per second.")
    reply(f"Section 6.4 and Table 12 now contain them, measured on one workstation. Batch scoring runs at "
          f"{lay['CICIDS2017']['batch_events_per_s']:,.0f} flows/s for the network layer, "
          f"{lay['BGL']['batch_events_per_s']:,.0f} lines/s for the system layer and "
          f"{lay['TDA']['batch_events_per_s']:,.0f} records/s for the application layer; we also report single-"
          f"event latency (mean and 99th percentile) and explain that it is dominated by library call overhead. "
          f"The correlation engine handles {corr['scaling'][-1]['n_events']:,} alerts in "
          f"{corr['scaling'][-1]['seconds']:.2f} s, and its measured scaling exponent is "
          f"{corr['empirical_exponent']:.2f}, i.e. close to linear, which matches the analysis in Section 4.4. Peak "
          f"memory was {B['host']['peak_python_mem_mb']:.0f} MB. The abstract and the conclusions now claim "
          "only what these numbers support and say what they exclude, namely network and storage I/O.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 2", 1)
    comment("The number of references is low, many are old and many lack a DOI or URL; the state of the art "
            "in Sections 1 to 3 should be reworked.")
    reply("The list has grown from 29 to 48 entries and every one of them now carries a DOI or a stable link. "
          "Among the additions are HERCULE, DBD-Guardian, the SIEM and big-data security-analytics literature "
          "(Marchal et al., Rassam et al., Sun et al., González-Granadillo et al.), the AIT log and alert "
          "datasets, the GDPR, two variance studies, three recent studies on fault detection in air-handling "
          "units, a 2023 survey on deep learning for log data, LogGPT, a survey on multi-step attack detection, "
          "a survey on provenance-based intrusion detection and the source paper of the TDA dataset. Sections 1 "
          "to 3 were rewritten around this material; Section 2 gained a subsection on SIEM and big-data "
          "analytics and a positioning subsection, and Table 1 now includes HERCULE, Marchal et al. and "
          "DBD-Guardian with a column that records whether the correlation step was evaluated. The older "
          "references that remain are the foundational ones (Random Forest, XGBoost, Isolation Forest, the "
          "dataset papers and Chandola's survey).")

    comment("The novel element, cross-layer correlation into multi-stage incidents, is supported mainly by "
            "description rather than by a controlled quantitative experiment.")
    reply("Please see our reply to Reviewer 1's first point: Section 6.3 is that experiment, Section 6.5 "
          "repeats it on real linked alerts, and Sections 4.5 and 6.3.3 add and evaluate the learned second "
          "stage.")

    comment("Complete all missing Table 3 metrics; report all six models, not just the winners, preferably as "
            "mean ± SD.")
    reply("The old Table 3, together with its internal note about missing values, is gone. Table 7 reports all "
          "eighteen model-dataset pairs with precision, recall, F1, ROC-AUC (each as mean ± SD over five seeds), "
          "the cross-validation F1, training time and inference throughput, and Fig. 3 shows the F1-scores "
          "side by side.")

    comment("Add a temporal or session-aware evaluation for CICIDS2017.")
    if T2:
        c_, g_, w_, r_, s_ = T2["cross_day"], T2["by_source_ip"], T2["within_day"], T2["random"], T2["by_session"]
        reply(f"We did this on the original per-day flow files, which carry timestamps and addresses, and the "
              f"result is the most instructive one of the revision (Section 6.2, Table 8). A chronological split "
              f"inside each day leaves LightGBM at F1 = {w_['lgbm']['f1']:.3f}, essentially the random-split value "
              f"of {r_['lgbm']['f1']:.3f}. A strict cross-day split, training on Monday to Wednesday and testing on "
              f"Thursday and Friday, drops LightGBM to {c_['lgbm']['f1']:.3f} and Random Forest to {c_['rf']['f1']:.3f}, "
              f"because the test days contain attack families that never occur in training. Holding out whole "
              f"source hosts with a stratified group split gives F1 = {g_['lgbm']['f1']:.3f} ± {g_['lgbm']['f1_std']:.3f} "
              f"(LightGBM) and {g_['rf']['f1']:.3f} ± {g_['rf']['f1_std']:.3f} (Random Forest), and holding out whole "
              f"(source, destination) sessions gives {s_['lgbm']['f1']:.3f} ± {s_['lgbm']['f1_std']:.3f} and "
              f"{s_['rf']['f1']:.3f} ± {s_['rf']['f1_std']:.3f}. In other words, the near-perfect random-split score "
              "holds only when the attacking hosts and the attack families were seen during training. The paper "
              "says this directly in Sections 6.2, 7.1 and 7.5, acknowledges that the first version overstated "
              "the generality of the network layer, and argues that this is in fact a reason for correlating "
              "across layers rather than against it.")
    else:
        reply(f"Section 6.2 and Table 8 add an order-preserving split (LightGBM F1 = {tt['f1']:.3f} against "
              f"{tr['f1']:.3f} for the random split); we are explicit that it is a block split on the consolidated CSV.")

    comment("Clarify exactly how the 70/15/15 split and five-fold cross-validation interact.")
    reply("Section 4.3 now spells it out. For each seed the data are split 70/15/15 with stratification. "
          "Five-fold cross-validation runs on the 70% training partition only and serves as an internal "
          "variance estimate and for model selection; the 15% validation partition is used for early stopping "
          "of the MLP; every headline number is measured once on the untouched 15% test partition. The whole "
          "procedure is repeated for five seeds and averaged.")

    comment("Complete the TDA URL and preferably release the cross-layer implementation.")
    reply("The TDA dataset is the Binary Access Traffic Matrices dataset released by Gutflaish et al. with "
          "their AAAI-19 paper on temporal anomaly detection, now cited as [48]; the link "
          "(https://www.kaggle.com/datasets/eyalgut/binary-traffic-matrices) is given in Section 4.1 and in the "
          "Availability statement. The implementation, including the experiments package that regenerates "
          "every table and figure, is public at https://github.com/RinesaBislimi/Cross-layer and is referenced "
          "in the same statement and in Section 5.3.")

    comment("Precision = recall = F1 = ROC-AUC = 1.000 can indicate overfitting.")
    reply(f"It deserved the suspicion. Under the new protocol - a stratified random sample over the whole file, "
          f"five seeds and scaling fitted on training data only - LightGBM reaches {R.F1_NET:.4f} ± "
          f"{mm('CICIDS2017', R.b_net, 'f1')['std']:.4f} on CICIDS2017: high, but not perfect, and with a measurable "
          "variance. Section 7.1 explains where the earlier 1.000 came from (one run on a non-random prefix of "
          "the file), why the number is not an artefact of class imbalance, why the benchmark is so separable, "
          "and, with the temporal and session-aware splits, what the number does and does not mean.")

    comment("TDA has no verified ground truth; Isolation Forest labels; the MLP reaches F1 = 0.848 against "
            "generated labels.")
    reply("Please see our reply to Reviewer 1's third point. Section 7.3 is devoted to this, and the TDA "
          "numbers are now presented as agreement with pseudo-labels, with the supervised Isolation Forest as "
          "the reference row.")

    comment("How can an event in CICIDS2017 genuinely correspond to an event in BGL or TDA? This is the "
            "fundamental dataset/correlation problem of the paper.")
    reply("It cannot, and the revised paper says so (Sections 6.3.1 and 7.5). That is why the correlation "
          "engine is evaluated on a controlled benchmark and, in Section 6.5, on the AIT Alert Data Set, in "
          "which the layers are captured together on the same hosts. A full end-to-end run of our own "
          "detectors on the raw AIT-LDS v2 logs is the first item of future work, and the experiments package "
          "contains a ready-to-run harness for it.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 3", 1)
    comment("It is not clear what rationale is used for correlating the events.")
    reply("Section 4.4 now opens with the rationale - the stages of one campaign are carried out by the same "
          "actor against the same target within a bounded time, so their traces share an identifier and lie "
          "close in time - and then defines the three criteria (window, canonical identifier, layer order), "
          "explains how identifiers are matched, why correlation is transitive and how duplicates are merged, "
          "and walks through a worked example with six concrete alerts.")

    comment("Does the work deal with privacy-related concerns? Would it fit regulations such as the GDPR?")
    reply("Section 4.6 is new. Identifiers are pseudonymised at ingestion with a keyed hash (HMAC-SHA-256), so "
          "the value used for matching does not reveal the address or account; identifiers are never used as "
          "model features; per-event rows are kept for a bounded time while incidents are stored in aggregate; "
          "and the API is authenticated and role-based. We relate these measures to Articles 5, 25 and 32 of "
          "the GDPR and to its Recital 49, and we note that a deployment still needs its own impact assessment. "
          "The pseudonymisation is implemented in the released code, and the dashboard shows only pseudonyms "
          "(Section 5.4).")

    comment("There is no evidence for the claim of a scalable, practical basis for real-world, high-volume "
            "environments.")
    reply("Please see our reply to Reviewer 1's fifth point: Section 6.4 provides the measurements and the "
          "claim has been reworded to match them.")

    comment("The background and related work must be improved; how does the proposal compare to SIEMs? "
            "Consider Frade et al., Marchal et al., Rassam et al. and Sun et al.")
    reply("All four are cited and discussed in the new Section 2.4, which compares the proposal with SIEM "
          "platforms along three lines - learned per-event alerts instead of signatures, one inspectable and "
          "empirically characterised correlation rule instead of a rule library, and a learned incident score - "
          "and also says what a SIEM offers that our prototype does not. Table 1 includes Marchal et al. and "
          "DBD-Guardian.")

    comment("The methodology is typical; the contribution of the authors is not clear.")
    reply("Section 1.2 restates the four contributions so that each one is tied to evidence in the paper: the "
          "unified pipeline; the correlation engine with its learned second stage, now evaluated; the complete "
          "comparison of six models with variance, timing and temporal splits; and the system-level evidence, "
          "the privacy design and the reproducible scripts. We do not claim novelty for the ingestion, feature "
          "or training stages as such.")

    comment("Identify the features, the rationale for each, and the preprocessing applied.")
    reply("Tables 3, 4 and 5 list all 52 CICIDS2017, 10 BGL and 6 TDA predictors with their meaning and the "
          "reason for including them; Section 4.2 names the 26 CICFlowMeter columns that were excluded and "
          "why; Section 4.1 documents the cleaning (infinite values, missing values, duplicates, with counts) "
          "and the sampling; and Section 4.3 documents the z-scoring, which is fitted on the training partition "
          "only.")

    comment("Are the data balanced? Is there any bias that led to the perfect F1-score?")
    reply(f"Table 2 gives the class proportions ({100*s_net['positive_rate']:.1f}% attack flows in CICIDS2017, "
          f"{100*s_sys['positive_rate']:.1f}% anomalous lines in BGL, 5% by construction in TDA). Section 7.1 "
          "discusses the near-perfect score: it is not an imbalance artefact, since precision and recall are "
          "both above 0.99; it reflects how separable several attack classes are in this benchmark; it is no "
          "longer exactly 1.000; and, as the temporal and session-aware splits of Section 6.2 show, it depends "
          "on the attacking hosts and attack families being present in training.")

    comment("How does the inter-layer correlation affect the results? Have different solutions been tried at "
            "each layer? Has an ablation study been conducted?")
    reply(f"Detection and correlation are evaluated separately on purpose. Table 7 reports six alternative "
          f"detectors for each layer rather than one, and Section 6.3 evaluates the correlation stage on its own, "
          f"with an ablation of the layer-ordering constraint and a comparison between the fixed rule and the "
          f"learned second-stage classifiers (incident F1 from {S2R['f1']['mean']:.3f} to {S2L['f1']['mean']:.3f} on "
          "the benchmark). Section 6.5 repeats the ordering ablation on real alerts, where the constraint turns "
          "out to be counter-productive because detectors fire in interleaved order; we report that as well.")

    comment("Reproducibility would be improved if the proposal were openly available.")
    reply("It is now public at https://github.com/RinesaBislimi/Cross-layer, and Section 5.3 lists the scripts "
          "that regenerate every table and figure from the raw CSV files without the database or the API.")

    comment("The frontend module for real-time monitoring is not described in sufficient detail.")
    reply("Section 5.4 describes the eleven modules of the dashboard (Dashboard, Logs, Incidents with the "
          "analyst's confirm/dismiss actions that feed the second-stage model, Attack chains, Entities, Heatmap, "
          "Analysis, Alert rules, Response rules, Statistics and Reports), the REST and WebSocket plumbing "
          "behind them, and the fact that only pseudonymised identifiers are displayed.")

    # ------------------------------------------------------------------ #
    d.add_heading("Reviewer 4", 1)
    comment("The source code of the cross-layer platform is not publicly available.")
    reply("It is now: https://github.com/RinesaBislimi/Cross-layer, referenced in the Availability statement "
          "and in Section 5.3, including the experiments package.")

    comment("The work does not deliver what the title promises: the ML is not cross-layer and the cross-layer "
            "part is not ML. Either tone down the title and claims or introduce a learned component operating "
            "across layers, as HERCULE does.")
    reply(f"We took the second route and tempered the claims as well. The system already contained a second-"
          f"stage model trained on aggregate cross-layer features, but the first version neither described nor "
          f"evaluated it, so your reading of the paper was the correct one. Section 4.5 now defines that stage "
          f"formally - eight features per candidate incident: per-layer counts, number of layers, time span, "
          f"maximum and mean detector score, and an ordering flag - and Section 6.3.3 with Table 11 evaluates "
          f"it on the benchmark, where it raises incident F1 from {S2R['f1']['mean']:.3f} (fixed rule) to "
          f"{S2L['f1']['mean']:.3f} ± {S2L['f1']['std']:.3f} (LightGBM). Fig. 2 shows it in the architecture. "
          "Section 7.2 states that learning happens per layer and then on incident features, i.e. late fusion, "
          "that early fusion and graph models such as HERCULE are the alternative, and that we do not claim to "
          "outperform HERCULE. We kept the title because machine learning is now applied both within and "
          "across layers, and the abstract and Section 1 describe the two levels precisely. In fairness we must "
          "add that, on the real alerts of Section 6.5, the same eight generic features do not transfer "
          "between testbeds; the paper reports this as a negative result.")

    comment("A list of the predictors for each layer is missing; the features removed from CICIDS2017, the ten "
            "BGL features and the six TDA features are not given; a table per dataset with features, number of "
            "samples and class proportions is needed.")
    reply("Tables 2 to 5 now provide exactly this; please see also our reply to Reviewer 3 on feature "
          "engineering.")

    comment("The normalisation method is not specified, nor whether the scaler was fitted on the training set "
            "only; the cleaning of CICIDS2017, the parser and classification unit for BGL, and the handling of "
            "class imbalance are not described.")
    reply("Section 4.3 now states that features are z-scored inside a scikit-learn pipeline, so the scaler is "
          "fitted on the training partition only and refitted inside every cross-validation fold; the service "
          "code was changed to match. Section 4.1 documents the CICIDS2017 cleaning with counts, explains that "
          "BGL needs no template parser because the alert flag in the first field is the label and the unit is "
          "one log line with lexical features from the raw message, and describes how imbalance is handled "
          "(stratification, metric choice, contamination set to the positive rate for Isolation Forest, no "
          "resampling).")

    comment("The work is not compared with any multi-source correlation approach, e.g. HERCULE.")
    reply("HERCULE is discussed in Section 2.3, included in Table 1 and contrasted in Section 7.2. A direct "
          "empirical comparison needs jointly captured logs with ground-truth attack traces for its weight "
          "learning; Section 6.5 is our first step in that direction, and the full comparison belongs to the "
          "AIT-LDS future work.")

    comment("Six algorithms are compared yet Table 3 reports a single model per dataset; hyperparameters are "
            "not reported; the internal note about 'n.r.' values should be removed.")
    reply("Table 7 reports every algorithm on every dataset with precision, recall, F1 and ROC-AUC as mean ± "
          "SD, the cross-validation F1 and the training and inference times; Table 6 lists all hyperparameters; "
          "the note has been removed.")

    comment("The datasets do not originate from a single real system; the evaluation should be repeated on "
            "datasets whose layers are genuinely linked, such as the AIT Log Data Set V2.")
    if A and A.get("scenarios"):
        ag = A["aggregate"]["W=60"]; ago = A["aggregate"].get("W=60,order"); n_scen = len(A["scenarios"]); ms_ = A.get("second_stage_loso_mean", {})
        reply(f"We agree that this was the most important missing piece, and Section 6.5 with Table 13 is our "
              f"answer. Downloading and parsing the raw AIT-LDS v2 logs (7 to 26 GB per scenario) was not feasible "
              f"within the revision period, but the AIT Alert Data Set, which the same group derived from those "
              f"logs by running Suricata, Wazuh and AMiner on all {n_scen} testbeds, is exactly the input of our "
              f"correlation engine: per-layer alerts with timestamps and identifiers, captured on the same hosts, "
              f"with attack-phase ground truth. Averaged over the {n_scen} scenarios the engine reduces the number "
              f"of items to triage by {100*ag['reduction_ratio']['mean']:.1f}%, absorbs "
              f"{100*ag['attack_alert_recall']['mean']:.0f}% of the attack alerts into incidents, and reconstructs the "
              f"attack as an incident spanning at least two layers in {ag['scenarios_with_multilayer_attack_incident']} "
              f"of {n_scen} scenarios; incident precision, however, is only {ag['incident_precision']['mean']:.3f} ± "
              f"{ag['incident_precision']['std']:.3f}, because the benign noise that Wazuh and AMiner emit forms "
              "hundreds of small multi-layer chains - the realistic false-positive load that our controlled "
              "benchmark only approximates. Two further findings are reported as they are: the layer-ordering "
              f"constraint is counter-productive on these streams (attack-alert recall "
              f"{ago['attack_alert_recall']['mean']:.3f} with it versus {ag['attack_alert_recall']['mean']:.3f} without), "
              "because host-based and network detectors fire in interleaved order; and a second-stage classifier "
              f"trained leave-one-scenario-out on the eight generic features is precise ({ms_['lgbm']['precision']:.3f}) "
              f"but recovers only {100*ms_['lgbm']['recall']:.1f}% of attack candidates (F1 {ms_['lgbm']['f1']:.3f}), so it "
              "does not transfer across testbeds without features that carry semantic content. The end-to-end "
              "run of our own per-layer detectors on the raw logs remains future work; the experiments package "
              "ships a ready-to-run harness for it (experiments/ait_lds_eval.py), and Sections 6.3.1, 7.5 and 8 "
              "keep the limitation explicit.")
    else:
        reply("We agree this is the most important remaining limitation and state it in Sections 6.3.1, 7.5 "
              "and 8; the experiments package contains a ready-to-run AIT-LDS v2 harness, and this evaluation is "
              "the first priority of future work.")

    comment("Section 4.2 states that four aggregate cross-layer features are computed, but does not say what "
            "they are or which models use them; either remove them or define them and use them in a second-"
            "stage model.")
    reply("Done: Section 4.2 now says that these features are not inputs to the per-layer detectors, and "
          "Section 4.5 defines the aggregate cross-layer features formally and uses them in the learned "
          "second-stage classifier of Section 6.3.3.")

    comment("The correlation engine is described only by pseudocode: how are heterogeneous identifiers "
            "matched, is correlation transitive, how does deduplication work, why W = 60 s; the layer-ordering "
            "constraint is missing from Algorithm 1; a step-by-step example and a sensitivity analysis on W are "
            "requested.")
    reply(f"Section 4.4 now covers identifier canonicalisation and exact matching, transitivity through union-"
          f"find merging, deduplication, and the choice of W. Algorithm 1 has been rewritten - with the hash-map "
          f"lookup, the order filter on line 4 and the union-find merge on line 7 - and is set in a box, followed "
          f"by a worked example with six concrete alerts. Table 10 and Fig. 4 sweep W from 5 s to 600 s; "
          f"incident F1 peaks at W = {best_w['window_s']} s on the benchmark, and we explain why 60 s is kept as a "
          "recall-favouring default. Section 6.4 also measures the engine's scaling empirically.")

    comment("The code is available only on reasonable request.")
    reply("Please see the Availability statement and Section 5.3: the repository is public.")

    comment("The TDA URL is missing, and Figure 1 is used to illustrate two different things.")
    reply("The TDA dataset is identified and linked (Binary Access Traffic Matrices, Gutflaish et al. [48], "
          "https://www.kaggle.com/datasets/eyalgut/binary-traffic-matrices). The figures are now separate: Fig. 1 "
          "is a new illustration of a multi-stage attack across the three layers, and Fig. 2 is the "
          "architecture, which now also shows the second-stage classifier.")

    # ------------------------------------------------------------------ #
    d.add_heading("Other changes", 1)
    for t in [
        "The abstract and Section 1.2 were rewritten around the two levels of learning, the quantitative "
        "correlation results, the variance reporting and the pseudo-label caveat.",
        "Section 3 gained a paragraph on experimental randomness with references.",
        "Section 5.2 records that scaling is implemented as a train-only pipeline; Section 5.3 lists the "
        "reproducibility scripts.",
        f"Headline values that changed under the new protocol: CICIDS2017 LightGBM F1 1.000 → "
        f"{R.F1_NET:.3f} ± {mm('CICIDS2017', R.b_net, 'f1')['std']:.3f}; BGL Random Forest F1 0.910 → "
        f"{mm('BGL','rf','f1')['mean']:.3f} ± {mm('BGL','rf','f1')['std']:.3f} (stratified random sample over the whole "
        f"file instead of a non-random prefix); TDA MLP F1 0.848 → {mm('TDA','mlp','f1')['mean']:.3f} ± "
        f"{mm('TDA','mlp','f1')['std']:.3f} (Isolation Forest pseudo-labels regenerated). The paper names the old "
        "values next to the new ones (Sections 6.1 and 7.1).",
        "The abbreviation list was extended (CV, GDPR, HMAC, SD, SIEM, TP/FP/FN); references and citations are "
        "clickable; Algorithm 1 is boxed.",
        "Code changes: TDA ingestion no longer assigns placeholder random labels; the StandardScaler lives inside "
        "the SVM and MLP pipelines; the Isolation Forest pseudo-labeller uses 100 trees; identifiers can be "
        "pseudonymised with HMAC-SHA-256; the layer-ordering constraint of Algorithm 1 is implemented and "
        "exposed on the incidents endpoint; a reference implementation of Algorithm 1 with binary-searched "
        "windows and union-find merging ships in experiments/correlation_eval.py.",
    ]:
        p = d.add_paragraph(style="List Bullet")
        r = p.add_run(t)
        r.font.color.rgb = BLACK

    para("We hope the revised manuscript now answers the concerns raised, and we thank the reviewers again for "
         "a review that made the paper considerably more honest and more useful.")
    para("With kind regards,")
    para("Rinesa Bislimi and Avni Rexhepi")

    d.save(OUT)
    print("saved ->", OUT)


if __name__ == "__main__":
    main()
