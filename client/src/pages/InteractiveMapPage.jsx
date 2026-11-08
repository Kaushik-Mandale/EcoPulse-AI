import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, MapPin, Truck, AlertTriangle, Info, MessageSquare } from 'lucide-react';
import InteractiveMap from '../components/InteractiveMap';

export default function InteractiveMapPage() {
  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white flex flex-col">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">City GIS & Live Fleet Tracking</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Dhule Pilot Region • 27 Wards Simulated Telemetry</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/report" className="text-xs font-bold bg-[#005C2B] text-white px-3.5 py-2 rounded-xl hover:bg-[#004a22] transition-colors">
              + Report Waste
            </Link>
            <Link to="/demo" className="text-xs font-bold text-slate-700 border border-slate-200 bg-white px-3.5 py-2 rounded-xl hover:bg-slate-50 transition-colors">
              Demo Switcher
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-4 flex flex-col gap-4">
        {/* Status Indicators Banner */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 text-[#005C2B] flex items-center justify-center font-bold">
              <Truck className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">Active Vehicles</span>
              <p className="text-lg font-black text-slate-900">8 In Service</p>
            </div>
          </div>

          <div className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-bold">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">Smart Bins Monitored</span>
              <p className="text-lg font-black text-slate-900">142 Telemetry Sensors</p>
            </div>
          </div>

          <div className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center font-bold">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">Reported Hotspots</span>
              <p className="text-lg font-black text-slate-900">5 Clearance Queued</p>
            </div>
          </div>

          <div className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold">
              🌱
            </div>
            <div>
              <span className="text-[11px] font-bold text-slate-400 uppercase">Route Efficiency</span>
              <p className="text-lg font-black text-slate-900">92% On-Schedule</p>
            </div>
          </div>
        </div>

        {/* Map Container */}
        <div className="flex-1 min-h-[550px] bg-white rounded-3xl border border-slate-200 shadow-xs overflow-hidden p-1">
          <InteractiveMap role="admin" />
        </div>
      </main>
    </div>
  );
}
