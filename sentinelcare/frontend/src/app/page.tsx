"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useWebSocket } from "@/hooks/useWebSocket";
import LiveFeed from "@/components/LiveFeed";
import StatusBadge from "@/components/StatusBadge";
import AgentCard from "@/components/AgentCard";
import RecoveryTimer from "@/components/RecoveryTimer";
import AlertPanel from "@/components/AlertPanel";
import EventLog from "@/components/EventLog";
import FutureAgents from "@/components/FutureAgents";
import ConsentModal from "@/components/ConsentModal";
import PrivacyStatus from "@/components/PrivacyStatus";
import SecurityStatus from "@/components/SecurityStatus";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<{ id: string; email?: string } | null>(null);
  const [showConsent, setShowConsent] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const {
    connected,
    frame,
    agentState,
    events,
    latestAlert,
    poseDetected,
    numPeople,
    sendMessage,
  } = useWebSocket(WS_URL);

  // Check authentication and consent status
  useEffect(() => {
    const supabase = createClient();

    const checkAuth = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      
      if (!user) {
        router.push("/auth/login");
        return;
      }

      setUser({ id: user.id, email: user.email });

      // Check if user has given consent
      const { data: consent } = await supabase
        .from("user_consent")
        .select("consent_given")
        .eq("user_id", user.id)
        .single();

      if (!consent?.consent_given) {
        setShowConsent(true);
      }

      setConsentChecked(true);
      setIsLoading(false);
    };

    checkAuth();
  }, [router]);

  const handleLogout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/auth/login");
    router.refresh();
  };

  const handleAcknowledge = () => {
    sendMessage({ type: "reset_agent" });
  };

  const handleConsentGiven = () => {
    setShowConsent(false);
  };

  // Show loading while checking auth
  if (isLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-400">
          <svg className="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <span>Loading dashboard...</span>
        </div>
      </main>
    );
  }

  return (
    <>
      {/* Consent Modal */}
      {showConsent && user && consentChecked && (
        <ConsentModal userId={user.id} onConsentGiven={handleConsentGiven} />
      )}

      <main className="flex-1 flex flex-col p-4 gap-4 max-w-[1920px] mx-auto w-full">
        {/* Header */}
        <header className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            {/* Logo */}
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">
                Sentinel<span className="text-cyan-400">Care</span>
              </h1>
              <p className="text-xs text-slate-500">AI Home Safety Monitor</p>
            </div>
          </div>

          {/* User Controls */}
          <div className="flex items-center gap-4">
            {/* Privacy Status Indicators */}
            <div className="hidden md:block">
              <PrivacyStatus connected={connected} />
            </div>

            {/* User Menu */}
            <div className="flex items-center gap-3">
              <div className="text-right hidden sm:block">
                <p className="text-sm text-slate-300 truncate max-w-[180px]">{user?.email}</p>
                <p className="text-xs text-slate-500">Authenticated</p>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 rounded-lg bg-slate-800/50 hover:bg-slate-700/50 text-slate-400 hover:text-white transition-colors"
                title="Sign out"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </button>
            </div>
          </div>
        </header>

        {/* Connection status pill */}
        <div className="stat-pill">
          <div className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.5)]" : "bg-red-400 animate-pulse"}`} />
          <span className={`text-[11px] ${connected ? "text-slate-400" : "text-red-400"}`}>
            {connected ? "Live" : "Offline"}
          </span>
        </div>

      {/* Main grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-5 min-h-0">
        {/* Left: Live feed */}
        <div className="lg:col-span-8 flex flex-col min-h-[420px]">
          <LiveFeed frame={frame} poseDetected={poseDetected} connected={connected} numPeople={numPeople} />
        </div>

        {/* Right sidebar */}
        <div className="lg:col-span-4 flex flex-col gap-4 min-h-0 overflow-y-auto pr-0.5">
          <StatusBadge agentState={agentState} />
          <AgentCard agentState={agentState} poseDetected={poseDetected} />
          <RecoveryTimer agentState={agentState} />
          <AlertPanel alert={latestAlert} onAcknowledge={handleAcknowledge} />
          <FutureAgents />
        </div>
      </div>

      {/* Bottom: Event Log */}
      <div className="h-[200px] shrink-0">
        <EventLog events={events} />
      </div>
      </main>
    </>
  );
}
