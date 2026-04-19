"""Feature extraction — 5-core-feature fall detection from pose landmarks.

Computes per-frame:
    1. Body Axis Angle      (体軸の角度)     — shoulder→hip deviation from vertical
    2. Center of Gravity Height (重心高さ)   — avg Y of major landmarks
    3. Aspect Ratio          (アスペクト比)  — bbox height / width
    4. Sudden Motion Change  (動きの急変度)  — frame-to-frame landmark displacement
    5. Stillness Duration    (静止継続時間)  — consecutive seconds of low motion

Derived:
    - Posture Score          — single-frame, velocity-independent (0–1)
    - Cumulative Delta       — change over sliding window for angle / CoG / AR
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .models import PoseData, PoseFeatures, LandmarkPoint

# ---------------------------------------------------------------------------
# MediaPipe landmark indices
# ---------------------------------------------------------------------------
NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16

# Minimum visibility to consider a landmark valid
_MIN_VIS = 0.3


# ---------------------------------------------------------------------------
# Internal snapshot stored in the sliding window
# ---------------------------------------------------------------------------
@dataclass
class _FrameSnapshot:
    body_axis_angle: float = 0.0
    cog_height: float = 0.0
    aspect_ratio: float = 1.5
    sudden_motion_change: float = 0.0
    landmarks: list[LandmarkPoint] = field(default_factory=list)
    is_gap: bool = False  # True when no pose was detected


# ---------------------------------------------------------------------------
# Posture Score weights
# ---------------------------------------------------------------------------
W_ANGLE = 0.40
W_COG = 0.35
W_AR = 0.25


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _normalize(v: float, lo: float, hi: float) -> float:
    """Map v from [lo, hi] → [0, 1], clamped."""
    if hi <= lo:
        return 0.0
    return _clamp((v - lo) / (hi - lo))


# ---------------------------------------------------------------------------
# FeatureExtractor
# ---------------------------------------------------------------------------

class FeatureExtractor:
    """Computes the 5 core features + Posture Score + Cumulative Delta + Speed metrics.

    Parameters
    ----------
    window_size : int
        Number of frames to keep in the sliding window (default 20).
    fps : float
        Expected frame rate, used to convert frame counts to seconds.
    stillness_threshold : float
        Sudden Motion Change below this value counts as "still".
    speed_window : int
        Number of frames to average body_speed and angle_change_rate over
        (default 5, i.e. ~0.17s at 30fps). Smooths out single-frame noise
        while still capturing fast transitions.
    """

    def __init__(
        self,
        window_size: int = 20,
        fps: float = 24.0,
        stillness_threshold: float = 0.005,
        speed_window: int = 5,
    ) -> None:
        self._window_size = max(2, window_size)
        self._fps = max(1.0, fps)
        self._stillness_threshold = stillness_threshold
        self._speed_window = max(2, speed_window)

        self._window: deque[_FrameSnapshot] = deque(maxlen=self._window_size)
        self._prev_landmarks: Optional[list[LandmarkPoint]] = None
        self._still_frames: int = 0  # consecutive frames below threshold

        # History for speed computation (stores (cog_height, body_axis_angle) per frame)
        self._cog_history: deque[float] = deque(maxlen=self._speed_window)
        self._angle_history: deque[float] = deque(maxlen=self._speed_window)

    def reset(self) -> None:
        """Clear all history."""
        self._window.clear()
        self._prev_landmarks = None
        self._still_frames = 0
        self._cog_history.clear()
        self._angle_history.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pose: PoseData) -> PoseFeatures:
        """Compute all features for one frame."""
        if not pose.detected or len(pose.landmarks) < 33:
            return self._handle_no_detection()

        lms = pose.landmarks

        # --- 1. Body Axis Angle ---
        body_axis_angle = self._compute_body_axis_angle(lms)

        # --- 2. Center of Gravity Height ---
        cog_height = self._compute_cog_height(lms)

        # --- 3. Aspect Ratio ---
        aspect_ratio = self._compute_aspect_ratio(lms)

        # --- 4. Sudden Motion Change ---
        sudden_motion = self._compute_sudden_motion(lms)

        # --- 5. Stillness Duration ---
        if sudden_motion < self._stillness_threshold:
            self._still_frames += 1
        else:
            self._still_frames = 0
        stillness_duration = self._still_frames / self._fps

        # --- Posture Score (single-frame, no history needed) ---
        posture_score = self._compute_posture_score(body_axis_angle, cog_height, aspect_ratio)

        # --- Store snapshot in sliding window ---
        snap = _FrameSnapshot(
            body_axis_angle=body_axis_angle,
            cog_height=cog_height,
            aspect_ratio=aspect_ratio,
            sudden_motion_change=sudden_motion,
            landmarks=list(lms),
            is_gap=False,
        )
        self._window.append(snap)
        self._prev_landmarks = list(lms)

        # --- Cumulative Delta (current vs oldest in window) ---
        delta_angle, delta_cog, delta_ar = self._compute_cumulative_delta(snap)

        # --- Body Speed & Angle Change Rate ---
        self._cog_history.append(cog_height)
        self._angle_history.append(body_axis_angle)
        body_speed = self._compute_body_speed()
        angle_change_rate = self._compute_angle_change_rate()

        # --- Legacy fields for backward compat ---
        shoulder_mid_y = (lms[LEFT_SHOULDER].y + lms[RIGHT_SHOULDER].y) / 2
        hip_mid_y = (lms[LEFT_HIP].y + lms[RIGHT_HIP].y) / 2
        body_centroid_y = (shoulder_mid_y + hip_mid_y) / 2
        ground_proximity = _clamp((body_centroid_y - 0.3) / 0.5)

        return PoseFeatures(
            # 5 core features
            body_axis_angle=round(body_axis_angle, 2),
            center_of_gravity_height=round(cog_height, 4),
            aspect_ratio=round(aspect_ratio, 3),
            sudden_motion_change=round(sudden_motion, 5),
            stillness_duration=round(stillness_duration, 2),
            # Derived
            posture_score=round(posture_score, 4),
            cumulative_delta_angle=round(delta_angle, 2),
            cumulative_delta_cog=round(delta_cog, 4),
            cumulative_delta_aspect=round(delta_ar, 3),
            # Speed / rate-of-change
            body_speed=round(body_speed, 5),
            angle_change_rate=round(angle_change_rate, 2),
            # Legacy
            body_centroid_y=round(body_centroid_y, 4),
            torso_angle=round(body_axis_angle, 2),
            head_height=round(lms[NOSE].y, 4),
            hip_height=round(hip_mid_y, 4),
            velocity=round(sudden_motion, 5),
            motion_energy=round(sudden_motion, 5),
            stillness_score=round(_clamp(1.0 - sudden_motion * 10), 4),
            ground_proximity=round(ground_proximity, 4),
        )

    # ------------------------------------------------------------------
    # Core feature computations
    # ------------------------------------------------------------------

    def _compute_body_axis_angle(self, lms: list[LandmarkPoint]) -> float:
        """Angle of shoulder→hip vector vs downward vertical (0°=upright, 90°=horizontal)."""
        sh_x = (lms[LEFT_SHOULDER].x + lms[RIGHT_SHOULDER].x) / 2
        sh_y = (lms[LEFT_SHOULDER].y + lms[RIGHT_SHOULDER].y) / 2
        hip_x = (lms[LEFT_HIP].x + lms[RIGHT_HIP].x) / 2
        hip_y = (lms[LEFT_HIP].y + lms[RIGHT_HIP].y) / 2

        dx = hip_x - sh_x
        dy = hip_y - sh_y

        if abs(dy) < 1e-6 and abs(dx) < 1e-6:
            return 0.0

        # atan2(|horizontal|, vertical) gives angle from vertical
        angle = math.degrees(math.atan2(abs(dx), abs(dy)))
        return _clamp(angle, 0.0, 90.0)

    def _compute_cog_height(self, lms: list[LandmarkPoint]) -> float:
        """Average Y of shoulders, hips, knees. 0=top, 1=bottom."""
        indices = [LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP, LEFT_KNEE, RIGHT_KNEE]
        total = 0.0
        count = 0
        for i in indices:
            if lms[i].visibility >= _MIN_VIS:
                total += lms[i].y
                count += 1
        if count == 0:
            return 0.5
        return total / count

    def _compute_aspect_ratio(self, lms: list[LandmarkPoint]) -> float:
        """Bounding box height / width from all visible landmarks."""
        xs, ys = [], []
        for lm in lms:
            if lm.visibility >= _MIN_VIS:
                xs.append(lm.x)
                ys.append(lm.y)
        if len(xs) < 2:
            return 1.5  # default upright
        w = max(xs) - min(xs)
        h = max(ys) - min(ys)
        if w < 1e-6:
            return 5.0  # very narrow = very tall
        return h / w

    def _compute_sudden_motion(self, lms: list[LandmarkPoint]) -> float:
        """Sum of Euclidean distances between current and previous landmarks."""
        if self._prev_landmarks is None:
            return 0.0
        total = 0.0
        for curr, prev in zip(lms, self._prev_landmarks):
            total += math.sqrt((curr.x - prev.x) ** 2 + (curr.y - prev.y) ** 2)
        return total

    # ------------------------------------------------------------------
    # Posture Score (velocity-independent, single-frame)
    # ------------------------------------------------------------------

    def _compute_posture_score(
        self, angle: float, cog: float, ar: float
    ) -> float:
        """Weighted combination of angle, CoG height, and aspect ratio.

        Designed so:
            - Upright (angle<15, cog<0.5, ar>1.5) → score < 0.2
            - Collapsed (angle>55, cog>0.6, ar<1.0) → score ≥ 0.7
        """
        # Normalize each signal to 0–1
        angle_norm = _normalize(angle, 0.0, 90.0)
        cog_norm = _normalize(cog, 0.3, 0.8)
        # Invert AR: low AR (wide body) → high score
        ar_inv = _normalize(1.0 / max(ar, 0.1), 0.5, 2.0)

        score = W_ANGLE * angle_norm + W_COG * cog_norm + W_AR * ar_inv
        return _clamp(score)

    # ------------------------------------------------------------------
    # Body Speed & Angle Change Rate (short-window derivatives)
    # ------------------------------------------------------------------

    def _compute_body_speed(self) -> float:
        """CoG descent speed in units/sec over the speed window.

        Positive = body moving downward (falling direction).
        Near-zero for someone already lying still.
        """
        if len(self._cog_history) < 2:
            return 0.0
        oldest = self._cog_history[0]
        newest = self._cog_history[-1]
        n_frames = len(self._cog_history) - 1
        time_span = n_frames / self._fps
        if time_span < 1e-6:
            return 0.0
        return (newest - oldest) / time_span

    def _compute_angle_change_rate(self) -> float:
        """Body axis angle change rate in deg/sec over the speed window.

        Positive = torso tilting away from vertical (toward horizontal).
        Near-zero for someone already lying still.
        """
        if len(self._angle_history) < 2:
            return 0.0
        oldest = self._angle_history[0]
        newest = self._angle_history[-1]
        n_frames = len(self._angle_history) - 1
        time_span = n_frames / self._fps
        if time_span < 1e-6:
            return 0.0
        return (newest - oldest) / time_span

    # ------------------------------------------------------------------
    # Cumulative Delta (sliding window)
    # ------------------------------------------------------------------

    def _compute_cumulative_delta(
        self, current: _FrameSnapshot
    ) -> tuple[float, float, float]:
        """Delta between current frame and oldest non-gap frame in window."""
        # Find oldest non-gap snapshot
        oldest = None
        for snap in self._window:
            if not snap.is_gap:
                oldest = snap
                break

        if oldest is None or oldest is current:
            return 0.0, 0.0, 0.0

        return (
            current.body_axis_angle - oldest.body_axis_angle,
            current.cog_height - oldest.cog_height,
            current.aspect_ratio - oldest.aspect_ratio,
        )

    # ------------------------------------------------------------------
    # No-detection handler
    # ------------------------------------------------------------------

    def _handle_no_detection(self) -> PoseFeatures:
        """When no pose is detected, retain last state and mark gap."""
        gap = _FrameSnapshot(is_gap=True)
        if self._window:
            last = self._window[-1]
            gap.body_axis_angle = last.body_axis_angle
            gap.cog_height = last.cog_height
            gap.aspect_ratio = last.aspect_ratio
        self._window.append(gap)
        return PoseFeatures()
