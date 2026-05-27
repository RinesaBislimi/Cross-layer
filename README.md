# Cross-Layer Log Analysis Platform

> **Master Thesis Project**
> This platform was developed as part of a Master's thesis research on multi-source anomaly detection and cross-layer security analysis. It demonstrates how combining system, network, and application logs under a unified ML pipeline can surface threats that single-layer analysis would miss.

---

## Overview

**Cross-Layer** is a full-stack security analysis platform that ingests logs from three infrastructure layers, runs machine learning anomaly detection across all of them, correlates findings into incidents, and presents everything in a real-time dashboard.

```
System layer   (BGL supercomputer logs)       ─┐
Network layer  (CICIDS-2017 traffic flows)     ─┼─▶  ML Detection  ─▶  Incident Correlation  ─▶  Dashboard
Application layer (TDA database access logs)  ─┘
```

### Core capabilities

| Feature | Description |
|---|---|
| **Multi-layer ingestion** | Parses and normalises BGL, CICIDS-2017 and TDA CSV datasets into a unified schema |
| **ML anomaly detection** | Six algorithm choices: Random Forest, XGBoost, LightGBM, SVM, Neural Network, Isolation Forest |
| **Incident correlation** | Cross-layer incidents generated from ML predictions and entity correlation |
| **Real-time dashboard** | Live WebSocket feed, threat score ring, layer health cards, severity breakdown |
| **Live simulation** | Replay ingested data through the detection pipeline at a configurable rate |
| **Alert rules** | Configurable threshold-based rules that trigger notifications via email (SMTP) |
| **Response rules** | Automated response actions linked to alert conditions |
| **AI assistant** | Ask questions about your data — supports Anthropic, Gemini, Groq, Ollama, OpenAI |
| **Reports & Analytics** | Heatmaps, entity views, attack chains, statistics, exportable reports |
| **JWT authentication** | Role-based access (admin / analyst), bcrypt-hashed passwords |

---

## Tech Stack

**Backend**
- Python 3.9+, FastAPI, Uvicorn
- SQLAlchemy 2.x — MySQL (production) or SQLite (development)
- scikit-learn, XGBoost, LightGBM — ML training and inference
- WebSockets (real-time broadcast via `asyncio`)
- passlib + python-jose — authentication
- pandas / numpy — feature engineering

**Frontend**
- Angular 17 (standalone components)
- Chart.js — metrics charts (ROC, PR, feature importance, threshold analysis)
- RxJS — reactive data streams and WebSocket integration

**Database**
- MySQL 8+ (recommended for production, 50M+ row datasets)
- SQLite (zero-config for development/demo)

---

## Project Structure

