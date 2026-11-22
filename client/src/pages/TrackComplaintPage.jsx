import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Search, ArrowLeft, CheckCircle2, Clock, MapPin, AlertCircle
} from 'lucide-react';
import api from '../services/api';

export default function TrackComplaintPage() {
  const { id } = useParams();
  const [searchId, setSearchId] = useState(id || '');
  const [trackingToken] = useState(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    return fragment.get('token') || '';
  });
  const [complaint, setComplaint] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleSearch = async (targetId) => {
    const query = (targetId || searchId).trim();
    if (!query) return;
    setLoading(true);
    setErrorMsg('');

    try {
      const res = await api.get(`/complaints/track/${encodeURIComponent(query)}`, {
        headers: trackingToken ? { 'X-Tracking-Token': trackingToken } : undefined,
      });
      const found = res.data;
      setComplaint({
        ...found,
        steps: [
          { name: 'Report received', time: found.created_at || 'Recorded', done: true },
          { name: 'Work in progress', time: found.status === 'Pending' ? 'Pending' : found.status, done: ['In Progress', 'Completed'].includes(found.status) },
          { name: 'Resolved', time: found.status === 'Completed' ? 'Completed' : 'Pending', done: found.status === 'Completed' },
        ]
      });
    } catch (error) {
      setComplaint(null);
      setErrorMsg(error.response?.status === 404
        ? 'No complaint matched that reference, or this secure tracking link is invalid. Open the original tracking link or sign in to view your own complaint.'
        : error.response?.data?.detail || 'Complaint status is unavailable. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) {
      setSearchId(id);
      handleSearch(id);
    }
  }, [id]);

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Track Complaint Status</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Complaint Status Tracker • Dhule Pilot</p>
            </div>
          </div>
          <Link to="/report" className="text-xs font-bold bg-[#005C2B] text-white px-3.5 py-2 rounded-xl hover:bg-[#004a22] transition-colors">
            + New Report
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        {/* Search Bar */}
        <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-xs mb-6">
          <label className="block text-xs font-extrabold text-slate-700 mb-2 uppercase tracking-wider">
            Enter Complaint Tracking Reference ID
          </label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input 
                type="text" 
                value={searchId}
                onChange={(e) => setSearchId(e.target.value)}
                placeholder="e.g. EP-2026-00123"
                className="w-full pl-10 pr-4 py-3 rounded-2xl border border-slate-200 bg-slate-50 text-sm font-mono font-bold focus:outline-none focus:border-[#005C2B] focus:bg-white"
              />
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
            </div>
            <button
              onClick={() => handleSearch(searchId)}
              disabled={loading}
              className="bg-[#005C2B] hover:bg-[#004a22] text-white font-bold px-6 py-3 rounded-2xl text-sm shadow-sm transition-all cursor-pointer"
            >
              {loading ? 'Searching...' : 'Track'}
            </button>
          </div>

        </div>

        {/* Complaint Details Card */}
        {complaint && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-xs space-y-6"
          >
            {/* Header Badge & ID */}
            <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-slate-100">
              <div>
                <span className="text-[11px] font-extrabold text-slate-400 uppercase tracking-widest block">Complaint Reference</span>
                <h2 className="text-2xl font-black text-slate-900 font-mono mt-0.5">{complaint.id}</h2>
                <p className="text-xs text-slate-500 font-semibold mt-1 flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  {complaint.location || complaint.location_address || 'Location unavailable'}
                </p>
              </div>

              <div className="text-right">
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-black uppercase tracking-wider ${
                  complaint.status === 'Completed'
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-amber-100 text-amber-800'
                }`}>
                  {complaint.status === 'Completed' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Clock className="w-3.5 h-3.5" />}
                  {complaint.status}
                </span>
                <p className="text-[11px] text-slate-400 font-bold mt-1">Logged: {complaint.created_at || 'Today'}</p>
              </div>
            </div>

            {/* Quick Metrics Bar */}
            <div className="grid grid-cols-2 gap-3 bg-slate-50 p-4 rounded-2xl border border-slate-200/70 text-xs">
              <div>
                <span className="text-slate-400 font-bold block text-[10px] uppercase">Category</span>
                <span className="font-extrabold text-slate-800">{complaint.type || complaint.waste_type}</span>
              </div>
              <div>
                <span className="text-slate-400 font-bold block text-[10px] uppercase">Ward Jurisdiction</span>
                <span className="font-extrabold text-slate-800">{complaint.ward || '—'}</span>
              </div>
            </div>

            {/* Timeline Progress */}
            <div>
              <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider mb-4">
                Resolution Timeline
              </h3>
              <div className="space-y-4">
                {(complaint.steps || []).map((step, idx) => (
                  <div key={idx} className="flex items-start gap-3.5">
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
                      step.done 
                        ? 'bg-[#005C2B] text-white' 
                        : 'bg-slate-100 text-slate-400 border border-slate-300'
                    }`}>
                      {step.done ? <CheckCircle2 className="w-4 h-4" /> : <Clock className="w-4 h-4" />}
                    </div>
                    <div className="flex-1 pb-1">
                      <div className="flex items-center justify-between">
                        <span className={`text-sm font-bold ${step.done ? 'text-slate-900' : 'text-slate-500'}`}>
                          {step.name}
                        </span>
                        <span className="text-xs font-semibold text-slate-400 font-mono">{step.time}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 text-xs font-semibold text-slate-500">
              This status reflects the information currently recorded for this complaint.
            </div>
          </motion.div>
        )}
      </main>
    </div>
  );
}
