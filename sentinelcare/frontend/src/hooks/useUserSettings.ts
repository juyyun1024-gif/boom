'use client';

import { useState, useEffect, useCallback } from 'react';
import { createClient } from '@/lib/supabase/client';

export interface UserSettings {
  id?: string;
  user_id: string;
  recording_enabled: boolean;
  monitoring_paused: boolean;
  privacy_mode: boolean;
  alert_notifications: boolean;
  notify_911: boolean;
  notify_emergency_contacts: boolean;
  notify_nearest_hospital: boolean;
}

const defaultSettings: Omit<UserSettings, 'user_id'> = {
  recording_enabled: true,
  monitoring_paused: false,
  privacy_mode: false,
  alert_notifications: true,
  notify_911: true,
  notify_emergency_contacts: true,
  notify_nearest_hospital: true,
};

export function useUserSettings() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const supabase = createClient();

  // Fetch user settings on mount
  useEffect(() => {
    async function fetchSettings() {
      try {
        const { data: { user } } = await supabase.auth.getUser();
        
        if (!user) {
          setLoading(false);
          return;
        }

        // Try to get existing settings
        const { data, error: fetchError } = await supabase
          .from('user_settings')
          .select('*')
          .eq('user_id', user.id)
          .single();

        if (fetchError && fetchError.code !== 'PGRST116') {
          // PGRST116 = no rows returned, which is fine for new users
          throw fetchError;
        }

        if (data) {
          setSettings(data);
        } else {
          // Create default settings for new user
          const newSettings: UserSettings = {
            ...defaultSettings,
            user_id: user.id,
          };

          const { data: insertedData, error: insertError } = await supabase
            .from('user_settings')
            .insert(newSettings)
            .select()
            .single();

          if (insertError) throw insertError;
          setSettings(insertedData);
        }
      } catch (err) {
        console.error('[v0] Error fetching user settings:', err);
        setError(err instanceof Error ? err.message : 'Failed to load settings');
      } finally {
        setLoading(false);
      }
    }

    fetchSettings();
  }, [supabase]);

  // Update a single setting
  const updateSetting = useCallback(async <K extends keyof Omit<UserSettings, 'id' | 'user_id'>>(
    key: K,
    value: UserSettings[K]
  ) => {
    if (!settings) return;

    // Optimistic update
    setSettings(prev => prev ? { ...prev, [key]: value } : null);

    try {
      const { error: updateError } = await supabase
        .from('user_settings')
        .update({ [key]: value })
        .eq('user_id', settings.user_id);

      if (updateError) throw updateError;
    } catch (err) {
      // Revert on error
      console.error('[v0] Error updating setting:', err);
      setSettings(prev => prev ? { ...prev, [key]: !value } : null);
      setError(err instanceof Error ? err.message : 'Failed to update setting');
    }
  }, [settings, supabase]);

  // Toggle recording
  const toggleRecording = useCallback(() => {
    if (settings) {
      updateSetting('recording_enabled', !settings.recording_enabled);
    }
  }, [settings, updateSetting]);

  // Toggle privacy mode
  const togglePrivacyMode = useCallback(() => {
    if (settings) {
      updateSetting('privacy_mode', !settings.privacy_mode);
    }
  }, [settings, updateSetting]);

  // Toggle monitoring pause
  const toggleMonitoringPaused = useCallback(() => {
    if (settings) {
      updateSetting('monitoring_paused', !settings.monitoring_paused);
    }
  }, [settings, updateSetting]);

  // Toggle alert notifications
  const toggleAlertNotifications = useCallback(() => {
    if (settings) {
      updateSetting('alert_notifications', !settings.alert_notifications);
    }
  }, [settings, updateSetting]);

  // Toggle 911 notifications
  const toggleNotify911 = useCallback(() => {
    if (settings) {
      updateSetting('notify_911', !settings.notify_911);
    }
  }, [settings, updateSetting]);

  // Toggle emergency contacts notifications
  const toggleNotifyEmergencyContacts = useCallback(() => {
    if (settings) {
      updateSetting('notify_emergency_contacts', !settings.notify_emergency_contacts);
    }
  }, [settings, updateSetting]);

  // Toggle nearest hospital notifications
  const toggleNotifyNearestHospital = useCallback(() => {
    if (settings) {
      updateSetting('notify_nearest_hospital', !settings.notify_nearest_hospital);
    }
  }, [settings, updateSetting]);

  return {
    settings,
    loading,
    error,
    updateSetting,
    toggleRecording,
    togglePrivacyMode,
    toggleMonitoringPaused,
    toggleAlertNotifications,
    toggleNotify911,
    toggleNotifyEmergencyContacts,
    toggleNotifyNearestHospital,
  };
}
