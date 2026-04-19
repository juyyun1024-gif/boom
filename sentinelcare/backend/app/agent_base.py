"""Base agent abstract class for all detection agents."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from .models import AgentState, AgentStateName, PoseFeatures


class BaseAgent(ABC):
    """Abstract base class for all detection agents.
    
    All agents follow the same state machine pattern:
    NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → RECOVERED | CRITICAL_ALERT
    
    Subclasses must implement:
    - update(): Process one frame and return updated state
    - reset(): Reset agent to NORMAL state
    - get_agent_name(): Return the agent's display name
    """

    def __init__(self, recovery_window: float, confidence_threshold: float):
        """Initialize base agent with common parameters.
        
        Args:
            recovery_window: Seconds to wait for recovery before raising critical alert
            confidence_threshold: Minimum confidence score to trigger suspicious event
        """
        self._state = AgentStateName.NORMAL
        self._confidence = 0.0
        self._recovery_window = recovery_window
        self._confidence_threshold = confidence_threshold
        self._timer_start: float | None = None
        self._last_change = time.time()

    @abstractmethod
    def update(self, features: PoseFeatures, pose_detected: bool) -> AgentState:
        """Process one frame's features and return updated agent state.
        
        Args:
            features: Extracted pose features for this frame
            pose_detected: Whether a valid pose was detected in this frame
            
        Returns:
            AgentState with current state, confidence, timer info, etc.
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset agent to NORMAL state.
        
        Clears all internal state, timers, and confidence scores.
        """
        pass

    @abstractmethod
    def get_agent_name(self) -> str:
        """Return the agent's display name.
        
        Returns:
            Agent name string (e.g., "ResponseGuard", "Seizure", "Stroke", "Wandering")
        """
        pass
