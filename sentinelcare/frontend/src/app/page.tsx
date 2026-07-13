"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useWebSocket, type HealthEventReport } from "@/hooks/useWebSocket";
import LiveFeed from "@/components/LiveFeed";
import StatusBadge from "@/components/StatusBadge";
import HealthEventAgentCard from "@/components/HealthEventAgentCard";
import RecoveryTimer from "@/components/RecoveryTimer";
import AlertPanel from "@/components/AlertPanel";
import EventLog from "@/components/EventLog";
import ConsentModal from "@/components/ConsentModal";
import PrivacyStatus from "@/components/PrivacyStatus";
import SecurityStatus from "@/components/SecurityStatus";
import AlertSettings from "@/components/AlertSettings";
import EmergencyAlertModal from "@/components/EmergencyAlertModal";
import { useUserSettings } from "@/hooks/useUserSettings";
import { useEmergencyContacts } from "@/hooks/useEmergencyContacts";
import { useUserLocation } from "@/hooks/useUserLocation";
import { useAlertDispatch } from "@/hooks/useAlertDispatch";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
const HEALTH_EVENT_AGENT_NAMES = ["FallGuard", "Seizure"];

export default function Dashboard() {
  const router = useRouter();
  const [user, setUser] = useState<{ id: string; email?: string } | null>(null);
  const [showConsent, setShowConsent] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [enabledAgents, setEnabledAgents] = useState<Set<string>>(
    new Set(HEALTH_EVENT_AGENT_NAMES)
  );
  const [showEmergencyModal, setShowEmergencyModal] = useState(false);
  const [emergencyAlertInfo, setEmergencyAlertInfo] = useState<{
    type: string;
    severity: string;
    timestamp: Date;
    healthReport: HealthEventReport | null;
  } | null>(null);
  const emergencyModalQueuedRef = useRef(false);

  const {
    connected,
    frame,
    agentState,
    agents,  // NEW: all agent states
    events,
    latestAlert,
    latestHealthReport,
    poseDetected,
    numPeople,
    sendMessage,
  } = useWebSocket(WS_URL);

  // User settings for privacy preferences
  const {
    settings,
    loading: settingsLoading,
    toggleRecording,
    togglePrivacyMode,
  } = useUserSettings();

  // Emergency contacts & location for auto-email alerts
  const { contacts } = useEmergencyContacts();
  const { location } = useUserLocation();
  const { syncAlertConfig, fetchNearestHospital } = useAlertDispatch();

  // Sync emergency contacts + location to backend for auto-email on critical alert
  useEffect(() => {
    if (!connected) return;

    const sync = async () => {
      let hospital = null;
      if (settings?.notify_nearest_hospital && location?.latitude && location?.longitude) {
        hospital = await fetchNearestHospital(
          Number(location.latitude),
          Number(location.longitude)
        );
      }
      await syncAlertConfig(contacts, location, hospital);
    };

    sync();
  }, [contacts, location, settings, connected, syncAlertConfig, fetchNearestHospital]);

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

  // Monitor for critical alerts
  useEffect(() => {
    const criticalAgent =
      agents.find((agent) => agent.state === "critical_alert") ??
      (agentState?.state === "critical_alert" ? agentState : null);

    if (!criticalAgent || showEmergencyModal || emergencyModalQueuedRef.current) {
      return;
    }

    const alertType =
      latestAlert?.event.event_type.replace(/_/g, " ") ??
      criticalAgent?.event_type.replace(/_/g, " ") ??
      "Critical Medical Event";
    const timestamp = latestAlert ? new Date(latestAlert.triggered_at) : new Date();
    const healthReport =
      latestHealthReport ??
      latestAlert?.health_report ??
      latestAlert?.event.health_report ??
      null;

    emergencyModalQueuedRef.current = true;
    const timeout = window.setTimeout(() => {
      setEmergencyAlertInfo({
        type: alertType,
        severity: "critical",
        timestamp,
        healthReport,
      });
      setShowEmergencyModal(true);
      emergencyModalQueuedRef.current = false;
    }, 0);

    return () => {
      window.clearTimeout(timeout);
      emergencyModalQueuedRef.current = false;
    };
  }, [agents, agentState, latestAlert, latestHealthReport, showEmergencyModal]);

  const handleCloseEmergencyModal = () => {
    setShowEmergencyModal(false);
    setEmergencyAlertInfo(null);
  };

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

  const toggleHealthEventAgent = () => {
    const nextEnabled = !HEALTH_EVENT_AGENT_NAMES.some((agentName) => enabledAgents.has(agentName));

    setEnabledAgents((prev) => {
      const updated = new Set(prev);

      HEALTH_EVENT_AGENT_NAMES.forEach((agentName) => {
        if (nextEnabled) {
          updated.add(agentName);
        } else {
          updated.delete(agentName);
        }

        sendMessage({
          type: "toggle_agent",
          agent: agentName,
          enabled: nextEnabled,
        });
      });

      return updated;
    });
  };

  const resetAllAgents = () => {
    setEnabledAgents(new Set(HEALTH_EVENT_AGENT_NAMES));
    
    // Send enable message for each agent
    HEALTH_EVENT_AGENT_NAMES.forEach(agentName => {
      sendMessage({
        type: "toggle_agent",
        agent: agentName,
        enabled: true,
      });
    });
  };

  const healthEventEnabled = HEALTH_EVENT_AGENT_NAMES.some((agentName) => enabledAgents.has(agentName));

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

      {/* Emergency Alert Modal */}
      {emergencyAlertInfo && (
        <EmergencyAlertModal
          isOpen={showEmergencyModal}
          alertType={emergencyAlertInfo.type}
          alertSeverity={emergencyAlertInfo.severity}
          alertTimestamp={emergencyAlertInfo.timestamp}
          healthReport={emergencyAlertInfo.healthReport}
          onClose={handleCloseEmergencyModal}
          onDispatched={handleAcknowledge}
        />
      )}

      <main className="flex-1 flex flex-col p-4 gap-4 max-w-[1920px] mx-auto w-full">
        {/* Header */}
        <header className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            {/* Logo */}
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="M12 15.5l-3.5-3.1a2.4 2.4 0 0 1-.7-1.8c0-1.3 1.1-2.4 2.5-2.4.7 0 1.3.3 1.7.7.4-.4 1-.7 1.7-.7 1.4 0 2.5 1.1 2.5 2.4 0 .7-.3 1.3-.7 1.8L12 15.5z" fill="currentColor" stroke="none" />
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
              <PrivacyStatus 
                connected={connected} 
                settings={settings}
                onToggleRecording={toggleRecording}
                onTogglePrivacyMode={togglePrivacyMode}
                loading={settingsLoading}
              />
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
          <LiveFeed 
            frame={frame} 
            poseDetected={poseDetected} 
            connected={connected} 
            numPeople={numPeople}
            recordingEnabled={settings?.recording_enabled ?? true}
            onToggleRecording={toggleRecording}
          />
        </div>

        {/* Right sidebar */}
        <div className="lg:col-span-4 flex flex-col gap-4 min-h-0 overflow-y-auto pr-0.5">
          <StatusBadge agentState={agentState} />
          <RecoveryTimer agentState={agentState} />
          <AlertPanel
            alert={latestAlert}
            healthReport={latestHealthReport}
            onAcknowledge={handleAcknowledge}
          />
          
          {/* Health Event Agent */}
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <h3 className="text-sm font-semibold text-slate-300">AI Agents</h3>
              <button
                onClick={resetAllAgents}
                className="text-[10px] px-2 py-1 rounded bg-slate-800/50 hover:bg-slate-700/50 text-slate-400 hover:text-slate-300 transition-colors"
                title="Reset health event monitoring"
              >
                Reset
              </button>
            </div>
            <div className={`space-y-1.5 transition-opacity ${healthEventEnabled ? "opacity-100" : "opacity-50"}`}>
              <div className="flex items-center justify-between px-1">
                <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">
                  {healthEventEnabled ? "Enabled" : "Disabled"}
                </span>
                <button
                  onClick={toggleHealthEventAgent}
                  className={`w-9 h-5 rounded-full transition-all flex items-center ${
                    healthEventEnabled
                      ? "bg-emerald-500/30 border border-emerald-500/50"
                      : "bg-slate-700/50 border border-slate-600/50"
                  }`}
                  title={`${healthEventEnabled ? "Disable" : "Enable"} Health Event Agent`}
                >
                  <div
                    className={`w-4 h-4 rounded-full bg-white transition-transform ${
                      healthEventEnabled ? "translate-x-4" : "translate-x-0.5"
                    }`}
                  />
                </button>
              </div>
              <HealthEventAgentCard
                agents={agents}
                fallbackState={agentState}
                poseDetected={poseDetected && healthEventEnabled}
                enabled={healthEventEnabled}
              />
            </div>
          </div>
        </div>

      </div>

      {/* Bottom: Event Log */}
      <div className="h-[200px] shrink-0">
        <EventLog events={events} />
      </div>

      {/* Security Status - Below Event Timeline */}
      <div className="shrink-0">
        <SecurityStatus connected={connected} />
      </div>

      {/* Alert Settings - Emergency Contacts & Notification Preferences */}
      <div className="shrink-0">
        <AlertSettings />
      </div>
      </main>
    </>
  );
}
