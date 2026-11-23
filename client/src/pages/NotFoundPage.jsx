import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Home, Search, HelpCircle } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen bg-[#f8faf9] flex items-center justify-center p-4 font-sans text-slate-800">
      <div className="max-w-md w-full bg-white rounded-3xl p-8 border border-slate-200 shadow-md text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-emerald-100 text-[#005C2B] font-black text-2xl flex items-center justify-center mx-auto">
          404
        </div>
        <h1 className="text-2xl font-black text-slate-900">Page Not Found</h1>
        <p className="text-xs text-slate-600 font-medium leading-relaxed">
          The requested route does not exist or has been moved. You can return home, report waste, or track a complaint.
        </p>

        <div className="pt-2 space-y-2">
          <Link to="/" className="w-full py-3 rounded-xl bg-[#005C2B] text-white font-extrabold text-xs flex items-center justify-center gap-2 hover:bg-[#004a22] transition-colors">
            <Home className="w-4 h-4" /> Back to Home
          </Link>
          <Link to="/track" className="w-full py-2 text-xs font-bold text-slate-500 hover:text-[#005C2B] block">
            Track Existing Complaint
          </Link>
        </div>
      </div>
    </div>
  );
}
