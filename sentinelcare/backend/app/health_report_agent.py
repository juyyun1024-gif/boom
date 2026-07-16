"""Health event report agent.

Creates a responder-facing report from the emergency alert, current agent
scores, pose quality, and location data. It returns a structured draft
immediately and can optionally ask an LLM to rewrite the report.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from .models import AgentState, Alert, HealthEventReport, PoseFeatures

logger = logging.getLogger("sentinelcare.health_report")


class HealthReportAgent:
    """Generate responder reports without blocking detection."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.model = os.getenv("HEALTH_REPORT_MODEL", "qwen2.5:7b")
        self.timeout_seconds = float(os.getenv("HEALTH_REPORT_TIMEOUT", "180"))
        self.llm_enabled = (
            os.getenv("HEALTH_REPORT_LLM", "1").strip().lower() not in {"0", "false", "off"}
        )

    def generate_draft_report(
        self,
        alert: Alert,
        agent_states: list[AgentState],
        features: PoseFeatures,
        location: dict[str, Any] | None = None,
        nearest_hospital: dict[str, Any] | None = None,
    ) -> HealthEventReport:
        evidence = self._build_evidence(alert, agent_states, features, location, nearest_hospital)
        summary = self._summary_from_evidence(evidence)
        responder_report = self._structured_report_text(evidence)

        return HealthEventReport(
            alert_id=alert.alert_id,
            event_id=alert.event.event_id,
            source="structured",
            model="none",
            risk_level=evidence["risk_level"],
            confidence=evidence["confidence"],
            location_label=evidence["location_label"],
            location=evidence["location"],
            nearest_hospital=evidence["nearest_hospital"],
            summary=summary,
            responder_report=responder_report,
            observed_signals=evidence["observed_signals"],
            timeline=evidence["timeline"],
            uncertainty=evidence["uncertainty"],
            recommended_actions=evidence["recommended_actions"],
        )

    def generate_llm_report(
        self,
        alert: Alert,
        agent_states: list[AgentState],
        features: PoseFeatures,
        location: dict[str, Any] | None = None,
        nearest_hospital: dict[str, Any] | None = None,
    ) -> HealthEventReport:
        draft = self.generate_draft_report(alert, agent_states, features, location, nearest_hospital)
        if not self.llm_enabled:
            return draft

        evidence = self._build_evidence(alert, agent_states, features, location, nearest_hospital)
        try:
            llm_text = self._call_ollama(evidence)
        except Exception as exc:
            logger.warning("Local health report LLM unavailable, keeping structured report: %s", exc)
            draft.source = "structured_fallback"
            draft.model = self.model
            draft.uncertainty.append(
                f"Local Qwen report did not complete before timeout; structured fallback is shown."
            )
            return draft

        if not llm_text:
            return draft

        draft.source = "ollama"
        draft.model = self.model
        draft.responder_report = llm_text
        draft.summary = llm_text.split(".")[0][:220].strip() or draft.summary
        return draft

    def _build_evidence(
        self,
        alert: Alert,
        agent_states: list[AgentState],
        features: PoseFeatures,
        location: dict[str, Any] | None,
        nearest_hospital: dict[str, Any] | None,
    ) -> dict[str, Any]:
        event = alert.event
        location_data = location or {}
        address = (
            location_data.get("address")
            or location_data.get("home_address")
            or event.location
            or "Location unavailable"
        )

        combined_alert_score = max(0.0, min(1.0, event.confidence))

        active_signals: list[str] = []
        for state in agent_states:
            if state.available is False:
                continue
            state_name = state.state.value if hasattr(state.state, "value") else str(state.state)
            if state.confidence > 0 or state_name in {"critical_alert", "monitoring_recovery"}:
                active_signals.append(
                    f"{state.agent_name}: {state_name.replace('_', ' ')}, event {state.event_type.replace('_', ' ')}"
                )

        observed_signals = [
            f"Combined alert score: {round(combined_alert_score * 100)}%",
            f"Primary trigger: {event.event_type.replace('_', ' ')}",
            f"Recovery status: no confirmed recovery within {event.recovery_window_seconds:.0f} seconds",
            f"Pose quality: {round(features.pose_quality * 100)}% ({features.visibility_reason})",
        ]
        observed_signals.extend(active_signals[:4])

        uncertainty: list[str] = []
        if not features.pose_reliable:
            uncertainty.append("Pose visibility was limited, so the report should be treated as camera-assisted evidence.")
        if not location_data:
            uncertainty.append("GPS/location payload was not available from the frontend at report time.")
        if event.agent == "Seizure":
            uncertainty.append("Repetitive motion can indicate distress, but the system cannot diagnose seizure cause.")
        if event.agent == "FallGuard":
            uncertainty.append("The system detected collapse/no recovery, but cannot determine the medical cause.")

        recommended_actions = [
            "Check the person immediately and verify responsiveness.",
            "Use the included location and nearest hospital data when contacting responders.",
            "Do not rely on the camera report as a medical diagnosis.",
        ]

        if nearest_hospital:
            hospital_name = nearest_hospital.get("name", "nearest hospital")
            recommended_actions.append(f"Nearest listed hospital: {hospital_name}.")

        return {
            "alert_id": alert.alert_id,
            "event_id": event.event_id,
            "risk_level": "critical",
            "agent": event.agent,
            "event_type": event.event_type,
            "status": event.status,
            "confidence": round(combined_alert_score, 3),
            "event_timestamp": event.timestamp,
            "triggered_at": alert.triggered_at,
            "recovery_window_seconds": event.recovery_window_seconds,
            "elapsed_seconds": event.elapsed_seconds,
            "location_label": str(address),
            "location": location_data,
            "nearest_hospital": nearest_hospital,
            "observed_signals": observed_signals,
            "timeline": [
                f"Event detected at {event.timestamp}.",
                f"Alert triggered at {alert.triggered_at}.",
                f"Recovery window: {event.recovery_window_seconds:.0f} seconds.",
                f"Elapsed before alert: {event.elapsed_seconds:.1f} seconds.",
            ],
            "uncertainty": uncertainty,
            "recommended_actions": recommended_actions,
        }

    def _summary_from_evidence(self, evidence: dict[str, Any]) -> str:
        event_type = str(evidence["event_type"]).replace("_", " ")
        combined_score = round(float(evidence["confidence"]) * 100)
        location = evidence["location_label"]
        return f"Critical health event detected: {event_type} at {location} with {combined_score}% combined alert score."

    def _structured_report_text(self, evidence: dict[str, Any]) -> str:
        event_type = str(evidence["event_type"]).replace("_", " ")
        combined_score = round(float(evidence["confidence"]) * 100)
        location = evidence["location_label"]
        hospital = evidence.get("nearest_hospital") or {}
        hospital_text = ""
        if hospital:
            hospital_text = f" Nearest listed hospital: {hospital.get('name', 'unknown')}."

        return (
            f"SentinelCare detected a critical health event classified as {event_type} "
            f"with a {combined_score}% combined alert score. Location payload: {location}."
            f"{hospital_text} The system observed body-motion evidence and recovery-window failure, "
            "but it cannot diagnose the medical cause. A responder should verify responsiveness, "
            "check breathing and injuries if trained, and use local emergency protocol."
        )

    def _call_ollama(self, evidence: dict[str, Any]) -> str:
        compact_evidence = {
            "trigger": str(evidence["event_type"]).replace("_", " "),
            "combined_alert_score_percent": round(float(evidence["confidence"]) * 100),
            "location": evidence["location_label"],
            "nearest_hospital": evidence["nearest_hospital"],
            "signals": evidence["observed_signals"][:5],
            "uncertainty": evidence["uncertainty"][:3],
        }
        prompt = (
            "Write a concise responder report in exactly 3 sentences. "
            "Do not diagnose or invent details. Include trigger, combined alert score, "
            "location, and uncertainty. Do not mention model confidence or rule confidence. "
            "Evidence JSON: "
            f"{json.dumps(compact_evidence, sort_keys=True)}"
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.2,
                "num_predict": 120,
            },
        }

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                chunks: list[str] = []
                for line in resp:
                    if not line.strip():
                        continue

                    data = json.loads(line.decode("utf-8"))
                    response_part = data.get("response")
                    if isinstance(response_part, str):
                        chunks.append(response_part)
                    if data.get("done"):
                        break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama API error {exc.code}: {body[:300]}") from exc

        return "".join(chunks).strip()
