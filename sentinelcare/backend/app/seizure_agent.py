"""Seizure Detection Agent — detects seizure-like repetitive motion patterns."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from .agent_base import BaseAgent
from .models import AgentState, AgentStateName, Event, PoseFeatures
from .event_store import event_store


class SeizureAgent(BaseAgent):
    """Rule-based seizure detection agent using repetitive motion analysis.

    States
    ------
    NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → RECOVERED | CRITICAL_ALERT

    Detection Logic
    ---------------
    - Uses RepetitionScore from autocorrelation of joint vertical displacement
    - Requires sustained high repetition score (>0.65) for 2+ seconds
    - Monitors for recovery (score drops below 0.30)
    """

    def __init__(
        self,
        recovery_window: float = 10.0,
        confidence_threshold: float = 0.65,
        recovery_threshold: float = 0.30,
        history_window: int = 60
    ) -> None:
        """Initialize SeizureAgent with seizure-specific parameters.
        
        Args:
            recovery_window: Seconds to wait for recovery before critical alert
            confidence_threshold: RepetitionScore threshold to trigger suspicious event
            recovery_threshold: RepetitionScore threshold for recovery detection
            history_window: Number of frames for repetition analysis (60 = ~2.5s at 24 FPS)
        """
        super().__init__(recovery_window, confidence_threshold)
        
        self._recovery_threshold = recovery_threshold
        self._history_window = history_window
        
        # Seizure-specific state tracking
        self._frames_since_suspicious = 0
        self._frames_above_threshold = 0
        self._high_score_started_at: float | None = None
        self._quiet_started_at: float | None = None
        self._timer_pause_started: float | None = None
        self._timer_paused_total = 0.0
        self._score_ema = 0.0
        self._last_seizure_score = 0.0
        self._last_pose_quality = 0.0
        self._last_pose_reliable = False
        self._last_visibility_reason = "no_pose"
        self._last_recovery_gesture_score = 0.0
        self._recovery_gesture_started_at: float | None = None
        self._recovery_gesture_confirmed_until = 0.0
        self._recovery_gesture_required_seconds = 0.5
        self._required_high_seconds = 2.0
        self._confirm_seconds = 0.6
        self._required_quiet_seconds = 1.0

    def get_agent_name(self) -> str:
        """Return the agent's display name."""
        return "Seizure"

    def update(self, features: PoseFeatures, pose_detected: bool) -> AgentState:
        """Process one frame's features and return updated agent state."""
        now = time.time()

        if not pose_detected:
            self._mark_pose_unusable("no_pose", 0.0, now)
            return self._build_state(now)

        self._last_pose_quality = features.pose_quality
        self._last_pose_reliable = features.pose_reliable
        self._last_visibility_reason = features.visibility_reason
        self._last_recovery_gesture_score = features.recovery_gesture_score

        if not features.pose_reliable:
            self._mark_pose_unusable(features.visibility_reason, features.pose_quality, now)
            return self._build_state(now)

        self._resume_recovery_timer(now)
        seizure_score = self._compute_seizure_confidence(features)

        # ---- State transitions ----------------------------------------

        if self._state == AgentStateName.NORMAL:
            if seizure_score >= self._confidence_threshold:
                if self._high_score_started_at is None:
                    self._high_score_started_at = now
                self._frames_above_threshold += 1
                if now - self._high_score_started_at >= self._required_high_seconds:
                    self._transition(AgentStateName.SUSPICIOUS_EVENT, seizure_score, now)
                    self._frames_since_suspicious = 0
                    self._quiet_started_at = None
            else:
                if seizure_score < self._confidence_threshold * 0.75:
                    self._high_score_started_at = None
                self._frames_above_threshold = 0

        elif self._state == AgentStateName.SUSPICIOUS_EVENT:
            self._frames_since_suspicious += 1
            self._confidence = max(self._confidence, seizure_score)
            
            if seizure_score >= self._confidence_threshold * 0.85:
                if now - self._last_change >= self._confirm_seconds:
                    self._transition(AgentStateName.MONITORING_RECOVERY, self._confidence, now)
                    self._timer_start = now
                    self._timer_paused_total = 0.0
                    self._timer_pause_started = None
                    self._log_event("seizure_suspected", "monitoring_recovery",
                                    "Sustained rhythmic motion detected. Monitoring for recovery.")
            elif seizure_score < self._recovery_threshold:
                if self._quiet_started_at is None:
                    self._quiet_started_at = now
                if now - self._quiet_started_at >= 0.8:
                    self._transition(AgentStateName.NORMAL, 0.0, now)
                    self._reset_detection_windows()
            else:
                self._quiet_started_at = None

        elif self._state == AgentStateName.MONITORING_RECOVERY:
            elapsed = self._monitoring_elapsed(now)
            
            if seizure_score < self._recovery_threshold:
                if self._quiet_started_at is None:
                    self._quiet_started_at = now
                if now - self._quiet_started_at >= self._required_quiet_seconds:
                    self._transition(AgentStateName.RECOVERED, seizure_score, now)
                    self._log_event("seizure_recovered", "recovered",
                                    f"Repetitive motion subsided after {elapsed:.1f}s.")
            else:
                self._quiet_started_at = None
                self._confidence = max(self._confidence, seizure_score)
                if elapsed >= self._recovery_window:
                    self._transition(AgentStateName.CRITICAL_ALERT, self._confidence, now)
                    self._log_event(
                        "seizure_no_recovery", "critical_alert",
                        f"Seizure-like motion persists after {self._recovery_window:.0f}s. "
                        "Subject may need immediate medical attention.",
                        recommended_action="Notify caregiver / emergency contact. Keep the area clear and do not restrain the subject.",
                        elapsed=elapsed,
                    )

        elif self._state == AgentStateName.RECOVERED:
            # Stay in recovered state briefly then return to normal
            if now - self._last_change > 3.0:
                self._transition(AgentStateName.NORMAL, 0.0, now)
                self._reset_detection_windows()

        elif self._state == AgentStateName.CRITICAL_ALERT:
            # Stay in alert until manually acknowledged or late recovery
            if seizure_score < self._recovery_threshold:
                if self._quiet_started_at is None:
                    self._quiet_started_at = now
                if now - self._quiet_started_at >= self._required_quiet_seconds:
                    self._transition(AgentStateName.RECOVERED, seizure_score, now)
                    self._log_event("seizure_late_recovery", "recovered",
                                    "Repetitive motion subsided after critical alert was raised.")
            else:
                self._quiet_started_at = None

        return self._build_state(now)

    def reset(self) -> None:
        """Reset agent to NORMAL state."""
        self._state = AgentStateName.NORMAL
        self._confidence = 0.0
        self._timer_start = None
        self._last_change = time.time()
        self._frames_since_suspicious = 0
        self._frames_above_threshold = 0
        self._high_score_started_at = None
        self._quiet_started_at = None
        self._timer_pause_started = None
        self._timer_paused_total = 0.0
        self._score_ema = 0.0
        self._last_seizure_score = 0.0
        self._last_pose_quality = 0.0
        self._last_pose_reliable = False
        self._last_visibility_reason = "no_pose"
        self._last_recovery_gesture_score = 0.0
        self._recovery_gesture_started_at = None
        self._recovery_gesture_confirmed_until = 0.0

    def _transition(self, new_state: AgentStateName, confidence: float, now: float) -> None:
        """Transition to new state and update internal tracking."""
        self._state = new_state
        self._confidence = confidence
        self._last_change = now
        self._recovery_gesture_started_at = None
        if new_state in {AgentStateName.NORMAL, AgentStateName.RECOVERED, AgentStateName.CRITICAL_ALERT}:
            self._timer_pause_started = None
            self._timer_paused_total = 0.0

    def _recovery_gesture_confirmed(self, f: PoseFeatures, now: float) -> bool:
        """Require a short sustained wave before treating it as explicit recovery."""
        self._last_recovery_gesture_score = f.recovery_gesture_score
        self._recovery_gesture_started_at = None
        return False

    def _compute_seizure_confidence(self, f: PoseFeatures) -> float:
        """Smooth and gate the rhythmic-motion score."""
        raw_score = f.repetition_score
        if f.visibility_reason != "ok":
            raw_score *= 0.85
        if f.pose_quality < 0.55:
            raw_score *= 0.75
        if f.motion_energy < 0.015 and raw_score < 0.80:
            raw_score *= 0.65

        alpha = 0.45 if raw_score >= self._score_ema else 0.65
        self._score_ema = alpha * raw_score + (1.0 - alpha) * self._score_ema
        self._last_seizure_score = max(raw_score, self._score_ema)

        if self._last_seizure_score >= 0.35:
            print(
                "[DEBUG] SEIZURE_SCORE="
                f"{self._last_seizure_score:.3f} | raw={raw_score:.3f}, "
                f"rep={f.repetition_score:.3f}, motion={f.motion_energy:.3f}, "
                f"pose={f.pose_quality:.2f}, reason={f.visibility_reason}"
            )

        return self._last_seizure_score

    def _mark_pose_unusable(self, reason: str, quality: float, now: float) -> None:
        self._last_pose_quality = quality
        self._last_pose_reliable = False
        self._last_visibility_reason = reason
        self._last_recovery_gesture_score = 0.0
        self._recovery_gesture_started_at = None
        self._last_seizure_score = 0.0
        self._score_ema = 0.0
        self._high_score_started_at = None
        self._frames_above_threshold = 0

        if self._state == AgentStateName.SUSPICIOUS_EVENT:
            self._transition(AgentStateName.NORMAL, 0.0, now)
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

    def _reset_detection_windows(self) -> None:
        self._frames_above_threshold = 0
        self._frames_since_suspicious = 0
        self._high_score_started_at = None
        self._quiet_started_at = None

    def _build_state(self, now: float) -> AgentState:
        """Build AgentState object for current state."""
        timer_active = self._state == AgentStateName.MONITORING_RECOVERY
        timer_remaining = 0.0
        if timer_active and self._timer_start is not None:
            elapsed = self._monitoring_elapsed(now)
            timer_remaining = max(0.0, self._recovery_window - elapsed)

        summaries = {
            AgentStateName.NORMAL: "Monitoring for seizure-like repetitive motion. No events detected.",
            AgentStateName.SUSPICIOUS_EVENT: "Repetitive motion pattern detected. Evaluating...",
            AgentStateName.MONITORING_RECOVERY: f"Possible seizure detected. Monitoring recovery ({timer_remaining:.1f}s remaining).",
            AgentStateName.RECOVERED: "Repetitive motion subsided. Returning to normal monitoring.",
            AgentStateName.CRITICAL_ALERT: "CRITICAL: Persistent seizure-like motion. Immediate medical attention required.",
        }
        summary = summaries.get(self._state, "")
        if not self._last_pose_reliable:
            reason = self._last_visibility_reason.replace("_", " ")
            if self._state == AgentStateName.MONITORING_RECOVERY:
                summary = f"Pose unreliable ({reason}). Seizure recovery timer paused."
            elif self._state in {AgentStateName.NORMAL, AgentStateName.SUSPICIOUS_EVENT}:
                summary = f"Pose unreliable ({reason}). Waiting for stable body view."

        display_confidence = (
            self._confidence
            if self._state != AgentStateName.NORMAL
            else self._last_seizure_score
        )

        return AgentState(
            agent_name=self.get_agent_name(),
            state=self._state,
            confidence=round(display_confidence, 3),
            event_type="seizure_suspected" if self._state != AgentStateName.NORMAL else "none",
            timer_active=timer_active,
            timer_remaining=round(timer_remaining, 1),
            timer_total=self._recovery_window,
            last_change=datetime.fromtimestamp(self._last_change, tz=timezone.utc).isoformat(),
            summary=summary,
            model_source="signal_processing",
            model_status="jitter_filtered",
            rule_confidence=round(self._last_seizure_score, 3),
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
        """Log event to EventStore."""
        evt = Event(
            agent=self.get_agent_name(),
            event_type=event_type,
            status=status,
            confidence=round(self._confidence, 3),
            location="Living Room",  # TODO: Make configurable
            recovery_window_seconds=self._recovery_window,
            elapsed_seconds=round(elapsed, 1),
            summary=summary,
            recommended_action=recommended_action,
        )
        event_store.add_event(evt)
        return evt
