import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Search, HelpCircle, ChevronDown, ChevronUp, MessageSquare } from 'lucide-react';

const FAQS = [
  {
    q: 'What can I do with EcoPulse AI?',
    a: 'Citizens can submit waste complaints and check their current status using a complaint reference. Submitted reports are made available through the municipal workflows enabled for this deployment.'
  },
  {
    q: 'कचरा तक्रार कशी नोंदवावी? (How to report waste?)',
    a: 'वेबसाइटवरील "Report Waste" वापरून तक्रारीची माहिती द्या. उपलब्ध असल्यास स्थान आणि फोटो जोडा. तक्रार नोंदवल्यानंतर मिळालेला संदर्भ क्रमांक जतन करा. (Use "Report Waste" on this website, add a location or photo when available, and save the reference shown after submission.)'
  },
  {
    q: 'What are EcoCoins and how can I redeem them?',
    a: 'The wallet displays the EcoCoin balance stored on your profile when available. Reward issuance, redemption, and transaction history are not configured in this application.'
  },
  {
    q: 'How does live garbage truck (Ghantagadi) tracking work?',
    a: 'The map displays submitted complaints that include coordinates. Live vehicle GPS, route progress, and estimated arrival times are not available in this interface.'
  },
  {
    q: 'What should I do for emergency hazardous or dead animal waste?',
    a: 'This application is not an emergency service. For urgent hazardous-waste issues, use your municipality’s official emergency or support channel.'
  }
];

export default function HelpFaqPage() {
  const [search, setSearch] = useState('');
  const [openIdx, setOpenIdx] = useState(0);

  const filtered = FAQS.filter(f => f.q.toLowerCase().includes(search.toLowerCase()) || f.a.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Help & Support Center</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Common platform questions</p>
            </div>
          </div>
          <Link to="/contact" className="text-xs font-bold bg-[#005C2B] text-white px-3.5 py-2 rounded-xl hover:bg-[#004a22] flex items-center gap-1.5">
            <MessageSquare className="w-3.5 h-3.5" /> Contact options
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-6">
        <div className="relative">
          <input 
            type="text" 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search FAQs (e.g. EcoCoins, ghantagadi, complaint, ward timing)..."
            className="w-full pl-10 pr-4 py-3 rounded-2xl border border-slate-200 bg-white text-sm font-semibold focus:outline-none focus:border-[#005C2B]"
          />
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
        </div>

        <div className="space-y-3">
          {filtered.map((item, idx) => (
            <div key={idx} className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-2xs">
              <button 
                onClick={() => setOpenIdx(openIdx === idx ? -1 : idx)}
                className="w-full px-5 py-4 text-left font-bold text-sm text-slate-900 flex items-center justify-between gap-4 cursor-pointer hover:bg-slate-50 transition-colors"
              >
                <span>{item.q}</span>
                {openIdx === idx ? <ChevronUp className="w-4 h-4 text-emerald-700 shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />}
              </button>
              {openIdx === idx && (
                <div className="px-5 pb-4 text-xs font-semibold text-slate-600 leading-relaxed border-t border-slate-100 pt-3 bg-slate-50/50">
                  {item.a}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-4">
          <div>
            <h4 className="text-sm font-black text-slate-900">Still have questions?</h4>
            <p className="text-xs text-slate-500 font-semibold mt-0.5">Use your municipality’s official support channel.</p>
          </div>
          <Link to="/contact" className="text-xs font-bold text-[#005C2B] bg-emerald-50 px-3.5 py-2 rounded-xl border border-emerald-200 hover:bg-emerald-100">
            View contact options
          </Link>
        </div>
      </main>
    </div>
  );
}
