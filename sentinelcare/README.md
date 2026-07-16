# SentinelCare

SentinelCare is a consent-based, camera-assisted home-safety prototype. It analyzes a live camera feed for observable signs of a fall or other concerning movement, gives the monitored person a recovery and cancellation window, and then notifies configured emergency contacts by email when a critical alert is confirmed.

> SentinelCare is not a medical device, does not diagnose medical conditions, and does not contact 911 or hospitals. Treat every alert as responder-support information and follow local emergency procedures.

## What it does

- Processes a webcam or video file with OpenCV and MediaPipe multi-person pose tracking.
- Extracts body-motion, posture, ground-proximity, visibility, and movement features.
- Evaluates events with modular agents: FallGuard, Seizure, Stroke, and Wandering.
- Uses a recovery window to reduce false positives before declaring a critical alert.
- Streams annotated video, agent state, events, and alerts to a Next.js dashboard over WebSocket.
- Lets users manage consent, emergency contacts, home location, and notification preferences through Supabase-backed UI flows (with local-browser fallback during development).
- Starts a visible 10-second cancellation countdown after a critical alert. Emergency-contact email is sent only if that countdown expires; canceling it prevents email dispatch.
- Sends an individual SMTP email to every configured emergency contact with an email address.

## Alert lifecycle

```text
Camera / video feed
  -> pose landmarks and features
  -> agent evaluates event confidence
  -> suspicious event
  -> recovery monitoring window
       -> recovered / return to normal
       -> critical alert
  -> dashboard 10-second cancellation countdown
       -> cancelled: no email
       -> expires: send email to every emergency contact
```

FallGuard currently transitions through:

```text
NORMAL -> SUSPICIOUS_EVENT -> MONITORING_RECOVERY -> RECOVERED
                                               -> CRITICAL_ALERT
```

## Emergency-email contents

When a user has enabled emergency-contact notifications and the cancellation countdown expires, SentinelCare sends a separate message to each saved contact that has an email address. Each email can contain:

- Event type, severity, and detection timestamp
- Detected issues and confidence scores
- Saved incident address and a Google Maps link
- A pinned static map image, when Google Maps Static API is configured
- Closest hospital name, address, distance, and directions, when Google Places is configured
- Responder-facing summary and recommended next steps

SMTP is configured in `backend/.env`. The visible sender is:

```text
SMTP_FROM_NAME <SMTP_FROM>
```

For example: `SentinelCare Alert System <alerts@example.com>`.

## Architecture

| Layer | Implementation |
|---|---|
| Dashboard | Next.js 16, React 19, Tailwind CSS |
| Authentication and persistence | Supabase Auth, Postgres, Row Level Security |
| Backend | Python, FastAPI, Uvicorn, WebSocket |
| Computer vision | OpenCV, MediaPipe Pose Landmarker |
| Detection | Rule-based agents with optional trained fall model and ML boost |
| Health report | Structured responder report; optional local Ollama/Qwen rewrite |
| Email | SMTP with plain-text and HTML variants |
| Location services | Browser Geolocation, Google Geocoding, Places API (New), Maps Static API |

```text
Camera/video -> OpenCV -> MediaPipe pose tracking -> feature extraction
  -> agent orchestrator -> event store -> WebSocket -> Next.js dashboard
                                         -> alert countdown -> SMTP email
```

## Project layout

```text
boom/
├── scripts/
│   ├── 001_create_security_tables.sql
│   ├── 002_add_data_retention.sql
│   └── 003_create_alert_tables.sql
└── sentinelcare/
    ├── backend/
    │   ├── app/
    │   │   ├── main.py                 # FastAPI API, WebSocket, alert pipeline
    │   │   ├── agent.py                # FallGuard state machine
    │   │   ├── seizure_agent.py        # Repetitive-motion monitoring
    │   │   ├── stroke_agent.py         # Pose asymmetry monitoring
    │   │   ├── wandering_agent.py      # Boundary/pacing monitoring
    │   │   ├── vision.py               # Video capture and pose tracking
    │   │   ├── features.py             # Pose feature extraction
    │   │   ├── orchestrator.py         # Multi-agent coordinator
    │   │   ├── health_report_agent.py  # Structured/optional LLM reports
    │   │   ├── email_sender.py          # SMTP email rendering and delivery
    │   │   └── event_store.py           # In-memory current-session event store
    │   ├── requirements.txt
    │   └── .env                         # Local secrets; never commit
    └── frontend/
        ├── src/app/                     # Dashboard, auth pages, API routes
        ├── src/components/              # Live feed, alert modal, settings UI
        ├── src/hooks/                   # WebSocket, settings, contacts, location
        ├── src/lib/supabase/             # Browser/server Supabase clients
        └── .env.local                    # Frontend server environment; never commit
```

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- A webcam or test video
- Supabase project for authentication and persistent user data
- SMTP account for real email delivery

