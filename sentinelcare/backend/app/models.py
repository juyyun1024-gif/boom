"""Pydantic models for SentinelCare backend."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent states
# ---------------------------------------------------------------------------

class AgentStateName(str, Enum):
    NORMAL = "normal"
    SUSPICIOUS_EVENT = "suspicious_event"
    MONITORING_RECOVERY = "monitoring_recovery"
    RECOVERED = "recovered"
    CRITICAL_ALERT = "critical_alert"


# ---------------------------------------------------------------------------
# Pose / feature data sent to frontend
# ---------------------------------------------------------------------------

class LandmarkPoint(BaseModel):
    x: float
    y: float
    z: float
    visibility: float


class PoseData(BaseModel):
    landmarks: list[LandmarkPoint] = Field(default_factory=list)
    detected: bool = False


class PoseFeatures(BaseModel):
    body_centroid_y: float = 0.0
    torso_angle: float = 0.0
    head_height: float = 0.0
    hip_height: float = 0.0
    velocity: float = 0.0
    motion_energy: float = 0.0
    stillness_score: float = 0.0
    ground_proximity: float = 0.0
    
    # New features for Phase 3 agents
    repetition_score: float = 0.0  # For SeizureAgent
    asymmetry_score: float = 0.0   # For StrokeAgent
    body_centroid_x: float = 0.0   # For WanderingAgent
    is_horizontal: bool = False    # For ResponseGuard: True when body is horizontal
    pose_quality: float = 0.0      # Reliability of full-body pose for fall detection
    pose_reliable: bool = False
    visibility_reason: str = "no_pose"
    visible_keypoints: int = 0


# ---------------------------------------------------------------------------
# Agent state payload
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    model_config = {"protected_namespaces": ()}

    agent_name: str = "Unknown"  # NEW: identifies which agent produced this state
    state: AgentStateName = AgentStateName.NORMAL
    confidence: float = 0.0
    event_type: str = "none"
    timer_active: bool = False
    timer_remaining: float = 0.0
    timer_total: float = 10.0
    last_change: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str = "System operating normally."
    available: bool = True  # NEW: indicates if agent is currently active
    ai_enabled: bool = False
    model_source: str = "rules"
    model_status: str = "not_configured"
    model_confidence: float = 0.0
    rule_confidence: float = 0.0
    pose_quality: float = 0.0
    pose_reliable: bool = False
    visibility_reason: str = "unknown"


# ---------------------------------------------------------------------------
# Events & alerts
# ---------------------------------------------------------------------------

class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent: str = "FallGuard"
    event_type: str = "unknown"
    status: str = "unknown"
    confidence: float = 0.0
    location: str = "Living Room"
    recovery_window_seconds: float = 10.0
    elapsed_seconds: float = 0.0
    summary: str = ""
    recommended_action: str = ""
    video_source: str = "camera_0"


class Alert(BaseModel):
    alert_id: str = Field(default_factory=lambda: f"alrt_{uuid.uuid4().hex[:8]}")
    event: Event
    triggered_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged: bool = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class SeizureConfig(BaseModel):
    """Configuration for SeizureAgent."""
    recovery_window: float = 10.0
    confidence_threshold: float = 0.65
    recovery_threshold: float = 0.30
    history_window: int = 60


class StrokeConfig(BaseModel):
    """Configuration for StrokeAgent."""
    recovery_window: float = 15.0
    asymmetry_threshold: float = 0.15
    motion_threshold: float = 0.01
    recovery_asymmetry_threshold: float = 0.10
    recovery_motion_threshold: float = 0.02


class WanderingConfig(BaseModel):
    """Configuration for WanderingAgent."""
    recovery_window: float = 20.0
    boundary_zone: Optional[dict] = None  # {"x_min": 0.1, "x_max": 0.9, "y_min": 0.1, "y_max": 0.9}
    exit_threshold: float = 5.0
    pacing_threshold: int = 20  # Increased from 8 to reduce false positives
    pacing_window: float = 30.0


class AppConfig(BaseModel):
    video_source: str = "0"  # "0" for webcam, or path to video file
    recovery_window: float = 10.0  # seconds
    location_label: str = "Living Room"
    fall_confidence_threshold: float = 0.35  # Lowered from 0.55 for better sensitivity
    show_pose_overlay: bool = True
    frame_skip: int = 0  # process every Nth frame (0 = every frame)
    
    # ML enhancement
    use_ml_boost: bool = False  # DISABLED: ML boost was reducing confidence below threshold
    ml_weight: float = 0.3  # Weight given to ML predictions (0-1)
    
    # AI-backed FallGuard model
    use_trained_model: bool = True
    trained_model_path: str = "app/models/fall_detector.pkl"
    
    # Agent enable/disable flags
    enabled_agents: dict[str, bool] = {
        "FallGuard": True,
        "Seizure": True,
        "Stroke": True,
        "Wandering": False,
    }
    
    # Per-agent configuration blocks
    seizure_config: SeizureConfig = Field(default_factory=SeizureConfig)
    stroke_config: StrokeConfig = Field(default_factory=StrokeConfig)
    wandering_config: WanderingConfig = Field(default_factory=WanderingConfig)


# ---------------------------------------------------------------------------
# WebSocket message
# ---------------------------------------------------------------------------

class WSMessage(BaseModel):
    type: str  # "frame_update", "agent_update", "event", "alert"
    frame: Optional[str] = None  # base64 JPEG
    agent_state: Optional[AgentState] = None  # Backward compatibility: single agent state
    agents: list[AgentState] = Field(default_factory=list)  # NEW: multi-agent support
    features: Optional[PoseFeatures] = None
    event: Optional[Event] = None
    alert: Optional[Alert] = None
    pose_detected: bool = False
    num_people: int = 0
