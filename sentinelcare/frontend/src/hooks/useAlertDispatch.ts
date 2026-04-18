'use client';

import { useState, useCallback } from 'react';
import { createClient } from '@/lib/supabase/client';
import { UserSettings } from './useUserSettings';
import { EmergencyContact } from './useEmergencyContacts';
import { UserLocation } from './useUserLocation';

interface Hospital {
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
  nearestHospital?: Hospital | null;
}

interface DispatchResult {
  success: boolean;
  notified911: boolean;
  notifiedContacts: EmergencyContact[];
  notifiedHospital: Hospital | null;
  alertId?: string;
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
    };

    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error('Not authenticated');

      // Get nearest hospital if location is available
      let nearestHospital: Hospital | null = null;
      if (location?.latitude && location?.longitude && settings?.notify_nearest_hospital) {
        nearestHospital = await fetchNearestHospital(
          Number(location.latitude),
          Number(location.longitude)
        );
      }

      // Simulate notifications (in production, these would be real API calls)
      
      // 1. Notify 911
      if (settings?.notify_911) {
        // In production: Integrate with emergency services API
        console.log('[ALERT DISPATCH] Notifying 911:', {
          location: location?.home_address,
          issue: alertInfo.type,
          time: alertInfo.timestamp.toISOString(),
        });
        result.notified911 = true;
      }

      // 2. Notify emergency contacts
      if (settings?.notify_emergency_contacts && contacts.length > 0) {
        // In production: Send SMS/calls via Twilio or similar
        for (const contact of contacts) {
          console.log('[ALERT DISPATCH] Notifying contact:', contact.name, contact.phone);
        }
        result.notifiedContacts = contacts;
      }

      // 3. Notify nearest hospital
      if (settings?.notify_nearest_hospital && nearestHospital) {
        // In production: Send alert to hospital emergency system
        console.log('[ALERT DISPATCH] Notifying hospital:', nearestHospital.name, nearestHospital.phone);
        result.notifiedHospital = nearestHospital;
      }

      // Log alert to database
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
          notified_contacts: result.notifiedContacts.map(c => ({ name: c.name, phone: c.phone })),
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

      result.success = true;
      setLastDispatch(result);
      return result;
    } catch (err) {
      console.error('Error dispatching alert:', err);
      return result;
    } finally {
      setDispatching(false);
    }
  }, [supabase, fetchNearestHospital]);

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
  };
}
