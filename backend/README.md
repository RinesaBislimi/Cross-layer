# Backend - Cross-Layer Log Analysis

## Lidhja me MySQL

Për të lidhur projektin me një bazë të dhënash **MySQL** (në vend të SQLite ose PostgreSQL), ndiq këto hapa.

### 1. Instalo MySQL

- Instalo MySQL Server në kompjuterin tënd (ose përdor një instancë në cloud).
- Mban mend **emrin e përdoruesit**, **fjalëkalimin** dhe **portin** (zakonisht 3306).

### 2. Krijo bazën e të dhënave në MySQL

Hap MySQL (Command Line, MySQL Workbench ose phpMyAdmin) dhe ekzekuto:

```sql
CREATE DATABASE crosslayer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Ose përdor një emër tjetër për databazën (p.sh. `cross_layer`). Përdor atë emër në hapin 4.

### 3. Instalo varësitë e backend-it (përfshirë driver-in për MySQL)

Nga dosja `backend`:

```bash
cd backend
pip install -r requirements.txt
```

`requirements.txt` përmban `PyMySQL` dhe `cryptography` për lidhjen me MySQL.

### 4. Vendos variablin e mjedisit `DATABASE_URL`

Në dosjen `backend`, krijo ose ndrysho skedarin **`.env`** dhe vendos:

```env
DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/DATABASE
```

Zëvendëso:

- **USER** – përdoruesi MySQL (p.sh. `root` ose një user që ke krijuar)
- **PASSWORD** – fjalëkalimi i atij përdoruesi
- **HOST** – adresa e serverit (`localhost` nëse MySQL është lokale)
- **3306** – porta (lëre 3306 nëse nuk e ke ndryshuar)
- **DATABASE** – emri i bazës (p.sh. `crosslayer`)

Shembull:

```env
DATABASE_URL=mysql+pymysql://root:mysecret@localhost:3306/crosslayer
```

**Shënim:** Nëse fjalëkalimi përmban karaktere të veçanta (p.sh. `@`, `#`, `:`), enkodoje në URL (URL-encode) ose vendose në thonjëza në `.env`.

### 5. Nise backend-in

```bash
cd backend
uvicorn app.main:app --reload
```

Në startup, FastAPI/SQLAlchemy do të krijojë automatikisht tabelat (`log_events`, `incidents`) në MySQL nëse nuk ekzistojnë (për shkak të `Base.metadata.create_all(bind=engine)` në `main.py`).

### 6. Testo lidhjen

- Hap `http://127.0.0.1:8000/health` → duhet të kthejë `{"status": "ok"}`.
- Nëse merr gabim lidhjeje, kontrollo:
  - MySQL serveri është në punë.
  - `USER` / `PASSWORD` / `HOST` / `DATABASE` në `.env` janë të sakta.
  - Porta 3306 është e hapur (firewall).

Pas kësaj, mund të bësh ingestion dhe trajnim si zakonisht (ingest → train); të dhënat do të ruhen në MySQL.

---

## Puna me dataset-et (BGL, CICIDS, TDA)

### 1. BGL – nga `.log` në `.csv`

- Vendos skedarin origjinal `BGL.log` në:
  - `backend/data/bgl/BGL.log`
- Konvertoje në CSV të normalizuar (krijon `bgl.csv`):

```bash
cd backend
python scripts/bgl_log_to_csv.py \
  --input data/bgl/BGL.log \
  --output data/bgl/bgl.csv
```

Skedari `bgl.csv` do të ketë kolonat:

- `timestamp` – vlera e parë në rreshtin e log-ut
- `node_id` – vlera e dytë (p.sh. host / node)
- `log_message` – pjesa tjetër e rreshtit
- `label` – bosh për momentin (mund të plotësohet më vonë)

Backend-i pret path-in default:

- `app/config.py` → `BGL_PATH = "data/bgl/bgl.csv"`

### 2. CICIDS2017 – network / security logs

- Shkarko dataset-in e pastruar nga Kaggle dhe ruaje si:
  - `backend/data/cicids/cicids.csv`
