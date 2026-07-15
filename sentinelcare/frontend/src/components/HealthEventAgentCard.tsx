"use client";

import type { AgentState } from "@/hooks/useWebSocket";

interface HealthEventAgentCardProps {
  agents: AgentState[];
  fallbackState: AgentState;
  poseDetected: boolean;
  enabled: boolean;
}

const HEALTH_EVENT_AGENT_NAMES = new Set(["FallGuard", "Seizure"]);
const STATE_PRIORITY: AgentState["state"][] = [
  "critical_alert",
  "monitoring_recovery",
  "suspicious_event",
  "recovered",
  "normal",
];

function scorePct(value: number | undefined): number {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value * 100)));
}

function maxScorePct(values: Array<number | undefined>): number {
  return values.reduce<number>((max, value) => Math.max(max, scorePct(value)), 0);
}

function stateRiskPct(agent: AgentState): number {
  switch (agent.state) {
    case "critical_alert":
    case "monitoring_recovery":
    case "suspicious_event":
      return scorePct(agent.confidence);
    case "recovered":
    case "normal":
    default:
      return 0;
  }
}

function pickPrimaryAgent(agents: AgentState[]): AgentState {
  for (const state of STATE_PRIORITY) {
    const match = agents.find((agent) => agent.state === state);
    if (match) return match;
  }

  return agents[0];
}

function getTimeLabel(timestamp: string): string {
  const changedAt = new Date(timestamp);
  const elapsedSeconds = Math.max(0, Math.round((Date.now() - changedAt.getTime()) / 1000));
  return elapsedSeconds < 60 ? `${elapsedSeconds}s ago` : `${Math.floor(elapsedSeconds / 60)}m ago`;
}

function getSummary(
  primary: AgentState,
  enabled: boolean,
  poseDetected: boolean,
  poseReliable: boolean
): string {
  if (!enabled) return "Health Event Agent is disabled.";
  if (!poseDetected) return "Waiting for a visible body view.";
  if (!poseReliable) return "Pose or camera view is unreliable. Monitoring is limited.";

  switch (primary.state) {
    case "critical_alert":
      return "Critical health event. Immediate attention required.";
    case "monitoring_recovery":
      return "Possible health event detected. Recovery window active.";
    case "suspicious_event":
      return "Body emergency pattern detected. Evaluating recovery signals.";
    case "recovered":
      return "Recovery detected. Returning to normal monitoring.";
    case "normal":
    default:
      return "Monitoring body-related health events. No emergency pattern detected.";
  }
}

