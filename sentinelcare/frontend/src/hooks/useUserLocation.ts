'use client';

import { useState, useEffect, useCallback } from 'react';
import { createClient } from '@/lib/supabase/client';

export interface UserLocation {
  id?: string;
  user_id?: string;
  home_address: string;
  latitude: number | null;
  longitude: number | null;
  city?: string;
  state?: string;
  country?: string;
}

export function useUserLocation() {
  const [location, setLocation] = useState<UserLocation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [geolocating, setGeolocating] = useState(false);
  const supabase = createClient();

  // Fetch location on mount
  useEffect(() => {
    async function fetchLocation() {
      try {
        const { data: { user } } = await supabase.auth.getUser();
        
        if (!user) {
          setLoading(false);
          return;
        }

        const { data, error: fetchError } = await supabase
          .from('user_location')
          .select('*')
          .eq('user_id', user.id)
          .single();

        if (fetchError && fetchError.code !== 'PGRST116') {
          throw fetchError;
        }

        setLocation(data || null);
      } catch (err) {
        console.error('Error fetching user location:', err);
        setError(err instanceof Error ? err.message : 'Failed to load location');
      } finally {
        setLoading(false);
      }
    }

    fetchLocation();
  }, [supabase]);

  // Save or update location
  const saveLocation = useCallback(async (locationData: Omit<UserLocation, 'id' | 'user_id'>) => {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error('Not authenticated');

      const newLocation = {
        ...locationData,
        user_id: user.id,
      };

      // Use upsert to handle both insert and update
      const { data, error: upsertError } = await supabase
        .from('user_location')
        .upsert(newLocation, { onConflict: 'user_id' })
        .select()
        .single();

      if (upsertError) throw upsertError;
      
      setLocation(data);
      return data;
    } catch (err) {
      console.error('Error saving location:', err);
      setError(err instanceof Error ? err.message : 'Failed to save location');
      throw err;
    }
  }, [supabase]);

  // Get current location using browser geolocation
  const getCurrentLocation = useCallback(async (): Promise<{ lat: number; lng: number } | null> => {
    if (!navigator.geolocation) {
      setError('Geolocation is not supported by your browser');
      return null;
    }

    setGeolocating(true);
    
    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          setGeolocating(false);
          resolve({
            lat: position.coords.latitude,
            lng: position.coords.longitude,
          });
        },
        (err: GeolocationPositionError) => {
          setGeolocating(false);
          let errorMessage = 'Failed to get current location. Please enter address manually.';
          
          switch (err.code) {
            case err.PERMISSION_DENIED:
              errorMessage = 'Location access denied. Please enable location permissions or enter address manually.';
              break;
            case err.POSITION_UNAVAILABLE:
              errorMessage = 'Location unavailable. Please enter address manually.';
              break;
            case err.TIMEOUT:
              errorMessage = 'Location request timed out. Please try again or enter address manually.';
              break;
          }
          
          console.error('Geolocation error:', err.code, err.message);
          setError(errorMessage);
          resolve(null);
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
      );
    });
  }, []);

  // Geocode an address to get coordinates (using a simple approach)
  const geocodeAddress = useCallback(async (address: string): Promise<{ lat: number; lng: number } | null> => {
    try {
      // Use the API route we'll create
      const response = await fetch('/api/geocode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address }),
      });

      if (!response.ok) throw new Error('Geocoding failed');
      
      const data = await response.json();
      return data.location || null;
    } catch (err) {
      console.error('Geocoding error:', err);
      return null;
    }
  }, []);

  return {
    location,
    loading,
    error,
    geolocating,
    saveLocation,
    getCurrentLocation,
    geocodeAddress,
  };
}
