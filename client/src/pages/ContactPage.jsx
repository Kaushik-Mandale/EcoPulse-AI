import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Building2 } from 'lucide-react';

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">Contact</h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">EcoPulse AI</p>
            </div>
          </div>
          <Link to="/" className="text-xs font-bold text-slate-600 hover:text-[#005C2B]">
            Back to Home
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-12">
        <section className="bg-white rounded-3xl p-8 border border-slate-200 shadow-xs text-center">
          <div className="w-14 h-14 rounded-2xl bg-emerald-100 text-[#005C2B] flex items-center justify-center mx-auto">
            <Building2 className="w-7 h-7" />
          </div>
          <h2 className="mt-5 text-2xl font-black text-slate-900">Municipal Support</h2>
          <p className="mt-3 text-sm text-slate-600">
            Contact details and inquiry handling have not been configured. Please use your municipality's official support channel.
          </p>
        </section>
      </main>
    </div>
  );
}
