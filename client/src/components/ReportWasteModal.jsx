import React, { useState } from 'react';
import { Camera, MapPin, X, CheckCircle2, Send, Crosshair } from 'lucide-react';
import { createComplaint } from '../services/complaintService';

const ReportWasteModal = ({ isOpen, onClose, user, onComplaintCreated }) => {
  const [formData, setFormData] = useState({
    location: '',
    type: 'Mixed Waste',
    description: '',
    lat: null,
    lng: null
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [locating, setLocating] = useState(false);
  const [accuracyMeter, setAccuracyMeter] = useState(null);
  const [successMsg, setSuccessMsg] = useState('');
  const [submissionError, setSubmissionError] = useState('');
  const [locationError, setLocationError] = useState('');

  if (!isOpen) return null;

  const handleDetectLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('Location access is not supported by this browser.');
      return;
    }
    setLocationError('');
    setLocating(true);
    
    const geoOptions = {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0
    };

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude, longitude, accuracy } = pos.coords;
        setAccuracyMeter(Number.isFinite(accuracy) ? Math.round(accuracy) : null);

        try {
          const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${latitude}&lon=${longitude}`);
          const data = await res.json();
          const exactAddr = data.display_name
            ? data.display_name.split(',').slice(0, 3).join(',')
            : `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;

          setFormData((prev) => ({
            ...prev,
            location: exactAddr,
            lat: latitude,
            lng: longitude
          }));
        } catch {
          setFormData((prev) => ({
            ...prev,
            location: `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`,
            lat: latitude,
            lng: longitude
          }));
        } finally {
          setLocating(false);
        }
      },
      () => {
        setLocationError('Unable to access your location. Enter a landmark or try again.');
        setLocating(false);
      },
      geoOptions
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.location) {
      setSubmissionError('Please enter a location address.');
      return;
    }
    setIsSubmitting(true);
    setSubmissionError('');
    try {
      const newComplaint = await createComplaint({
        location: formData.location,
        type: formData.type,
        ward: user?.ward || null,
        description: formData.description,
        latitude: formData.lat,
        longitude: formData.lng
      });

      setSuccessMsg(`Complaint ${newComplaint.id} submitted. Current status: ${newComplaint.status}.`);
      if (onComplaintCreated) onComplaintCreated(newComplaint);

      setTimeout(() => {
        setSuccessMsg('');
        setFormData({ location: '', type: 'Mixed Waste', description: '', lat: null, lng: null });
        setAccuracyMeter(null);
        onClose();
      }, 1400);
    } catch (error) {
      console.error('Error reporting issue:', error);
      setSubmissionError(error?.response?.data?.detail || 'Unable to submit the report. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div className="w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl border border-slate-200 relative overflow-visible">
        
        <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-[#02471f] text-white flex items-center justify-center font-bold">
              <Camera className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-slate-900">Report Waste Issue</h3>
              <p className="text-[11px] font-medium text-slate-500">Enter the actual location or use your device location</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-full bg-slate-100 text-slate-400 hover:text-slate-600 flex items-center justify-center cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {successMsg && (
          <div className="mb-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-bold text-slate-700">Location Address *</label>
              <button
                type="button"
                onClick={handleDetectLocation}
                className="text-[11px] font-bold text-[#02471f] hover:underline flex items-center gap-1 cursor-pointer"
              >
                <Crosshair className="w-3 h-3 text-emerald-600" />
                <span>{locating ? 'Acquiring GPS...' : 'GPS Hardware Precision'}</span>
              </button>
            </div>

            <div className="relative">
              <MapPin className="w-4 h-4 text-slate-400 absolute left-3 top-3 z-10" />
              <input
                type="text"
                value={formData.location}
                onChange={(e) => setFormData((prev) => ({ ...prev, location: e.target.value, lat: null, lng: null }))}
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold focus:border-[#02471f] focus:outline-none shadow-2xs"
                placeholder="Enter the actual location or landmark"
                required
              />
            </div>
            {locationError && <p role="alert" className="mt-1 text-[11px] font-semibold text-red-700">{locationError}</p>}

            {accuracyMeter && (
              <div className="mt-1 text-[10px] font-bold text-emerald-700 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                <span>Hardware GPS Sensor Locked: ±{accuracyMeter} meters precision</span>
              </div>
            )}
          </div>
          {submissionError && <p role="alert" className="rounded-lg bg-red-50 p-2 text-xs font-semibold text-red-700">{submissionError}</p>}

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Waste Category</label>
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-xs font-semibold focus:border-[#02471f] focus:outline-none bg-white"
            >
              <option value="Mixed Waste">Mixed Waste</option>
              <option value="Garbage Overflow">Garbage Overflow</option>
              <option value="Plastic Waste">Plastic Waste</option>
              <option value="E-Waste">E-Waste</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Additional Details (Optional)</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              className="w-full p-3 rounded-xl border border-slate-200 text-xs font-semibold focus:border-[#02471f] focus:outline-none"
              placeholder="Describe issue (e.g. Bin overflowing, obstruction on sidewalk)"
            />
          </div>

          <div className="pt-2 flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 px-4 rounded-xl border border-slate-200 text-slate-600 text-xs font-extrabold hover:bg-slate-50 transition-all cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 py-2.5 px-4 rounded-xl bg-[#02471f] hover:bg-[#003617] text-white text-xs font-extrabold shadow-sm transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-80"
            >
              <Send className="w-4 h-4" />
              <span>{isSubmitting ? 'Submitting...' : 'Submit Precise Report'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ReportWasteModal;
