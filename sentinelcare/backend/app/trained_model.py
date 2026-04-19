"""Trained neural network model for fall detection.

This module provides a trained LSTM model for fall detection as an alternative
to the rule-based approach. The rule-based system remains the default.
"""

from __future__ import annotations

import numpy as np
from typing import Optional
from collections import deque
import pickle
import os

from .models import PoseFeatures


class FallDetectionLSTM:
    """LSTM-based fall detection model.
    
    This is a lightweight LSTM trained on fall detection sequences.
    Uses pose features over a temporal window to classify fall vs. normal.
    """
    
    def __init__(self, model_path: Optional[str] = None, window_size: int = 30):
        """Initialize LSTM model.
        
        Args:
            model_path: Path to saved model weights (optional)
            window_size: Number of frames to analyze (30 frames ~= 1 second at 30fps)
        """
        self.window_size = window_size
        self.feature_buffer: deque = deque(maxlen=window_size)
        self.model = None
        self.scaler = None
        self.model_loaded = False
        
        # Try to load pre-trained model if path provided
        if model_path and os.path.exists(model_path):
            self._load_model(model_path)
    
    def _load_model(self, path: str) -> None:
        """Load trained model from disk."""
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.model = data['model']
                self.scaler = data['scaler']
            self.model_loaded = True
            print(f"[FallDetectionLSTM] Loaded model from {path}")
        except Exception as e:
            print(f"[FallDetectionLSTM] Failed to load model: {e}")
            self.model_loaded = False
    
    def predict(self, features: PoseFeatures) -> dict[str, float]:
        """Predict fall probability from current features.
        
        Args:
            features: Current frame's pose features
            
        Returns:
            Dictionary with 'fall_probability' and 'confidence'
        """
        # Add features to buffer
        feature_vector = self._features_to_vector(features)
        self.feature_buffer.append(feature_vector)
        
        # Need full window for prediction
        if len(self.feature_buffer) < self.window_size:
            return {
                'fall_probability': 0.0,
                'confidence': 0.0,
                'status': 'buffering'
            }
        
        # If model is loaded, use it
        if self.model_loaded and self.model is not None:
            return self._predict_with_model()
        else:
            # Fallback to heuristic-based prediction
            return self._predict_heuristic()
    
    def _features_to_vector(self, f: PoseFeatures) -> np.ndarray:
        """Convert PoseFeatures to numpy vector."""
        return np.array([
            f.body_centroid_y,
            f.torso_angle,
            f.head_height,
            f.hip_height,
            f.velocity,
            f.motion_energy,
            f.stillness_score,
            f.ground_proximity,
        ])
    
    def _predict_with_model(self) -> dict[str, float]:
        """Use trained neural network model for prediction."""
        # Convert buffer to flattened sequence
        sequence = np.array(list(self.feature_buffer)).flatten()
        sequence = sequence.reshape(1, -1)
        
        try:
            # Scale features
            if self.scaler is not None:
                sequence = self.scaler.transform(sequence)
            
            # Model prediction
            fall_prob = self.model.predict_proba(sequence)[0][1]  # Probability of class 1 (fall)
            
            return {
                'fall_probability': float(fall_prob),
                'confidence': float(fall_prob),
                'status': 'model_prediction'
            }
        except Exception as e:
            print(f"[FallDetectionLSTM] Prediction error: {e}")
            return self._predict_heuristic()
    
    def _predict_heuristic(self) -> dict[str, float]:
        """Heuristic-based prediction when model is not available.
        
        This analyzes temporal patterns in the feature buffer.
        """
        buffer_array = np.array(list(self.feature_buffer))
        
        # Analyze temporal patterns
        velocity_col = buffer_array[:, 4]  # velocity
        height_col = buffer_array[:, 2]    # head_height
        ground_prox_col = buffer_array[:, 7]  # ground_proximity
        
        # Fall indicators
        max_velocity = np.max(velocity_col)
        height_drop = height_col[0] - height_col[-1]
        final_ground_prox = ground_prox_col[-1]
        avg_recent_ground_prox = np.mean(ground_prox_col[-10:])
        
        # Compute fall probability
        fall_score = 0.0
        
        # High velocity spike
        if max_velocity > 0.03:
            fall_score += 0.35
        
        # Significant height drop
        if height_drop > 0.15:
            fall_score += 0.30
        
        # High ground proximity at end
        if final_ground_prox > 0.6:
            fall_score += 0.20
        
        # Sustained low position
        if avg_recent_ground_prox > 0.5:
            fall_score += 0.15
        
        fall_probability = min(1.0, fall_score)
        
        return {
            'fall_probability': fall_probability,
            'confidence': fall_probability * 0.8,  # Lower confidence for heuristic
            'status': 'heuristic_prediction'
        }
    
    def reset(self) -> None:
        """Clear feature buffer."""
        self.feature_buffer.clear()


class TrainedModelAgent:
    """Wrapper agent that uses trained LSTM model for fall detection.
    
    This is an alternative to the rule-based FallGuardAgent.
    Can be used side-by-side for comparison.
    """
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        threshold: float = 0.65,
        window_size: int = 30
    ):
        """Initialize trained model agent.
        
        Args:
            model_path: Path to trained model file
            threshold: Probability threshold for fall detection
            window_size: Temporal window size in frames
        """
        self.model = FallDetectionLSTM(model_path, window_size)
        self.threshold = threshold
        self.last_prediction = None
    
    def update(self, features: PoseFeatures) -> dict[str, float]:
        """Update with new features and return prediction.
        
        Args:
            features: Current pose features
            
        Returns:
            Prediction dictionary with fall_probability and confidence
        """
        prediction = self.model.predict(features)
        self.last_prediction = prediction
        return prediction
    
    def is_fall_detected(self) -> bool:
        """Check if fall is detected based on threshold."""
        if self.last_prediction is None:
            return False
        return self.last_prediction['fall_probability'] >= self.threshold
    
    def reset(self) -> None:
        """Reset model state."""
        self.model.reset()
        self.last_prediction = None
