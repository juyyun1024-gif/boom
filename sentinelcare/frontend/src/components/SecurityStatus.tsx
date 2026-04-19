"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

interface SecurityStatusProps {
  connected: boolean;
}

export default function SecurityStatus({ connected }: SecurityStatusProps) {
  const [user, setUser] = useState<{ email?: string } | null>(null);
  const [lastLogin, setLastLogin] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();
    
    const getUser = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (user) {
        setUser({ email: user.email });
        setLastLogin(user.last_sign_in_at || null);
      }
    };
    
    getUser();
  }, []);

  const formatLastLogin = (dateStr: string | null) => {
    if (!dateStr) return "Unknown";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="glass-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <path d="M12 15.5l-3.5-3.1a2.4 2.4 0 0 1-.7-1.8c0-1.3 1.1-2.4 2.5-2.4.7 0 1.3.3 1.7.7.4-.4 1-.7 1.7-.7 1.4 0 2.5 1.1 2.5 2.4 0 .7-.3 1.3-.7 1.8L12 15.5z" fill="currentColor" stroke="none" />
        </svg>
        <span className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Security Status</span>
      </div>

      <div className="space-y-3">
        {/* Connection Status */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">Connection</span>
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg ${
            connected ? "bg-emerald-500/10" : "bg-red-500/10"
          }`}>
            <div className={`w-1.5 h-1.5 rounded-full ${
              connected ? "bg-emerald-400" : "bg-red-400"
            }`} />
            <span className={`text-xs font-medium ${
              connected ? "text-emerald-400" : "text-red-400"
            }`}>
              {connected ? "Secure" : "Disconnected"}
            </span>
          </div>
        </div>

        {/* Authentication Status */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">Authenticated</span>
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-lg ${
            user ? "bg-emerald-500/10" : "bg-amber-500/10"
          }`}>
            <div className={`w-1.5 h-1.5 rounded-full ${
              user ? "bg-emerald-400" : "bg-amber-400"
            }`} />
            <span className={`text-xs font-medium ${
              user ? "text-emerald-400" : "text-amber-400"
            }`}>
              {user ? "Yes" : "No"}
            </span>
          </div>
        </div>

        {/* Last Login */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">Last Login</span>
          <span className="text-xs text-slate-400">{formatLastLogin(lastLogin)}</span>
        </div>

        {/* User Email */}
        {user?.email && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">Account</span>
            <span className="text-xs text-slate-400 truncate max-w-[150px]">{user.email}</span>
          </div>
        )}

        {/* Data Protection Badges */}
        <div className="pt-2 border-t border-white/5">
          <div className="flex flex-wrap gap-1.5">
            <span className="px-2 py-0.5 text-[10px] font-medium rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              AES-256
            </span>
            <span className="px-2 py-0.5 text-[10px] font-medium rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              TLS 1.3
            </span>
            <span className="px-2 py-0.5 text-[10px] font-medium rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              JWT Auth
            </span>
          </div>
        </div>

        {/* Data Retention Policy */}
        <div className="pt-2 border-t border-white/5">
          <div className="flex items-center gap-2 mb-2">
            <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Data Retention</span>
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-slate-500">Video frames</span>
              <span className="text-[10px] text-emerald-400 font-medium">Never stored</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-slate-500">Pose data</span>
              <span className="text-[10px] text-amber-400 font-medium">In-memory only</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-slate-500">Event logs</span>
              <span className="text-[10px] text-slate-400 font-medium">30 days</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-slate-500">Consent history</span>
              <span className="text-[10px] text-slate-400 font-medium">90 days</span>
            </div>
          </div>
          <p className="mt-2 text-[9px] text-slate-600 leading-relaxed">
            Data is automatically purged after retention period. You can request immediate deletion at any time.
          </p>
        </div>
      </div>
    </div>
  );
}
