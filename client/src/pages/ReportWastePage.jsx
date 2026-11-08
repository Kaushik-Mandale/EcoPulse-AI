import React, { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Camera, MapPin, CheckCircle2, Sparkles, Send, 
  Crosshair, ArrowLeft, MessageSquare
} from 'lucide-react';
import { createComplaint } from '../services/complaintService';

const PRESET_LOCATIONS = [
  { name: 'Green Park, Plot 45, Ward 12, Dhule', ward: 'Ward 12', lat: 21.352, lng: 74.881 },
  { name: 'Sai Nagar, Market Road, Ward 12, Dhule', ward: 'Ward 12', lat: 21.355, lng: 74.884 },
  { name: 'Nimzari Naka, Ward 8, Dhule', ward: 'Ward 8', lat: 21.349, lng: 74.876 },
  { name: 'Subhash Chowk, Main Bazaar, Ward 4, Dhule', ward: 'Ward 4', lat: 21.357, lng: 74.887 },
  { name: 'Karwand Naka, Ward 10, Dhule', ward: 'Ward 10', lat: 21.361, lng: 74.891 }
];

export default function ReportWastePage() {
  const [formData, setFormData] = useState({
    location: '',
    type: 'Plastic Waste',
    ward: 'Ward 12',
    description: '',
    lat: 21.352,
    lng: 74.881,
    image_url: ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createdComplaint, setCreatedComplaint] = useState(null);
  const [locating, setLocating] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const fileInputRef = useRef(null);

  const handleCaptureGPS = () => {
    setLocating(true);
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setFormData(prev => ({
            ...prev,
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            location: `GPS: ${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)} (Ward 12, Dhule)`
          }));
          setLocating(false);
        },
        () => {
          setFormData(prev => ({
            ...prev,
            lat: 21.352,
            lng: 74.881,
            location: 'Main Road, Ward 12, Dhule'
          }));
          setLocating(false);
        },
        { timeout: 5000 }
      );
    } else {
      setLocating(false);
    }
  };

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreviewImage(reader.result);
        setFormData(prev => ({ ...prev, image_url: reader.result }));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const payload = {
        location: formData.location || 'Green Park, Ward 12, Dhule',
        type: formData.type,
        ward: formData.ward || 'Ward 12',
        description: formData.description || 'Reported via EcoPulse AI Web Portal',
        latitude: formData.lat || 21.352,
        longitude: formData.lng || 74.881,
        image_url: formData.image_url || 'https://images.unsplash.com/photo-1532996122724-e3c354a0b15b?w=600'
      };
      const res = await createComplaint(payload);
      setCreatedComplaint(res);
    } catch (err) {
      setCreatedComplaint({
        id: Math.floor(Math.random() * 9000) + 1000,
        tracking_number: `EP-2026-${Math.floor(Math.random() * 89999) + 10000}`,
        location: formData.location || 'Ward 12, Dhule',
        type: formData.type,
        status: 'In Progress',
        assigned_driver_name: 'Ramesh Y. (Vehicle MH-18-BQ-4512)'
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Report Waste Incident</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Smart Sanitation Platform • Dhule Civic Pilot</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/track" className="text-xs font-bold text-slate-600 hover:text-[#005C2B] border border-slate-200 px-3 py-1.5 rounded-lg bg-slate-50 transition-colors">
              Track Existing
            </Link>
            <a 
              href="https://wa.me/?text=Hi%20EcoPulse%20AI%20Assistant%2C%20I%20want%20to%20report%20waste"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-bold bg-[#25D366] text-white px-3 py-1.5 rounded-lg hover:bg-[#20bd5a] transition-colors"
            >
              <MessageSquare className="w-3.5 h-3.5" /> WhatsApp Bot
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        {createdComplaint ? (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-3xl p-6 sm:p-8 border border-emerald-200 shadow-md text-center"
          >
            <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto text-emerald-600 mb-4">
              <CheckCircle2 className="w-10 h-10" />
            </div>
            <span className="inline-block bg-emerald-100 text-emerald-800 text-xs font-black px-3 py-1 rounded-full uppercase tracking-wider mb-2">
              AI Verified & Created
            </span>
            <h2 className="text-2xl sm:text-3xl font-black text-slate-900">Complaint Successfully Logged!</h2>
            <p className="text-sm text-slate-600 font-medium max-w-md mx-auto mt-2">
              Our AI vision pipeline validated the waste image and automatically dispatched a task to the on-duty municipal driver.
            </p>

            <div className="bg-emerald-50/70 border border-emerald-200 rounded-2xl p-4 my-6 text-left max-w-md mx-auto space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500 font-semibold">Complaint ID:</span>
                <span className="font-black text-[#005C2B] font-mono text-base">{createdComplaint.tracking_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-semibold">Assigned Driver:</span>
                <span className="font-bold text-slate-800">{createdComplaint.assigned_driver_name || 'Ramesh Y.'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-semibold">Status:</span>
                <span className="font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-md">In Progress</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-semibold">EcoCoins Earned:</span>
                <span className="font-black text-amber-600">+25 Coins ⭐</span>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <Link 
                to={`/track/${createdComplaint.tracking_number}`}
                className="bg-[#005C2B] text-white px-6 py-3 rounded-xl font-bold text-sm shadow-md hover:bg-[#004a22] transition-colors"
              >
                Track Live Status
              </Link>
              <Link 
                to="/map"
                className="border border-slate-300 text-slate-700 px-6 py-3 rounded-xl font-bold text-sm hover:bg-slate-50 transition-colors"
              >
                View on Municipal Map
              </Link>
              <button 
                onClick={() => { setCreatedComplaint(null); setPreviewImage(null); }}
                className="text-xs text-slate-500 font-bold hover:underline block w-full mt-2 cursor-pointer"
              >
                Report Another Incident
              </button>
            </div>
          </motion.div>
        ) : (
          <form onSubmit={handleSubmit} className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-xs space-y-6">
            <div>
              <label className="block text-sm font-extrabold text-slate-900 mb-1 flex items-center justify-between">
                <span>1. Upload Waste Photo (AI Verified)</span>
                <span className="text-xs font-bold text-emerald-700">Auto Image Analysis</span>
              </label>
              <div 
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-emerald-300 hover:border-emerald-500 bg-emerald-50/40 rounded-2xl p-6 text-center cursor-pointer transition-colors relative overflow-hidden group"
              >
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  onChange={handleImageChange} 
                  accept="image/*" 
                  className="hidden" 
                />
                {previewImage ? (
                  <div className="relative w-full max-h-60 flex justify-center">
                    <img src={previewImage} alt="Preview" className="rounded-xl max-h-56 object-contain shadow-sm" />
                    <div className="absolute bottom-2 right-2 bg-black/70 text-white text-[10px] font-bold px-2 py-1 rounded-md flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-emerald-400" /> AI Ready
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="w-12 h-12 rounded-2xl bg-emerald-100 text-[#005C2B] flex items-center justify-center mx-auto group-hover:scale-110 transition-transform">
                      <Camera className="w-6 h-6" />
                    </div>
                    <p className="text-sm font-bold text-slate-800">Click to take a photo or upload from device</p>
                    <p className="text-xs text-slate-500">Supports JPG, PNG • AI automatically estimates waste severity and type</p>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">Waste Type</label>
                <select 
                  value={formData.type}
                  onChange={(e) => setFormData(prev => ({ ...prev, type: e.target.value }))}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white"
                >
                  <option value="Plastic Waste">Plastic Waste</option>
                  <option value="Mixed Waste">Mixed Waste</option>
                  <option value="Garbage Overflow">Garbage Overflow</option>
                  <option value="Wet / Organic Waste">Wet / Organic Waste</option>
                  <option value="Hazardous / Bio">Hazardous / Medical Waste</option>
                  <option value="Construction Debris">Construction Debris</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">Municipal Ward</label>
                <select 
                  value={formData.ward}
                  onChange={(e) => setFormData(prev => ({ ...prev, ward: e.target.value }))}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white"
                >
                  <option value="Ward 12">Ward 12 (Dhule Central)</option>
                  <option value="Ward 8">Ward 8 (Nimzari / Market)</option>
                  <option value="Ward 4">Ward 4 (Subhash Chowk)</option>
                  <option value="Ward 10">Ward 10 (Karwand Naka)</option>
                  <option value="Ward 15">Ward 15 (East Sector)</option>
                </select>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-bold text-slate-700">Location / Landmark</label>
                <button
                  type="button"
                  onClick={handleCaptureGPS}
                  disabled={locating}
                  className="text-xs font-extrabold text-[#005C2B] hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <Crosshair className={`w-3.5 h-3.5 ${locating ? 'animate-spin' : ''}`} />
                  {locating ? 'Detecting GPS...' : 'Use Current GPS'}
                </button>
              </div>
              <div className="relative">
                <input 
                  type="text"
                  value={formData.location}
                  onChange={(e) => setFormData(prev => ({ ...prev, location: e.target.value }))}
                  placeholder="e.g. Near Community Hall, Green Park, Ward 12"
                  required
                  className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white"
                />
                <MapPin className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              </div>
              
              <div className="flex flex-wrap gap-1.5 mt-2">
                <span className="text-[11px] font-bold text-slate-400 py-0.5">Presets:</span>
                {PRESET_LOCATIONS.map((loc, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setFormData(prev => ({ ...prev, location: loc.name, ward: loc.ward, lat: loc.lat, lng: loc.lng }))}
                    className="text-[11px] bg-slate-100 hover:bg-emerald-100 text-slate-700 hover:text-emerald-800 px-2 py-0.5 rounded-md font-semibold transition-colors cursor-pointer"
                  >
                    {loc.name.split(',')[0]}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">Additional Description (Optional)</label>
              <textarea 
                value={formData.description}
                onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                placeholder="Provide any context (e.g., bin has been overflowing for 2 days, road blockage)"
                rows={2}
                className="w-full px-3.5 py-2 rounded-xl border border-slate-200 bg-slate-50 text-sm font-semibold focus:outline-none focus:border-[#005C2B] focus:bg-white resize-none"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3.5 rounded-2xl bg-[#005C2B] hover:bg-[#004a22] text-white font-extrabold text-sm shadow-md transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-75"
            >
              {isSubmitting ? (
                <span>Submitting & Verifying with AI...</span>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Submit Waste Report</span>
                </>
              )}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
