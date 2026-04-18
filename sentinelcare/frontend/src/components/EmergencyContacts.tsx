'use client';

import { useState } from 'react';
import { useEmergencyContacts, EmergencyContact } from '@/hooks/useEmergencyContacts';

const RELATIONSHIPS = ['Spouse', 'Parent', 'Child', 'Sibling', 'Friend', 'Caregiver', 'Neighbor', 'Other'];

export default function EmergencyContacts() {
  const { contacts, loading, addContact, updateContact, deleteContact } = useEmergencyContacts();
  const [isAdding, setIsAdding] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<Partial<EmergencyContact>>({
    name: '',
    phone: '',
    email: '',
    relationship: 'Family',
    priority: 1,
  });
  const [saving, setSaving] = useState(false);

  const resetForm = () => {
    setFormData({ name: '', phone: '', email: '', relationship: 'Family', priority: 1 });
    setIsAdding(false);
    setEditingId(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.phone || !formData.relationship) return;

    setSaving(true);
    try {
      if (editingId) {
        await updateContact(editingId, formData);
      } else {
        await addContact({
          name: formData.name,
          phone: formData.phone,
          email: formData.email || '',
          relationship: formData.relationship,
          priority: formData.priority || contacts.length + 1,
        });
      }
      resetForm();
    } catch (err) {
      console.error('Error saving contact:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (contact: EmergencyContact) => {
    setFormData(contact);
    setEditingId(contact.id || null);
    setIsAdding(true);
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to remove this emergency contact?')) return;
    try {
      await deleteContact(id);
    } catch (err) {
      console.error('Error deleting contact:', err);
    }
  };

  if (loading) {
    return (
      <div className="glass-card p-4 rounded-xl">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-slate-700 rounded w-1/3"></div>
          <div className="h-10 bg-slate-700 rounded"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-4 rounded-xl">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
          <h3 className="text-sm font-semibold text-slate-200">Emergency Contacts</h3>
        </div>
        {!isAdding && (
          <button
            onClick={() => setIsAdding(true)}
            className="px-3 py-1 text-xs font-medium rounded-lg bg-rose-500/20 text-rose-400 hover:bg-rose-500/30 transition-colors"
          >
            + Add Contact
          </button>
        )}
      </div>

      {/* Contact List */}
      {contacts.length === 0 && !isAdding && (
        <p className="text-xs text-slate-500 text-center py-4">
          No emergency contacts added yet. Add contacts to be notified in case of an emergency.
        </p>
      )}

      <div className="space-y-2 mb-4">
        {contacts.map((contact, index) => (
          <div
            key={contact.id}
            className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-slate-700/50"
          >
            <div className="flex items-center gap-3">
              <span className="w-6 h-6 flex items-center justify-center rounded-full bg-rose-500/20 text-rose-400 text-xs font-bold">
                {index + 1}
              </span>
              <div>
                <p className="text-sm font-medium text-slate-200">{contact.name}</p>
                <p className="text-xs text-slate-500">{contact.relationship} &bull; {contact.phone}</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => handleEdit(contact)}
                className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition-colors"
                title="Edit"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                </svg>
              </button>
              <button
                onClick={() => contact.id && handleDelete(contact.id)}
                className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-rose-400 transition-colors"
                title="Delete"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Add/Edit Form */}
      {isAdding && (
        <form onSubmit={handleSubmit} className="space-y-3 p-3 rounded-lg bg-slate-800/30 border border-slate-700/50">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Name *</label>
              <input
                type="text"
                value={formData.name || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-slate-900/50 border border-slate-700 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500/50"
                placeholder="John Doe"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Phone *</label>
              <input
                type="tel"
                value={formData.phone || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, phone: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-slate-900/50 border border-slate-700 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500/50"
                placeholder="+1 (555) 123-4567"
                required
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Email</label>
              <input
                type="email"
                value={formData.email || ''}
                onChange={(e) => setFormData(prev => ({ ...prev, email: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-slate-900/50 border border-slate-700 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-rose-500/50"
                placeholder="email@example.com"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Relationship *</label>
              <select
                value={formData.relationship || 'Family'}
                onChange={(e) => setFormData(prev => ({ ...prev, relationship: e.target.value }))}
                className="w-full px-3 py-2 rounded-lg bg-slate-900/50 border border-slate-700 text-sm text-slate-200 focus:outline-none focus:border-rose-500/50"
                required
              >
                {RELATIONSHIPS.map(rel => (
                  <option key={rel} value={rel}>{rel}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={resetForm}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-700 text-slate-300 hover:bg-slate-600 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-rose-500 text-white hover:bg-rose-600 transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving...' : editingId ? 'Update' : 'Add Contact'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