export default function HealthEventAgentCard({
  agents,
  fallbackState,
  poseDetected,
  enabled,
}: HealthEventAgentCardProps) {
  const sourceAgents = agents.length > 0 ? agents : [fallbackState];
  const healthAgents = sourceAgents.filter((agent) => HEALTH_EVENT_AGENT_NAMES.has(agent.agent_name));
  const visibleAgents = healthAgents.length > 0 ? healthAgents : [fallbackState];
  const activeAgents = visibleAgents.filter((agent) => agent.available !== false);
  const signalAgents = activeAgents.length > 0 ? activeAgents : visibleAgents;
  const primary = pickPrimaryAgent(signalAgents);

  const collapseAgent = signalAgents.find((agent) => agent.agent_name === "FallGuard");
  const rhythmAgent = signalAgents.find((agent) => agent.agent_name === "Seizure");
  const aiEnabled = signalAgents.some((agent) => agent.ai_enabled === true);

  const overallRiskPct = signalAgents.reduce((max, agent) => Math.max(max, stateRiskPct(agent)), 0);
  const collapsePct = maxScorePct([
    collapseAgent?.confidence,
    collapseAgent?.model_confidence,
    collapseAgent?.rule_confidence,
  ]);
  const rhythmPct = maxScorePct([rhythmAgent?.confidence, rhythmAgent?.rule_confidence]);
  const poseQualityPct = maxScorePct(signalAgents.map((agent) => agent.pose_quality));

  const poseReliable = signalAgents.every((agent) => agent.pose_reliable !== false);
  const visibilityReason =
    signalAgents.find((agent) => agent.visibility_reason && agent.visibility_reason !== "unknown")
      ?.visibility_reason ?? "ok";
  const poseDegraded = poseReliable && visibilityReason !== "ok" && visibilityReason !== "unknown";

  const statusLabel = !enabled
    ? "Disabled"
    : !poseDetected
    ? "No Subject"
    : poseDegraded
    ? "Partial"
    : poseReliable
    ? "Active"
    : "Pose Poor";

  const statusClass = !enabled
    ? "bg-slate-800/60 text-slate-500 border border-slate-700/30"
    : !poseDetected
    ? "bg-slate-800/60 text-slate-500 border border-slate-700/30"
    : poseDegraded
    ? "bg-amber-500/15 text-amber-300 border border-amber-500/20"
    : poseReliable
    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
    : "bg-rose-500/15 text-rose-300 border border-rose-500/20";

  const barColor =
    overallRiskPct >= 70
      ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.3)]"
      : overallRiskPct >= 40
      ? "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.3)]"
      : "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]";

  const barBg =
    overallRiskPct >= 70
      ? "bg-red-500/10"
      : overallRiskPct >= 40
      ? "bg-amber-500/10"
      : "bg-emerald-500/10";

  const modelStatus =
    signalAgents.find((agent) => agent.model_status && agent.model_status !== "rules")?.model_status ??
    primary.model_status ??
    "monitoring";
  const timeLabel = getTimeLabel(primary.last_change);
  const summary = getSummary(primary, enabled, poseDetected, poseReliable);

  return (
    <div className="glass-card p-4">
      <div className="flex items-start justify-between mb-4 gap-2">
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/10 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"
              />
              <path
                d="M12 15.5l-3.5-3.1a2.4 2.4 0 0 1-.7-1.8c0-1.3 1.1-2.4 2.5-2.4.7 0 1.3.3 1.7.7.4-.4 1-.7 1.7-.7 1.4 0 2.5 1.1 2.5 2.4 0 .7-.3 1.3-.7 1.8L12 15.5z"
                fill="currentColor"
                stroke="none"
              />
            </svg>
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-slate-200 leading-none">Health Event Agent</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">Body motion and recovery monitoring</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {aiEnabled && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold bg-cyan-500/15 text-cyan-300 border border-cyan-500/20">
              AI-assisted
            </span>
          )}
          <span
            title={visibilityReason.replace(/_/g, " ")}
            className={`text-[11px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${statusClass}`}
          >
            {statusLabel}
          </span>
        </div>
      </div>

      <div className="mb-4">
        <div className="flex justify-between text-[11px] mb-1.5">
          <span className="text-slate-500 font-medium">Health Event Risk</span>
          <span className="text-slate-300 font-mono font-semibold">{overallRiskPct}%</span>
        </div>
        <div className={`h-1.5 ${barBg} rounded-full overflow-hidden`}>
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-700 ease-out`}
            style={{ width: `${overallRiskPct}%` }}
          />
        </div>
      </div>

      <div className="mb-4 grid grid-cols-3 gap-2">
        <div className="bg-cyan-500/[0.06] rounded-lg px-2.5 py-2 border border-cyan-500/10">
          <span className="text-[9px] text-cyan-400/70 block font-medium uppercase tracking-wider">Collapse</span>
          <span className="text-[12px] text-cyan-200 font-mono font-semibold mt-0.5 block">{collapsePct}%</span>
        </div>
        <div className="bg-slate-800/40 rounded-lg px-2.5 py-2 border border-slate-700/20">
          <span className="text-[9px] text-slate-500 block font-medium uppercase tracking-wider">Rhythm</span>
          <span className="text-[12px] text-slate-300 font-mono font-semibold mt-0.5 block">{rhythmPct}%</span>
        </div>
        <div className="bg-slate-800/40 rounded-lg px-2.5 py-2 border border-slate-700/20">
          <span className="text-[9px] text-slate-500 block font-medium uppercase tracking-wider">Pose</span>
          <span className="text-[12px] text-slate-300 font-mono font-semibold mt-0.5 block">{poseQualityPct}%</span>
        </div>
      </div>

      <p className="text-[12px] text-slate-400 leading-relaxed mb-3">{summary}</p>

      <div className="grid grid-cols-2 gap-2">
        <div className="bg-slate-800/40 rounded-xl px-3 py-2 border border-slate-700/20">
          <span className="text-[10px] text-slate-500 block font-medium uppercase tracking-wider">State</span>
          <span className="text-[13px] text-slate-300 font-medium capitalize mt-0.5 block">
            {primary.state.replace(/_/g, " ")}
          </span>
        </div>
        <div className="bg-slate-800/40 rounded-xl px-3 py-2 border border-slate-700/20">
          <span className="text-[10px] text-slate-500 block font-medium uppercase tracking-wider">Changed</span>
          <span className="text-[13px] text-slate-300 font-mono font-medium mt-0.5 block">{timeLabel}</span>
        </div>
        <div className="bg-slate-800/40 rounded-xl px-3 py-2 border border-slate-700/20 col-span-2">
          <span className="text-[10px] text-slate-500 block font-medium uppercase tracking-wider">Signal Status</span>
          <span className="text-[13px] text-slate-300 font-medium mt-0.5 block truncate" title={modelStatus}>
            {modelStatus.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {primary.timer_active && (
        <div className="mt-2 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2">
          <div className="flex justify-between text-[11px] mb-1.5">
            <span className="text-amber-400 font-medium">Recovery Window</span>
            <span className="text-amber-300 font-mono font-semibold">{primary.timer_remaining.toFixed(1)}s</span>
          </div>
          <div className="h-1.5 bg-amber-500/20 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber-500 rounded-full transition-all duration-500"
              style={{ width: `${(primary.timer_remaining / primary.timer_total) * 100}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
