"""Pydantic models for SentinelCare backend."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


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
    """Extended feature set for 5-feature fall detection.

    New fields (5 core features + derived metrics):
        body_axis_angle        — degrees from vertical (0=upright, 90=horizontal)
        center_of_gravity_height — avg Y of shoulders/hips/knees (0=top, 1=bottom)
        aspect_ratio           — bounding-box height / width
        sudden_motion_change   — sum of landmark displacements vs previous frame
        stillness_duration     — consecutive seconds below stillness threshold
        posture_score          — composite 0–1, velocity-independent
        cumulative_delta_angle — angle change over sliding window
        cumulative_delta_cog   — CoG change over sliding window
        cumulative_delta_aspect — aspect ratio change over sliding window

    Legacy fields kept for frontend backward compatibility.
    """

    # --- 5 core features ---
    body_axis_angle: float = 0.0
    center_of_gravity_height: float = 0.0
    aspect_ratio: float = 1.5
    sudden_motion_change: float = 0.0
    stillness_duration: float = 0.0

    # --- Derived metrics ---
    posture_score: float = 0.0
    cumulative_delta_angle: float = 0.0
    cumulative_delta_cog: float = 0.0
    cumulative_delta_aspect: float = 0.0

    # --- Legacy fields (backward compat with frontend) ---
    body_centroid_y: float = 0.0
    torso_angle: float = 0.0
    head_height: float = 0.0
    hip_height: float = 0.0
    velocity: float = 0.0
    motion_energy: float = 0.0
    stillness_score: float = 0.0
    ground_proximity: float = 0.0


# ---------------------------------------------------------------------------
# Agent state payload
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    state: AgentStateName = AgentStateName.NORMAL
    confidence: float = 0.0
    event_type: str = "none"
    timer_active: bool = False
    timer_remaining: float = 0.0
    timer_total: float = 10.0
    last_change: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str = "System operating normally."


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

class AppConfig(BaseModel):
    video_source: str = "0"  # "0" for webcam, or path to video file
    recovery_window: float = 10.0  # seconds
    location_label: str = "Living Room"
    fall_confidence_threshold: float = 0.55
    show_pose_overlay: bool = True
    frame_skip: int = 0  # process every Nth frame (0 = every frame)

    # --- New: 5-feature detection config ---
    sliding_window_size: int = 20       # frames of history
    stillness_threshold: float = 0.005  # motion below this = still
    ema_alpha: float = 0.3              # EMA smoothing factor

    @field_validator("fall_confidence_threshold")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        if not 0.1 <= v <= 0.95:
            raise ValueError(f"fall_confidence_threshold must be between 0.1 and 0.95, got {v}")
        return v

    @field_validator("recovery_window")
    @classmethod
    def _validate_recovery(cls, v: float) -> float:
        if not 3.0 <= v <= 60.0:
            raise ValueError(f"recovery_window must be between 3.0 and 60.0, got {v}")
        return v

    @field_validator("sliding_window_size")
    @classmethod
    def _validate_window(cls, v: int) -> int:
        if not 5 <= v <= 60:
            raise ValueError(f"sliding_window_size must be between 5 and 60, got {v}")
        return v

    @field_validator("stillness_threshold")
    @classmethod
    def _validate_stillness(cls, v: float) -> float:
        if not 0.001 <= v <= 0.05:
            raise ValueError(f"stillness_threshold must be between 0.001 and 0.05, got {v}")
        return v

    @field_validator("ema_alpha")
    @classmethod
    def _validate_ema(cls, v: float) -> float:
        if not 0.05 <= v <= 0.5:
            raise ValueError(f"ema_alpha must be between 0.05 and 0.5, got {v}")
        return v


# ---------------------------------------------------------------------------
# WebSocket message
# ---------------------------------------------------------------------------

class WSMessage(BaseModel):
    type: str  # "frame_update", "agent_update", "event", "alert"
    frame: Optional[str] = None  # base64 JPEG
    agent_state: Optional[AgentState] = None
    features: Optional[PoseFeatures] = None
    event: Optional[Event] = None
    alert: Optional[Alert] = None
    pose_detected: bool = False
    num_people: int = 0

