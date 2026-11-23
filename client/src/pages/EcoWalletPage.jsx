import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Coins, ArrowLeft, AlertCircle
} from 'lucide-react';
import { getCurrentUser } from '../services/authService';

export default function EcoWalletPage() {
  const [balance, setBalance] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((user) => {
        if (!active) return;
        if (Number.isFinite(user?.eco_coins)) setBalance(user.eco_coins);
        else setError('Wallet balance is not available for this account.');
      })
      .catch(() => {
        if (active) setError('Wallet balance is temporarily unavailable.');
      });
    return () => { active = false; };
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
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Wallet Status</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">EcoPulse AI citizen wallet</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* Wallet Hero Card */}
        <div className="bg-gradient-to-br from-[#005C2B] via-[#004a22] to-emerald-900 rounded-3xl p-6 sm:p-8 text-white shadow-lg relative overflow-hidden">
          <div className="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
            <Coins className="w-64 h-64 text-white" />
          </div>

          <div className="relative z-10 max-w-md">
            <span className="inline-block bg-white/20 backdrop-blur-xs text-emerald-100 text-[11px] font-black px-3 py-1 rounded-full uppercase tracking-wider mb-3">
              Citizen Balance
            </span>
            <div className="flex items-baseline gap-3">
              <h2 className="text-4xl sm:text-5xl font-black tracking-tight">{balance ?? '—'}</h2>
              <span className="text-xl font-bold text-emerald-200">Recorded Balance</span>
            </div>
            <p className="text-xs text-emerald-100/80 font-semibold mt-2">
              Your account balance is read from your EcoPulse AI profile.
            </p>

            <div className="flex flex-wrap items-center gap-3 mt-6">
              <Link 
                to="/report" 
                className="bg-white text-[#005C2B] px-5 py-2.5 rounded-xl font-black text-xs hover:bg-emerald-50 transition-colors shadow-sm"
              >
                Report Waste
              </Link>
              <Link
                to="/login"
                className="bg-emerald-800/80 border border-emerald-600 text-white px-5 py-2.5 rounded-xl font-bold text-xs hover:bg-emerald-700 transition-colors"
              >
                Sign in
              </Link>
            </div>
          </div>
        </div>

        {error && (
          <div role="status" className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 text-sm font-semibold flex items-center gap-2">
            <AlertCircle className="w-5 h-5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-xs">
          <h3 className="text-lg font-black text-slate-900">Rewards and transaction history</h3>
          <p className="mt-2 text-sm text-slate-600">
            Reward issuance, redemption, and transaction history are not supported. No rewards are issued automatically.
          </p>
        </div>
      </main>
    </div>
  );
}