```
Cross-Layer/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, startup, summary endpoint
│   │   ├── config.py                # Settings (DATABASE_URL, model paths, SMTP, JWT)
│   │   ├── db.py                    # SQLAlchemy engine & session
│   │   ├── models/                  # ORM models (LogEvent, Incident, User, AlertRule…)
│   │   ├── routers/                 # API route handlers
│   │   │   ├── admin.py             # Ingest, train, generate incidents, fix labels
│   │   │   ├── simulate.py          # Live dataset replay simulator
│   │   │   ├── auth.py              # Register, login, JWT tokens
│   │   │   ├── analytics.py         # Statistics and analytics queries
│   │   │   ├── alert_rules.py       # Alert rule CRUD
│   │   │   ├── response_rules.py    # Response rule CRUD
│   │   │   ├── ingest.py            # Live single-event ingestion
│   │   │   └── feedback.py          # Incident feedback
│   │   ├── services/
│   │   │   ├── ingestion.py         # BGL / CICIDS / TDA CSV parsers
│   │   │   ├── training.py          # Model training pipeline
│   │   │   ├── ml_models.py         # Model load/predict helpers
│   │   │   ├── ml_incidents.py      # ML-driven incident generation
│   │   │   ├── correlation.py       # Cross-layer entity correlation
│   │   │   ├── feature_engineering.py
│   │   │   ├── alert_service.py     # Alert evaluation & SMTP delivery
│   │   │   ├── response_service.py  # Automated response execution
│   │   │   ├── llm_service.py       # AI assistant (multi-provider)
│   │   │   └── auth_service.py      # Password hashing, JWT creation
│   │   └── ws/
│   │       └── realtime.py          # WebSocket connection manager
│   ├── data/
│   │   ├── bgl/bgl.csv              # BGL supercomputer log dataset
│   │   ├── cicids/cicids.csv        # CICIDS-2017 network dataset
│   │   └── tda/tda.csv              # TDA application/DB access dataset
│   ├── models/                      # Trained .pkl model files (generated at runtime)
│   ├── requirements.txt
│   └── .env                         # Environment variables (DATABASE_URL, API keys…)
│
└── frontend/
    └── src/app/
        ├── core/services/           # ApiService, WebSocketService
        ├── shared/models/           # LogEvent, Incident interfaces
        └── features/
            ├── dashboard/           # Real-time overview, threat score, layer health
            ├── analysis/            # Step-by-step ML pipeline (ingest → train → generate)
            ├── incidents/           # Incident list, filters, severity breakdown
            ├── logs/                # Log feed with anomaly highlighting
            ├── statistics/          # Charts and aggregate stats
            ├── heatmap/             # Anomaly heatmap by layer/time
            ├── entities/            # Entity-level drill-down
            ├── attack-chains/       # Cross-layer attack chain visualisation
            ├── alert-rules/         # Alert rule management UI
            ├── response-rules/      # Response rule management UI
            ├── reports/             # Report generation
            └── login/               # Auth (sign in / create account)
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.9 or higher |
| Node.js | 18 or higher |
| MySQL | 8.0+ (or use SQLite for development) |
| npm | 9+ |

---

## Getting Started

### 1. Clone the repository

```bash
git clone <repository-url>
cd Cross-Layer
```

### 2. Set up the backend

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file (copy the example below and fill in your values):

```env
# Database — use MySQL for production, remove line for SQLite dev mode
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/crosslayer

# Dataset paths (relative to backend/)
BGL_PATH=data/bgl/bgl.csv
CICIDS_PATH=data/cicids/cicids.csv
TDA_PATH=data/tda/tda.csv

# AI assistant provider: local | anthropic | gemini | groq | ollama | openai
LLM_PROVIDER=local
ANTHROPIC_API_KEY=

# Email notifications (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your@email.com
SMTP_PASS=your_app_password
SMTP_FROM=your@email.com

# JWT (change the secret in production)
JWT_SECRET=change-me-in-production-use-a-long-random-string
JWT_EXPIRE_HOURS=24
```

Start the backend:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.
Interactive API docs: `http://localhost:8000/docs`

### 3. Set up the frontend

```bash
cd frontend
npm install
ng serve
```

The app will be available at `http://localhost:4200`.

### 4. Create your account

Open `http://localhost:4200` in your browser and click **Create account**.
The first registered user is automatically assigned the **admin** role.

---

## First-Run Workflow (ML Pipeline)

After starting both servers, follow these steps in the **ML Analysis** page:

```
Step 1 — Ingest datasets
  Click "Ingest BGL", "Ingest CICIDS", "Ingest TDA"
  (This loads CSV data into the database — may take several minutes for large files)

Step 2 — Fix labels  (run once after first ingest)
  Click "Fix Labels Now"
  (Assigns anomaly labels: BGL uses keyword detection, CICIDS uses traffic type,
   TDA uses a deterministic synthetic rate)

Step 3 — Train models
  Select an algorithm (Random Forest recommended for first run)
  Click "Train BGL", "Train CICIDS", "Train TDA"
  (Training metrics — F1, ROC AUC, Precision-Recall — are shown immediately)

Step 4 — Generate incidents
  Click "Generate ML incidents"
  (Creates incidents from model predictions — visible on the Incidents page)

Step 5 — Compute layer stats  (dashboard only)
  On the Dashboard, click "Compute now" in the layer breakdown banner
  (Pre-computes GROUP BY stats for the layer health cards)
```

