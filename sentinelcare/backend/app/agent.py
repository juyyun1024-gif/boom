"""ResponseGuard Agent — state machine for fall/collapse detection + recovery monitoring."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from .ai_fall_model import AIFallPrediction, AIFallRiskModel
from .agent_base import BaseAgent
from .models import AgentState, AgentStateName, Event, Alert, PoseFeatures
from .event_store import event_store


class ResponseGuardAgent(BaseAgent):
    """AI-backed response detection agent with recovery window escalation.

    States
    ------
    NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → RECOVERED | CRITICAL_ALERT

    The agent evaluates rolling pose-feature sequences with a trained model
    and keeps weighted rule logic as a safety fallback.
    
    Optionally supports ML confidence boosting for improved accuracy.
    """

    def __init__(
        self, 
        recovery_window: float = 10.0, 
        confidence_threshold: float = 0.55,
        use_ml_boost: bool = False,
        ml_weight: float = 0.3,
        use_trained_model: bool = True,
        trained_model_path: Optional[str] = None
    ) -> None:
        super().__init__(recovery_window, confidence_threshold)
        
        # ResponseGuard-specific state
        self._event_start: float | None = None
        self._location = "Living Room"
        self._last_pose_quality = 0.0
        self._last_pose_reliable = False
        self._last_visibility_reason = "no_pose"
        self._last_recovery_gesture_score = 0.0
        self._recovery_gesture_started_at: float | None = None
        self._recovery_gesture_confirmed_until = 0.0
        self._recovery_gesture_required_seconds = 0.5

        # Baseline tracking
        self._baseline_centroid: float | None = None
        self._baseline_frames = 0
        self._frames_since_suspicious = 0
        self._timer_pause_started: float | None = None
        self._timer_paused_total = 0.0

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
        
        # AI sequence model (primary) with rule fallback.
        self._use_trained_model = use_trained_model
        self._ai_fall_model: AIFallRiskModel | None = None
        self._last_ai_prediction: AIFallPrediction | None = None
        self._last_rule_confidence = 0.0
        if use_trained_model:
            self._ai_fall_model = AIFallRiskModel(trained_model_path)
            print(f"[FallGuard] AI model status: {self._ai_fall_model.status}")

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
            reason = features.visibility_reason if features.visibility_reason != "no_pose" else "no_pose"
            self._mark_pose_unreliable(reason, features.pose_quality, now)
            return self._build_state(now)

        self._last_pose_quality = features.pose_quality
        self._last_pose_reliable = features.pose_reliable
        self._last_visibility_reason = features.visibility_reason
        self._last_recovery_gesture_score = features.recovery_gesture_score

        if not features.pose_reliable:
            self._mark_pose_unreliable(features.visibility_reason, features.pose_quality, now)
            return self._build_state(now)

        self._resume_recovery_timer(now)

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
                self._timer_paused_total = 0.0
                self._timer_pause_started = None
                self._log_event("collapse_suspected", "monitoring_recovery",
                                "Possible collapse detected. Monitoring for recovery.")
            elif fall_confidence < self._confidence_threshold * 0.5:
                # False alarm
                self._transition(AgentStateName.NORMAL, 0.0, now)

        elif self._state == AgentStateName.MONITORING_RECOVERY:
            elapsed = self._monitoring_elapsed(now)
            recovery_score = self._compute_recovery_score(features)

            if recovery_score >= 0.55:
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
            if recovery_score >= 0.65:
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
        self._last_ai_prediction = None
        self._last_rule_confidence = 0.0
        self._last_pose_quality = 0.0
        self._last_pose_reliable = False
        self._last_visibility_reason = "no_pose"
        self._last_recovery_gesture_score = 0.0
        self._recovery_gesture_started_at = None
        self._recovery_gesture_confirmed_until = 0.0
        self._timer_pause_started = None
        self._timer_paused_total = 0.0
        if self._ai_fall_model:
            self._ai_fall_model.reset()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _recovery_gesture_confirmed(self, f: PoseFeatures, now: float) -> bool:
        """Require a short sustained wave before treating it as explicit recovery."""
        self._last_recovery_gesture_score = f.recovery_gesture_score
        self._recovery_gesture_started_at = None
        return False

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
        """AI-backed fall/collapse confidence (0-1)."""
        rule_confidence = self._compute_rule_fall_confidence(f)
        self._last_rule_confidence = rule_confidence

        if self._use_trained_model and self._ai_fall_model:
            self._last_ai_prediction = self._ai_fall_model.update(f, rule_confidence)
            return self._last_ai_prediction.fall_probability

        final_confidence = rule_confidence
        if self._use_ml_boost and self._ml_booster:
            final_confidence = self._ml_booster.boost_confidence("FallGuard", rule_confidence, f)

        return final_confidence

    def _compute_rule_fall_confidence(self, f: PoseFeatures) -> float:
        """Multi-signal rule fallback for fall/collapse confidence."""
        if not f.pose_reliable:
            return 0.0

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
        
        # DEBUG: Log when confidence is high
        if rule_confidence > 0.2:
            horiz_flag = "HORIZ" if f.is_horizontal else ""
            print(f"[DEBUG] RULE_CONFIDENCE={rule_confidence:.3f} | vel={velocity_score:.3f}, torso={torso_score:.3f}, ground={ground_score:.3f}, drop={drop_score:.3f} {horiz_flag}")
        
        return rule_confidence

    def _compute_recovery_score(self, f: PoseFeatures) -> float:
        """Assess whether the subject has recovered (0–1)."""
        if not f.pose_reliable:
            return 0.0

        score = 0.0
        upright_score = 0.0
        ground_score = 0.0
        baseline_score = 0.0
        head_score = 0.0
        movement_score = 0.0

        # Upright torso
        if f.torso_angle < 25:
            upright_score = 0.35
        elif f.torso_angle < 45 and not f.is_horizontal:
            upright_score = 0.25
        elif not f.is_horizontal:
            upright_score = 0.15
        score += upright_score

        # No longer floor-level. This is intentionally looser than fall detection
        # because recovery frames are often partial while the person stands up.
        if f.ground_proximity < 0.40:
            ground_score = 0.30
        elif f.ground_proximity < 0.58:
            ground_score = 0.20
        elif f.ground_proximity < 0.68 and not f.is_horizontal:
            ground_score = 0.10
        score += ground_score

        # Centroid back near baseline
        if self._baseline_centroid is not None:
            distance_from_baseline = f.body_centroid_y - self._baseline_centroid
            if distance_from_baseline <= 0.12:
                baseline_score = 0.25
            elif distance_from_baseline <= 0.22:
                baseline_score = 0.15
            score += baseline_score

        # Head clearly above hips is a strong standing/sitting recovery clue.
        if f.head_height < f.hip_height - 0.08:
            head_score = 0.15
        elif f.head_height < f.hip_height - 0.03:
            head_score = 0.08
        score += head_score

        # Active movement or upward centroid motion means the person is getting up.
        if f.velocity < -0.018:
            movement_score = 0.15
        elif f.motion_energy > 0.02:
            movement_score = 0.10
        score += movement_score

        recovery_score = min(1.0, score)
        if recovery_score >= 0.35:
            print(
                "[DEBUG] RECOVERY_SCORE="
                f"{recovery_score:.3f} | upright={upright_score:.2f}, "
                f"ground={ground_score:.2f}, baseline={baseline_score:.2f}, "
                f"head={head_score:.2f}, move={movement_score:.2f}, "
                f"torso={f.torso_angle:.1f}, ground_prox={f.ground_proximity:.3f}, "
                f"centroid_y={f.body_centroid_y:.3f}, vel={f.velocity:.4f}"
            )

        return recovery_score

    def _transition(self, new_state: AgentStateName, confidence: float, now: float) -> None:
        self._state = new_state
        self._confidence = confidence
        self._last_change = now
        self._recovery_gesture_started_at = None

        if new_state in {AgentStateName.NORMAL, AgentStateName.RECOVERED, AgentStateName.CRITICAL_ALERT}:
            self._timer_pause_started = None
            self._timer_paused_total = 0.0

    def _mark_pose_unreliable(self, reason: str, quality: float, now: float) -> None:
        """Block alert starts from frames where FallGuard cannot trust the pose."""
        self._last_pose_quality = quality
        self._last_pose_reliable = False
        self._last_visibility_reason = reason
        self._high_confidence_frames = 0
        self._last_rule_confidence = 0.0
        self._last_ai_prediction = None
        self._last_recovery_gesture_score = 0.0
        self._recovery_gesture_started_at = None

        if self._ai_fall_model:
            self._ai_fall_model.reset()

        if self._state == AgentStateName.SUSPICIOUS_EVENT:
            self._transition(AgentStateName.MONITORING_RECOVERY, self._confidence, now)
            self._timer_start = now
            self._timer_paused_total = 0.0
            self._timer_pause_started = now
            self._log_event(
                "collapse_suspected",
                "monitoring_recovery",
                "Fall-like motion detected, but the camera view became unclear. Monitoring for recovery.",
            )
        elif self._state == AgentStateName.MONITORING_RECOVERY and self._timer_pause_started is None:
            self._timer_pause_started = now

    def _resume_recovery_timer(self, now: float) -> None:
        if self._timer_pause_started is None:
            return

        self._timer_paused_total += now - self._timer_pause_started
        self._timer_pause_started = None

    def _monitoring_elapsed(self, now: float) -> float:
        if self._timer_start is None:
            return 0.0

        paused_total = self._timer_paused_total
        if self._timer_pause_started is not None:
            paused_total += now - self._timer_pause_started

        return max(0.0, now - self._timer_start - paused_total)

    def _build_state(self, now: float) -> AgentState:
        timer_active = self._state == AgentStateName.MONITORING_RECOVERY
        timer_remaining = 0.0
        if timer_active and self._timer_start is not None:
            elapsed = self._monitoring_elapsed(now)
            timer_remaining = max(0.0, self._recovery_window - elapsed)

        prediction = self._last_ai_prediction
        ai_enabled = bool(self._use_trained_model and self._ai_fall_model)
        model_source = prediction.source if prediction else ("ai_model" if ai_enabled else "rules")
        model_status = (
            prediction.status
            if prediction
            else (self._ai_fall_model.status if self._ai_fall_model else "not_configured")
        )
        model_confidence = prediction.model_probability if prediction else 0.0
        rule_confidence = prediction.rule_probability if prediction else self._last_rule_confidence

        normal_summary = (
            "AI FallGuard monitoring pose-sequence risk. No events detected."
            if ai_enabled
            else "System operating normally. No events detected."
        )
        summaries = {
            AgentStateName.NORMAL: normal_summary,
            AgentStateName.SUSPICIOUS_EVENT: "Fall-like pose sequence detected. Evaluating...",
            AgentStateName.MONITORING_RECOVERY: f"Possible collapse detected. Monitoring recovery ({timer_remaining:.1f}s remaining).",
            AgentStateName.RECOVERED: "Subject recovered. Returning to normal monitoring.",
            AgentStateName.CRITICAL_ALERT: "CRITICAL: No recovery detected. Immediate attention required.",
        }
        summary = summaries.get(self._state, "")
        if not self._last_pose_reliable:
            reason = self._last_visibility_reason.replace("_", " ")
            if self._state == AgentStateName.MONITORING_RECOVERY:
                summary = f"Pose unreliable ({reason}). Recovery timer paused."
            elif self._state in {AgentStateName.NORMAL, AgentStateName.SUSPICIOUS_EVENT}:
                summary = f"Pose unreliable ({reason}). Waiting for full-body view."

        return AgentState(
            agent_name=self.get_agent_name(),
            state=self._state,
            confidence=round(self._confidence, 3),
            event_type="fall_collapse" if self._state != AgentStateName.NORMAL else "none",
            timer_active=timer_active,
            timer_remaining=round(timer_remaining, 1),
            timer_total=self._recovery_window,
            last_change=datetime.fromtimestamp(self._last_change, tz=timezone.utc).isoformat(),
            summary=summary,
            ai_enabled=ai_enabled,
            model_source=model_source,
            model_status=model_status,
            model_confidence=round(model_confidence, 3),
            rule_confidence=round(rule_confidence, 3),
            pose_quality=round(self._last_pose_quality, 3),
            pose_reliable=self._last_pose_reliable,
            visibility_reason=self._last_visibility_reason,
            recovery_gesture_score=round(self._last_recovery_gesture_score, 3),
            recovery_gesture_detected=(
                self._recovery_gesture_started_at is not None
                or now < self._recovery_gesture_confirmed_until
            ),
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
            agent=self.get_agent_name(),
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
