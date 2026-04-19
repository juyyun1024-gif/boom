"use client";

import type { AgentState } from "@/hooks/useWebSocket";

interface AgentCardProps {
  agentState: AgentState;
  poseDetected: boolean;
}

export default function AgentCard({ agentState, poseDetected }: AgentCardProps) {
  const confidencePct = Math.round(agentState.confidence * 100);
  const isAvailable = agentState.available !== false; // Default to true if not specified

  // Agent-specific configuration
  const agentConfig = {
    Fall: {
      title: "Fall Agent",
      description: "Fall / Collapse Detection",
      icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
      confidenceLabel: "Fall Confidence"
    },
    Seizure: {
      title: "Seizure Agent",
      description: "Seizure / Repetitive Motion Detection",
      icon: "M13 10V3L4 14h7v7l9-11h-7z",
      confidenceLabel: "Repetition Score"
    },
    Stroke: {
      title: "Stroke Agent", 
      description: "Stroke / Asymmetric Motion Detection",
      icon: "M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z",
      confidenceLabel: "Asymmetry Score"
    },
    Wandering: {
      title: "Wandering Agent",
      description: "Wandering / Boundary Detection", 
      icon: "M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
      confidenceLabel: "Detection Score"
    }
  };

  const config = agentConfig[agentState.agent_name as keyof typeof agentConfig] || agentConfig.Fall;

  // Confidence bar color
  const barColor =
    confidencePct >= 70
      ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.3)]"
      : confidencePct >= 40
      ? "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.3)]"
      : "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.3)]";

  const barBg =
    confidencePct >= 70
      ? "bg-red-500/10"
      : confidencePct >= 40
      ? "bg-amber-500/10"
      : "bg-emerald-500/10";

  const lastChange = new Date(agentState.last_change);
  const timeAgo = Math.round((Date.now() - lastChange.getTime()) / 1000);
  const timeLabel = timeAgo < 60 ? `${timeAgo}s ago` : `${Math.floor(timeAgo / 60)}m ago`;

  // Unavailable agent styling
  if (!isAvailable) {
    return (
      <div className="glass-card p-4 opacity-60 relative overflow-hidden">
        {/* Unavailable overlay */}
        <div className="absolute top-2 right-2 z-10">
          <span className="text-[10px] px-2 py-1 rounded-full font-semibold bg-slate-700/80 text-slate-400 border border-slate-600/50">
            UNAVAILABLE
          </span>
        </div>
        
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-slate-800/40 border border-slate-700/30 flex items-center justify-center">
              <svg className="w-4 h-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={config.icon} />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-400 leading-none">{config.title}</h3>
              <p className="text-[11px] text-slate-600 mt-0.5">{config.description}</p>
            </div>
          </div>
        </div>

        {/* Summary message */}
        <div className="bg-slate-800/30 rounded-lg px-3 py-2 border border-slate-700/20">
          <p className="text-[11px] text-slate-500 italic">{agentState.summary}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-4">
      <div className="flex items-start justify-between mb-4 gap-2">
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-500/20 border border-cyan-500/10 flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={config.icon} />
            </svg>
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-slate-200 leading-none">{config.title}</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">{config.description}</p>
          </div>
        </div>
        <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap flex-shrink-0 ${
          poseDetected
            ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
            : "bg-slate-800/60 text-slate-500 border border-slate-700/30"
        }`}>
          {poseDetected ? "Active" : "No Subject"}
        </span>
      </div>

      {/* Confidence bar */}
      <div className="mb-4">
        <div className="flex justify-between text-[11px] mb-1.5">
          <span className="text-slate-500 font-medium">{config.confidenceLabel}</span>
          <span className="text-slate-300 font-mono font-semibold">{confidencePct}%</span>
        </div>
        <div className={`h-1.5 ${barBg} rounded-full overflow-hidden`}>
          <div
            className={`h-full ${barColor} rounded-full transition-all duration-700 ease-out`}
            style={{ width: `${confidencePct}%` }}
          />
        </div>
      </div>

      {/* Meta grid */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-slate-800/40 rounded-xl px-3 py-2 border border-slate-700/20">
          <span className="text-[10px] text-slate-500 block font-medium uppercase tracking-wider">State</span>
          <span className="text-[13px] text-slate-300 font-medium capitalize mt-0.5 block">
            {agentState.state.replace(/_/g, " ")}
          </span>
        </div>
        <div className="bg-slate-800/40 rounded-xl px-3 py-2 border border-slate-700/20">
          <span className="text-[10px] text-slate-500 block font-medium uppercase tracking-wider">Changed</span>
          <span className="text-[13px] text-slate-300 font-mono font-medium mt-0.5 block">{timeLabel}</span>
        </div>
      </div>
    </div>
  );
}
