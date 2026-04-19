"""FallGuard Agent — state machine for fall/collapse detection + recovery monitoring."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from .agent_base import BaseAgent
from .models import AgentState, AgentStateName, Event, Alert, PoseFeatures
from .event_store import event_store


class FallGuardAgent(BaseAgent):
    """Rule-based fall detection agent with recovery window escalation.

    States
    ------
    NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → RECOVERED | CRITICAL_ALERT

    The agent evaluates multiple weighted signals each frame and uses a
    confidence score to decide on state transitions.
    
    Optionally supports ML confidence boosting for improved accuracy.
    """

    def __init__(
        self, 
        recovery_window: float = 10.0, 
        confidence_threshold: float = 0.55,
        use_ml_boost: bool = False,
        ml_weight: float = 0.3,
        use_trained_model: bool = False,
        trained_model_path: Optional[str] = None
    ) -> None:
        super().__init__(recovery_window, confidence_threshold)
        
        # FallGuard-specific state
        self._event_start: float | None = None
        self._location = "Living Room"

        # Baseline tracking
        self._baseline_centroid: float | None = None
        self._baseline_frames = 0
        self._frames_since_suspicious = 0

        # Cooldown after recovery
        self._recovery_cooldown_until: float = 0.0
        
        # Sustained detection tracking
        self._high_confidence_frames = 0  # Count frames with high fall confidence
        self._required_sustained_frames = 2  # Reduced from 3 to 2 frames (~0.08s at 24fps)
        
        # ML confidence booster (optional)
        self._use_ml_boost = use_ml_boost
        self._ml_booster: Optional['MLConfidenceBooster'] = None
        if use_ml_boost:
            from .ml_classifier import MLConfidenceBooster
            self._ml_booster = MLConfidenceBooster(ml_weight=ml_weight)
        
        # Trained model (alternative to rules)
        self._use_trained_model = use_trained_model
        self._trained_model: Optional['TrainedModelAgent'] = None
        if use_trained_model and trained_model_path:
            from .trained_model import TrainedModelAgent
            self._trained_model = TrainedModelAgent(
                model_path=trained_model_path,
                threshold=confidence_threshold
            )
            print(f"[FallGuard] Using trained model from {trained_model_path}")

    # ------------------------------------------------------------------
    # Public API (BaseAgent implementation)
    # ------------------------------------------------------------------
    
    def get_agent_name(self) -> str:
        """Return the agent's display name."""
        return "FallGuard"

    def update(self, features: PoseFeatures, pose_detected: bool) -> AgentState:
        """Process one frame's features and return updated agent state."""
        now = time.time()

        if not pose_detected:
            return self._build_state(now)

        # Update baseline (rolling average of centroid when in NORMAL)
        if self._state == AgentStateName.NORMAL:
            self._update_baseline(features)

        # Compute fall confidence
        fall_confidence = self._compute_fall_confidence(features)

        # ---- State transitions ----------------------------------------

        if self._state == AgentStateName.NORMAL:
            if now < self._recovery_cooldown_until:
                pass  # cooldown period after recovery
            elif fall_confidence >= self._confidence_threshold:
                # Require sustained high confidence, not just a spike
                self._high_confidence_frames += 1
                print(f"[DEBUG] High confidence frame {self._high_confidence_frames}/{self._required_sustained_frames} (conf={fall_confidence:.3f})")
                if self._high_confidence_frames >= self._required_sustained_frames:
                    print(f"[ALERT] TRIGGERING SUSPICIOUS EVENT! Sustained {self._high_confidence_frames} frames")
                    self._transition(AgentStateName.SUSPICIOUS_EVENT, fall_confidence, now)
                    print(f"[STATE] Transitioned to SUSPICIOUS_EVENT with confidence {fall_confidence:.3f}")
                    self._event_start = now
                    self._frames_since_suspicious = 0
            else:
                # Reset counter if confidence drops
                if self._high_confidence_frames > 0:
                    print(f"[DEBUG] Confidence dropped to {fall_confidence:.3f}, resetting counter from {self._high_confidence_frames}")
                self._high_confidence_frames = 0

        elif self._state == AgentStateName.SUSPICIOUS_EVENT:
            self._frames_since_suspicious += 1
            self._confidence = max(self._confidence, fall_confidence)
            # Confirm immediately - we already required 2 sustained frames to get here
            if self._frames_since_suspicious >= 1 and self._confidence >= self._confidence_threshold:
                self._transition(AgentStateName.MONITORING_RECOVERY, self._confidence, now)
                print(f"[STATE] Transitioned to MONITORING_RECOVERY with confidence {self._confidence:.3f}")
                self._timer_start = now
                self._log_event("collapse_suspected", "monitoring_recovery",
                                "Possible collapse detected. Monitoring for recovery.")
            elif fall_confidence < self._confidence_threshold * 0.5:
                # False alarm
                self._transition(AgentStateName.NORMAL, 0.0, now)

        elif self._state == AgentStateName.MONITORING_RECOVERY:
            recovery_score = self._compute_recovery_score(features)
            elapsed = now - (self._timer_start or now)

            if recovery_score > 0.6:
                self._transition(AgentStateName.RECOVERED, recovery_score, now)
                self._log_event("collapse_recovered", "recovered",
                                f"Subject recovered after {elapsed:.1f}s.")
                self._recovery_cooldown_until = now + 3.0
            elif elapsed >= self._recovery_window:
                self._transition(AgentStateName.CRITICAL_ALERT, self._confidence, now)
                evt = self._log_event(
                    "collapse_no_recovery", "critical_alert",
                    f"No recovery detected within {self._recovery_window:.0f}s window. "
                    "Subject remains in dangerous position.",
                    recommended_action="Notify caregiver / emergency contact",
                    elapsed=elapsed,
                )
                alert = Alert(event=evt)
                event_store.add_alert(alert)

        elif self._state == AgentStateName.RECOVERED:
            # Stay in recovered state briefly then return to normal
            if now - self._last_change > 3.0:
                self._transition(AgentStateName.NORMAL, 0.0, now)
                self._baseline_centroid = None
                self._baseline_frames = 0

        elif self._state == AgentStateName.CRITICAL_ALERT:
            # Stay in alert until manually acknowledged or timeout
            recovery_score = self._compute_recovery_score(features)
            if recovery_score > 0.7:
                self._transition(AgentStateName.RECOVERED, recovery_score, now)
                self._log_event("late_recovery", "recovered",
                                "Subject recovered after critical alert was raised.")
                self._recovery_cooldown_until = now + 5.0

        return self._build_state(now)

    def reset(self) -> None:
        """Reset agent to NORMAL state."""
        self._state = AgentStateName.NORMAL
        self._confidence = 0.0
        self._event_start = None
        self._timer_start = None
        self._last_change = time.time()
        self._baseline_centroid = None
        self._baseline_frames = 0
        self._high_confidence_frames = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_baseline(self, f: PoseFeatures) -> None:
        """Track baseline centroid height during normal state."""
        if self._baseline_centroid is None:
            self._baseline_centroid = f.body_centroid_y
            self._baseline_frames = 1
        else:
            # Exponential moving average
            alpha = min(1.0, 1.0 / (self._baseline_frames + 1))
            self._baseline_centroid = (
                alpha * f.body_centroid_y + (1 - alpha) * self._baseline_centroid
            )
            self._baseline_frames += 1

    def _compute_fall_confidence(self, f: PoseFeatures) -> float:
        """Multi-signal weighted fall/collapse confidence (0–1).
        
        Requires rapid downward velocity as a prerequisite — without it,
        normal sitting/crouching won't trigger a fall event.
        
        Optionally boosts confidence with ML predictions if enabled.
        Can use trained model instead of rules if configured.
        """
        # If using trained model, get prediction from it
        if self._use_trained_model and self._trained_model:
            prediction = self._trained_model.update(f)
            return prediction['fall_probability']
        
        # DEBUG: Log velocity every 30 frames (~1 second)
        import random
        if random.random() < 0.03:  # ~3% of frames
            print(f"[DEBUG] velocity={f.velocity:.4f}, ground_prox={f.ground_proximity:.3f}, torso={f.torso_angle:.1f}, centroid_y={f.body_centroid_y:.3f}")
        
        # Otherwise use rule-based detection
        # CRITICAL GATE: Must have rapid downward velocity to distinguish fall from lying down
        # This prevents false positives when someone is sleeping or lying down intentionally
        if f.velocity < 0.015:  # Lowered back to be more sensitive
            return 0.0

        score = 0.0

        # Signal 1: Rapid downward velocity (positive velocity = moving down)
        # This is the PRIMARY signal - without it, no fall
        # BUT: velocity alone is not enough - need at least one other signal
        velocity_score = min(0.30, (f.velocity - 0.015) * 10)  # Reduced max from 0.40 to 0.30
        score += velocity_score

        # Signal 2: High torso angle (leaning / horizontal) OR horizontal body position
        torso_score = 0.0
        if f.torso_angle > 30:  # Sideways lean
            torso_score = min(0.25, (f.torso_angle - 30) / 60 * 0.25)  # Increased weight
            score += torso_score
        elif f.is_horizontal:  # Body is horizontal (lying down)
            torso_score = 0.25  # Full score for horizontal position
            score += torso_score

        # Signal 3: Ground proximity (body low in frame)
        # This is CRITICAL - must be close to ground for a fall
        ground_score = 0.0
        if f.ground_proximity > 0.45:  # Lowered from 0.5
            ground_score = min(0.25, (f.ground_proximity - 0.45) / 0.55 * 0.25)  # Increased weight
            score += ground_score

        # Signal 4: Centroid significantly below baseline
        drop_score = 0.0
        if self._baseline_centroid is not None:
            drop = f.body_centroid_y - self._baseline_centroid
            if drop > 0.08:  # Lowered from 0.10
                drop_score = min(0.20, (drop - 0.08) * 4)
                score += drop_score
        
        # CRITICAL: Require velocity + at least one other strong signal
        # This prevents false positives from fast movements like jumping or waving
        has_ground_proximity = f.ground_proximity > 0.45
        has_torso_angle = f.torso_angle > 30 or f.is_horizontal
        has_baseline_drop = (self._baseline_centroid is not None and 
                            (f.body_centroid_y - self._baseline_centroid) > 0.08)
        
        other_signals = sum([has_ground_proximity, has_torso_angle, has_baseline_drop])
        
        # If only velocity is high but no other signals, reduce confidence dramatically
        if other_signals == 0:
            score *= 0.3  # Reduce to 30% if only velocity detected

        rule_confidence = min(1.0, score)
        
        # Boost with ML if enabled
        final_confidence = rule_confidence
        if self._use_ml_boost and self._ml_booster:
            final_confidence = self._ml_booster.boost_confidence("FallGuard", rule_confidence, f)
        
        # DEBUG: Log when confidence is high
        if rule_confidence > 0.2:
            horiz_flag = "HORIZ" if f.is_horizontal else ""
            if self._use_ml_boost:
                print(f"[DEBUG] RULE={rule_confidence:.3f} → ML_BOOSTED={final_confidence:.3f} | vel={velocity_score:.3f}, torso={torso_score:.3f}, ground={ground_score:.3f}, drop={drop_score:.3f} {horiz_flag}")
            else:
                print(f"[DEBUG] CONFIDENCE={rule_confidence:.3f} | vel={velocity_score:.3f}, torso={torso_score:.3f}, ground={ground_score:.3f}, drop={drop_score:.3f} {horiz_flag}")
        
        return final_confidence

    def _compute_recovery_score(self, f: PoseFeatures) -> float:
        """Assess whether the subject has recovered (0–1)."""
        score = 0.0

        # Upright torso
        if f.torso_angle < 20:
            score += 0.35

        # Not on ground
        if f.ground_proximity < 0.3:
            score += 0.30

        # Centroid back near baseline
        if self._baseline_centroid is not None:
            rise = self._baseline_centroid - f.body_centroid_y
            if abs(f.body_centroid_y - self._baseline_centroid) < 0.1:
                score += 0.20

        # Active movement
        if f.motion_energy > 0.02:
            score += 0.15

        return min(1.0, score)

    def _transition(self, new_state: AgentStateName, confidence: float, now: float) -> None:
        self._state = new_state
        self._confidence = confidence
        self._last_change = now

    def _build_state(self, now: float) -> AgentState:
        timer_active = self._state == AgentStateName.MONITORING_RECOVERY
        timer_remaining = 0.0
        if timer_active and self._timer_start is not None:
            elapsed = now - self._timer_start
            timer_remaining = max(0.0, self._recovery_window - elapsed)

        summaries = {
            AgentStateName.NORMAL: "System operating normally. No events detected.",
            AgentStateName.SUSPICIOUS_EVENT: "Suspicious posture change detected. Evaluating...",
            AgentStateName.MONITORING_RECOVERY: f"Possible collapse detected. Monitoring recovery ({timer_remaining:.1f}s remaining).",
            AgentStateName.RECOVERED: "Subject recovered. Returning to normal monitoring.",
            AgentStateName.CRITICAL_ALERT: "CRITICAL: No recovery detected. Immediate attention required.",
        }

        return AgentState(
            agent_name=self.get_agent_name(),
            state=self._state,
            confidence=round(self._confidence, 3),
            event_type="fall_collapse" if self._state != AgentStateName.NORMAL else "none",
            timer_active=timer_active,
            timer_remaining=round(timer_remaining, 1),
            timer_total=self._recovery_window,
            last_change=datetime.fromtimestamp(self._last_change, tz=timezone.utc).isoformat(),
            summary=summaries.get(self._state, ""),
        )

    def _log_event(
        self,
        event_type: str,
        status: str,
        summary: str,
        recommended_action: str = "",
        elapsed: float = 0.0,
    ) -> Event:
        evt = Event(
            event_type=event_type,
            status=status,
            confidence=round(self._confidence, 3),
            location=self._location,
            recovery_window_seconds=self._recovery_window,
            elapsed_seconds=round(elapsed, 1),
            summary=summary,
            recommended_action=recommended_action,
        )
        event_store.add_event(evt)
        return evt