- Ose ndrysho `CICIDS_PATH` në `app/config.py` për t’iu përshtatur emrit të skedarit tënd.

### 3. TDA Binary Traffic Matrices – application layer

- Shkarko dataset-in nga Kaggle dhe ruaje si:
  - `backend/data/tda/tda.csv`
- Ose ndrysho `TDA_PATH` në `app/config.py` sipas emrit të skedarit tënd.

### 4. Ingestion i dataset-eve në PostgreSQL

Pasi skedarët janë në vend:

1. Nise backend-in:

```bash
cd backend
uvicorn app.main:app --reload
```

2. Hape `http://127.0.0.1:8000/docs` (Swagger UI) dhe thirr këto endpoint-e në këtë rend:

- `POST /admin/ingest/bgl`   – lexon `data/bgl/bgl.csv` dhe i fut në `log_events`
- `POST /admin/ingest/cicids` – lexon `data/cicids/cicids.csv`
- `POST /admin/ingest/tda`   – lexon `data/tda/tda.csv`

### 5. Trajnimi i modeleve ML për secilin dataset

Pasi të kesh bërë ingestion:

- `POST /admin/train/bgl`
- `POST /admin/train/cicids`
- `POST /admin/train/tda`

Çdo endpoint:

- ndërton tiparet bazë (`feature_engineering.py`)
- trajnon një `RandomForest`
- ruan modelin në dosjen `models/` (shiko `BGL_MODEL_PATH`, `CICIDS_MODEL_PATH`, `TDA_MODEL_PATH` në `config.py`)
- kthen në JSON metrikat: `precision`, `recall`, `f1`, `false_positive_rate`, `tp`, `tn`, `fp`, `fn` dhe një raport tekstual.

### 6. Shikimi i log-eve dhe incidenteve cross-layer

- `GET /logs` – shfaq log-et e ruajtura (`layer`, `source`, `timestamp`, etj.)
  - mund të filtrosh me query params: `?layer=system`, `?source=BGL`, etj.
- `GET /incidents` – shfaq incidentet e korreluara nga `correlation.py`
- `POST /correlate/{entity}` – krijon një incident cross-layer për një entitet (p.sh. IP ose node_id) në një dritare kohe (default 10 minuta).

---

## Përshkrim

Ky është backend-i në Python për sistemin **Cross-Layer Log Analysis** me:

- **FastAPI** për API dhe WebSockets
- **PostgreSQL** (opsionalisht me **pgvector**) për ruajtjen e log-eve, tipareve dhe incidenteve
- **Pandas / NumPy / Scikit-Learn / XGBoost** për përpunimin e të dhënave dhe modele ML

Struktura kryesore:

- `app/main.py` – aplikacioni FastAPI, konfigurimi CORS, health-check, routes bazë
- `app/config.py` – konfigurimi (DATABASE_URL, paths e dataset-eve)
- `app/db.py` – lidhja me PostgreSQL (SQLAlchemy)
- `app/models/` – modelet ORM (`LogEvent`, `Incident`, etj.)
- `app/schemas/` – Pydantic schemas për request/response
- `app/services/` – ingestion i dataset-eve, feature engineering, modele ML, correlation engine
- `app/ws/` – WebSocket endpoints për monitorim në kohë reale

## Si të nisësh backend-in

1. Krijo dhe aktivizo virtualenv:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
```

2. Instalo varësitë:

```bash
pip install -r requirements.txt
```

3. Vendos variablat e mjedisit në `.env` (opsionale, por e rekomanduar):

```bash
DATABASE_URL=postgresql://user:password@localhost:5432/crosslayer
```

4. Nise serverin FastAPI:

```bash
uvicorn app.main:app --reload
```

Backend-i do të jetë tek `http://127.0.0.1:8000`.

## Hapat e radhës

- Shto dataset-et në dosjen `backend/data/` (p.sh. `data/bgl/...`, `data/cicids/...`, `data/tda/...`)
- Përdor endpoint-et administrative për ingestion të të dhënave
- Trajno modelet ML dhe testoje correlation engine

