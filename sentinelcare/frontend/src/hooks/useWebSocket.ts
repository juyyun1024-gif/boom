"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// ---- Types matching backend models ----

export interface AgentState {
  agent_name: string;  // NEW: identifies which agent produced this state
  state: "normal" | "suspicious_event" | "monitoring_recovery" | "recovered" | "critical_alert";
  confidence: number;
  event_type: string;
  timer_active: boolean;
  timer_remaining: number;
  timer_total: number;
  last_change: string;
  summary: string;
  available?: boolean;  // NEW: indicates if agent is currently active (defaults to true)
  ai_enabled?: boolean;
  model_source?: string;
  model_status?: string;
  model_confidence?: number;
  rule_confidence?: number;
  pose_quality?: number;
  pose_reliable?: boolean;
  visibility_reason?: string;
  recovery_gesture_score?: number;
  recovery_gesture_detected?: boolean;
}

export interface PoseFeatures {
  body_centroid_y: number;
  torso_angle: number;
  head_height: number;
  hip_height: number;
  velocity: number;
  motion_energy: number;
  stillness_score: number;
  ground_proximity: number;
  pose_quality?: number;
  pose_reliable?: boolean;
  visibility_reason?: string;
  visible_keypoints?: number;
  recovery_gesture_score?: number;
  recovery_gesture_detected?: boolean;
}

export interface HealthEventReport {
  report_id: string;
  generated_at: string;
  alert_id: string;
  event_id: string;
  source: "structured" | "llm" | string;
  model: string;
  risk_level: string;
  confidence: number;
  location_label: string;
  location: Record<string, unknown>;
  nearest_hospital?: Record<string, unknown> | null;
  summary: string;
  responder_report: string;
  observed_signals: string[];
  timeline: string[];
  uncertainty: string[];
  recommended_actions: string[];
}

export interface EventData {
  event_id: string;
  timestamp: string;
  agent: string;
  event_type: string;
  status: string;
  confidence: number;
  location: string;
  recovery_window_seconds: number;
  elapsed_seconds: number;
  summary: string;
  recommended_action: string;
  video_source: string;
  health_report?: HealthEventReport | null;
}

export interface AlertData {
  alert_id: string;
  event: EventData;
  triggered_at: string;
  acknowledged: boolean;
  health_report?: HealthEventReport | null;
}

export interface WSMessage {
  type: string;
  frame?: string;
  agent_state?: AgentState;  // Backward compatibility: single agent state
  agents?: AgentState[];     // NEW: multi-agent support
  features?: PoseFeatures;
  event?: EventData;
  alert?: AlertData;
  health_report?: HealthEventReport | null;
  pose_detected?: boolean;
  num_people?: number;
  agent?: string;
  enabled?: boolean;
}

// ---- Hook ----

export function useWebSocket(url: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<(() => void) | null>(null);

  const [connected, setConnected] = useState(false);
  const [frame, setFrame] = useState<string | null>(null);
  const [agentState, setAgentState] = useState<AgentState>({
    agent_name: "FallGuard",
    state: "normal",
    confidence: 0,
    event_type: "none",
    timer_active: false,
    timer_remaining: 0,
    timer_total: 10,
    last_change: new Date().toISOString(),
    summary: "Waiting for connection...",
  });
  const [agents, setAgents] = useState<AgentState[]>([]);  // NEW: all agent states
  const [features, setFeatures] = useState<PoseFeatures | null>(null);
  const [events, setEvents] = useState<EventData[]>([]);
  const [latestAlert, setLatestAlert] = useState<AlertData | null>(null);
  const [latestHealthReport, setLatestHealthReport] = useState<HealthEventReport | null>(null);
  const [poseDetected, setPoseDetected] = useState(false);
  const [numPeople, setNumPeople] = useState(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.log("[WS] Connected");
    };

    ws.onmessage = (evt) => {
      try {
        const msg: WSMessage = JSON.parse(evt.data);

        if (msg.frame) setFrame(msg.frame);
        if (msg.agents) {
          setAgents(msg.agents);  // NEW: handle multi-agent states
          const primary =
            msg.agents.find((agent) => agent.state === "critical_alert") ??
            msg.agents.find((agent) => agent.state === "monitoring_recovery") ??
            msg.agents.find((agent) => agent.state === "suspicious_event") ??
            msg.agents.find((agent) => agent.agent_name === "FallGuard") ??
            msg.agent_state ??
            msg.agents[0];
          if (primary) setAgentState(primary);
        } else if (msg.agent_state) {
          setAgentState(msg.agent_state);
        }
        if (msg.features) setFeatures(msg.features);
        if (msg.pose_detected !== undefined) setPoseDetected(msg.pose_detected);
        if (msg.num_people !== undefined) setNumPeople(msg.num_people);

        if (msg.event) {
          setEvents((prev) => [msg.event!, ...prev].slice(0, 100));
        }

        if (msg.alert) {
          setLatestAlert(msg.alert);
          setLatestHealthReport(
            msg.health_report ??
            msg.alert.health_report ??
            msg.alert.event.health_report ??
            null
          );
        } else if (msg.health_report) {
          setLatestHealthReport(msg.health_report);
        } else if (msg.agents && !msg.agents.some((agent) => agent.state === "critical_alert")) {
          setLatestAlert(null);
          setLatestHealthReport(null);
        }

        // Handle agent toggle response
        if (msg.type === "agent_toggled") {
          console.log(`Agent ${msg.agent} toggled to ${msg.enabled}`);
        }
      } catch (e) {
        console.warn("[WS] Parse error:", e);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log("[WS] Disconnected — reconnecting in 2s");
      reconnectTimer.current = setTimeout(() => connectRef.current?.(), 2000);
    };

    ws.onerror = (err) => {
      console.warn("[WS] Error:", err);
      ws.close();
    };
  }, [url]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendMessage = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
      
      // Clear alert when reset_agent message is sent
      if (msg.type === "reset_agent") {
        setLatestAlert(null);
        setLatestHealthReport(null);
      }
    }
  }, []);

  return {
    connected,
    frame,
    agentState,
    agents,  // NEW: expose all agent states
    features,
    events,
    latestAlert,
    latestHealthReport,
    poseDetected,
    numPeople,
    sendMessage,
  };
}
