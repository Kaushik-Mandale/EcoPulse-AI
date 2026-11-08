import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Bell, CheckCircle2, AlertTriangle, Info, Truck } from 'lucide-react';
import api from '../services/api';

const BROADCASTS = [
  { id: 1, type: 'urgent', title: 'Ward 12 Intensive Cleanliness Drive Active', desc: '4 additional compactors deployed near Green Park and Nimzari Naka.', date: 'Today, 07:00 AM' },
  { id: 2, type: 'info', title: 'Monsoon Waste Segregation Advisory', desc: 'Please ensure separate wet waste containers to prevent drain clogs during rainfall.', date: 'Yesterday' },
  { id: 3, type: 'success', title: 'Simulated Ward Clearance Demonstration Hits 92% SLA', desc: 'Pilot scenario: 42 tonnes of simulated segregated solid waste logged on schedule.', date: '08 Sep 2026' },
];

export default function NotificationsPage() {
  const [alerts, setAlerts] = useState(BROADCASTS);

  useEffect(() => {
    api.get('/notifications')
      .then(res => {
        if (Array.isArray(res.data) && res.data.length > 0) {
          const mapped = res.data.map(n => ({
            id: n.id,
            type: n.priority?.toLowerCase().includes('emergency') ? 'urgent' : 'info',
            title: n.title,
            desc: n.message,
            date: n.created_at ? new Date(n.created_at).toLocaleDateString() : 'Recent'
          }));
          setAlerts([...mapped, ...BROADCASTS]);
        }
      })
      .catch(err => console.warn('Could not load live alerts:', err));
  }, []);
  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Municipal Civic Alerts</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Broadcasts & Sanitation Notices</p>
            </div>
          </div>
          <Link to="/" className="text-xs font-bold text-slate-600 hover:text-[#005C2B]">Home</Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-4">
        {alerts.map((item) => (
          <div key={item.id} className="bg-white rounded-2xl p-5 border border-slate-200 shadow-2xs flex items-start gap-4">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
              item.type === 'urgent' ? 'bg-amber-100 text-amber-700' : item.type === 'success' ? 'bg-emerald-100 text-emerald-700' : 'bg-blue-100 text-blue-700'
            }`}>
              {item.type === 'urgent' ? <AlertTriangle className="w-5 h-5" /> : item.type === 'success' ? <CheckCircle2 className="w-5 h-5" /> : <Info className="w-5 h-5" />}
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <h3 className="font-extrabold text-sm text-slate-900">{item.title}</h3>
                <span className="text-[11px] font-semibold text-slate-400">{item.date}</span>
              </div>
              <p className="text-xs text-slate-600 font-medium mt-1 leading-relaxed">{item.desc}</p>
            </div>
          </div>
        ))}
      </main>
    </div>
  );
}
