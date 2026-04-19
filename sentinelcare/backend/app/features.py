"""Feature extraction from MediaPipe pose landmarks."""

from __future__ import annotations

import math
from collections import deque
from typing import Optional

from .models import PoseData, PoseFeatures

# MediaPipe landmark indices
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


class FeatureExtractor:
    """Computes derived posture/motion features from raw landmarks.
    
    All Y coordinates use MediaPipe convention: 0 = top, 1 = bottom.
    So a *lower* body position → *higher* Y value → higher ground proximity.
    """

    HISTORY_LEN = 15  # frames of history for velocity / motion
    JOINT_HISTORY_LEN = 60  # frames for repetition score (seizure detection)

    def __init__(self) -> None:
        self._centroid_history: deque[float] = deque(maxlen=self.HISTORY_LEN)
        self._motion_history: deque[float] = deque(maxlen=self.HISTORY_LEN)
        self._prev_landmarks: Optional[list] = None
        
        # New: Joint history for RepetitionScore (60-frame rolling window)
        self._joint_history: deque[list[float]] = deque(maxlen=self.JOINT_HISTORY_LEN)

    def reset(self) -> None:
        self._centroid_history.clear()
        self._motion_history.clear()
        self._prev_landmarks = None
        self._joint_history.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pose: PoseData) -> PoseFeatures:
        """Compute features from a single frame's pose data."""
        if not pose.detected or len(pose.landmarks) < 33:
            return PoseFeatures()

        lms = pose.landmarks

        # Core positions (Y axis: 0=top, 1=bottom)
        shoulder_mid_y = (lms[LEFT_SHOULDER].y + lms[RIGHT_SHOULDER].y) / 2
        hip_mid_y = (lms[LEFT_HIP].y + lms[RIGHT_HIP].y) / 2
        shoulder_mid_x = (lms[LEFT_SHOULDER].x + lms[RIGHT_SHOULDER].x) / 2
        hip_mid_x = (lms[LEFT_HIP].x + lms[RIGHT_HIP].x) / 2

        body_centroid_y = (shoulder_mid_y + hip_mid_y) / 2
        body_centroid_x = (shoulder_mid_x + hip_mid_x) / 2
        head_height = lms[NOSE].y
        hip_height = hip_mid_y

        # Torso angle: angle of shoulder→hip vector vs downward vertical
        dx = hip_mid_x - shoulder_mid_x
        dy = hip_mid_y - shoulder_mid_y
        torso_angle = math.degrees(math.atan2(abs(dx), dy)) if dy != 0 else 0.0
        
        # Horizontal body detection: when lying down, shoulder and hip Y are similar
        # In upright position, hip_y > shoulder_y (hip is lower in frame)
        # When horizontal, hip_y ≈ shoulder_y (both at same height)
        vertical_separation = abs(hip_mid_y - shoulder_mid_y)
        is_horizontal = vertical_separation < 0.15  # Less than 15% of frame height

        # Velocity: centroid displacement frame-to-frame
        velocity = 0.0
        if self._centroid_history:
            prev_y = self._centroid_history[-1]
            velocity = body_centroid_y - prev_y  # positive = moving down

        self._centroid_history.append(body_centroid_y)

        # Motion energy: sum of all joint displacements
        motion_energy = 0.0
        if self._prev_landmarks is not None:
            for i, lm in enumerate(lms):
                prev = self._prev_landmarks[i]
                motion_energy += math.sqrt(
                    (lm.x - prev.x) ** 2 + (lm.y - prev.y) ** 2
                )

        self._motion_history.append(motion_energy)
        self._prev_landmarks = list(lms)

        # Stillness: inverse of recent motion (rolling average)
        avg_motion = (
            sum(self._motion_history) / len(self._motion_history)
            if self._motion_history
            else 0.0
        )
        stillness_score = max(0.0, 1.0 - avg_motion * 10)

        # Ground proximity: how low in frame (higher Y = lower in scene)
        ground_proximity = max(0.0, min(1.0, (body_centroid_y - 0.3) / 0.5))

        # ---- New Phase 3 Features ----
        
        # RepetitionScore: autocorrelation of per-joint vertical displacement
        repetition_score = self._compute_repetition_score(lms)
        
        # AsymmetryScore: left/right landmark Y-coordinate difference
        asymmetry_score = self._compute_asymmetry_score(lms)

        return PoseFeatures(
            body_centroid_y=round(body_centroid_y, 4),
            torso_angle=round(torso_angle, 2),
            head_height=round(head_height, 4),
            hip_height=round(hip_height, 4),
            velocity=round(velocity, 5),
            motion_energy=round(motion_energy, 5),
            stillness_score=round(stillness_score, 4),
            ground_proximity=round(ground_proximity, 4),
            repetition_score=round(repetition_score, 4),
            asymmetry_score=round(asymmetry_score, 4),
            body_centroid_x=round(body_centroid_x, 4),
            is_horizontal=is_horizontal,
        )

    def get_rapid_drop(self, window: int = 5) -> float:
        """Sum of positive (downward) centroid changes over last N frames."""
        if len(self._centroid_history) < 2:
            return 0.0
        changes = []
        hist = list(self._centroid_history)
        for i in range(max(0, len(hist) - window), len(hist)):
            if i > 0:
                delta = hist[i] - hist[i - 1]
                if delta > 0:  # moving downward
                    changes.append(delta)
        return sum(changes)

    # ------------------------------------------------------------------
    # Phase 3: New feature computations
    # ------------------------------------------------------------------

    def _compute_repetition_score(self, lms: list) -> float:
        """Compute RepetitionScore via autocorrelation of vertical joint displacement.
        
        Measures periodic oscillation in joint trajectories over a 60-frame window.
        High score indicates repetitive motion (potential seizure).
        """
        # Extract vertical displacements for key joints
        joint_indices = [LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW,
                        LEFT_WRIST, RIGHT_WRIST, LEFT_HIP, RIGHT_HIP,
                        LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE]
        
        current_displacements = [lms[i].y for i in joint_indices if i < len(lms)]
        self._joint_history.append(current_displacements)
        
        # Need at least 24 frames for meaningful autocorrelation
        if len(self._joint_history) < 24:
            return 0.0
        
        # Compute autocorrelation at lag=12 frames (~0.5s at 24 FPS)
        lag = 12
        if len(self._joint_history) < lag + 1:
            return 0.0
        
        # Average autocorrelation across all joints
        autocorr_sum = 0.0
        joint_count = len(current_displacements)
        
        for joint_idx in range(joint_count):
            # Extract time series for this joint
            series = [frame[joint_idx] for frame in self._joint_history if joint_idx < len(frame)]
            
            if len(series) < lag + 1:
                continue
            
            # Compute autocorrelation at lag
            n = len(series)
            mean = sum(series) / n
            
            # Variance
            variance = sum((x - mean) ** 2 for x in series) / n
            if variance < 1e-6:  # Avoid division by zero
                continue
            
            # Autocorrelation
            covariance = sum((series[i] - mean) * (series[i - lag] - mean) 
                           for i in range(lag, n)) / (n - lag)
            autocorr = covariance / variance
            
            # Accumulate absolute autocorrelation (high periodicity = high abs value)
            autocorr_sum += abs(autocorr)
        
        # Normalize to [0, 1] range
        if joint_count == 0:
            return 0.0
        
        avg_autocorr = autocorr_sum / joint_count
        # Clamp to [0, 1]
        return max(0.0, min(1.0, avg_autocorr))

    def _compute_asymmetry_score(self, lms: list) -> float:
        """Compute AsymmetryScore from left/right landmark Y-coordinate differences.
        
        Measures bilateral asymmetry (potential stroke indicator).
        Returns value in [0, 1] where 0 = perfect symmetry, 1 = maximum asymmetry.
        """
        # Bilateral landmark pairs: (left_idx, right_idx)
        pairs = [
            (LEFT_SHOULDER, RIGHT_SHOULDER),
            (LEFT_HIP, RIGHT_HIP),
            (LEFT_ELBOW, RIGHT_ELBOW),
            (LEFT_WRIST, RIGHT_WRIST),
        ]
        
        asymmetries = []
        for left_idx, right_idx in pairs:
            if left_idx >= len(lms) or right_idx >= len(lms):
                continue
            
            left_y = lms[left_idx].y
            right_y = lms[right_idx].y
            
            # Absolute difference in Y-coordinates
            diff = abs(left_y - right_y)
            asymmetries.append(diff)
        
        if not asymmetries:
            return 0.0
        
        # Average asymmetry across all pairs
        avg_asymmetry = sum(asymmetries) / len(asymmetries)
        
        # Normalize: typical asymmetry in normal posture is < 0.05
        # Scale so that 0.2 difference = score of 1.0
        normalized = avg_asymmetry / 0.2
        
        # Clamp to [0, 1]
        return max(0.0, min(1.0, normalized))
