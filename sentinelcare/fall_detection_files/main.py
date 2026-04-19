"""SentinelCare Backend — FastAPI application with WebSocket streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .agent import FallGuardAgent
from .event_store import event_store
from .features import FeatureExtractor
from .models import AppConfig, WSMessage, AgentStateName, PoseFeatures
from .vision import PoseTracker, VideoCapture, frame_to_base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinelcare")

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

config = AppConfig()
connected_clients: Set[WebSocket] = set()
_running = False


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SentinelCare backend starting up")
    yield
    logger.info("SentinelCare backend shutting down")
    global _running
    _running = False


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SentinelCare API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.get("/status")
async def get_status():
    return {
        "status": "running" if _running else "idle",
        "connected_clients": len(connected_clients),
        "config": config.model_dump(),
    }


@app.get("/events")
async def get_events(limit: int = 50):
    return {"events": [e.model_dump() for e in event_store.get_events(limit)]}


@app.get("/alerts")
async def get_alerts(limit: int = 20):
    return {"alerts": [a.model_dump() for a in event_store.get_alerts(limit)]}


@app.post("/config")
async def update_config(new_config: AppConfig):
    global config
    config = new_config
    return {"status": "updated", "config": config.model_dump()}


@app.get("/config")
async def get_config():
    return config.model_dump()


@app.post("/alerts/test")
async def test_alert():
    """Generate a test critical alert."""
    from .models import Event, Alert

    evt = Event(
        event_type="test_alert",
        status="critical_alert",
        confidence=0.95,
        summary="This is a test alert to verify the alert pipeline.",
        recommended_action="No action required — test only.",
    )
    event_store.add_event(evt)
    alert = Alert(event=evt)
    event_store.add_alert(alert)

    # Broadcast to connected clients
    msg = WSMessage(
        type="alert",
        agent_state=None,
        event=evt,
        alert=alert,
        pose_detected=False,
    )
    await _broadcast(msg.model_dump())

    return {"status": "test_alert_sent", "alert": alert.model_dump()}


@app.post("/stream/start")
async def start_stream():
    """Signal intent to start — actual streaming happens via WebSocket."""
    return {"status": "connect_to_ws", "ws_url": "/ws"}


@app.post("/stream/stop")
async def stop_stream():
    global _running
    _running = False
    return {"status": "stopping"}


@app.post("/agent/reset")
async def reset_agent():
    """Reset the agent to NORMAL state (useful after critical alert)."""
    return {"status": "reset_requested"}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

async def _broadcast(data: dict) -> None:
    """Send data to all connected WebSocket clients."""
    dead: list[WebSocket] = []
    msg = json.dumps(data)
    for ws in connected_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.discard(ws)


async def _vision_loop(ws: WebSocket) -> None:
    """Main processing loop: capture → pose → features → agent → send."""
    global _running

    capture = VideoCapture(config.video_source)
    if not capture.open():
        await ws.send_json({"type": "error", "message": f"Cannot open video source: {config.video_source}"})
        logger.error(f"Cannot open video source: {config.video_source}")
        return

    tracker = PoseTracker()
    # Per-person feature extractors (keyed by person index)
    extractors: dict[int, FeatureExtractor] = {}
    agent = FallGuardAgent(
        recovery_window=config.recovery_window,
        confidence_threshold=config.fall_confidence_threshold,
    )

    _running = True
    frame_count = 0
    last_event_count = len(event_store.get_events(limit=999))
    target_interval = 1.0 / 24  # ~24 FPS target for streaming

    logger.info(f"Vision loop started — source: {config.video_source}")

    try:
        while _running:
            loop_start = time.time()

            ret, frame = capture.read()
            if not ret or frame is None:
                await asyncio.sleep(0.1)
                continue

            frame_count += 1

            # Skip frames if configured
            if config.frame_skip > 0 and frame_count % (config.frame_skip + 1) != 0:
                await asyncio.sleep(0.001)
                continue

            # Process — returns list of PoseData (one per detected person)
            annotated, all_poses = tracker.process_frame(frame, draw_overlay=config.show_pose_overlay)

            num_people = len(all_poses)
            any_detected = num_people > 0

            # Extract features for each person, find worst-case for agent
            worst_features = PoseFeatures()
            worst_confidence = 0.0

            for idx, pose in enumerate(all_poses):
                if idx not in extractors:
                    extractors[idx] = FeatureExtractor()
                feats = extractors[idx].extract(pose)

                # Compute a quick fall signal to pick the worst-case person
                fall_signal = feats.velocity + feats.ground_proximity * 0.5
                if fall_signal > worst_confidence or idx == 0:
                    worst_confidence = fall_signal
                    worst_features = feats

            # Clean up extractors for people no longer detected
            for idx in list(extractors.keys()):
                if idx >= num_people:
                    del extractors[idx]

            # Run agent on worst-case person
            agent_state = agent.update(worst_features, any_detected)

            # Encode frame
            b64_frame = frame_to_base64(annotated, quality=65)

            # Build message
            msg = WSMessage(
                type="frame_update",
                frame=b64_frame,
                agent_state=agent_state,
                features=worst_features,
                pose_detected=any_detected,
                num_people=num_people,
            )

            # Check for new events and include the latest one
            current_events = event_store.get_events(limit=999)
            if len(current_events) > last_event_count:
                msg.event = current_events[0]
                last_event_count = len(current_events)

            # If critical alert just triggered, include alert
            if agent_state.state == AgentStateName.CRITICAL_ALERT:
                latest = event_store.get_latest_alert()
                if latest:
                    msg.alert = latest
                    msg.type = "critical_alert"

            await _broadcast(msg.model_dump())

            # Pace the loop
            elapsed = time.time() - loop_start
            sleep_time = max(0.001, target_interval - elapsed)
            await asyncio.sleep(sleep_time)

    except Exception as e:
        logger.exception(f"Vision loop error: {e}")
    finally:
        _running = False
        tracker.close()
        capture.release()
        logger.info("Vision loop stopped")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global config, _running

    await ws.accept()
    connected_clients.add(ws)
    logger.info(f"Client connected ({len(connected_clients)} total)")

    # Start vision loop if not running
    vision_task = None
    if not _running:
        vision_task = asyncio.create_task(_vision_loop(ws))

    try:
        while True:
            # Listen for client messages (config updates, reset, etc.)
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=0.5)
                msg = json.loads(data)

                if msg.get("type") == "reset_agent":
                    logger.info("Agent reset requested via WebSocket")
                elif msg.get("type") == "update_config":
                    config = AppConfig(**msg.get("config", {}))
                    logger.info(f"Config updated: {config}")

            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(ws)
        logger.info(f"Client disconnected ({len(connected_clients)} remaining)")
        if vision_task and len(connected_clients) == 0:
            _running = False
