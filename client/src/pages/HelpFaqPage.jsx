import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Search, HelpCircle, ChevronDown, ChevronUp, MessageSquare, Phone, Mail } from 'lucide-react';

const FAQS = [
  {
    q: 'What is EcoPulse AI and how does it work in Dhule?',
    a: 'EcoPulse AI is a smart waste management platform connecting citizens, sanitation drivers, and municipal officers. Citizens report waste via WhatsApp or Web, AI automatically validates the photo and location, and dispatches the nearest ghantagadi driver for resolution.'
  },
  {
    q: 'कचरा तक्रार कशी नोंदवावी? (How to report waste?)',
    a: 'नागरिक WhatsApp वरून थेट कचऱ्याचा फोटो व लोकेशन पाठवून किंवा या वेबसाइटवरील "Report Waste" बटणावर क्लिक करून तक्रार नोंदवू शकतात. AI तक्रार तपासून आपोआप EP-2026 क्रमांकाची पावती देईल.'
  },
  {
    q: 'What are EcoCoins and how can I redeem them?',
    a: 'EcoCoins are reward points granted to citizens for verified waste reports (+25 coins) and community cleanliness participation. Coins can be redeemed for municipal property tax rebates, city transit passes, and organic compost kits.'
  },
  {
    q: 'How does live garbage truck (Ghantagadi) tracking work?',
    a: 'Each municipal vehicle is equipped with GPS telemetry. When you view the City GIS Map or check tracking via your complaint ID, the platform computes estimated arrival time (ETA) based on active route progress in your ward.'
  },
  {
    q: 'What should I do for emergency hazardous or dead animal waste?',
    a: 'For urgent hazardous waste, select "Hazardous / Medical Waste" in the report form or call the municipal emergency helpline or contact support@ecopulse.ai for platform assistance.'
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
              <p className="text-xs text-emerald-700 font-bold mt-0.5">Municipal Sanitation FAQ & Contact</p>
            </div>
          </div>
          <a
            href="https://wa.me/?text=Hi%20EcoPulse%20Support"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-bold bg-[#25D366] text-white px-3.5 py-2 rounded-xl hover:bg-[#20bd5a] flex items-center gap-1.5"
          >
            <MessageSquare className="w-3.5 h-3.5" /> WhatsApp Support
          </a>
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

        {/* Contact info card */}
        <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-xs flex flex-wrap items-center justify-between gap-4">
          <div>
            <h4 className="text-sm font-black text-slate-900">Still have questions?</h4>
            <p className="text-xs text-slate-500 font-semibold mt-0.5">Contact the EcoPulse AI pilot support team</p>
          </div>
          <div className="flex items-center gap-3 text-xs font-bold">
            <a href="tel:18002330123" className="flex items-center gap-1.5 text-[#005C2B] bg-emerald-50 px-3.5 py-2 rounded-xl border border-emerald-200 hover:bg-emerald-100">
              <Phone className="w-3.5 h-3.5" /> 1800-233-0123
            </a>
            <a href="mailto:support@ecopulse.ai" className="flex items-center gap-1.5 text-slate-700 bg-slate-100 px-3.5 py-2 rounded-xl hover:bg-slate-200">
              <Mail className="w-3.5 h-3.5" /> support@ecopulse.ai
            </a>
          </div>
        </div>
      </main>
    </div>
  );
}
