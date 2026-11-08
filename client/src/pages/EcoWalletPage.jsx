import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Coins, Gift, ArrowLeft, CheckCircle2, TrendingUp, 
  Award, ShieldCheck, ShoppingBag, Sparkles, AlertCircle
} from 'lucide-react';
import { getCurrentUser, updateUserProfile } from '../services/authService';

const REWARD_ITEMS = [
  { id: 1, title: '10% Municipal Property Tax Rebate', cost: 500, category: 'Civic Rebate', partner: 'Civic Rewards Demo Partner' },
  { id: 2, title: '1 Month Free City Bus Transit Pass', cost: 300, category: 'Public Transit', partner: 'Public Transit Demo Partner' },
  { id: 3, title: '5kg Certified Organic Compost Kit', cost: 150, category: 'Sustainability', partner: 'Community Compost Demo Partner' },
  { id: 4, title: '₹100 Solar Utility Energy Voucher', cost: 250, category: 'Clean Energy', partner: 'MSEDCL Clean Energy' },
];

const TRANSACTIONS = [
  { id: 101, title: 'Verified Waste Incident Reported', ward: 'Ward 12', points: '+25', date: 'Today, 09:15 AM', type: 'credit' },
  { id: 102, title: 'Community Plastic Cleanup Drive', ward: 'Ward 8', points: '+50', date: 'Yesterday', type: 'credit' },
  { id: 103, title: 'Segregated Waste Morning Deposit', ward: 'Ward 12', points: '+15', date: '08 Sep 2026', type: 'credit' },
  { id: 104, title: 'Redeemed Organic Compost Kit', ward: 'Self', points: '-150', date: '01 Sep 2026', type: 'debit' },
];

export default function EcoWalletPage() {
  const [balance, setBalance] = useState(350);
  const [redeemed, setRedeemed] = useState([]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const savedUser = localStorage.getItem('ecopulse_user');
    if (savedUser) {
      try {
        const u = JSON.parse(savedUser);
        if (u.eco_coins !== undefined) setBalance(u.eco_coins);
      } catch (e) {}
    }
    getCurrentUser().then(u => {
      if (u?.eco_coins !== undefined) setBalance(u.eco_coins);
    });
  }, []);

  const handleRedeem = (item) => {
    if (balance < item.cost) {
      setMessage(`Insufficient EcoCoins! You need ${item.cost - balance} more coins.`);
      setTimeout(() => setMessage(''), 3000);
      return;
    }
    const newBal = balance - item.cost;
    setBalance(newBal);
    setRedeemed(prev => [...prev, item.id]);
    setMessage(`Successfully redeemed voucher for "${item.title}"! Voucher code: DHULE-${Math.floor(Math.random() * 89999 + 10000)}`);
    setTimeout(() => setMessage(''), 5000);
    updateUserProfile({ eco_coins: newBal });
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
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">EcoCoin Rewards & Wallet</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Citizen Cleanliness Gamification • Dhule Pilot</p>
            </div>
          </div>
          <Link to="/report" className="text-xs font-bold bg-[#005C2B] text-white px-3.5 py-2 rounded-xl hover:bg-[#004a22] transition-colors">
            Earn Coins
          </Link>
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
              <h2 className="text-4xl sm:text-5xl font-black tracking-tight">{balance}</h2>
              <span className="text-xl font-bold text-emerald-200">EcoCoins</span>
            </div>
            <p className="text-xs text-emerald-100/80 font-semibold mt-2">
              Earned by reporting waste, segregating dry/wet garbage, and participating in municipal cleanliness drives.
            </p>

            <div className="flex flex-wrap items-center gap-3 mt-6">
              <Link 
                to="/report" 
                className="bg-white text-[#005C2B] px-5 py-2.5 rounded-xl font-black text-xs hover:bg-emerald-50 transition-colors shadow-sm"
              >
                + Report Waste (+25 Coins)
              </Link>
              <Link 
                to="/demo" 
                className="bg-emerald-800/80 border border-emerald-600 text-white px-5 py-2.5 rounded-xl font-bold text-xs hover:bg-emerald-700 transition-colors"
              >
                Explore Demo Hub
              </Link>
            </div>
          </div>
        </div>

        {message && (
          <div className="p-4 rounded-2xl bg-emerald-100 border border-emerald-300 text-emerald-900 text-sm font-bold flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-emerald-700 shrink-0" />
            <span>{message}</span>
          </div>
        )}

        {/* Rewards Catalog */}
        <div>
          <h3 className="text-lg font-black text-slate-900 tracking-tight mb-3 flex items-center gap-2">
            <Gift className="w-5 h-5 text-[#005C2B]" /> Municipal Reward Redemption Catalog
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {REWARD_ITEMS.map((item) => {
              const isRedeemed = redeemed.includes(item.id);
              return (
                <div 
                  key={item.id} 
                  className="bg-white rounded-2xl p-5 border border-slate-200 shadow-2xs flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="font-extrabold text-emerald-700 uppercase text-[10px] tracking-wider">{item.category}</span>
                      <span className="font-black text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md">{item.cost} Coins</span>
                    </div>
                    <h4 className="font-extrabold text-slate-900 text-sm leading-snug">{item.title}</h4>
                    <p className="text-xs text-slate-500 font-semibold mt-1">Partner: {item.partner}</p>
                  </div>

                  <button
                    onClick={() => handleRedeem(item)}
                    disabled={isRedeemed || balance < item.cost}
                    className={`w-full mt-4 py-2.5 rounded-xl text-xs font-bold transition-colors cursor-pointer ${
                      isRedeemed 
                        ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                        : balance >= item.cost 
                          ? 'bg-[#005C2B] text-white hover:bg-[#004a22]'
                          : 'bg-slate-100 text-slate-400 hover:bg-slate-200'
                    }`}
                  >
                    {isRedeemed ? '✓ Voucher Redeemed' : balance >= item.cost ? 'Redeem Voucher' : `Needs ${item.cost - balance} more coins`}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Transactions Ledger */}
        <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-xs">
          <h3 className="text-xs font-black text-slate-900 uppercase tracking-wider mb-4">
            Recent EcoCoin Transactions
          </h3>
          <div className="space-y-3">
            {TRANSACTIONS.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0 text-sm">
                <div>
                  <p className="font-bold text-slate-800">{tx.title}</p>
                  <p className="text-xs text-slate-400 font-semibold">{tx.ward} • {tx.date}</p>
                </div>
                <span className={`font-black font-mono text-base ${
                  tx.type === 'credit' ? 'text-emerald-700' : 'text-slate-600'
                }`}>
                  {tx.points}
                </span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