### Backend

```bash
cd sentinelcare/backend
python -m venv .venv
# Activate .venv using your shell's normal command.
pip install -r requirements.txt

# Download the MediaPipe pose model if it is not already present.
# Save it as backend/pose_landmarker.task.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd sentinelcare/frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The frontend expects the backend at `http://localhost:8000` and WebSocket at `ws://localhost:8000/ws` unless the matching `NEXT_PUBLIC_*` environment variables are set.

### Supabase migrations

Run these in order in the Supabase SQL Editor:

1. `scripts/001_create_security_tables.sql`
2. `scripts/002_add_data_retention.sql`
3. `scripts/003_create_alert_tables.sql`

The third migration creates `emergency_contacts`, `user_location`, and `alert_history`, with Row Level Security so users can access only their own records.

## Environment configuration

### SMTP: `backend/.env`

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-gmail-address@gmail.com
SMTP_PASSWORD=your-16-character-google-app-password
SMTP_FROM=your-gmail-address@gmail.com
SMTP_FROM_NAME=SentinelCare Alert System
```

For Gmail, enable two-step verification and generate a Google App Password. Do not use the account's ordinary password. Restart the backend after changing this file.

### Optional local health report: `backend/.env`

```env
HEALTH_REPORT_LLM=1
OLLAMA_BASE_URL=http://localhost:11434
HEALTH_REPORT_MODEL=qwen2.5:7b
```

Set `HEALTH_REPORT_LLM=0` to keep the structured report only.

## Google Maps status and limitation

Google Maps Platform APIs require a billing account. This project currently does **not** have a billing account attached, so we could not use the live Google Maps APIs in the demo.

Consequences in the current configuration:

- Address geocoding is intentionally rejected when no key is configured; it does not silently substitute a fake location.
- The nearest-hospital route returns clearly marked mock hospital data when Google Places is unavailable.
- Alert emails still include the saved coordinates as a standard Google Maps link when coordinates are available, but cannot embed a Google static map image without a valid key and billing-enabled Maps Static API.

To enable real mapping later, create a billing-enabled Google Cloud project, enable **Geocoding API**, **Places API (New)**, and **Maps Static API**, then add the same key to both files below:

`sentinelcare/frontend/.env.local`

```env
GOOGLE_MAPS_API_KEY=your-key
```

`sentinelcare/backend/.env`

```env
GOOGLE_MAPS_API_KEY=your-key
```

Restart both servers after adding or changing the key. Restrict the key to those APIs and the deployment environment before production use.

## Key API endpoints

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/status` | Backend state and active configuration |
| `GET` | `/events` | Current in-memory event log |
| `GET` | `/alerts` | Current in-memory alerts |
| `GET/POST` | `/config` | Read or update monitoring configuration |
| `POST` | `/agent/toggle` | Enable or disable an agent |
| `POST` | `/agent/reset` | Reset agents to normal state |
| `POST` | `/alerts/test` | Create a test alert |
| `POST` | `/alerts/config` | Sync contacts and location for dispatch |
| `POST` | `/alerts/dispatch-email` | Send email after frontend countdown expires |
| `WS` | `/ws` | Live frames, states, events, and alerts |

The frontend also provides server-side routes:

- `POST /api/geocode` — converts a verified address to coordinates.
- `POST /api/nearby-hospitals` — finds nearby hospitals through Google Places when configured; otherwise returns flagged mock data for the demo.

## Demo scenarios

| Scenario | Expected behavior |
|---|---|
| Normal movement | Dashboard remains in normal state. |
| Fall followed by recovery | Monitoring begins, then returns to recovered/normal state without escalation. |
| Fall with no recovery | Critical alert appears, then the 10-second cancellation countdown starts. |
| Cancel during countdown | No emergency-contact email is sent. |
| Countdown expires | One SMTP email is sent to each contact with an email address. |

To use a video file instead of a camera:

```bash
curl -X POST http://localhost:8000/config \
  -H "Content-Type: application/json" \
  -d '{"video_source":"/path/to/video.mp4"}'
```

## Privacy and safety

- Monitoring requires user consent.
- Continuous video is processed locally; the application focuses on event summaries rather than recording video by default.
- Emergency contacts, location, and alert history are sensitive data. Use Supabase RLS, strong SMTP credentials, and restricted Maps keys.
- The system does not diagnose falls, seizures, strokes, or other medical conditions.
- The 911 toggle is a demo indicator only; it does not place emergency calls.

## Development checks

```bash
cd sentinelcare/frontend
npm run lint
npx tsc --noEmit

cd ../backend
python -m py_compile app/main.py app/email_sender.py
```

## Built for a hackathon

SentinelCare is a prototype for shortening time-to-awareness in potential at-home emergencies while preserving an explicit recovery/cancellation safeguard. It is not a replacement for professional monitoring or emergency services.
