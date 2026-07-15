'use client';

import { useState, useCallback } from 'react';
import { createClient } from '@/lib/supabase/client';
import { UserSettings } from './useUserSettings';
import { EmergencyContact } from './useEmergencyContacts';
import { UserLocation } from './useUserLocation';
import type { HealthEventReport } from './useWebSocket';

export interface Hospital {
  name: string;
  address: string;
  phone?: string;
  distance: number;
}

interface AlertInfo {
  type: string;
  severity: string;
  timestamp: Date;
  location?: UserLocation | null;
  healthReport?: HealthEventReport | null;
}

export interface DispatchResult {
  success: boolean;
  notified911: boolean;
  notifiedContacts: EmergencyContact[];
  notifiedHospital: Hospital | null;
  emailSent: boolean;
  emailStatus?: string;
  emailMessage?: string;
  emailRecipients: number;
  alertId?: string;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

const localContactsKey = (userId: string) => `sentinelcare_emergency_contacts_${userId}`;

function loadLocalEmergencyContacts(userId: string): EmergencyContact[] {
  try {
    const saved = window.localStorage.getItem(localContactsKey(userId));
    if (!saved) return [];
    const contacts = JSON.parse(saved) as EmergencyContact[];
    return Array.isArray(contacts) ? contacts : [];
  } catch {
    return [];
  }
}

function mergeContacts(primary: EmergencyContact[], fallback: EmergencyContact[]): EmergencyContact[] {
  const merged = new Map<string, EmergencyContact>();
  [...primary, ...fallback].forEach((contact) => {
    const key = contact.id || contact.email || contact.phone || contact.name;
    if (key) merged.set(key, contact);
  });
  return [...merged.values()].sort((a, b) => a.priority - b.priority);
}

export function useAlertDispatch() {
  const [dispatching, setDispatching] = useState(false);
  const [lastDispatch, setLastDispatch] = useState<DispatchResult | null>(null);
  const supabase = createClient();

  // Fetch nearest hospital based on location
  const fetchNearestHospital = useCallback(async (lat: number, lng: number): Promise<Hospital | null> => {
    try {
      const response = await fetch('/api/nearby-hospitals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ latitude: lat, longitude: lng }),
      });

      if (!response.ok) return null;

      const data = await response.json();
      return data.hospitals?.[0] || null;
    } catch (err) {
      console.error('Error fetching nearest hospital:', err);
      return null;
    }
  }, []);

