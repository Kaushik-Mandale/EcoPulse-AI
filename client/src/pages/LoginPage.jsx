import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, ShieldCheck, Leaf } from 'lucide-react';
import ThreePortalLogins from '../components/auth/ThreePortalLogins';

const LoginPage = () => {
  const navigate = useNavigate();

  const handleSuccess = (user) => {
    localStorage.setItem('ecopulse_user', JSON.stringify(user));
    if (user?.role === 'driver') {
      navigate('/driver');
    } else if (user?.role === 'admin' || user?.role === 'collector') {
      navigate('/admin');
    } else {
      navigate('/citizen');
    }
  };

  return (
    <div className="min-h-screen w-full relative flex flex-col justify-between items-center p-3 sm:p-6 md:p-8 bg-[#f4faf6] font-sans selection:bg-[#005C2B] selection:text-white overflow-x-hidden">
      
      {/* Background Graphic Overlay (/background_1.png) */}
      <div
        className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-90 pointer-events-none"
        style={{ backgroundImage: `url('/background_1.png')` }}
      />

      {/* Soft Backdrop Gradient */}
      <div className="absolute inset-0 z-0 bg-gradient-to-br from-white/90 via-white/80 to-emerald-50/60 pointer-events-none" />

      {/* Ambient Floating Glow Orbs */}
      <motion.div
        animate={{ scale: [1, 1.15, 1], opacity: [0.3, 0.5, 0.3] }}
        transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute top-10 left-1/4 w-80 h-80 bg-orange-400/15 rounded-full blur-3xl pointer-events-none"
      />
      <motion.div
        animate={{ scale: [1.15, 1, 1.15], opacity: [0.3, 0.5, 0.3] }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute bottom-10 right-1/4 w-96 h-96 bg-[#005C2B]/15 rounded-full blur-3xl pointer-events-none"
      />

      {/* Top Header Navigation */}
      <header className="w-full max-w-[1480px] relative z-10 flex items-center justify-between py-2 mb-4 sm:mb-6">
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="w-10 h-10 bg-[#005C2B] rounded-2xl flex items-center justify-center text-white shadow-md group-hover:scale-105 transition-transform">
            <svg className="w-6 h-6 fill-current" viewBox="0 0 24 24">
              <path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
            </svg>
          </div>
          <div>
            <div className="text-xl font-black text-slate-900 tracking-tight leading-none">
              EcoPulse AI
            </div>
            <div className="text-[10px] font-bold text-emerald-700 tracking-wide mt-0.5">
              Smart Civic & Sustainability Ecosystem
            </div>
          </div>
        </Link>

        <Link
          to="/"
          className="inline-flex items-center gap-2 bg-white/90 hover:bg-white backdrop-blur-md px-4 py-2 rounded-2xl text-xs font-bold text-slate-700 border border-slate-200 shadow-xs hover:text-[#005C2B] transition-all cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Home</span>
        </Link>
      </header>

      {/* Main Container displaying all 3 login components */}
      <main className="w-full max-w-[1480px] relative z-10 my-auto py-2">
        <ThreePortalLogins onSuccess={handleSuccess} />
      </main>

      {/* Dedicated Page Footer */}
      <footer className="w-full max-w-[1480px] relative z-10 text-center py-4 mt-6 text-xs font-bold text-slate-500 border-t border-slate-200/60">
        <div className="flex items-center justify-center gap-4 mb-1">
          <span className="inline-flex items-center gap-1 text-[#005C2B]">
            <Leaf className="w-3.5 h-3.5" /> 100% Eco-Certified
          </span>
          <span>•</span>
          <span className="inline-flex items-center gap-1 text-[#d9531e]">
            <ShieldCheck className="w-3.5 h-3.5" /> Municipal Sanitation Prototype
          </span>
        </div>
        <p className="text-[11px] text-slate-400 font-semibold">
          © 2026 EcoPulse AI • Smart Civic & Sustainability Ecosystem
        </p>
      </footer>

    </div>
  );
};

export default LoginPage;
