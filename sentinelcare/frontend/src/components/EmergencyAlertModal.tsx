'use client';

import { useState, useEffect, useCallback } from 'react';
import { useUserSettings } from '@/hooks/useUserSettings';
import { useEmergencyContacts } from '@/hooks/useEmergencyContacts';
import { useUserLocation } from '@/hooks/useUserLocation';
import { useAlertDispatch } from '@/hooks/useAlertDispatch';

interface EmergencyAlertModalProps {
  isOpen: boolean;
  alertType: string;
  alertSeverity: string;
  alertTimestamp: Date;
  onClose: () => void;
  onDispatched?: () => void;
}

const COUNTDOWN_SECONDS = 10;

export default function EmergencyAlertModal({
  isOpen,
  alertType,
  alertSeverity,
  alertTimestamp,
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
  const [dispatchResult, setDispatchResult] = useState<any>(null);
  const [nearestHospital, setNearestHospital] = useState<any>(null);

  // Fetch nearest hospital on open
  useEffect(() => {
    if (isOpen && location?.latitude && location?.longitude) {
      fetchNearestHospital(Number(location.latitude), Number(location.longitude))
        .then(setNearestHospital);
    }
  }, [isOpen, location, fetchNearestHospital]);

  // Countdown timer
  useEffect(() => {
    if (!isOpen || isCancelled || isDispatched) return;

    if (countdown <= 0) {
      handleDispatch();
      return;
    }

    const timer = setTimeout(() => {
      setCountdown(prev => prev - 1);
    }, 1000);

    return () => clearTimeout(timer);
  }, [isOpen, countdown, isCancelled, isDispatched]);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setCountdown(COUNTDOWN_SECONDS);
      setIsCancelled(false);
      setIsDispatched(false);
      setDispatchResult(null);
    }
  }, [isOpen]);

  const handleDispatch = useCallback(async () => {
    if (isDispatched || dispatching) return;

    const result = await dispatchAlert(
      {
        type: alertType,
        severity: alertSeverity,
        timestamp: alertTimestamp,
        location,
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
    settings,
    contacts,
    location,
    onDispatched,
  ]);

  const handleCancel = () => {
    setIsCancelled(true);
    onClose();
  };

  const handleImmediateDispatch = () => {
    setCountdown(0);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-slate-900 border border-red-500/50 rounded-2xl shadow-2xl shadow-red-500/20 overflow-hidden">
        {/* Pulsing border effect */}
        <div className="absolute inset-0 rounded-2xl border-2 border-red-500 animate-pulse opacity-50" />

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
                <p className="text-slate-400 mb-2">Emergency services will be notified in</p>
                <div className="text-6xl font-bold text-red-400 tabular-nums">
                  {countdown}
                </div>
                <p className="text-slate-500 text-sm mt-2">seconds</p>
              </div>

              {/* Alert Info */}
              <div className="space-y-2 p-4 rounded-lg bg-slate-800/50 border border-slate-700">
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Issue:</span>
                  <span className="text-slate-200 font-medium">{alertType}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">Time:</span>
                  <span className="text-slate-200">{alertTimestamp.toLocaleTimeString()}</span>
                </div>
                {location?.home_address && (
                  <div className="flex justify-between text-sm">
                    <span className="text-slate-500">Location:</span>
                    <span className="text-slate-200 text-right max-w-[200px] truncate">{location.home_address}</span>
                  </div>
                )}
              </div>

              {/* Who will be notified */}
              <div className="space-y-2">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Will Notify:</p>
                <div className="flex flex-wrap gap-2">
                  {settings?.notify_911 && (
                    <span className="px-3 py-1 rounded-full bg-red-500/20 text-red-400 text-xs font-medium">
                      911 Emergency
                    </span>
                  )}
                  {settings?.notify_emergency_contacts && contacts.length > 0 && (
                    <span className="px-3 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-medium">
                      {contacts.length} Contact{contacts.length > 1 ? 's' : ''}
                    </span>
                  )}
                  {settings?.notify_nearest_hospital && nearestHospital && (
                    <span className="px-3 py-1 rounded-full bg-cyan-500/20 text-cyan-400 text-xs font-medium">
                      {nearestHospital.name}
                    </span>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3 pt-4">
                <button
                  onClick={handleCancel}
                  className="flex-1 px-4 py-3 rounded-lg bg-slate-700 text-slate-200 font-medium hover:bg-slate-600 transition-colors"
                >
                  Cancel Alert
                </button>
                <button
                  onClick={handleImmediateDispatch}
                  disabled={dispatching}
                  className="flex-1 px-4 py-3 rounded-lg bg-red-500 text-white font-medium hover:bg-red-600 transition-colors disabled:opacity-50"
                >
                  {dispatching ? 'Dispatching...' : 'Send Now'}
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
                <p className="text-slate-400">Emergency services have been notified.</p>
              </div>

              {/* Dispatch Summary */}
              <div className="space-y-2 p-4 rounded-lg bg-slate-800/50 border border-slate-700">
                {dispatchResult?.notified911 && (
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-slate-300">911 Emergency Services notified</span>
                  </div>
                )}
                {dispatchResult?.notifiedContacts?.length > 0 && (
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-slate-300">
                      {dispatchResult.notifiedContacts.length} emergency contact{dispatchResult.notifiedContacts.length > 1 ? 's' : ''} notified
                    </span>
                  </div>
                )}
                {dispatchResult?.notifiedHospital && (
                  <div className="flex items-center gap-2 text-sm">
                    <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-slate-300">{dispatchResult.notifiedHospital.name} alerted</span>
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
