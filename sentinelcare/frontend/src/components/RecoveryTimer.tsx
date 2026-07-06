import type { AgentState } from "@/hooks/useWebSocket";

interface RecoveryTimerProps {
  agentState: AgentState;
}

export default function RecoveryTimer({ agentState }: RecoveryTimerProps) {
  const { timer_active, timer_remaining, timer_total } = agentState;

  if (!timer_active && agentState.state !== "monitoring_recovery") {
    return null;
  }

  const pct = timer_total > 0 ? (timer_remaining / timer_total) * 100 : 0;
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const strokeOffset = circumference * (1 - pct / 100);
  const isUrgent = timer_remaining < timer_total * 0.3;

  const strokeColor = isUrgent ? "#ef4444" : timer_remaining < timer_total * 0.6 ? "#f59e0b" : "#10b981";
  const glowColor = isUrgent ? "rgba(239,68,68,0.25)" : timer_remaining < timer_total * 0.6 ? "rgba(245,158,11,0.2)" : "rgba(16,185,129,0.2)";

  return (
    <div className={`glass-card p-5 flex flex-col items-center animate-slide-up ${isUrgent ? "timer-urgent border-red-500/30" : ""}`}>
      <h3 className="section-label mb-4">{agentState.agent_name} Recovery</h3>

      {/* Circular timer */}
      <div className="relative w-28 h-28 mb-3">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 112 112">
          {/* Background ring */}
          <circle
            cx="56" cy="56" r={radius}
            fill="none"
            stroke="rgba(100,116,139,0.1)"
            strokeWidth="6"
          />
          {/* Progress ring */}
          <circle
            cx="56" cy="56" r={radius}
            fill="none"
            stroke={strokeColor}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeOffset}
            style={{
              transition: "stroke-dashoffset 0.3s ease, stroke 0.5s ease",
              filter: `drop-shadow(0 0 8px ${glowColor})`,
            }}
          />
        </svg>

        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="text-2xl font-bold font-mono tabular-nums leading-none"
            style={{ color: strokeColor }}
          >
            {timer_remaining.toFixed(1)}
          </span>
          <span className="text-[10px] text-slate-500 mt-1 uppercase tracking-wider">seconds</span>
        </div>
      </div>

      <p className={`text-[11px] text-center leading-relaxed ${isUrgent ? "text-red-400 font-medium" : "text-slate-500"}`}>
        {isUrgent
          ? "No recovery detected — escalating soon"
          : agentState.agent_name === "Seizure"
          ? "Monitoring for rhythmic motion to stop..."
          : "Monitoring for recovery movement..."}
      </p>
    </div>
  );
}
