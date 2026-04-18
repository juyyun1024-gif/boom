'use client';

import { useState, useEffect, useCallback } from 'react';
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

export function useEmergencyContacts() {
  const [contacts, setContacts] = useState<EmergencyContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const supabase = createClient();

  // Fetch contacts on mount
  useEffect(() => {
    async function fetchContacts() {
      try {
        const { data: { user } } = await supabase.auth.getUser();
        
        if (!user) {
          setLoading(false);
          return;
        }

        const { data, error: fetchError } = await supabase
          .from('emergency_contacts')
          .select('*')
          .eq('user_id', user.id)
          .order('priority', { ascending: true });

        if (fetchError) throw fetchError;
        setContacts(data || []);
      } catch (err) {
        console.error('Error fetching emergency contacts:', err);
        setError(err instanceof Error ? err.message : 'Failed to load contacts');
      } finally {
        setLoading(false);
      }
    }

    fetchContacts();
  }, [supabase]);

  // Add a new contact
  const addContact = useCallback(async (contact: Omit<EmergencyContact, 'id' | 'user_id' | 'created_at' | 'updated_at'>) => {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) throw new Error('Not authenticated');

      const newContact = {
        ...contact,
        user_id: user.id,
      };

      const { data, error: insertError } = await supabase
        .from('emergency_contacts')
        .insert(newContact)
        .select()
        .single();

      if (insertError) throw insertError;
      
      setContacts(prev => [...prev, data].sort((a, b) => a.priority - b.priority));
      return data;
    } catch (err) {
      console.error('Error adding contact:', err);
      setError(err instanceof Error ? err.message : 'Failed to add contact');
      throw err;
    }
  }, [supabase]);

  // Update an existing contact
  const updateContact = useCallback(async (id: string, updates: Partial<EmergencyContact>) => {
    try {
      const { data, error: updateError } = await supabase
        .from('emergency_contacts')
        .update(updates)
        .eq('id', id)
        .select()
        .single();

      if (updateError) throw updateError;
      
      setContacts(prev => 
        prev.map(c => c.id === id ? data : c).sort((a, b) => a.priority - b.priority)
      );
      return data;
    } catch (err) {
      console.error('Error updating contact:', err);
      setError(err instanceof Error ? err.message : 'Failed to update contact');
      throw err;
    }
  }, [supabase]);

  // Delete a contact
  const deleteContact = useCallback(async (id: string) => {
    try {
      const { error: deleteError } = await supabase
        .from('emergency_contacts')
        .delete()
        .eq('id', id);

      if (deleteError) throw deleteError;
      
      setContacts(prev => prev.filter(c => c.id !== id));
    } catch (err) {
      console.error('Error deleting contact:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete contact');
      throw err;
    }
  }, [supabase]);

  return {
    contacts,
    loading,
    error,
    addContact,
    updateContact,
    deleteContact,
  };
}
