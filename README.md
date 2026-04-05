```
 __   __   ___   ____   _____   ___    ____
 \ \ / /  / _ \ |  _ \ |_   _| / _ \  / ___|
  \ V /  | | | || | | |  | |  | | | || |  _
   \_/   | |_| || |_| |  | |  | |_| || |_| |
    _     \__,_||____/   |_|   \___/  \____|
   | |  ___  _  _  ____  ___  ____
   | | / _ \| || ||_  _|/ _ \|  _ \
   | || (_) | \/ |  | | | (_) | | | |
   |_| \___/  \/   |_|  \___/|_| |_|
```

> **Vantag** — AI-powered retail loss prevention and store intelligence platform.

---

## Features

Vantag is organized across **6 phases** delivering **21 production-ready features**:

### Phase 1 — Intelligent Video Ingestion & Preprocessing
| # | Feature |
|---|---------|
| 1 | Multi-camera RTSP stream manager with auto-reconnect |
| 2 | Camera registry and health monitor |
| 3 | Zero-DCE low-light enhancement preprocessing |

### Phase 2 — AI Inference Engine
| # | Feature |
|---|---------|
| 4 | YOLOv8 object detection engine |
| 5 | TensorRT accelerated inference (Jetson / GPU) |
| 6 | Dynamic model scheduler (CPU / GPU load balancing) |

### Phase 3 — Behavioral Analyzers
| # | Feature |
|---|---------|
| 7 | Dwell-time tracker (zone loitering detection) |
| 8 | Heatmap generator (customer flow visualization) |
| 9 | Queue depth detector |
| 10 | Product sweeping / concealment detector |
| 11 | Slip & fall incident detector |
| 12 | Staff monitoring (idle / coverage) |
| 13 | Empty-shelf detector |
| 14 | Tamper / camera-obstruction detector |
| 15 | Facial recognition with encrypted embeddings |

### Phase 4 — Risk Scoring & Predictive Intelligence
| # | Feature |
|---|---------|
| 16 | Real-time weighted risk scorer (0–100) |
| 17 | LightGBM predictive theft-probability scorer |

### Phase 5 — Alerting, Integrations & Controls
| # | Feature |
|---|---------|
| 18 | MQTT door controller (one-tap lock) |
| 19 | Webhook engine (Slack, Teams, POS, custom) |
| 20 | POS transaction correlation |
| 21 | Two-way audio intercom over WebSocket |

### Phase 6 — Dashboard & Mobile App
| # | Feature |
|---|---------|
| 21 | React web dashboard + Expo React Native mobile app |

---

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/your-org/vantag.git
cd vantag
cp .env.example .env          # fill in VANTAG_FACE_KEY and VANTAG_JWT_SECRET

# 2. Launch the full stack
docker compose -f docker/docker-compose.yml up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| MQTT Broker | localhost:1883 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Vantag Platform                             │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │  React Web   │    │  Expo Mobile │    │   External Systems │    │
│  │  Dashboard   │    │     App      │    │  (POS / Webhooks)  │    │
│  └──────┬───────┘    └──────┬───────┘    └────────┬───────────┘    │
│         │                   │                     │                │
│         └──────────┬────────┘                     │                │
│                    │ HTTP / WebSocket              │ HTTP           │
│         ┌──────────▼──────────────────────────────▼────────┐      │
│         │              FastAPI Backend (port 8000)          │      │
│         │  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │      │
│         │  │ Ingestion│ │Analyzers │ │  Risk / Predict  │  │      │
│         │  │ Pipeline │→│ (15 AI   │→│    Scorers       │  │      │
│         │  │  RTSP    │ │ modules) │ │ (0-100 score)    │  │      │
│         │  └──────────┘ └──────────┘ └──────────────────┘  │      │
│         │  ┌──────────────────┐  ┌──────────────────────┐   │      │
│         │  │  MQTT Client     │  │   Webhook Engine     │   │      │
│         │  │  Door Controller │  │   POS Integration    │   │      │
│         │  └────────┬─────────┘  └──────────────────────┘   │      │
│         └───────────┼───────────────────────────────────────┘      │
│                     │ MQTT                                          │
│         ┌───────────▼──────────┐                                   │
│         │  Mosquitto Broker    │                                   │
│         │  (port 1883 / 9001)  │                                   │
│         └──────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Backend Setup

**Requirements:** Python 3.11+, pip

```bash
pip install -r requirements.txt

# Run the API server
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Frontend Setup

**Requirements:** Node.js 20+

```bash
cd frontend/web
npm install
npm run dev          # Vite dev server → http://localhost:5173
```

---

## Mobile Setup

**Requirements:** Node.js 20+, Expo CLI

```bash
cd frontend/mobile
npx expo install
npx expo start       # scan QR with Expo Go, or press i/a for simulator
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VANTAG_ENV` | `development` | Runtime environment (`development` / `staging` / `production` / `edge`) |
| `VANTAG_JWT_SECRET` | *(required in prod)* | JWT signing secret (min 32 chars) |
| `VANTAG_FACE_KEY` | *(required)* | Fernet key for face-embedding encryption |
| `MQTT_BROKER` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `VANTAG_ALLOWED_ORIGINS` | `*` | CORS allowed origins (comma-separated in prod) |
| `VANTAG_REPORT_DIR` | `snapshots/reports` | Directory for generated PDF reports |
| `VANTAG_DEBUG` | `0` | Set to `1` to enable verbose debug logging |

Generate secrets:
```bash
# Face key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# JWT secret
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Platform health check |
| `GET` | `/api/stores` | List all stores |
| `GET` | `/api/cameras` | List cameras and status |
| `POST` | `/api/cameras/{id}/snapshot` | Capture live snapshot |
| `GET` | `/api/reports` | List incident reports |
| `POST` | `/api/reports/generate` | Generate PDF incident report |
| `GET` | `/api/watchlist` | Retrieve watchlist entries |
| `POST` | `/api/watchlist` | Add face to watchlist |
| `DELETE` | `/api/watchlist/{id}` | Remove watchlist entry |
| `POST` | `/api/doors/{id}/lock` | Trigger door lock via MQTT |
| `POST` | `/api/audio/call/{camera_id}` | Initiate intercom call |
| `WS` | `/ws` | Real-time event stream (alerts, scores, heatmaps) |

Full interactive docs available at **http://localhost:8000/docs** (Swagger UI).

---

## Contributing

1. Fork the repository and create a feature branch: `git checkout -b feat/your-feature`
2. Follow existing module patterns — each analyzer lives in `backend/analyzers/`, each router in `backend/api/`
3. Add tests under `tests/backend/` mirroring the module path
4. Run `pytest tests/` before submitting
5. Open a pull request with a clear description of the change and any new environment variables

**Code style:** PEP 8, type-annotated, docstrings on all public functions.

---

*Vantag — Intelligent Retail Loss Prevention*
