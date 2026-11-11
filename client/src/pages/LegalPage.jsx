import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, Lock, FileText } from 'lucide-react';

export default function LegalPage() {
  const location = useLocation();
  const isPrivacy = location.pathname.includes('privacy');

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 font-sans selection:bg-[#005C2B] selection:text-white">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="w-9 h-9 rounded-xl bg-[#005C2B] text-white flex items-center justify-center hover:opacity-90 transition-opacity">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-lg font-black text-slate-900 tracking-tight leading-none">
                {isPrivacy ? 'Privacy & Data Protection Policy' : 'Municipal Terms of Service'}
              </h1>
              <p className="text-xs text-emerald-700 font-bold mt-0.5">EcoPulse AI • Official Legal Terms</p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs font-bold text-slate-600">
            <Link to="/privacy" className={isPrivacy ? 'text-[#005C2B] underline' : 'hover:underline'}>Privacy</Link>
            <span>•</span>
            <Link to="/terms" className={!isPrivacy ? 'text-[#005C2B] underline' : 'hover:underline'}>Terms</Link>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-xs space-y-6 text-xs sm:text-sm text-slate-600 leading-relaxed">
          {isPrivacy ? (
            <>
              <div className="flex items-center gap-2 text-[#005C2B] font-black uppercase tracking-wider text-xs">
                <Lock className="w-4 h-4" /> Compliance with Indian DPDP Act 2023
              </div>
              <h2 className="text-2xl font-black text-slate-900">Privacy Policy</h2>
              <p>
                EcoPulse AI respects citizen privacy and is committed to protecting personal information collected through our WhatsApp agent, mobile, and web interfaces.
              </p>
              <h3 className="text-base font-extrabold text-slate-900 pt-2">1. Data We Collect</h3>
              <ul className="list-disc pl-5 space-y-1">
                <li>Geolocation coordinates shared explicitly during waste incident reporting.</li>
                <li>Photographs submitted to the AI vision pipeline to categorize waste severity.</li>
                <li>WhatsApp Phone Number or Email address used to receive status notifications.</li>
              </ul>
              <h3 className="text-base font-extrabold text-slate-900 pt-2">2. How Data is Used</h3>
              <p>
                Coordinates and waste images are shared strictly with authorized municipal staff and dispatched sanitation drivers for route clearance. We never sell, monetize, or expose citizen personal data.
              </p>
              <h3 className="text-base font-extrabold text-slate-900 pt-2">3. Data Security</h3>
              <p>
                All data transmission between the browser/WhatsApp and our FastAPI backend occurs over encrypted TLS 1.3 / HTTPS. Database records are stored securely with role-based access control.
              </p>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 text-[#005C2B] font-black uppercase tracking-wider text-xs">
                <FileText className="w-4 h-4" /> Municipal Service Agreement
              </div>
              <h2 className="text-2xl font-black text-slate-900">Terms of Service</h2>
              <p>
                By using EcoPulse AI platform services, you agree to the following terms and guidelines established for municipal sanitation operations.
              </p>
              <h3 className="text-base font-extrabold text-slate-900 pt-2">1. Citizen Reporting Responsibilities</h3>
              <p>
                Reports must be made in good faith with authentic photographs of waste incidents located within municipal jurisdictions. Fraudulent submissions or false reports may result in account suspension.
              </p>
              <h3 className="text-base font-extrabold text-slate-900 pt-2">2. EcoCoin Rewards Policy</h3>
              <p>
                EcoCoins are municipal gamification points and hold no real financial or cryptocurrency value. They may be redeemed solely against approved partner rewards and civic rebates as defined by the municipal council.
              </p>
              <h3 className="text-base font-extrabold text-slate-900 pt-2">3. Service Level Agreemements (SLA)</h3>
              <p>
                Target clearance times (e.g. 4–24 hours) depend on municipal fleet availability, weather conditions, and incident severity tiering.
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
