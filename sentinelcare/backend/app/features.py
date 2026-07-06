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

FALL_GUARD_KEYPOINTS = [
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_HIP,
    RIGHT_HIP,
    LEFT_KNEE,
    RIGHT_KNEE,
    LEFT_ANKLE,
    RIGHT_ANKLE,
]

CORE_KEYPOINTS = [LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP]
LOWER_BODY_KEYPOINTS = [LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE]
VISIBILITY_THRESHOLD = 0.45


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
        self._joint_history: deque[list[tuple[float, float]]] = deque(maxlen=self.JOINT_HISTORY_LEN)
        self._joint_visibility_history: deque[list[float]] = deque(maxlen=self.JOINT_HISTORY_LEN)

    def reset(self) -> None:
        self._centroid_history.clear()
        self._motion_history.clear()
        self._prev_landmarks = None
        self._joint_history.clear()
        self._joint_visibility_history.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pose: PoseData) -> PoseFeatures:
        """Compute features from a single frame's pose data."""
        if not pose.detected or len(pose.landmarks) < 33:
            return PoseFeatures()

        lms = pose.landmarks
        pose_quality, pose_reliable, visibility_reason, visible_keypoints = (
            self._compute_pose_quality(lms)
        )

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
        if pose_reliable and self._centroid_history:
            prev_y = self._centroid_history[-1]
            velocity = body_centroid_y - prev_y  # positive = moving down

        if pose_reliable:
            self._centroid_history.append(body_centroid_y)

        # Motion energy: sum of all joint displacements
        motion_energy = 0.0
        if pose_reliable and self._prev_landmarks is not None:
            for i, lm in enumerate(lms):
                prev = self._prev_landmarks[i]
                motion_energy += math.sqrt(
                    (lm.x - prev.x) ** 2 + (lm.y - prev.y) ** 2
                )

        if pose_reliable:
            self._motion_history.append(motion_energy)
            self._prev_landmarks = list(lms)
        else:
            self._prev_landmarks = None

        # Stillness: inverse of recent motion (rolling average)
        avg_motion = (
            sum(self._motion_history) / len(self._motion_history)
            if self._motion_history
            else 0.0
        )
        stillness_score = max(0.0, 1.0 - avg_motion * 10) if pose_reliable else 0.0

        # Ground proximity: how low in frame (higher Y = lower in scene)
        ground_proximity = max(0.0, min(1.0, (body_centroid_y - 0.3) / 0.5))

        # ---- New Phase 3 Features ----
        
        # RepetitionScore: autocorrelation of per-joint vertical displacement
        repetition_score = self._compute_repetition_score(lms) if pose_reliable else 0.0
        
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
            pose_quality=round(pose_quality, 4),
            pose_reliable=pose_reliable,
            visibility_reason=visibility_reason,
            visible_keypoints=visible_keypoints,
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
        """Compute jitter-resistant rhythmic motion score for SeizureAgent."""
        joint_indices = [
            LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW,
            LEFT_WRIST, RIGHT_WRIST, LEFT_HIP, RIGHT_HIP,
            LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE,
        ]

        current_positions = [(lms[i].x, lms[i].y) for i in joint_indices if i < len(lms)]
        current_visibility = [lms[i].visibility for i in joint_indices if i < len(lms)]
        self._joint_history.append(current_positions)
        self._joint_visibility_history.append(current_visibility)

        if len(self._joint_history) < 36:
            return 0.0

        history = list(self._joint_history)
        visibility_history = list(self._joint_visibility_history)
        joint_count = min(len(frame) for frame in history)
        joint_scores: list[float] = []

        for joint_idx in range(joint_count):
            vis_series = [frame[joint_idx] for frame in visibility_history if joint_idx < len(frame)]
            avg_visibility = sum(vis_series) / len(vis_series)
            if avg_visibility < 0.35:
                continue

            x_series = [frame[joint_idx][0] for frame in history]
            y_series = [frame[joint_idx][1] for frame in history]

            x_amplitude = max(x_series) - min(x_series)
            y_amplitude = max(y_series) - min(y_series)
            amplitude = math.sqrt(x_amplitude ** 2 + y_amplitude ** 2)
            if amplitude < 0.018:
                continue

            dominant_series = x_series if x_amplitude >= y_amplitude else y_series
            per_frame_motion = self._average_deadband_motion(x_series, y_series)
            if per_frame_motion < 0.0025:
                continue

            rhythm = self._dominant_autocorrelation(dominant_series)
            direction_changes = self._direction_change_score(dominant_series)

            amplitude_score = self._clamp((amplitude - 0.018) / 0.055)
            motion_score = self._clamp((per_frame_motion - 0.0025) / 0.011)
            joint_score = amplitude_score * motion_score * rhythm * direction_changes
            if joint_score > 0:
                joint_scores.append(joint_score)

        if not joint_scores:
            return 0.0

        joint_scores.sort(reverse=True)
        top_scores = joint_scores[:4]
        active_joint_factor = self._clamp(len(joint_scores) / 3)
        score = (sum(top_scores) / len(top_scores)) * active_joint_factor
        return self._clamp(score)

    def _average_deadband_motion(
        self,
        x_series: list[float],
        y_series: list[float],
        deadband: float = 0.0035,
    ) -> float:
        if len(x_series) < 2:
            return 0.0

        total = 0.0
        for idx in range(1, len(x_series)):
            movement = math.sqrt(
                (x_series[idx] - x_series[idx - 1]) ** 2
                + (y_series[idx] - y_series[idx - 1]) ** 2
            )
            total += max(0.0, movement - deadband)
        return total / (len(x_series) - 1)

    def _dominant_autocorrelation(self, series: list[float]) -> float:
        n = len(series)
        if n < 18:
            return 0.0

        mean = sum(series) / n
        centered = [value - mean for value in series]
        variance = sum(value ** 2 for value in centered) / n
        if variance < 1e-6:
            return 0.0

        best = 0.0
        for lag in range(5, min(17, n // 2)):
            covariance = sum(
                centered[idx] * centered[idx - lag]
                for idx in range(lag, n)
            ) / (n - lag)
            best = max(best, abs(covariance / variance))

        return self._clamp((best - 0.28) / 0.55)

    def _direction_change_score(self, series: list[float], deadband: float = 0.003) -> float:
        signs: list[int] = []
        for idx in range(1, len(series)):
            delta = series[idx] - series[idx - 1]
            if abs(delta) <= deadband:
                continue
            signs.append(1 if delta > 0 else -1)

        if len(signs) < 6:
            return 0.0

        changes = sum(1 for idx in range(1, len(signs)) if signs[idx] != signs[idx - 1])
        return self._clamp((changes - 3) / 9)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _compute_pose_quality(self, lms: list) -> tuple[float, bool, str, int]:
        """Estimate whether the frame has enough full-body pose for FallGuard."""
        keypoints = [lms[i] for i in FALL_GUARD_KEYPOINTS if i < len(lms)]
        if not keypoints:
            return 0.0, False, "no_pose", 0

        visible = [lm for lm in keypoints if lm.visibility >= VISIBILITY_THRESHOLD]
        in_frame = [
            lm
            for lm in keypoints
            if -0.05 <= lm.x <= 1.05 and -0.05 <= lm.y <= 1.05
        ]

        core_visible = sum(
            1
            for idx in CORE_KEYPOINTS
            if idx < len(lms) and lms[idx].visibility >= VISIBILITY_THRESHOLD
        )
        lower_visible = sum(
            1
            for idx in LOWER_BODY_KEYPOINTS
            if idx < len(lms) and lms[idx].visibility >= VISIBILITY_THRESHOLD
        )

        avg_visibility = sum(max(0.0, min(1.0, lm.visibility)) for lm in keypoints) / len(keypoints)
        visible_fraction = len(visible) / len(keypoints)
        in_frame_fraction = len(in_frame) / len(keypoints)
        core_fraction = core_visible / len(CORE_KEYPOINTS)
        lower_fraction = lower_visible / len(LOWER_BODY_KEYPOINTS)

        quality = (
            0.40 * avg_visibility
            + 0.25 * visible_fraction
            + 0.20 * in_frame_fraction
            + 0.10 * core_fraction
            + 0.05 * lower_fraction
        )
        quality = max(0.0, min(1.0, quality))

        if avg_visibility < 0.25 or len(visible) < 3 or core_visible < 2:
            return quality, False, "low_visibility", len(visible)

        if in_frame_fraction < 0.70:
            return quality, True, "out_of_frame", len(visible)

        if core_visible < 3 or lower_visible < 2:
            return quality, True, "partial_body", len(visible)

        if avg_visibility < 0.42 or visible_fraction < 0.62:
            if core_visible >= 3 and len(visible) >= 4:
                return quality, True, "partial_body", len(visible)
            return quality, False, "low_visibility", len(visible)

        return quality, True, "ok", len(visible)

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
