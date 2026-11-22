import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { User, MapPin, Phone, Mail, X, Check, Save, AlertCircle } from 'lucide-react';
import { updateUserProfile } from '../services/authService';
import { buildProfileUpdatePayload } from '../utils/profilePayload.js';

const ProfileModal = ({ isOpen, onClose, user, onProfileUpdated }) => {
  const canEditWard = (user?.role || '').toLowerCase() === 'citizen';
  const [formData, setFormData] = useState({
    full_name: '',
    ward: '',
    phone: ''
  });
  const [isSaving, setIsSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  useEffect(() => {
    if (user) {
      setFormData({
        full_name: user.name || user.full_name || '',
        ward: user.ward || '',
        phone: user.phone || ''
      });
    }
  }, [user]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    // Strict compulsory validation check for every single field
    if (!formData.full_name.trim()) {
      setErrorMsg('Full Name is compulsory (*)');
      return;
    }
    if (canEditWard && !formData.ward.trim()) {
      setErrorMsg('Assigned Ward is compulsory (*)');
      return;
    }
    if (!formData.phone.trim()) {
      setErrorMsg('Phone Number is compulsory (*)');
      return;
    }

    setIsSaving(true);
    try {
      const updatedUser = await updateUserProfile(buildProfileUpdatePayload(user, formData));
      
      setSuccessMsg('Profile data updated & saved to database!');
      if (onProfileUpdated) onProfileUpdated(updatedUser);
      
      setTimeout(() => {
        setSuccessMsg('');
        onClose();
      }, 1200);
    } catch (error) {
      console.error('Error updating profile:', error);
      setErrorMsg('Failed to update profile. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl border border-slate-200 relative overflow-hidden"
      >
        <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-[#02471f] text-white flex items-center justify-center font-bold">
              <User className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-slate-900">User Profile Settings</h3>
              <p className="text-[11px] font-medium text-slate-500">All fields marked with (*) are compulsory</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full bg-slate-100 text-slate-400 hover:text-slate-600 flex items-center justify-center cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {errorMsg && (
          <div className="mb-4 p-2.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-extrabold flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="mb-4 p-2.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center gap-2">
            <Check className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">
              Full Name <span className="text-red-500 font-black ml-0.5">*</span>
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => {
                  setFormData({ ...formData, full_name: e.target.value });
                  if (errorMsg) setErrorMsg('');
                }}
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold focus:border-[#02471f] focus:outline-none"
                placeholder="Enter your full name"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">
              Email Address <span className="text-red-500 font-black ml-0.5">*</span> (Read-only)
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="email"
                value={user?.email || ''}
                disabled
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-xs font-semibold text-slate-500 cursor-not-allowed"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
              Assigned Ward {canEditWard && <span className="text-red-500 font-black ml-0.5">*</span>}
              </label>
              <div className="relative">
                <MapPin className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  value={formData.ward}
                  placeholder="Ward not assigned"
                  readOnly={!canEditWard}
                  onChange={(e) => {
                    setFormData({ ...formData, ward: e.target.value });
                    if (errorMsg) setErrorMsg('');
                  }}
                  className={`w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold focus:border-[#02471f] focus:outline-none ${canEditWard ? 'bg-white' : 'bg-slate-50 text-slate-500'}`}
                  required={canEditWard}
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Phone Number <span className="text-red-500 font-black ml-0.5">*</span>
              </label>
              <div className="relative">
                <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  value={formData.phone}
                  onChange={(e) => {
                    setFormData({ ...formData, phone: e.target.value });
                    if (errorMsg) setErrorMsg('');
                  }}
                  className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold focus:border-[#02471f] focus:outline-none"
                  placeholder="+91 9876543210"
                  required
                />
              </div>
            </div>
          </div>

          <div className="pt-3 flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 px-4 rounded-xl border border-slate-200 text-slate-600 text-xs font-extrabold hover:bg-slate-50 transition-all cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="flex-1 py-2.5 px-4 rounded-xl bg-[#02471f] hover:bg-[#003617] text-white text-xs font-extrabold shadow-sm transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-80"
            >
              <Save className="w-4 h-4" />
              <span>{isSaving ? 'Saving...' : 'Save Profile'}</span>
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
};

export default ProfileModal;
