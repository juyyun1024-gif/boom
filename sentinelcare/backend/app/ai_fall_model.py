"""AI-backed fall-risk model over rolling pose-feature sequences."""

from __future__ import annotations

import pickle
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .models import PoseFeatures


@dataclass(frozen=True)
class AIFallPrediction:
    """Structured output from the AI fall-risk model."""

    fall_probability: float
    model_probability: float
    rule_probability: float
    smoothed_probability: float
    source: str
    status: str
    ready: bool
    model_loaded: bool


class AIFallRiskModel:
    """Runs a trained sequence model with temporal smoothing and safe fallback.

    The primary model is the sklearn MLP saved in ``app/models/fall_detector.pkl``.
    If that artifact cannot be loaded, this class falls back to a temporal
    sequence scorer so the backend keeps running.
    """

    FEATURE_COUNT = 8

    def __init__(
        self,
        model_path: Optional[str],
        window_size: int = 30,
        model_weight: float = 0.72,
        smoothing_up: float = 0.55,
        smoothing_down: float = 0.25,
    ) -> None:
        self.window_size = window_size
        self.model_weight = model_weight
        self.smoothing_up = smoothing_up
        self.smoothing_down = smoothing_down
        self._feature_buffer: deque[np.ndarray] = deque(maxlen=window_size)
        self._model = None
        self._scaler = None
        self._model_loaded = False
        self._load_error = ""
        self._smoothed_probability = 0.0

        if model_path:
            self._model_path = self._resolve_model_path(model_path)
            self._load_model()
        else:
            self._model_path = None
            self._load_error = "model_path_not_configured"

    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    @property
    def status(self) -> str:
        if self._model_loaded:
            return "model_loaded"
        return self._load_error or "model_unavailable"

    def update(self, features: PoseFeatures, rule_probability: float) -> AIFallPrediction:
        if not features.pose_reliable:
            self.reset()
            return AIFallPrediction(
                fall_probability=0.0,
                model_probability=0.0,
                rule_probability=0.0,
                smoothed_probability=0.0,
                source="pose_quality_gate",
                status=features.visibility_reason,
                ready=False,
                model_loaded=self._model_loaded,
            )

        vector = self._features_to_vector(features)
        self._feature_buffer.append(vector)

        ready = len(self._feature_buffer) >= self.window_size
        model_probability = 0.0
        source = "ai_model"
        status = self.status

        if ready and self._model_loaded:
            model_probability, predict_status = self._predict_with_model()
            if predict_status != "model_prediction":
                status = predict_status
                model_probability = self._temporal_sequence_probability()
                source = "temporal_fallback"
        elif ready:
            model_probability = self._temporal_sequence_probability()
            source = "temporal_fallback"
        else:
            model_probability = rule_probability
            source = "warming_up"
            status = "buffering"

        raw_probability = self._combine_probabilities(
            model_probability=model_probability,
            rule_probability=rule_probability,
            model_active=self._model_loaded and ready and source == "ai_model",
        )
        raw_probability = self._apply_context_suppression(raw_probability, rule_probability)
        smoothed = self._smooth(raw_probability)

        return AIFallPrediction(
            fall_probability=round(smoothed, 4),
            model_probability=round(model_probability, 4),
            rule_probability=round(rule_probability, 4),
            smoothed_probability=round(smoothed, 4),
            source=source,
            status=status,
            ready=ready,
            model_loaded=self._model_loaded,
        )

    def reset(self) -> None:
        self._feature_buffer.clear()
        self._smoothed_probability = 0.0

    def _resolve_model_path(self, model_path: str) -> Path:
        path = Path(model_path)
        if path.is_absolute():
            return path

        backend_root = Path(__file__).resolve().parents[1]
        candidates = [
            Path.cwd() / path,
            backend_root / path,
            Path(__file__).resolve().parent / path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return backend_root / path

    def _load_model(self) -> None:
        if self._model_path is None or not self._model_path.exists():
            self._load_error = "model_file_missing"
            return

        try:
            with self._model_path.open("rb") as f:
                data = pickle.load(f)
            if isinstance(data, dict):
                self._model = data.get("model")
                self._scaler = data.get("scaler")
            else:
                self._model = data
                self._scaler = None

            if not hasattr(self._model, "predict_proba"):
                self._model = None
                self._load_error = "model_missing_predict_proba"
                return

            self._model_loaded = True
            self._load_error = ""
        except Exception as exc:
            self._model = None
            self._scaler = None
            self._model_loaded = False
            self._load_error = f"model_load_failed:{exc.__class__.__name__}"

    def _features_to_vector(self, f: PoseFeatures) -> np.ndarray:
        return np.array(
            [
                f.body_centroid_y,
                f.torso_angle,
                f.head_height,
                f.hip_height,
                f.velocity,
                f.motion_energy,
                f.stillness_score,
                f.ground_proximity,
            ],
            dtype=float,
        )

    def _predict_with_model(self) -> tuple[float, str]:
        sequence = np.array(list(self._feature_buffer), dtype=float).flatten().reshape(1, -1)

        try:
            if self._scaler is not None:
                sequence = self._scaler.transform(sequence)
            probability = float(self._model.predict_proba(sequence)[0][1])
            return self._clip(probability), "model_prediction"
        except Exception as exc:
            return 0.0, f"model_predict_failed:{exc.__class__.__name__}"

    def _temporal_sequence_probability(self) -> float:
        if len(self._feature_buffer) < 2:
            return 0.0

        sequence = np.array(list(self._feature_buffer), dtype=float)
        centroid_y = sequence[:, 0]
        torso_angle = sequence[:, 1]
        head_height = sequence[:, 2]
        velocity = sequence[:, 4]
        motion_energy = sequence[:, 5]
        ground_proximity = sequence[:, 7]

        total_centroid_drop = float(centroid_y[-1] - centroid_y[0])
        head_drop = float(head_height[-1] - head_height[0])
        max_velocity = float(np.max(velocity))
        max_torso = float(np.max(torso_angle))
        final_ground = float(ground_proximity[-1])
        recent_ground = float(np.mean(ground_proximity[-8:]))
        motion_spike = float(np.max(motion_energy) - np.mean(motion_energy))

        score = 0.0
        if max_velocity > 0.03:
            score += min(0.25, (max_velocity - 0.03) * 5.0)
        if total_centroid_drop > 0.12:
            score += min(0.25, (total_centroid_drop - 0.12) * 1.6)
        if head_drop > 0.10:
            score += min(0.15, (head_drop - 0.10) * 1.2)
        if max_torso > 38:
            score += min(0.15, (max_torso - 38) / 80)
        if final_ground > 0.58 or recent_ground > 0.55:
            score += min(0.15, max(final_ground - 0.55, recent_ground - 0.52) * 0.8)
        if motion_spike > 0.08:
            score += min(0.05, motion_spike * 0.25)

        return self._clip(score)

    def _combine_probabilities(
        self,
        model_probability: float,
        rule_probability: float,
        model_active: bool,
    ) -> float:
        if model_active:
            raw = self.model_weight * model_probability + (1.0 - self.model_weight) * rule_probability
            if rule_probability >= 0.68:
                raw = max(raw, rule_probability)
            return self._clip(raw)

        return self._clip(max(rule_probability, model_probability * 0.9))

    def _apply_context_suppression(self, probability: float, rule_probability: float) -> float:
        if len(self._feature_buffer) < 4:
            return probability

        sequence = np.array(list(self._feature_buffer), dtype=float)
        recent = sequence[-8:]
        max_recent_downward_velocity = float(np.max(recent[:, 4]))
        recent_motion_spike = float(np.max(recent[:, 5]) - np.mean(recent[:, 5]))
        centroid_drop = float(recent[-1, 0] - recent[0, 0])
        window_downward_velocity = float(np.max(sequence[:, 4]))
        window_centroid_drop = float(sequence[-1, 0] - sequence[0, 0])
        window_head_drop = float(sequence[-1, 2] - sequence[0, 2])
        window_motion_spike = float(np.max(sequence[:, 5]) - np.mean(sequence[:, 5]))
        final_ground = float(recent[-1, 7])

        has_fast_transition = (
            max_recent_downward_velocity > 0.018
            or window_downward_velocity > 0.03
            or recent_motion_spike > 0.10
            or window_motion_spike > 0.14
        )
        has_drop_context = (
            centroid_drop > 0.06
            or window_centroid_drop > 0.14
            or window_head_drop > 0.10
            or (rule_probability > 0.45 and final_ground > 0.45)
        )
        has_dynamic_fall_context = has_fast_transition and has_drop_context

        if final_ground > 0.55 and window_downward_velocity < 0.018 and window_motion_spike < 0.08:
            return min(probability, 0.22)
        if not has_dynamic_fall_context and rule_probability < 0.45:
            return min(probability, 0.28)
        return probability

    def _smooth(self, probability: float) -> float:
        alpha = self.smoothing_up if probability >= self._smoothed_probability else self.smoothing_down
        self._smoothed_probability = (
            alpha * probability + (1.0 - alpha) * self._smoothed_probability
        )
        return self._clip(self._smoothed_probability)

    @staticmethod
    def _clip(value: float) -> float:
        return max(0.0, min(1.0, float(value)))
