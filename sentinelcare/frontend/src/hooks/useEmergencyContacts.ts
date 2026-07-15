'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { createClient } from '@/lib/supabase/client';

export interface EmergencyContact {
  id?: string;
  user_id?: string;
  name: string;
  phone: string;
  email?: string;
  relationship: string;
  priority: number;
  created_at?: string;
  updated_at?: string;
}

const localContactsKey = (userId: string) => `sentinelcare_emergency_contacts_${userId}`;

function createLocalId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `local_${crypto.randomUUID()}`;
  }
  return `local_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function loadLocalContacts(userId: string): EmergencyContact[] {
  try {
    const saved = window.localStorage.getItem(localContactsKey(userId));
    if (!saved) return [];
    const contacts = JSON.parse(saved) as EmergencyContact[];
    return contacts.sort((a, b) => a.priority - b.priority);
  } catch {
    return [];
  }
}

function saveLocalContacts(userId: string, contacts: EmergencyContact[]) {
  window.localStorage.setItem(localContactsKey(userId), JSON.stringify(contacts));
  window.dispatchEvent(new CustomEvent('sentinelcare:emergency-contacts-updated', {
    detail: { userId, contacts },
  }));
}

export function useEmergencyContacts() {
  const [contacts, setContacts] = useState<EmergencyContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const supabase = useMemo(() => createClient(), []);

  // Fetch contacts on mount
  useEffect(() => {
    async function fetchContacts() {
      try {
        const { data: { user } } = await supabase.auth.getUser();
        
        if (!user) {
          setLoading(false);
          return;
        }

        setUserId(user.id);

        const { data, error: fetchError } = await supabase
          .from('emergency_contacts')
          .select('*')
          .eq('user_id', user.id)
          .order('priority', { ascending: true });

        if (fetchError) {
          console.warn('Emergency contacts table unavailable, using local contacts:', fetchError);
          setContacts(loadLocalContacts(user.id));
          setError(fetchError.message ?? 'Using local emergency contacts');
          return;
        }

        const remoteContacts = data || [];
        setContacts(remoteContacts);
        saveLocalContacts(user.id, remoteContacts);
      } catch (err) {
        console.error('Error fetching emergency contacts:', err);
        setError(err instanceof Error ? err.message : 'Failed to load contacts');
      } finally {
        setLoading(false);
      }
    }

    fetchContacts();
  }, [supabase]);

  useEffect(() => {
    if (!userId) return;

    const handleContactsUpdated = (event: Event) => {
      const detail = (event as CustomEvent<{ userId?: string; contacts?: EmergencyContact[] }>).detail;
      if (detail?.userId !== userId || !Array.isArray(detail.contacts)) return;
      setContacts([...detail.contacts].sort((a, b) => a.priority - b.priority));
    };

    window.addEventListener('sentinelcare:emergency-contacts-updated', handleContactsUpdated);
    return () => window.removeEventListener('sentinelcare:emergency-contacts-updated', handleContactsUpdated);
  }, [userId]);

  // Add a new contact
  const addContact = useCallback(async (contact: Omit<EmergencyContact, 'id' | 'user_id' | 'created_at' | 'updated_at'>) => {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error('Not authenticated');
      setUserId(user.id);

      const newContact = {
        ...contact,
        id: createLocalId(),
        user_id: user.id,
      };

      const locallyAdded = [...contacts, newContact].sort((a, b) => a.priority - b.priority);
      setContacts(locallyAdded);
      saveLocalContacts(user.id, locallyAdded);

      const { data, error: insertError } = await supabase
        .from('emergency_contacts')
        .insert({ ...contact, user_id: user.id })
        .select()
        .single();

      if (insertError) {
        console.warn('Could not sync emergency contact to Supabase, keeping local contact:', insertError);
        setError(insertError.message ?? 'Using local emergency contacts');
        return newContact;
      }
      
      setContacts(prev => {
        const updated = prev
          .map(c => c.id === newContact.id ? data : c)
          .sort((a, b) => a.priority - b.priority);
        saveLocalContacts(user.id, updated);
        return updated;
      });
      return data;
    } catch (err) {
      console.error('Error adding contact:', err);
      setError(err instanceof Error ? err.message : 'Failed to add contact');
      throw err;
    }
  }, [contacts, supabase]);

  // Update an existing contact
  const updateContact = useCallback(async (id: string, updates: Partial<EmergencyContact>) => {
    try {
      const currentUserId = userId ?? contacts.find(c => c.id === id)?.user_id;
      if (currentUserId) {
        const locallyUpdated = contacts
          .map(c => c.id === id ? { ...c, ...updates } : c)
          .sort((a, b) => a.priority - b.priority);
        setContacts(locallyUpdated);
        saveLocalContacts(currentUserId, locallyUpdated);
      }

      if (id.startsWith('local_')) {
        return contacts.find(c => c.id === id) ?? null;
      }

      const { data, error: updateError } = await supabase
        .from('emergency_contacts')
        .update(updates)
        .eq('id', id)
        .select()
        .single();

      if (updateError) {
        console.warn('Could not sync emergency contact update to Supabase, keeping local update:', updateError);
        setError(updateError.message ?? 'Using local emergency contacts');
        return contacts.find(c => c.id === id) ?? null;
      }
      
      setContacts(prev => 
        prev.map(c => c.id === id ? data : c).sort((a, b) => a.priority - b.priority)
      );
      return data;
    } catch (err) {
      console.error('Error updating contact:', err);
      setError(err instanceof Error ? err.message : 'Failed to update contact');
      throw err;
    }
  }, [contacts, supabase, userId]);

  // Delete a contact
  const deleteContact = useCallback(async (id: string) => {
    try {
      const contact = contacts.find(c => c.id === id);
      const currentUserId = userId ?? contact?.user_id;
      const locallyDeleted = contacts.filter(c => c.id !== id);
      setContacts(locallyDeleted);
      if (currentUserId) {
        saveLocalContacts(currentUserId, locallyDeleted);
      }

      if (id.startsWith('local_')) {
        return;
      }

      const { error: deleteError } = await supabase
        .from('emergency_contacts')
        .delete()
        .eq('id', id);

      if (deleteError) {
        console.warn('Could not sync emergency contact delete to Supabase, keeping local delete:', deleteError);
        setError(deleteError.message ?? 'Using local emergency contacts');
      }
    } catch (err) {
      console.error('Error deleting contact:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete contact');
      throw err;
    }
  }, [contacts, supabase, userId]);

  return {
    contacts,
    loading,
    error,
    addContact,
    updateContact,
    deleteContact,
  };
}
