'use client';

import { useState } from 'react';
import { useUserSettings } from '@/hooks/useUserSettings';
import { useUserLocation } from '@/hooks/useUserLocation';
import EmergencyContacts from './EmergencyContacts';

export default function AlertSettings() {
  const {
    settings,
    loading: settingsLoading,
    toggleNotify911,
    toggleNotifyEmergencyContacts,
    toggleNotifyNearestHospital,
  } = useUserSettings();

  const {
    location,
    loading: locationLoading,
    geolocating,
    saveLocation,
    getCurrentLocation,
  } = useUserLocation();

  const [isExpanded, setIsExpanded] = useState(false);
  const [addressInput, setAddressInput] = useState('');
  const [savingLocation, setSavingLocation] = useState(false);

  const handleSaveAddress = async () => {
    if (!addressInput.trim()) return;
    
    setSavingLocation(true);
    try {
      // For hackathon demo, we'll save the address without geocoding
      // In production, you'd call the geocode API
      await saveLocation({
        home_address: addressInput,
        latitude: null,
        longitude: null,
        city: '',
        state: '',
        country: 'USA',
      });
      setAddressInput('');
    } catch (err) {
      console.error('Error saving address:', err);
    } finally {
      setSavingLocation(false);
    }
  };

  const handleUseCurrentLocation = async () => {
    const coords = await getCurrentLocation();
    if (coords) {
      // Save with coordinates, address will need reverse geocoding in production
      await saveLocation({
        home_address: `Lat: ${coords.lat.toFixed(6)}, Lng: ${coords.lng.toFixed(6)}`,
        latitude: coords.lat,
        longitude: coords.lng,
        city: '',
        state: '',
        country: 'USA',
      });
    }
  };

  const loading = settingsLoading || locationLoading;

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      {/* Header - Click to expand */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-slate-800/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-rose-500/20 flex items-center justify-center">
            <svg className="w-4 h-4 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-slate-200">Emergency Alert Settings</h3>
            <p className="text-xs text-slate-500">Configure who gets notified in emergencies</p>
          </div>
        </div>
        <svg
          className={`w-5 h-5 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expandable Content */}
      {isExpanded && (
        <div className="p-4 pt-0 space-y-4 border-t border-slate-700/50">
          {/* Notification Toggles */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Notify on Critical Alert</h4>
            
            {/* 911 Toggle */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center">
                  <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">Emergency Services (911)</p>
                  <p className="text-xs text-slate-500">Automatically call 911</p>
                </div>
              </div>
              <button
                onClick={toggleNotify911}
                disabled={loading}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings?.notify_911 ? 'bg-red-500' : 'bg-slate-600'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    settings?.notify_911 ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </div>

            {/* Emergency Contacts Toggle */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-amber-500/20 flex items-center justify-center">
                  <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">Emergency Contacts</p>
                  <p className="text-xs text-slate-500">Notify your listed contacts</p>
                </div>
              </div>
              <button
                onClick={toggleNotifyEmergencyContacts}
                disabled={loading}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings?.notify_emergency_contacts ? 'bg-amber-500' : 'bg-slate-600'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    settings?.notify_emergency_contacts ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </div>

            {/* Nearest Hospital Toggle */}
            <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/30">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/20 flex items-center justify-center">
                  <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-200">Nearest Hospital</p>
                  <p className="text-xs text-slate-500">Alert closest medical facility</p>
                </div>
              </div>
              <button
                onClick={toggleNotifyNearestHospital}
                disabled={loading}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  settings?.notify_nearest_hospital ? 'bg-cyan-500' : 'bg-slate-600'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    settings?.notify_nearest_hospital ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Home Location */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Home Location</h4>
            
            {location?.home_address ? (
              <div className="p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <svg className="w-5 h-5 text-emerald-400 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <div>
                      <p className="text-sm text-slate-200">{location.home_address}</p>
                      {location.latitude && location.longitude && (
                        <p className="text-xs text-slate-500 mt-0.5">
                          {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
                        </p>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => setAddressInput(location.home_address)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Edit
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={addressInput}
                    onChange={(e) => setAddressInput(e.target.value)}
                    placeholder="Enter your home address"
                    className="flex-1 px-3 py-2 rounded-lg bg-slate-900/50 border border-slate-700 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50"
                  />
                  <button
                    onClick={handleSaveAddress}
                    disabled={savingLocation || !addressInput.trim()}
                    className="px-3 py-2 rounded-lg bg-emerald-500/20 text-emerald-400 text-sm font-medium hover:bg-emerald-500/30 disabled:opacity-50 transition-colors"
                  >
                    {savingLocation ? 'Saving...' : 'Save'}
                  </button>
                </div>
                <button
                  onClick={handleUseCurrentLocation}
                  disabled={geolocating}
                  className="flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                  </svg>
                  {geolocating ? 'Getting location...' : 'Use current location'}
                </button>
              </div>
            )}
          </div>

          {/* Emergency Contacts Section */}
          <EmergencyContacts />
        </div>
      )}
    </div>
  );
}
