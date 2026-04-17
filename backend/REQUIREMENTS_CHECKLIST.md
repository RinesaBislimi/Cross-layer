# Kontrolli i kërkesave të fazave (Backend)

Krahasim i kërkesave të punimit me implementimin aktual në backend.

---

## Faza 1 – Analiza e literaturës dhe definimi i kornizës teorike

| Kërkesa | A është në backend? | Shënim |
|--------|----------------------|--------|
| Studim i literaturës (ELFA-Log, GeneralLog, FusionLog) | ❌ Nuk është pjesë e backend-it | Bëhet në pjesën teorike të punimit (kapitulli i literaturës). |
| Studim i dataset-eve (BGL, TDA, CIC-IDS2017) | ✅ Përkrahësisht | Backend lexon dhe normalizon këto burime; studimi i detajuar i strukturës bëhet nga ti në tezë. |
| Formulimi i pyetjeve kërkimore dhe korniza teorike | ❌ Nuk është pjesë e backend-it | Pjesë e shkrimit të punimit. |

**Përfundim Faza 1:** Backend nuk “realizon” këtë fazë; ajo bëhet me literaturë dhe shkrim. Backend mbulon pjesën praktike që mbështet kornizën.

---

## Faza 2 – Grumbullimi dhe përpunimi i të dhënave

| Kërkesa | A është në backend? | Ku në backend |
|--------|----------------------|-----------------|
| Shkarkimi i tre dataset-eve (GitHub, Kaggle) | ⚠️ Manuel | Ti i shkarkon; backend pret CSV në `data/bgl`, `data/cicids`, `data/tda`. |
| Pastrim, normalizim, format i unifikuar | ✅ Po | `ingestion.py`: BGL, CICIDS, TDA → të gjitha shkruhen në `LogEvent` (layer, source, timestamp, entity, raw, label). |
| Konvertim BGL .log → CSV | ✅ Po | `scripts/bgl_log_to_csv.py`. |
| Analizë eksploruese (shpërndarje, pattern-e) | ✅ Pjesërisht | `GET /stats`: numra sipas layer, source, severity; faqja Statistics në frontend me grafikë. Nuk ka skript të veçantë EDA (p.sh. notebook). |
| Ndarje train / validation / test | ✅ Po | `ml_models.train_and_evaluate_with_split`: 70% train, 15% val, 15% test; metrika raportohen për train, val dhe test. |

**Përfundim Faza 2:** E plotë për pjesën e implementuar në backend (ndarja train/val/test është shtuar).

---

## Faza 3 – Dizajnimi dhe implementimi i backend-it

| Kërkesa | A është në backend? | Ku në backend |
|--------|----------------------|-----------------|
| **Log Ingestor** – lexim dhe normalizim nga të tri burimet | ✅ Po | `app/services/ingestion.py`: `ingest_bgl_csv`, `ingest_cicids_csv`, `ingest_tda_csv`; të dhënat ruhen në DB si `LogEvent`. |
| **Feature Extractor** – nxjerrje tiparesh (pandas, numpy) | ✅ Po | `app/services/feature_engineering.py`: `build_bgl_features`, `build_cicids_features`, `build_tda_features` (tipare nga raw/label). |
| **Correlation Engine** – grupim në dritare kohore, entitete të përbashkëta | ✅ Po | `app/services/correlation.py`: `correlate_entity_in_window` (dritare kohe + entity), `find_common_entities`; krijon `Incident`. |
| **Modele ML – Random Forest** (scikit-learn) | ✅ Po | `app/services/ml_models.py`: `RandomForestClassifier`; `training.py`: trajnim për BGL, CICIDS, TDA. |
| **Modele ML – XGBoost** | ✅ Po | `ml_models.train_xgb_classifier`; përdoret kur thirret trajnimi me `model_type=xgboost` (query param në `/admin/train/*`). |
| **Trajnim për secilën shtresë veçmas** | ✅ Po | `POST /admin/train/bgl`, `train/cicids`, `train/tda`; ruajtje modele në `models/`. |
| **Model i integruar cross-layer** | ✅ Po | `feature_engineering.build_cross_layer_features` (tipare të kombinuara për entity + dritare kohore); `training.train_cross_layer`; `POST /admin/train/cross-layer`; ruajtje në `models/cross_layer_model.pkl`. |

**Përfundim Faza 3:** Të gjitha kërkesat e implementuara në backend janë të plotësuara.

---

## Përmbledhje: çfarë është bërë dhe çfarë mungon

### ✅ Të realizuara

- Log Ingestor për BGL, CICIDS2017, TDA me format të unifikuar (`LogEvent`).
- Konvertues BGL .log → CSV.
- Feature Extractor (tipare për secilën shtresë).
- Correlation Engine (dritare kohore, entitete të përbashkëta, incidente cross-layer).
- Trajnim me **Random Forest** dhe **XGBoost** për secilën shtresë (`model_type=rf` ose `model_type=xgboost`).
- **Ndarje train / validation / test** (70% / 15% / 15%) dhe metrika mbi train, val dhe test (precision, recall, F1, FPR).
- **Model i integruar cross-layer**: tipare të kombinuara (numri i ngjarjeve për shtresë për entity + dritare kohore), trajnim me RF ose XGBoost, endpoint `POST /admin/train/cross-layer`.
- API (ingest, train, logs, incidents, stats, correlate) dhe frontend (dashboard, logs, incidents, statistics).

### Të paplotësuara (nuk varen nga backend)

- Pjesa e literaturës dhe korniza teorike (Faza 1) bëhet në tezë.
