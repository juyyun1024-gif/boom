'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useUserSettings } from '@/hooks/useUserSettings';
import { useEmergencyContacts } from '@/hooks/useEmergencyContacts';
import { useUserLocation } from '@/hooks/useUserLocation';
import { useAlertDispatch } from '@/hooks/useAlertDispatch';
import type { Hospital, DispatchResult } from '@/hooks/useAlertDispatch';
import type { HealthEventReport } from '@/hooks/useWebSocket';

interface EmergencyAlertModalProps {
  isOpen: boolean;
  alertType: string;
  alertSeverity: string;
  alertTimestamp: Date;
  healthReport?: HealthEventReport | null;
  onClose: () => void;
  onDispatched?: () => void;
}

const COUNTDOWN_SECONDS = 10;

export default function EmergencyAlertModal({
  isOpen,
  alertType,
  alertSeverity,
  alertTimestamp,
  healthReport,
  onClose,
  onDispatched,
}: EmergencyAlertModalProps) {
  const { settings } = useUserSettings();
  const { contacts } = useEmergencyContacts();
  const { location } = useUserLocation();
  const { dispatching, dispatchAlert, fetchNearestHospital } = useAlertDispatch();

  const [countdown, setCountdown] = useState(COUNTDOWN_SECONDS);
  const [isCancelled, setIsCancelled] = useState(false);
  const [isDispatched, setIsDispatched] = useState(false);
  const [dispatchResult, setDispatchResult] = useState<DispatchResult | null>(null);
  const [nearestHospital, setNearestHospital] = useState<Hospital | null>(null);
  const [loadingHospital, setLoadingHospital] = useState(false);
  const countdownDeadlineRef = useRef<number | null>(null);
  const dispatchStartedRef = useRef(false);
  const handleDispatchRef = useRef<() => Promise<void>>(async () => {});
  const reportIsStructuredDraft = healthReport?.source === 'structured';
  const reportIsStructuredFallback = healthReport?.source === 'structured_fallback';
  const reportSourceLabel = reportIsStructuredDraft
    ? 'Generating Qwen'
    : reportIsStructuredFallback
      ? 'Qwen Timeout'
      : healthReport?.model || healthReport?.source || '';
  const reportStatusText = reportIsStructuredDraft
    ? 'Structured draft shown now. Local Qwen report will replace it when ready.'
    : reportIsStructuredFallback
      ? 'Qwen did not return before timeout, so the structured fallback is shown.'
      : '';

  const handleDispatch = useCallback(async () => {
    if (isDispatched || dispatching) return;

    const result = await dispatchAlert(
      {
        type: alertType,
        severity: alertSeverity,
        timestamp: alertTimestamp,
        location,
        healthReport,
      },
      settings,
      contacts,
      location
    );

    setDispatchResult(result);
    setIsDispatched(true);
    onDispatched?.();
  }, [
    isDispatched,
    dispatching,
    dispatchAlert,
    alertType,
    alertSeverity,
    alertTimestamp,
    healthReport,
    settings,
    contacts,
    location,
    onDispatched,
  ]);

  useEffect(() => {
    handleDispatchRef.current = handleDispatch;
  }, [handleDispatch]);

  // Fetch nearest hospital on open when the option is checked
  useEffect(() => {
    if (!isOpen || !location?.latitude || !location?.longitude) {
      return;
    }

    let active = true;
    const timer = window.setTimeout(() => {
      setLoadingHospital(true);
      fetchNearestHospital(Number(location.latitude), Number(location.longitude))
        .then((hospital) => {
          if (active) setNearestHospital(hospital);
        })
        .finally(() => {
          if (active) setLoadingHospital(false);
        });
    }, 0);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [isOpen, location, fetchNearestHospital]);

  // Reset state when modal opens
  useEffect(() => {
    if (!isOpen) {
      countdownDeadlineRef.current = null;
      dispatchStartedRef.current = false;
      return;
    }

    const timer = window.setTimeout(() => {
      countdownDeadlineRef.current = Date.now() + COUNTDOWN_SECONDS * 1000;
      dispatchStartedRef.current = false;
      setCountdown(COUNTDOWN_SECONDS);
      setIsCancelled(false);
      setIsDispatched(false);
      setDispatchResult(null);
      setNearestHospital(null);
    }, 0);

    return () => window.clearTimeout(timer);
  }, [isOpen, alertTimestamp]);

  // Countdown timer uses a fixed real-time deadline so report/settings updates cannot restart it.
  useEffect(() => {
    if (!isOpen || isCancelled || isDispatched) return;

    if (!countdownDeadlineRef.current) {
      countdownDeadlineRef.current = Date.now() + COUNTDOWN_SECONDS * 1000;
    }

    const tick = () => {
      const deadline = countdownDeadlineRef.current ?? Date.now();
      const remainingMs = Math.max(0, deadline - Date.now());
      const remainingSeconds = Math.ceil(remainingMs / 1000);

      setCountdown(remainingSeconds);

      if (remainingMs <= 0 && !dispatchStartedRef.current) {
        dispatchStartedRef.current = true;
        void handleDispatchRef.current();
      }
    };

    tick();
    const timer = window.setInterval(tick, 250);

    return () => window.clearInterval(timer);
  }, [isOpen, isCancelled, isDispatched]);

  const handleCancel = () => {
    setIsCancelled(true);
    onClose();
  };

  if (!isOpen) return null;

  const emailContacts = contacts.filter(c => c.email && c.email.trim() !== '');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-slate-900 border border-red-500/50 rounded-2xl shadow-2xl shadow-red-500/20 overflow-hidden max-h-[90vh] overflow-y-auto">
        {/* Pulsing border effect */}
        <div className="absolute inset-0 rounded-2xl border-2 border-red-500 animate-pulse opacity-50 pointer-events-none" />

        {/* Header */}
        <div className="relative bg-red-500/20 p-6 border-b border-red-500/30">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-red-500/30 flex items-center justify-center animate-pulse">
              <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div>
              <h2 className="text-2xl font-bold text-red-400">CRITICAL ALERT</h2>
              <p className="text-red-300/80">{alertType} Detected</p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="relative p-6 space-y-4">
          {!isDispatched ? (
            <>
              {/* Countdown */}
              <div className="text-center">
                <p className="text-slate-400 mb-2">Alert will be dispatched in</p>
                <div className="text-6xl font-bold text-red-400 tabular-nums">
                  {countdown}
                </div>
                <p className="text-slate-500 text-sm mt-2">seconds</p>
              </div>

              {/* Alert Info */}
              <div className="space-y-2 p-4 rounded-lg bg-slate-800/50 border border-slate-700">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Event:</span>
                  <span className="text-slate-200 font-medium">{alertType}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Severity:</span>
                  <span className="text-red-400 font-medium uppercase">{alertSeverity}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Time:</span>
                  <span className="text-slate-200">{alertTimestamp.toLocaleString()}</span>
                </div>
                {location?.home_address && (
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-500">Location:</span>
                    <span className="text-slate-200 text-right max-w-[200px] truncate">{location.home_address}</span>
                  </div>
                )}
              </div>

              {/* Health Event Report */}
              {healthReport && (
                <div className="p-4 rounded-lg bg-cyan-500/5 border border-cyan-500/20">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-xs font-semibold text-cyan-400 uppercase tracking-wide">Responder Report</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 uppercase">
                      {reportSourceLabel}
                    </span>
                  </div>
                  <p className="text-sm text-slate-200 leading-relaxed">{healthReport.responder_report}</p>
                  {reportStatusText && (
                    <p className="mt-2 text-xs text-cyan-300/75">{reportStatusText}</p>
                  )}
                  {healthReport.uncertainty.length > 0 && (
                    <div className="mt-3 space-y-1">
                      {healthReport.uncertainty.slice(0, 2).map((item) => (
                        <p key={item} className="text-xs text-amber-300/80">{item}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Hospital Reference */}
              {location?.latitude && location?.longitude && (
                <div className="p-4 rounded-lg bg-cyan-500/5 border border-cyan-500/20">
                  <div className="flex items-center gap-2 mb-2">
                    <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                    </svg>
                    <span className="text-xs font-semibold text-cyan-400 uppercase tracking-wide">Hospital Reference</span>
                  </div>
                  {loadingHospital ? (
                    <p className="text-xs text-slate-500">Finding nearest hospital reference…</p>
                  ) : nearestHospital ? (
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-slate-200">{nearestHospital.name}</p>
                      <p className="text-xs text-slate-400">{nearestHospital.address}</p>
                      <div className="flex items-center gap-3 text-xs text-slate-500">
                        <span>{nearestHospital.distance} mi away</span>
                        {nearestHospital.phone && <span>📞 {nearestHospital.phone}</span>}
                      </div>
                      <p className="text-xs text-cyan-300/70">Reference only. SentinelCare does not contact this hospital.</p>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500">Unable to find hospital reference from saved location.</p>
                  )}
                </div>
              )}

              {/* Who will be notified */}
              <div className="space-y-2">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Will Notify:</p>
                <div className="flex flex-wrap gap-2">
                  {settings?.notify_911 && (
                    <span className="px-3 py-1 rounded-full bg-red-500/20 text-red-400 text-xs font-medium">
                      911 demo flag
                    </span>
                  )}
                  {settings?.notify_emergency_contacts && emailContacts.length > 0 && (
                    <span className="px-3 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-medium">
                      {emailContacts.length} Contact{emailContacts.length > 1 ? 's' : ''} via backend email
                    </span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="pt-4">
                <button
                  onClick={handleCancel}
                  className="w-full px-4 py-3 rounded-lg bg-slate-700 text-slate-200 font-medium hover:bg-slate-600 transition-colors"
                >
                  Cancel Alert
                </button>
              </div>
            </>
          ) : (
            <>
              {/* Dispatched Confirmation */}
              <div className="text-center py-4">
                <div className="w-16 h-16 mx-auto rounded-full bg-emerald-500/20 flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h3 className="text-xl font-bold text-slate-200 mb-2">Alert Dispatched</h3>
                <p className="text-slate-400">
                  {dispatchResult?.emailSent
                    ? 'Emergency contact email was sent by the backend.'
                    : dispatchResult?.emailMessage || 'Alert has been logged.'}
                </p>
              </div>

              {healthReport && (
                <div className="p-4 rounded-lg bg-cyan-500/5 border border-cyan-500/20">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span className="text-xs font-semibold text-cyan-400 uppercase tracking-wide">Responder Report</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 uppercase">
                      {reportSourceLabel}
                    </span>
                  </div>
                  <p className="text-sm text-slate-200 leading-relaxed">{healthReport.responder_report}</p>
                  {reportStatusText && (
                    <p className="mt-2 text-xs text-cyan-300/75">{reportStatusText}</p>
                  )}
                </div>
              )}

              {/* Dispatch Summary */}
              <div className="space-y-2 p-4 rounded-lg bg-slate-800/50 border border-slate-700">
                {dispatchResult?.notified911 && (
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-slate-300">911 demo flag recorded. No call placed.</span>
                  </div>
                )}
                {dispatchResult?.emailSent && (
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-slate-300">
                      Email sent to {dispatchResult.emailRecipients || emailContacts.length} contact{(dispatchResult.emailRecipients || emailContacts.length) > 1 ? 's' : ''}
                    </span>
                  </div>
                )}
                {(dispatchResult?.notifiedContacts.length ?? 0) > 0 && !dispatchResult?.emailSent && (
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                    </svg>
                    <span className="text-slate-300">
                      Emergency contact email not sent: {dispatchResult?.emailMessage || 'backend email service unavailable'}
                    </span>
                  </div>
                )}
                {settings?.notify_emergency_contacts && emailContacts.length === 0 && (
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                    </svg>
                    <span className="text-slate-300">
                      No contact email addresses saved. Add an email address in Alert Settings.
                    </span>
                  </div>
                )}
                {dispatchResult?.notifiedHospital && (
                  <div className="flex items-start gap-2 text-sm">
                    <svg className="w-4 h-4 text-emerald-400 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <div>
                      <span className="text-slate-300">Hospital reference added to alert details</span>
                      <p className="text-cyan-400 text-xs mt-0.5">
                        {dispatchResult.notifiedHospital.name} — {dispatchResult.notifiedHospital.distance} mi
                      </p>
                      <p className="text-slate-500 text-xs mt-0.5">
                        Reference only. The hospital was not contacted.
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Close button */}
              <button
                onClick={onClose}
                className="w-full px-4 py-3 rounded-lg bg-slate-700 text-slate-200 font-medium hover:bg-slate-600 transition-colors"
              >
                Close
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
