"""Lightweight ML classifier for action recognition using pre-trained models."""

from __future__ import annotations

import numpy as np
from typing import Optional
from collections import deque

from .models import PoseFeatures


class ActionClassifier:
    """Lightweight action classifier using pose features.
    
    This is a simple ML-based confidence booster that works alongside
    rule-based detection. Uses temporal patterns in pose features to
    classify actions like falls, seizures, etc.
    """

    def __init__(self, window_size: int = 30):
        """Initialize classifier.
        
        Args:
            window_size: Number of frames to consider for temporal patterns
        """
        self.window_size = window_size
        self.feature_history: deque = deque(maxlen=window_size)
        
    def update(self, features: PoseFeatures) -> dict[str, float]:
        """Update with new features and return action probabilities.
        
        Args:
            features: Current frame's pose features
            
        Returns:
            Dictionary of action probabilities: {"fall": 0.8, "seizure": 0.1, ...}
        """
        # Add to history
        self.feature_history.append(self._features_to_array(features))
        
        if len(self.feature_history) < 10:
            # Not enough data yet
            return {"fall": 0.0, "seizure": 0.0, "stroke": 0.0, "normal": 1.0}
        
        # Compute temporal features
        temporal_features = self._compute_temporal_features()
        
        # Simple heuristic-based classification (can be replaced with trained model)
        return self._classify(temporal_features)
    
    def _features_to_array(self, features: PoseFeatures) -> np.ndarray:
        """Convert PoseFeatures to numpy array."""
        return np.array([
            features.body_centroid_y,
            features.torso_angle,
            features.head_height,
            features.hip_height,
            features.velocity,
            features.motion_energy,
            features.stillness_score,
            features.ground_proximity,
            features.repetition_score,
            features.asymmetry_score,
        ])
    
    def _compute_temporal_features(self) -> dict[str, float]:
        """Compute temporal statistics from feature history."""
        history_array = np.array(list(self.feature_history))
        
        # Compute statistics
        mean = np.mean(history_array, axis=0)
        std = np.std(history_array, axis=0)
        delta = history_array[-1] - history_array[0]
        
        # Specific temporal patterns
        velocity_spike = np.max(history_array[:, 4]) - np.mean(history_array[:, 4])
        height_drop = history_array[0, 2] - history_array[-1, 2]  # head_height drop
        motion_variance = np.var(history_array[:, 5])  # motion_energy variance
        
        return {
            "velocity_spike": velocity_spike,
            "height_drop": height_drop,
            "motion_variance": motion_variance,
            "mean_ground_proximity": mean[7],
            "mean_repetition": mean[8],
            "mean_asymmetry": mean[9],
        }
    
    def _classify(self, temporal_features: dict[str, float]) -> dict[str, float]:
        """Classify action based on temporal features.
        
        This is a simple heuristic classifier. In production, this would be
        replaced with a trained neural network (LSTM, Transformer, etc.)
        """
        fall_score = 0.0
        seizure_score = 0.0
        stroke_score = 0.0
        
        # Fall detection: rapid height drop + high ground proximity
        if temporal_features["height_drop"] > 0.3:
            fall_score += 0.4
        if temporal_features["velocity_spike"] > 0.5:
            fall_score += 0.3
        if temporal_features["mean_ground_proximity"] > 0.6:
            fall_score += 0.3
        
        # Seizure detection: high motion variance + repetition
        if temporal_features["motion_variance"] > 0.1:
            seizure_score += 0.5
        if temporal_features["mean_repetition"] > 0.5:
            seizure_score += 0.5
        
        # Stroke detection: high asymmetry + low motion
        if temporal_features["mean_asymmetry"] > 0.3:
            stroke_score += 0.6
        if temporal_features["motion_variance"] < 0.05:
            stroke_score += 0.4
        
        # Normalize to probabilities
        total = fall_score + seizure_score + stroke_score + 0.1  # Add small constant
        
        return {
            "fall": min(1.0, fall_score / total),
            "seizure": min(1.0, seizure_score / total),
            "stroke": min(1.0, stroke_score / total),
            "normal": max(0.0, 1.0 - (fall_score + seizure_score + stroke_score)),
        }
    
    def reset(self) -> None:
        """Clear feature history."""
        self.feature_history.clear()


class MLConfidenceBooster:
    """Boosts rule-based confidence with ML predictions.
    
    Combines rule-based detection with ML classifier to improve accuracy.
    """
    
    def __init__(self, ml_weight: float = 0.3):
        """Initialize booster.
        
        Args:
            ml_weight: Weight given to ML predictions (0-1). 
                      0 = pure rule-based, 1 = pure ML
        """
        self.ml_weight = ml_weight
        self.classifier = ActionClassifier()
    
    def boost_confidence(
        self,
        agent_name: str,
        rule_confidence: float,
        features: PoseFeatures
    ) -> float:
        """Boost rule-based confidence with ML prediction.
        
        Args:
            agent_name: Name of the agent (ResponseGuard, Seizure, Stroke)
            rule_confidence: Confidence from rule-based detection (0-1)
            features: Current pose features
            
        Returns:
            Boosted confidence score (0-1)
        """
        # Get ML predictions
        ml_probs = self.classifier.update(features)
        
        # Map agent name to ML prediction
        agent_to_action = {
            "ResponseGuard": "fall",
            "Seizure": "seizure",
            "Stroke": "stroke",
        }
        
        action = agent_to_action.get(agent_name, "normal")
        ml_confidence = ml_probs.get(action, 0.0)
        
        # Weighted combination
        boosted = (1 - self.ml_weight) * rule_confidence + self.ml_weight * ml_confidence
        
        return min(1.0, boosted)
    
    def reset(self) -> None:
        """Reset classifier state."""
        self.classifier.reset()
