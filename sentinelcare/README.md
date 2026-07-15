# SentinelCare

**Multi-agent AI monitoring for critical at-home emergencies.**

Real-time fall detection and emergency monitoring for vulnerable people living alone. SentinelCare uses live camera feeds, pose tracking, and specialized AI agents to detect dangerous observable states, monitor recovery windows, and escalate when help is needed.

![SentinelCare Dashboard](https://img.shields.io/badge/Status-Prototype-blue) ![Python](https://img.shields.io/badge/Python-3.10-green) ![Next.js](https://img.shields.io/badge/Next.js-16-black) ![MediaPipe](https://img.shields.io/badge/MediaPipe-PoseLandmarker-orange)

---

## 🎯 What It Does

SentinelCare monitors a live camera feed and runs a **FallGuard Agent** that:

1. **Detects** likely collapse/fall events using multi-signal pose analysis
2. **Monitors** a recovery window (10s) to avoid false alarms
3. **Escalates** with a structured alert if no recovery occurs
4. **Tracks** multiple people simultaneously with per-person skeleton overlay

### Agent State Machine

```
NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → RECOVERED
                                                 → CRITICAL_ALERT
```

---

## 🖥️ Dashboard

The real-time dashboard shows:

- **Live Feed** — Camera stream with multi-person pose skeleton overlay
- **Status Badge** — Color-coded system state (Normal / Monitoring / Alert)
- **FallGuard Agent Card** — Confidence score, state, last change
- **Recovery Timer** — Circular countdown during monitoring phase
- **Alert Panel** — Structured event details with recommended action
- **Event Timeline** — Scrollable log of all detected events
- **Future Agents** — Modular cards for seizure, stroke, injury, and wandering detection

---

## 🏗️ Architecture

```
Camera/Video → OpenCV Capture → MediaPipe PoseLandmarker (multi-person)
    → Feature Extraction → FallGuard Agent → State Machine
    → Alert Generator → WebSocket → Next.js Dashboard
```

| Layer | Tech |
|-------|------|
| Backend | Python, FastAPI, WebSocket |
| Vision | OpenCV, MediaPipe PoseLandmarker |
| Agent | Rule-based multi-signal state machine |
| Frontend | Next.js 16, Tailwind CSS, WebSocket |
| Storage | In-memory event log |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+ (conda recommended)
- Node.js 18+
- Webcam (or a video file for testing)

### 1. Clone & Setup Backend

```bash
git clone https://github.com/YOUR_USERNAME/sentinelcare.git
cd sentinelcare

# Create conda environment
conda create -n sentinelcare python=3.10 -y
conda activate sentinelcare

# Install Python dependencies
pip install -r backend/requirements.txt

# Download MediaPipe pose model (30MB)
wget -O backend/pose_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task
```

### 2. Setup Frontend

```bash
cd frontend
npm install
cd ..
```

### 3. Run

**Terminal 1 — Backend:**
```bash
conda activate sentinelcare
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open **http://localhost:3000** in your browser.

### Emergency email and Maps setup

Create `backend/.env` before starting the API:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=your-provider-app-password
SMTP_FROM=alerts@example.com
SMTP_FROM_NAME=SentinelCare Alert System
GOOGLE_MAPS_API_KEY=your-google-maps-platform-key
```

Enable the **Places API (New)** and **Maps Static API** for that Google Maps key.
When a critical alert is raised, the backend sends one email to every saved emergency-contact email address. The message includes the detected issues and confidence scores, timestamp, incident address and Google Maps link, a pin map image, and the closest hospital returned by Google Places. Run `scripts/003_create_alert_tables.sql` after the existing security migrations to persist contacts, locations, and alert history in Supabase.

---

## 🧪 Demo Scenarios

| Scenario | What to Do | Expected Result |
|----------|-----------|-----------------|
| **Normal** | Stand, walk, sit normally | Status stays "Normal", 0% confidence |
| **Fall + Recovery** | Drop to floor, then stand back up within 10s | Monitoring → Recovered |
| **Fall + No Recovery** | Drop to floor and stay down | Monitoring → Timer expires → Critical Alert |

### Using a Video File

Update the video source via the API:
```bash
curl -X POST http://localhost:8000/config \
  -H "Content-Type: application/json" \
  -d '{"video_source": "/path/to/video.mp4"}'
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/status` | System status + config |
| `GET` | `/events` | Event log |
| `GET` | `/alerts` | Alert history |
| `GET` | `/config` | Current configuration |
| `POST` | `/config` | Update configuration |
| `POST` | `/alerts/test` | Trigger a test alert |
| `WS` | `/ws` | Real-time frame + agent streaming |

---

## 🔒 Privacy

- **Opt-in only** — designed for users who consent to safety monitoring
- **Edge-first** — all processing runs locally, no cloud dependency
- **Event-focused** — only event summaries are retained, not continuous video
- **No diagnosis** — detects dangerous observable states, not medical conditions

---

## 🔮 Future Agents

The modular architecture supports additional specialized agents:

- **Seizure Agent** — Abnormal repetitive motion patterns
- **Stroke Risk Agent** — Asymmetry and sudden immobility
- **Injury Angle Agent** — Unnatural joint angle detection
- **Wandering Agent** — Prolonged immobility or pacing

The pipeline stays the same — only the agent logic changes.

---

## 📁 Project Structure

```
sentinelcare/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app + WebSocket streaming
│   │   ├── vision.py         # OpenCV + MediaPipe PoseLandmarker
│   │   ├── features.py       # Pose feature extraction
│   │   ├── agent.py          # FallGuard state machine
│   │   ├── models.py         # Pydantic data models
│   │   └── event_store.py    # In-memory event log
│   ├── requirements.txt
│   └── environment.yml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx      # Dashboard layout
│   │   │   ├── layout.tsx    # App shell
│   │   │   └── globals.css   # Dark theme + animations
│   │   ├── components/
│   │   │   ├── LiveFeed.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   ├── AgentCard.tsx
│   │   │   ├── RecoveryTimer.tsx
│   │   │   ├── AlertPanel.tsx
│   │   │   ├── EventLog.tsx
│   │   │   └── FutureAgents.tsx
│   │   └── hooks/
│   │       └── useWebSocket.ts
│   └── package.json
└── .gitignore
```

---

## 🏆 Built for Hackathon

> "SentinelCare shortens time-to-awareness during emergencies at home. We are not claiming diagnosis. We are detecting dangerous observable states and escalating when recovery does not happen."
