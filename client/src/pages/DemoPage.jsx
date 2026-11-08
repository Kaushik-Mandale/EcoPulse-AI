import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  ArrowLeft, ShieldCheck, Truck, Users, LayoutDashboard, 
  MapPin, CheckCircle2, ChevronRight, Sparkles, Building2
} from 'lucide-react';

import { loginUser } from '../services/authService';

export default function DemoPage() {
  const navigate = useNavigate();

  const handleLaunchRole = async (role) => {
    try {
      if (role === 'citizen') {
        await loginUser({ email: 'priya@cityswap.io', password: 'Password123!', role: 'citizen' });
        navigate('/citizen');
      } else if (role === 'driver') {
        await loginUser({ email: 'ramesh@cityswap.io', password: 'Password123!', role: 'driver' });
        navigate('/driver');
      } else {
        await loginUser({ email: 'admin@cityswap.io', password: 'Password123!', role: 'admin' });
        navigate('/admin');
      }
    } catch (err) {
      // Fallback
      if (role === 'citizen') {
        localStorage.setItem('ecopulse_user', JSON.stringify({ id: 1, name: 'Priya Patil', email: 'priya@cityswap.io', role: 'citizen', ward: 'Ward 12', eco_coins: 350 }));
        navigate('/citizen');
      } else if (role === 'driver') {
        localStorage.setItem('ecopulse_user', JSON.stringify({ id: 2, name: 'Ramesh Yadav', email: 'ramesh@cityswap.io', role: 'driver', ward: 'Ward 12', vehicle_number: 'MH-18-BQ-4512' }));
        navigate('/driver');
      } else {
        localStorage.setItem('ecopulse_user', JSON.stringify({ id: 3, name: 'Sanitation Officer Joshi', email: 'admin@cityswap.io', role: 'admin', ward: 'All 27 Wards', designation: 'Municipal Chief Sanitation Inspector' }));
        navigate('/admin');
      }
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
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Interactive Municipal Sandbox</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Dhule Pilot Sandbox • 1-Click Role Switcher</p>
            </div>
          </div>
          <Link to="/" className="text-xs font-bold text-slate-600 hover:text-[#005C2B]">
            Back to Home
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* Pilot Overview Banner */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-xs">
          <div className="flex items-center gap-2 text-[#005C2B] font-extrabold text-xs uppercase tracking-wider mb-2">
            <Building2 className="w-4 h-4" /> Evaluator Sandbox
          </div>
          <h2 className="text-2xl sm:text-3xl font-black text-slate-900">Explore All 3 Portals Live with Zero Signup</h2>
          <p className="text-sm text-slate-600 font-medium mt-2 max-w-2xl leading-relaxed">
            As evaluated in the municipal feasibility audit, you can test every workflow end-to-end: citizen waste reporting, driver turn-by-turn route collection, and municipal commissioner administrative telemetry.
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6 pt-4 border-t border-slate-100 text-xs font-semibold text-slate-600">
            <div><span className="text-slate-400 block text-[10px] uppercase">Pilot Scenario</span> Dhule Urban Sandbox</div>
            <div><span className="text-slate-400 block text-[10px] uppercase">Population</span> ~90,000 citizens</div>
            <div><span className="text-slate-400 block text-[10px] uppercase">Wards</span> 27 Municipal Wards</div>
            <div><span className="text-slate-400 block text-[10px] uppercase">Daily Waste</span> ~45 tonnes</div>
          </div>
        </div>

        {/* 3 Portal Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* 1. Citizen */}
          <div className="bg-white rounded-3xl p-6 border border-emerald-200 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-emerald-100 text-[#005C2B] flex items-center justify-center mb-4">
                <Users className="w-6 h-6" />
              </div>
              <span className="text-[10px] font-black uppercase tracking-wider text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-md">Role: Citizen</span>
              <h3 className="text-xl font-black text-slate-900 mt-2">Citizen Portal</h3>
              <p className="text-xs text-slate-600 font-medium mt-2 leading-relaxed">
                Report waste with AI photo analysis, track complaint IDs in real-time, and manage EcoCoin reward wallet.
              </p>
            </div>
            <button
              onClick={() => handleLaunchRole('citizen')}
              className="mt-6 w-full py-3 rounded-2xl bg-[#005C2B] hover:bg-[#004a22] text-white font-extrabold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-sm transition-colors"
            >
              <span>Launch Citizen Demo</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* 2. Driver */}
          <div className="bg-white rounded-3xl p-6 border border-amber-200 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-amber-100 text-amber-700 flex items-center justify-center mb-4">
                <Truck className="w-6 h-6" />
              </div>
              <span className="text-[10px] font-black uppercase tracking-wider text-amber-800 bg-amber-50 px-2 py-0.5 rounded-md">Role: Driver / Worker</span>
              <h3 className="text-xl font-black text-slate-900 mt-2">Driver Portal</h3>
              <p className="text-xs text-slate-600 font-medium mt-2 leading-relaxed">
                View assigned collection tasks, turn-by-turn navigation on GIS map, fuel logs, and dispatch proof of collection.
              </p>
            </div>
            <button
              onClick={() => handleLaunchRole('driver')}
              className="mt-6 w-full py-3 rounded-2xl bg-amber-600 hover:bg-amber-700 text-white font-extrabold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-sm transition-colors"
            >
              <span>Launch Driver Demo</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          {/* 3. Admin */}
          <div className="bg-white rounded-3xl p-6 border border-blue-200 shadow-xs flex flex-col justify-between hover:shadow-md transition-shadow">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-blue-100 text-blue-700 flex items-center justify-center mb-4">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <span className="text-[10px] font-black uppercase tracking-wider text-blue-800 bg-blue-50 px-2 py-0.5 rounded-md">Role: Municipal Officer</span>
              <h3 className="text-xl font-black text-slate-900 mt-2">Admin Dashboard</h3>
              <p className="text-xs text-slate-600 font-medium mt-2 leading-relaxed">
                City-wide sanitation telemetry, driver dispatch, smart bin fill rates, daily tonnage analytics, and emergency broadcasts.
              </p>
            </div>
            <button
              onClick={() => handleLaunchRole('admin')}
              className="mt-6 w-full py-3 rounded-2xl bg-slate-900 hover:bg-black text-white font-extrabold text-xs flex items-center justify-center gap-2 cursor-pointer shadow-sm transition-colors"
            >
              <span>Launch Admin Demo</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Quick Links to Public Workflows */}
        <div className="bg-emerald-50/60 border border-emerald-200 rounded-3xl p-6">
          <h4 className="text-xs font-black text-emerald-900 uppercase tracking-wider mb-3">Direct Public Flows</h4>
          <div className="flex flex-wrap gap-2.5">
            <Link to="/report" className="text-xs font-bold bg-white text-slate-800 border border-emerald-200 px-3.5 py-2 rounded-xl hover:border-[#005C2B]">
              📸 Report Waste Incident
            </Link>
            <Link to="/track" className="text-xs font-bold bg-white text-slate-800 border border-emerald-200 px-3.5 py-2 rounded-xl hover:border-[#005C2B]">
              🔍 Public Reference Tracker
            </Link>
            <Link to="/map" className="text-xs font-bold bg-white text-slate-800 border border-emerald-200 px-3.5 py-2 rounded-xl hover:border-[#005C2B]">
              🗺️ City GIS Map
            </Link>
            <Link to="/wallet" className="text-xs font-bold bg-white text-slate-800 border border-emerald-200 px-3.5 py-2 rounded-xl hover:border-[#005C2B]">
              ⭐ EcoCoin Rewards
            </Link>
            <Link to="/help" className="text-xs font-bold bg-white text-slate-800 border border-emerald-200 px-3.5 py-2 rounded-xl hover:border-[#005C2B]">
              ❓ Knowledge Base & FAQ
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
