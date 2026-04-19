"""FallGuard Agent — 5-feature fall detection with EMA smoothing and consecutive-frame gating.

States
------
NORMAL → SUSPICIOUS_EVENT → MONITORING_RECOVERY → RECOVERED | CRITICAL_ALERT

Key changes from the original velocity-gated approach:
    - Dynamic-transition gate using body_speed and angle_change_rate:
      high posture score alone is NOT enough — there must be evidence of
      rapid downward movement or rapid angle change to trigger detection.
      This prevents false positives on people already lying/sitting still.
    - EMA smoothing on confidence prevents single-frame flicker
    - Consecutive-frame gating requires sustained evidence for state transitions
    - Combined scoring uses Posture Score + Cumulative Delta + Sudden Motion Change
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from .models import AgentState, AgentStateName, Event, Alert, PoseFeatures
from .event_store import event_store


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _normalize(v: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return _clamp((v - lo) / (hi - lo))


class FallGuardAgent:
    """Rule-based fall detection agent with 5-feature scoring.

    Parameters
    ----------
    recovery_window : float
        Seconds to wait for recovery before escalating to CRITICAL_ALERT.
    confidence_threshold : float
        Minimum smoothed confidence to trigger state transitions.
    ema_alpha : float
        Smoothing factor for exponential moving average (0.05–0.5).
    """

    # --- Confidence weights ---
    W_POSTURE = 0.45
    W_DELTA_COG = 0.25
    W_MOTION = 0.15
    W_DELTA_ANGLE = 0.15

    # --- Consecutive-frame requirements ---
    FRAMES_TO_SUSPICIOUS = 2
    FRAMES_TO_NORMAL = 5
    FRAMES_TO_MONITORING = 3
    FRAMES_GAP_HOLD = 10

    def __init__(
        self,
        recovery_window: float = 10.0,
        confidence_threshold: float = 0.55,
        ema_alpha: float = 0.3,
    ) -> None:
        self.recovery_window = recovery_window
        self.confidence_threshold = confidence_threshold
        self.ema_alpha = _clamp(ema_alpha, 0.05, 0.5)

        # State
        self._state = AgentStateName.NORMAL
        self._confidence = 0.0
        self._smoothed_confidence = 0.0
        self._last_change = time.time()
        self._location = "Living Room"

        # Timers
        self._timer_start: float | None = None
        self._event_start: float | None = None

        # Consecutive-frame counters
        self._frames_above = 0   # consecutive frames with confidence >= threshold
        self._frames_below = 0   # consecutive frames with confidence < threshold * 0.5
        self._gap_frames = 0     # consecutive frames with no pose detected

        # Track motion spike for impact detection
        self._recent_motion_spike = False
        self._motion_spike_time: float = 0.0

        # Cooldown
        self._recovery_cooldown_until: float = 0.0

        # Track peak posture score during monitoring
        self._peak_cog_in_monitoring: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, features: PoseFeatures, pose_detected: bool) -> AgentState:
        """Process one frame's features and return updated agent state."""
        now = time.time()

        if not pose_detected:
            return self._handle_no_detection(now)

        self._gap_frames = 0

        # Compute raw fall confidence from 5 features
        raw_confidence = self._compute_fall_confidence(features)

        # EMA smoothing
        if self._smoothed_confidence == 0.0:
            self._smoothed_confidence = raw_confidence
        else:
            self._smoothed_confidence = (
                self.ema_alpha * raw_confidence
                + (1.0 - self.ema_alpha) * self._smoothed_confidence
            )

        # Track motion spikes for impact detection
        if features.sudden_motion_change > 0.08:
            self._recent_motion_spike = True
            self._motion_spike_time = now

        # Clear old motion spikes (older than 1.5s)
        if self._recent_motion_spike and (now - self._motion_spike_time) > 1.5:
            self._recent_motion_spike = False

        # Update consecutive-frame counters
        if self._smoothed_confidence >= self.confidence_threshold:
            self._frames_above += 1
            self._frames_below = 0
        elif self._smoothed_confidence < self.confidence_threshold * 0.5:
            self._frames_below += 1
            self._frames_above = 0
        else:
            # In the middle zone — don't reset either counter
            pass

        # --- State transitions ---
        self._update_state(features, now)

        return self._build_state(now)

    def reset(self) -> None:
        """Reset agent to NORMAL state."""
        self._state = AgentStateName.NORMAL
        self._confidence = 0.0
        self._smoothed_confidence = 0.0
        self._last_change = time.time()
        self._timer_start = None
        self._event_start = None
        self._frames_above = 0
        self._frames_below = 0
        self._gap_frames = 0
        self._recent_motion_spike = False
        self._recovery_cooldown_until = 0.0

    # ------------------------------------------------------------------
    # Fall confidence (no velocity gate!)
    # ------------------------------------------------------------------

    def _compute_fall_confidence(self, f: PoseFeatures) -> float:
        """Combined 5-feature fall confidence (0–1).

        Uses body_speed and angle_change_rate as a dynamic-transition gate:
        a person already lying still has high posture_score but near-zero
        speed/rate, so confidence stays low. A real fall shows rapid
        downward movement AND rapid angle change alongside high posture.
        """
        # Posture Score is the strongest signal (works on static images too)
        posture_component = f.posture_score

        # CoG delta: positive = person moved downward over the window
        cog_delta_component = _normalize(f.cumulative_delta_cog, 0.0, 0.3)

        # Sudden motion spike (impact moment)
        motion_component = _normalize(f.sudden_motion_change, 0.0, 0.1)

        # Angle delta: positive = torso tilted more from vertical
        angle_delta_component = _normalize(f.cumulative_delta_angle, 0.0, 60.0)

        raw = (
            self.W_POSTURE * posture_component
            + self.W_DELTA_COG * cog_delta_component
            + self.W_MOTION * motion_component
            + self.W_DELTA_ANGLE * angle_delta_component
        )

        # Boost if motion spike was followed by high posture score
        if self._recent_motion_spike and f.posture_score > 0.6:
            raw += 0.1

        # --- Dynamic-transition gate ---
        # body_speed > 0 means CoG is descending (units/sec)
        # angle_change_rate > 0 means torso is tilting toward horizontal (deg/sec)
        #
        # If NEITHER speed signal is active, the person is likely already on
        # the ground (static). We attenuate confidence so it can still reach
        # SUSPICIOUS (yellow) but not easily escalate to MONITORING/CRITICAL.

        speed_signal = _normalize(f.body_speed, 0.0, 0.3)          # 0–1
        angle_rate_signal = _normalize(f.angle_change_rate, 0.0, 60.0)  # 0–1
        dynamic_score = max(speed_signal, angle_rate_signal)

        # Also count sudden_motion_change as a dynamic signal
        motion_signal = _normalize(f.sudden_motion_change, 0.0, 0.08)
        dynamic_score = max(dynamic_score, motion_signal)

        # If there's been a recent motion spike (within 1.5s), keep dynamic_score high
        if self._recent_motion_spike:
            dynamic_score = max(dynamic_score, 0.6)

        # Gate: when dynamic_score is low, attenuate confidence
        # dynamic_score=0 → multiply by 0.35 (enough for SUSPICIOUS, not MONITORING)
        # dynamic_score=1 → multiply by 1.0 (full confidence)
        gate = 0.35 + 0.65 * dynamic_score
        raw *= gate

        return _clamp(raw)

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _update_state(self, f: PoseFeatures, now: float) -> None:
        """Apply consecutive-frame gating to state transitions."""

        if self._state == AgentStateName.NORMAL:
            if now < self._recovery_cooldown_until:
                return
            if self._frames_above >= self.FRAMES_TO_SUSPICIOUS:
                self._transition(AgentStateName.SUSPICIOUS_EVENT, self._smoothed_confidence, now)
                self._event_start = now
                self._confidence = self._smoothed_confidence

        elif self._state == AgentStateName.SUSPICIOUS_EVENT:
            self._confidence = max(self._confidence, self._smoothed_confidence)

            # Escalate to MONITORING only if there's strong dynamic evidence
            # of a rapid fall transition. Key insight: a slow sit-down or
            # gradual lying motion has high angle_change_rate noise from pose
            # jitter but LOW body_speed (CoG barely moves per second).
            # A real fall has body_speed > 0.15 (rapid descent).
            #
            # We require EITHER:
            #   - High body_speed (rapid CoG descent) — the strongest signal
            #   - A recent motion spike (sudden impact detected earlier)
            has_dynamic_evidence = (
                f.body_speed > 0.15
                or self._recent_motion_spike
            )

            if self._frames_above >= self.FRAMES_TO_MONITORING and has_dynamic_evidence:
                self._transition(AgentStateName.MONITORING_RECOVERY, self._confidence, now)
                self._timer_start = now
                self._peak_cog_in_monitoring = f.center_of_gravity_height
                self._log_event(
                    "collapse_suspected", "monitoring_recovery",
                    "Possible collapse detected. Monitoring for recovery.",
                )
            elif self._frames_below >= self.FRAMES_TO_NORMAL:
                self._transition(AgentStateName.NORMAL, 0.0, now)
            # If stuck in SUSPICIOUS without dynamic evidence for too long,
            # decay back to NORMAL (person is just in an odd posture)
            elif not has_dynamic_evidence and (now - self._last_change) > 2.0:
                self._transition(AgentStateName.NORMAL, 0.0, now)
                self._frames_above = 0

        elif self._state == AgentStateName.MONITORING_RECOVERY:
            elapsed = now - (self._timer_start or now)

            # Track peak CoG (highest point = most collapsed)
            self._peak_cog_in_monitoring = max(
                self._peak_cog_in_monitoring, f.center_of_gravity_height
            )

            # Recovery: posture score drops AND person rises
            cog_rise = self._peak_cog_in_monitoring - f.center_of_gravity_height
            if f.posture_score < 0.3 and cog_rise > 0.1:
                self._transition(AgentStateName.RECOVERED, 1.0 - f.posture_score, now)
                self._log_event(
                    "collapse_recovered", "recovered",
                    f"Subject recovered after {elapsed:.1f}s.",
                )
                self._recovery_cooldown_until = now + 3.0

            # Critical alert: posture stays collapsed for full recovery window
            elif elapsed >= self.recovery_window and f.posture_score > 0.6:
                self._transition(AgentStateName.CRITICAL_ALERT, self._confidence, now)
                evt = self._log_event(
                    "collapse_no_recovery", "critical_alert",
                    f"No recovery detected within {self.recovery_window:.0f}s window. "
                    "Subject remains in dangerous position.",
                    recommended_action="Notify caregiver / emergency contact",
                    elapsed=elapsed,
                )
                alert = Alert(event=evt)
                event_store.add_alert(alert)

            # Timeout even if posture score is moderate
            elif elapsed >= self.recovery_window:
                self._transition(AgentStateName.CRITICAL_ALERT, self._confidence, now)
                evt = self._log_event(
                    "collapse_no_recovery", "critical_alert",
                    f"No recovery detected within {self.recovery_window:.0f}s window.",
                    recommended_action="Notify caregiver / emergency contact",
                    elapsed=elapsed,
                )
                alert = Alert(event=evt)
                event_store.add_alert(alert)

        elif self._state == AgentStateName.RECOVERED:
            if now - self._last_change > 3.0:
                self._transition(AgentStateName.NORMAL, 0.0, now)
                self._frames_above = 0
                self._frames_below = 0

        elif self._state == AgentStateName.CRITICAL_ALERT:
            # Recovery from critical: need strong upright signal
            if f.posture_score < 0.2 and f.sudden_motion_change > 0.02:
                self._transition(AgentStateName.RECOVERED, 1.0 - f.posture_score, now)
                self._log_event(
                    "late_recovery", "recovered",
                    "Subject recovered after critical alert was raised.",
                )
                self._recovery_cooldown_until = now + 5.0

    # ------------------------------------------------------------------
    # No-detection handler
    # ------------------------------------------------------------------

    def _handle_no_detection(self, now: float) -> AgentState:
        """Hold current state during detection gaps, revert after N frames."""
        self._gap_frames += 1
        if self._gap_frames >= self.FRAMES_GAP_HOLD:
            if self._state not in (AgentStateName.NORMAL, AgentStateName.RECOVERED):
                self._transition(AgentStateName.NORMAL, 0.0, now)
                self._frames_above = 0
                self._frames_below = 0
        return self._build_state(now)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _transition(self, new_state: AgentStateName, confidence: float, now: float) -> None:
        self._state = new_state
        self._confidence = confidence
        self._last_change = now

    def _build_state(self, now: float) -> AgentState:
        timer_active = self._state == AgentStateName.MONITORING_RECOVERY
        timer_remaining = 0.0
        if timer_active and self._timer_start is not None:
            elapsed = now - self._timer_start
            timer_remaining = max(0.0, self.recovery_window - elapsed)

        summaries = {
            AgentStateName.NORMAL: "System operating normally. No events detected.",
            AgentStateName.SUSPICIOUS_EVENT: "Suspicious posture change detected. Evaluating...",
            AgentStateName.MONITORING_RECOVERY: (
                f"Possible collapse detected. Monitoring recovery "
                f"({timer_remaining:.1f}s remaining)."
            ),
            AgentStateName.RECOVERED: "Subject recovered. Returning to normal monitoring.",
            AgentStateName.CRITICAL_ALERT: (
                "CRITICAL: No recovery detected. Immediate attention required."
            ),
        }

        return AgentState(
            state=self._state,
            confidence=round(self._smoothed_confidence, 3),
            event_type="fall_collapse" if self._state != AgentStateName.NORMAL else "none",
            timer_active=timer_active,
            timer_remaining=round(timer_remaining, 1),
            timer_total=self.recovery_window,
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
            recovery_window_seconds=self.recovery_window,
            elapsed_seconds=round(elapsed, 1),
            summary=summary,
            recommended_action=recommended_action,
        )
        event_store.add_event(evt)
        return evt