  // Push contacts + location to backend so it can auto-send emails on alert
  const syncAlertConfig = useCallback(async (
    contacts: EmergencyContact[],
    location: UserLocation | null,
    nearestHospital: Hospital | null,
    emailAlertsEnabled = true,
  ) => {
    try {
      const payload = {
        contacts: contacts
          .filter(c => c.email && c.email.trim())
          .map(c => ({ name: c.name, email: c.email, phone: c.phone })),
        location: location
          ? {
              address: location.home_address || '',
              latitude: location.latitude,
              longitude: location.longitude,
            }
          : {},
        nearest_hospital: nearestHospital
          ? {
              name: nearestHospital.name,
              address: nearestHospital.address,
              phone: nearestHospital.phone || '',
              distance: nearestHospital.distance,
            }
          : null,
        email_alerts_enabled: emailAlertsEnabled,
      };

      await fetch(`${BACKEND_URL}/alerts/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.error('Error syncing alert config to backend:', err);
    }
  }, []);

  const sendEmergencyContactEmail = useCallback(async (
    alertInfo: AlertInfo,
    contactsWithEmail: EmergencyContact[],
    location: UserLocation | null,
    nearestHospital: Hospital | null,
  ) => {
    const response = await fetch(`${BACKEND_URL}/alerts/dispatch-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alert_id: alertInfo.healthReport?.alert_id || null,
        contacts: contactsWithEmail.map(c => ({
          name: c.name,
          email: c.email,
          phone: c.phone,
          relationship: c.relationship,
        })),
        alert_type: alertInfo.type,
        severity: alertInfo.severity,
        timestamp: alertInfo.timestamp.toISOString(),
        location: location
          ? {
              address: location.home_address || '',
              latitude: location.latitude,
              longitude: location.longitude,
            }
          : {},
        nearest_hospital: nearestHospital
          ? {
              name: nearestHospital.name,
              address: nearestHospital.address,
              phone: nearestHospital.phone || '',
              distance: nearestHospital.distance,
            }
          : null,
        summary: alertInfo.healthReport?.responder_report || alertInfo.healthReport?.summary || '',
        recommended_action: alertInfo.healthReport?.recommended_actions?.slice(0, 2).join(' ') || '',
        issues: alertInfo.healthReport?.observed_signals.map((signal) => ({ label: signal })) || [{
          label: alertInfo.type,
        }],
      }),
    });

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.message || `Backend email dispatch failed (${response.status})`);
    }
    return data as {
      sent: boolean;
      status: string;
      recipients: number;
      message: string;
      smtp_configured: boolean;
    };
  }, []);

  // Main dispatch function
  const dispatchAlert = useCallback(async (
    alertInfo: AlertInfo,
    settings: UserSettings | null,
    contacts: EmergencyContact[],
    location: UserLocation | null
  ): Promise<DispatchResult> => {
    setDispatching(true);

    const result: DispatchResult = {
      success: false,
      notified911: false,
      notifiedContacts: [],
      notifiedHospital: null,
      emailSent: false,
      emailRecipients: 0,
    };

    try {
      const { data: { user } } = await supabase.auth.getUser();
      const latestContacts = user
        ? mergeContacts(loadLocalEmergencyContacts(user.id), contacts)
        : contacts;

      // 1. Fetch nearest hospital as responder reference only.
      let nearestHospital: Hospital | null = null;
      if (location?.latitude && location?.longitude) {
        nearestHospital = await fetchNearestHospital(
          Number(location.latitude),
          Number(location.longitude)
        );
        if (nearestHospital) {
          result.notifiedHospital = nearestHospital;
        }
      }

      // 2. Flag 911 intent
      if (settings?.notify_911) {
        console.log('[ALERT DISPATCH] 911 flag set:', {
          location: location?.home_address,
          issue: alertInfo.type,
          time: alertInfo.timestamp.toISOString(),
        });
        result.notified911 = true;
      }

      // 3. Send emergency-contact email through backend SMTP.
      const shouldNotifyContacts = settings?.notify_emergency_contacts ?? true;
      if (shouldNotifyContacts && latestContacts.length > 0) {
        const contactsWithEmail = latestContacts.filter(c => c.email?.trim());
        result.notifiedContacts = contactsWithEmail;

        if (contactsWithEmail.length > 0) {
          try {
            const emailResult = await sendEmergencyContactEmail(
              alertInfo,
              contactsWithEmail,
              location,
              nearestHospital,
            );
            result.emailSent = Boolean(emailResult.sent);
            result.emailStatus = emailResult.status;
            result.emailMessage = emailResult.message;
            result.emailRecipients = emailResult.recipients;
          } catch (err) {
            result.emailSent = false;
            result.emailStatus = 'backend_error';
            result.emailMessage = err instanceof Error ? err.message : 'Backend email dispatch failed.';
            result.emailRecipients = contactsWithEmail.length;
            console.error('Error sending emergency contact email:', err);
          }
        } else {
          result.emailStatus = 'no_recipients';
          result.emailMessage = 'No emergency contact emails configured.';
        }
      } else if (shouldNotifyContacts) {
        result.emailStatus = 'no_contacts';
        result.emailMessage = 'No emergency contacts saved.';
      }

      // 4. Log alert to database
      if (user) {
        const { data: alertData, error: alertError } = await supabase
          .from('alert_history')
          .insert({
            user_id: user.id,
            alert_type: alertInfo.type,
            severity: alertInfo.severity,
            location_address: location?.home_address || null,
            latitude: location?.latitude || null,
            longitude: location?.longitude || null,
            triggered_at: alertInfo.timestamp.toISOString(),
            notified_911: result.notified911,
            notified_contacts: result.notifiedContacts.map(c => ({ name: c.name, phone: c.phone, email: c.email })),
            notified_hospital: result.notifiedHospital?.name || null,
            status: 'dispatched',
          })
          .select()
          .single();

        if (alertError) {
          console.error('Error logging alert:', alertError);
        } else {
          result.alertId = alertData.id;
        }
      } else {
        console.warn('Alert dispatched without Supabase auth; skipped alert_history insert.');
      }

      result.success = true;
      setLastDispatch(result);
      return result;
    } catch (err) {
      console.error('Error dispatching alert:', err);
      return result;
    } finally {
      setDispatching(false);
    }
  }, [supabase, fetchNearestHospital, sendEmergencyContactEmail]);

  // Cancel/acknowledge an alert
  const acknowledgeAlert = useCallback(async (alertId: string) => {
    try {
      const { error } = await supabase
        .from('alert_history')
        .update({
          acknowledged_at: new Date().toISOString(),
          status: 'acknowledged',
        })
        .eq('id', alertId);

      if (error) throw error;
    } catch (err) {
      console.error('Error acknowledging alert:', err);
    }
  }, [supabase]);

  return {
    dispatching,
    lastDispatch,
    dispatchAlert,
    acknowledgeAlert,
    fetchNearestHospital,
    syncAlertConfig,
  };
}
