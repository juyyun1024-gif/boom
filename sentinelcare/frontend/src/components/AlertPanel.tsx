"use client";

import { useEffect, useState } from "react";
import type { AlertData } from "@/hooks/useWebSocket";

interface Hospital {
  name: string;
  address: string;
  distance: number;
  latitude: number;
  longitude: number;
  rating?: number;
}

interface AlertPanelProps {
  alert: AlertData | null;
  onAcknowledge?: () => void;
}

export default function AlertPanel({ alert, onAcknowledge }: AlertPanelProps) {
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [loadingHospitals, setLoadingHospitals] = useState(false);
  const [isMockData, setIsMockData] = useState(false);

  useEffect(() => {
    if (!alert) return;
    setLoadingHospitals(true);
    setHospitals([]);

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await fetch("/api/nearby-hospitals", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
          });
          const data = await res.json();
          setHospitals(data.hospitals || []);
          setIsMockData(data.isMockData || false);
        } catch { /* silently fail */ }
        finally { setLoadingHospitals(false); }
      },
      () => setLoadingHospitals(false),
      { timeout: 10000, maximumAge: 300000 }
    );
  }, [alert?.alert_id]);

  if (!alert) return null;

  const { event } = alert;
  const ts = new Date(event.timestamp);
  const timeStr = ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <div className="glass-card border-red-500/30 bg-red-500/[0.06] p-4 animate-slide-up">
      {/* Header */}
      <div className="flex items-center gap-2.5 mb-3">
        <div className="w-8 h-8 rounded-lg bg-red-500/20 border border-red-500/20 flex items-center justify-center">
          <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-bold text-red-400 leading-none">Critical Alert</h3>
          <p className="text-[11px] text-red-300/50 mt-0.5 font-mono">{timeStr}</p>
        </div>
        <div className="w-2 h-2 rounded-full bg-red-500 pulse-alert" />
      </div>

      {/* Summary */}
      <p className="text-[13px] text-slate-300 mb-3 leading-relaxed">{event.summary}</p>

      {/* Details grid */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="bg-black/20 rounded-xl px-3 py-2 border border-red-500/10">
          <span className="text-[10px] text-slate-500 block uppercase tracking-wider">Type</span>
          <span className="text-[12px] text-slate-200 font-medium capitalize mt-0.5 block">{event.event_type.replace(/_/g, " ")}</span>
        </div>
        <div className="bg-black/20 rounded-xl px-3 py-2 border border-red-500/10">
          <span className="text-[10px] text-slate-500 block uppercase tracking-wider">Confidence</span>
          <span className="text-[12px] text-slate-200 font-mono font-semibold mt-0.5 block">{Math.round(event.confidence * 100)}%</span>
        </div>
        <div className="bg-black/20 rounded-xl px-3 py-2 border border-red-500/10">
          <span className="text-[10px] text-slate-500 block uppercase tracking-wider">Location</span>
          <span className="text-[12px] text-slate-200 font-medium mt-0.5 block">{event.location}</span>
        </div>
        <div className="bg-black/20 rounded-xl px-3 py-2 border border-red-500/10">
          <span className="text-[10px] text-slate-500 block uppercase tracking-wider">Elapsed</span>
          <span className="text-[12px] text-slate-200 font-mono font-semibold mt-0.5 block">{event.elapsed_seconds}s</span>
        </div>
      </div>

      {/* Recommended action */}
      {event.recommended_action && (
        <div className="bg-red-500/[0.06] border border-red-500/15 rounded-xl px-3 py-2.5 mb-3">
          <span className="text-[10px] text-red-300/50 block uppercase tracking-wider mb-0.5">Recommended Action</span>
          <span className="text-[13px] text-red-300 font-medium">{event.recommended_action}</span>
        </div>
      )}

      {/* Nearest Hospitals */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">Nearest Hospitals</span>
          {isMockData && <span className="text-[9px] text-slate-600 italic">demo data</span>}
        </div>
        {loadingHospitals ? (
          <div className="space-y-1.5">
            {[1,2,3].map(i => <div key={i} className="h-10 bg-slate-800/40 rounded-lg animate-pulse" />)}
          </div>
        ) : hospitals.length > 0 ? (
          <div className="space-y-1.5">
            {hospitals.map((h, i) => (
              <a
                key={i}
                href={`https://www.google.com/maps/dir/?api=1&destination=${h.latitude},${h.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between bg-slate-800/40 hover:bg-slate-700/40 border border-slate-700/30 rounded-lg px-3 py-2 transition-colors"
              >
                <div className="min-w-0">
                  <p className="text-[12px] text-slate-200 font-medium truncate">{h.name}</p>
                  <p className="text-[10px] text-slate-500 truncate">{h.address}</p>
                </div>
                <div className="text-right flex-shrink-0 ml-2">
                  <p className="text-[11px] text-cyan-400 font-mono">{h.distance} mi</p>
                  {h.rating && <p className="text-[10px] text-slate-500">★ {h.rating}</p>}
                </div>
              </a>
            ))}
          </div>
        ) : (
          <p className="text-[11px] text-slate-500 italic">Unable to load hospitals. Call 911 immediately.</p>
        )}
      </div>

      {onAcknowledge && (
        <button
          onClick={onAcknowledge}
          className="w-full py-2 px-4 bg-red-500/15 hover:bg-red-500/25 border border-red-500/25 hover:border-red-500/40 rounded-xl text-sm font-medium text-red-300 transition-all duration-200 cursor-pointer active:scale-[0.98]"
        >
          Acknowledge Alert
        </button>
      )}
    </div>
  );
}
