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

from .agent import ResponseGuardAgent
from .event_store import event_store
from .features import FeatureExtractor
from .models import AppConfig, WSMessage, AgentStateName, PoseFeatures
from .orchestrator import AgentOrchestrator
from .seizure_agent import SeizureAgent
from .stroke_agent import StrokeAgent
from .wandering_agent import WanderingAgent
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


@app.post("/agent/toggle")
async def toggle_agent(agent_name: str, enabled: bool):
    """Toggle an agent on/off."""
    global config
    if agent_name in config.enabled_agents:
        config.enabled_agents[agent_name] = enabled
        return {
            "status": "toggled",
            "agent": agent_name,
            "enabled": enabled,
            "config": config.model_dump()
        }
    return {"status": "error", "message": f"Unknown agent: {agent_name}"}


@app.get("/config")
async def get_config():
    return config.model_dump()


@app.get("/debug/features")
async def get_debug_features():
    """Debug endpoint to see current feature values."""
    return {
        "message": "Feature values are sent in WebSocket messages",
        "tip": "Open browser console and look for 'features' in frame_update messages",
        "check": "Look for velocity, ground_proximity, torso_angle values"
    }


@app.get("/debug/thresholds")
async def get_debug_thresholds():
    """Show current detection thresholds."""
    return {
        "velocity_threshold": 0.025,
        "confidence_threshold": config.fall_confidence_threshold,
        "sustained_frames_required": 5,
        "ground_proximity_threshold": 0.5,
        "torso_angle_threshold": 35,
        "tip": "If velocity is below 0.025 during your fall, we need to lower it"
    }


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
    """Reset all agents to NORMAL state (useful after critical alert)."""
    return {"status": "all_agents_reset"}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

async def _broadcast(data: dict) -> None:
    """Send data to all connected WebSocket clients."""
    dead: list[WebSocket] = []
    msg = json.dumps(data)
    for ws in list(connected_clients):
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
    
    # Create AgentOrchestrator and register all agents
    # Use a list to hold orchestrator so we can modify it from nested function
    orchestrator_ref = [AgentOrchestrator()]
    
    def rebuild_orchestrator():
        """Rebuild orchestrator based on current config."""
        # Clear existing agents by creating new orchestrator
        orchestrator_ref[0] = AgentOrchestrator()
        
        # Register ResponseGuardAgent if enabled
        if config.enabled_agents.get("ResponseGuard", True):
            response_agent = ResponseGuardAgent(
                recovery_window=config.recovery_window,
                confidence_threshold=config.fall_confidence_threshold,
                use_ml_boost=config.use_ml_boost,
                ml_weight=config.ml_weight,
                use_trained_model=config.use_trained_model,
                trained_model_path=config.trained_model_path,
            )
            orchestrator_ref[0].register_agent("ResponseGuard", response_agent)
        
        # Register SeizureAgent if enabled
        if config.enabled_agents.get("Seizure", True):
            seizure_agent = SeizureAgent(
                recovery_window=config.seizure_config.recovery_window,
                confidence_threshold=config.seizure_config.confidence_threshold,
                recovery_threshold=config.seizure_config.recovery_threshold,
                history_window=config.seizure_config.history_window,
            )
            orchestrator_ref[0].register_agent("Seizure", seizure_agent)
        
        # Register StrokeAgent if enabled
        if config.enabled_agents.get("Stroke", True):
            stroke_agent = StrokeAgent(
                recovery_window=config.stroke_config.recovery_window,
                asymmetry_threshold=config.stroke_config.asymmetry_threshold,
                motion_threshold=config.stroke_config.motion_threshold,
                recovery_asymmetry_threshold=config.stroke_config.recovery_asymmetry_threshold,
                recovery_motion_threshold=config.stroke_config.recovery_motion_threshold,
            )
            orchestrator_ref[0].register_agent("Stroke", stroke_agent)
        
        logger.info(f"Orchestrator rebuilt with agents: {list(orchestrator_ref[0]._agents.keys())}")
    
    # Initial build
    rebuild_orchestrator()
    
    # Store rebuild function for WebSocket handler
    ws.state.rebuild_orchestrator = rebuild_orchestrator

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

            # Run orchestrator on worst-case person
            agent_states = orchestrator_ref[0].update(worst_features, any_detected)
            
            # Add unavailable/disabled agents for UI display
            from .models import AgentState, AgentStateName
            all_agent_names = ["ResponseGuard", "Seizure", "Stroke", "Wandering"]
            registered_names = set(orchestrator_ref[0]._agents.keys())
            
            for agent_name in all_agent_names:
                if agent_name not in registered_names:
                    # Agent is disabled or unavailable
                    unavailable_agent = AgentState(
                        agent_name=agent_name,
                        state=AgentStateName.NORMAL,
                        confidence=0.0,
                        summary="Agent currently disabled",
                        available=False
                    )
                    agent_states.append(unavailable_agent)
            
            # Get ResponseGuard state for backward compatibility
            responseguard_state = None
            for state in agent_states:
                if state.agent_name == "ResponseGuard":
                    responseguard_state = state
                    break

            # Encode frame
            b64_frame = frame_to_base64(annotated, quality=65)

            # Build message with multi-agent support
            msg = WSMessage(
                type="frame_update",
                frame=b64_frame,
                agent_state=responseguard_state,  # Backward compatibility
                agents=agent_states,  # NEW: all agent states
                features=worst_features,
                pose_detected=any_detected,
                num_people=num_people,
            )

            # Check for new events and include the latest one
            current_events = event_store.get_events(limit=999)
            if len(current_events) > last_event_count:
                msg.event = current_events[0]
                last_event_count = len(current_events)

            # If any agent has critical alert, include alert
            critical_alert_detected = any(state.state == AgentStateName.CRITICAL_ALERT for state in agent_states)
            if critical_alert_detected:
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
                    # Reset all agents via orchestrator
                    orchestrator_ref[0].reset_all()
                    logger.info("All agents reset requested via WebSocket")
                elif msg.get("type") == "toggle_agent":
                    # Toggle agent on/off
                    agent_name = msg.get("agent")
                    enabled = msg.get("enabled", True)
                    logger.info(f"Received toggle request: {agent_name} -> {enabled}")
                    logger.info(f"Current enabled_agents: {config.enabled_agents}")
                    
                    if agent_name in config.enabled_agents:
                        config.enabled_agents[agent_name] = enabled
                        logger.info(f"Updated enabled_agents: {config.enabled_agents}")
                        
                        # Rebuild orchestrator with new config
                        if hasattr(ws.state, 'rebuild_orchestrator'):
                            ws.state.rebuild_orchestrator()
                            logger.info("Orchestrator rebuilt successfully")
                        else:
                            logger.warning("rebuild_orchestrator not found in ws.state")
                        
                        # Send confirmation
                        await ws.send_json({
                            "type": "agent_toggled",
                            "agent": agent_name,
                            "enabled": enabled
                        })
                    else:
                        logger.warning(f"Agent {agent_name} not found in enabled_agents")
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