---

## Datasets

| Layer | Dataset | Records | Description |
|---|---|---|---|
| System | **BGL** (Blue Gene/L) | ~4.7M | Supercomputer system log messages with alert flags |
| Network | **CICIDS-2017** | ~2.8M | Labelled network traffic flows (DoS, DDoS, infiltration, brute-force…) |
| Application | **TDA** | ~5M | Database and application access logs |

> Place CSV files in `backend/data/bgl/`, `backend/data/cicids/`, and `backend/data/tda/` respectively, or set custom paths in `.env`.

---

## ML Algorithms

| Algorithm | Key strength |
|---|---|
| **Random Forest** | Best all-round; built-in feature importance |
| **XGBoost** | High accuracy, fewer false positives |
| **LightGBM** | Fastest on large datasets, low memory |
| **SVM (Linear)** | Works well on high-dimensional network features |
| **Neural Network** | Learns complex non-linear patterns |
| **Isolation Forest** | Unsupervised — no labels required |

---

## Real-Time Simulation

The simulation feature replays ingested data through the detection pipeline at a configurable rate, broadcasting anomalies via WebSocket as if they were arriving live.

Located in **ML Analysis → Real-Time Simulation**:

- Choose dataset layer: BGL, CICIDS, TDA, or All
- Set rate (events/second) and maximum event count
- Watch live anomalies arrive on the Dashboard in real time
- Use **Clear Simulated Incidents** after testing to remove test data and restore real ML incidents

---

## AI Assistant

The built-in chat assistant can answer questions about your detection results. Configure the provider in `.env`:

| Provider | Setting | Requirement |
|---|---|---|
| Local (offline) | `LLM_PROVIDER=local` | No API key needed |
| Anthropic Claude | `LLM_PROVIDER=anthropic` | `ANTHROPIC_API_KEY` |
| Google Gemini | `LLM_PROVIDER=gemini` | `GEMINI_API_KEY` |
| Groq | `LLM_PROVIDER=groq` | `GROQ_API_KEY` |
| Ollama (local) | `LLM_PROVIDER=ollama` | Ollama running locally |
| OpenAI | `LLM_PROVIDER=openai` | `OPENAI_API_KEY` |

---

## API Reference

The full interactive API documentation is available at `http://localhost:8000/docs` once the backend is running.

Key endpoint groups:

| Prefix | Description |
|---|---|
| `POST /auth/login` | Authenticate and receive JWT token |
| `POST /auth/register` | Create new user account |
| `GET /logs` | Query log events with filtering |
| `GET /incidents` | Query incidents with severity/type filtering |
| `GET /summary` | Dashboard stats (counts, severity breakdown, layer health) |
| `POST /admin/ingest-*` | Ingest BGL / CICIDS / TDA datasets |
| `POST /admin/train-*` | Train ML models per layer |
| `POST /admin/incidents/generate-ml` | Generate incidents from ML predictions |
| `DELETE /admin/incidents/clear-simulated` | Remove simulated test incidents |
| `POST /admin/simulate/start` | Start live simulation |
| `GET /admin/simulate/status` | Get simulation progress |
| `WS /ws` | WebSocket endpoint for real-time events |

---

## Known Issues & Fixes

**`bcrypt` AttributeError on startup**
```bash
pip install bcrypt==4.0.1
```

**MySQL slow queries on large datasets**
Create the composite index after first ingest:
```sql
CREATE INDEX idx_log_events_layer_label ON log_events (layer, label);
```

**MySQL access denied on startup**
Update `DATABASE_URL` in `.env` with the correct password, or reset the MySQL root password and restart the backend.

---

## License

See [LICENSE](LICENSE) for details.
