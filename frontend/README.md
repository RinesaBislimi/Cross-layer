# Cross-Layer Log Analysis – Frontend

Angular frontend for **real-time monitoring** of the Cross-Layer Log Analysis system.

## Features

- **Dashboard**: API/WebSocket status, recent logs, recent cross-layer incidents, live WebSocket messages
- **Logs**: Filter by layer (system / network / application / security) and source (BGL, CICIDS2017, TDA)
- **Incidents**: List of correlated cross-layer incidents with severity and timestamps
- **WebSocket**: Connects to `ws://127.0.0.1:8000/ws/alerts` for real-time updates (indicator in nav)

## Prerequisites

- Node.js 18+
- Backend running at `http://127.0.0.1:8000` (see `backend/README.md`)

## Setup and run

```bash
cd frontend
npm install
npm start
```

Open **http://localhost:4200**. The app will call the backend API and connect to the WebSocket for live alerts.

## Configuration

- API and WebSocket URLs are in `src/environments/environment.ts`.
- For production, create `environment.prod.ts` and set `apiUrl` / `wsUrl` to your deployed backend.
