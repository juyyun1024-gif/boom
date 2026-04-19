"use client";

import { useState } from "react";

interface LiveFeedProps {
  frame: string | null;
  poseDetected: boolean;
  connected: boolean;
  numPeople: number;
}

export default function LiveFeed({ frame, poseDetected, connected, numPeople }: LiveFeedProps) {
  const [isPaused, setIsPaused] = useState(false);

  return (
    <div className="glass-card overflow-hidden flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              connected ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.6)]" : "bg-red-400"
            }`}
          />
          <span className="text-sm font-semibold text-slate-300 tracking-wide uppercase">
            Live Feed
          </span>
          {/* LIVE indicator */}
          {connected && !isPaused && (
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/20 border border-red-500/30">
              <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              <span className="text-[10px] font-semibold text-red-400 uppercase">Live</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* AI Processing indicator */}
          {poseDetected && connected && (
            <span className="flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              AI Active
            </span>
          )}
          {poseDetected && (
            <div className="stat-pill !bg-emerald-500/10 !border-emerald-500/20">
              <svg className="w-3 h-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span className="text-emerald-400 font-medium">
                {numPeople} {numPeople === 1 ? "Person" : "People"}
              </span>
            </div>
          )}
          <div className="stat-pill">
            <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
            <span className="text-slate-400">CAM-01</span>
          </div>
        </div>
      </div>

      {/* Video area */}
      <div className="relative flex-1 bg-black/50 flex items-center justify-center min-h-[300px]">
        {isPaused ? (
          <div className="flex flex-col items-center gap-4 text-slate-400">
            <div className="w-20 h-20 rounded-full bg-amber-500/20 flex items-center justify-center">
              <svg className="w-10 h-10 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-amber-400">Privacy Mode Active</p>
              <p className="text-xs text-slate-500 mt-1">Monitoring paused for privacy</p>
            </div>
            <button
              onClick={() => setIsPaused(false)}
              className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-sm font-medium transition-colors"
            >
              Resume Monitoring
            </button>
          </div>
        ) : frame ? (
          <div className="relative w-full h-full">
            <img
              src={`data:image/jpeg;base64,${frame}`}
              alt="Live camera feed with pose overlay"
              className="w-full h-full object-contain"
              style={{ imageRendering: "auto" }}
            />
            {/* Subtle scanline overlay */}
            <div className="absolute inset-0 scanline-overlay" />
            
            {/* Privacy Mode Toggle */}
            <div className="absolute top-2 right-2">
              <button
                onClick={() => setIsPaused(true)}
                className="p-1.5 rounded-lg transition-colors bg-slate-700/50 text-slate-400 hover:bg-slate-600/50 hover:text-slate-300"
                title="Pause monitoring (Privacy mode)"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4 text-slate-600">
            <div className="w-16 h-16 rounded-2xl bg-slate-800/50 flex items-center justify-center">
              <svg className="w-8 h-8 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-slate-500">
                {connected ? "Waiting for stream..." : "Connecting..."}
              </p>
              <p className="text-xs text-slate-600 mt-1">
                {connected ? "Video feed will appear shortly" : "Establishing backend connection"}
              </p>
            </div>
          </div>
        )}

        {/* Disconnected overlay */}
        {!connected && (
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <svg className="w-6 h-6 text-amber-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor"
                  d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              <span className="text-sm font-medium text-amber-400/90">Reconnecting</span>
            </div>
          </div>
        )}

        {/* Corner decorations */}
        <div className="absolute top-3 left-3 w-4 h-4 border-l-2 border-t-2 border-cyan-500/20 rounded-tl" />
        <div className="absolute top-3 right-3 w-4 h-4 border-r-2 border-t-2 border-cyan-500/20 rounded-tr" />
        <div className="absolute bottom-3 left-3 w-4 h-4 border-l-2 border-b-2 border-cyan-500/20 rounded-bl" />
        <div className="absolute bottom-3 right-3 w-4 h-4 border-r-2 border-b-2 border-cyan-500/20 rounded-br" />
        
        {/* Bottom overlay: monitoring indicators */}
        {connected && !isPaused && (
          <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              {/* Edge processing badge */}
              <span className="flex items-center gap-1 px-2 py-1 rounded-lg bg-black/60 backdrop-blur-sm text-[10px] font-medium text-emerald-400">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                Local Processing
              </span>
              {/* No recording badge */}
              <span className="flex items-center gap-1 px-2 py-1 rounded-lg bg-black/60 backdrop-blur-sm text-[10px] font-medium text-emerald-400">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                </svg>
                Not Recording
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}