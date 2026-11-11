import React, { useState, useEffect } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import CitizenPortalLogin from './CitizenPortalLogin';
import DriverPortalLogin from './DriverPortalLogin';
import CollectorPortalLogin from './CollectorPortalLogin';
import ForgotPasswordModal from './ForgotPasswordModal';
import { UserCheck, Truck, ShoppingBag, UserPlus } from 'lucide-react';

const ThreePortalLogins = ({ onSuccess }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialPortalParam = searchParams.get('portal');
  const initialPortal = ['citizen', 'driver', 'collector'].includes(initialPortalParam) 
    ? initialPortalParam 
    : 'citizen';

  const [activePortal, setActivePortal] = useState(initialPortal);
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false);

  useEffect(() => {
    if (initialPortalParam && ['citizen', 'driver', 'collector'].includes(initialPortalParam)) {
      setActivePortal(initialPortalParam);
    }
  }, [initialPortalParam]);

  return (
    <div className="w-full px-2 sm:px-4">
      
      {/* Ultra-Professional Centered Portal Selection Navbar */}
      <div className="w-full max-w-md sm:max-w-lg mx-auto mb-5 sm:mb-6">
        
        {/* Sleek 3-Equal-Column Glassmorphism Pill Selector */}
        <div className="p-1.5 bg-white/95 backdrop-blur-xl rounded-2xl border border-slate-200/90 shadow-md grid grid-cols-3 gap-1 w-full select-none">
          
          {/* Tab 1: Citizen Portal */}
          <button
            type="button"
            onClick={() => setActivePortal('citizen')}
            className={`py-2 sm:py-2.5 px-2 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              activePortal === 'citizen'
                ? 'bg-[#16a34a] text-white shadow-md scale-[1.01]'
                : 'text-slate-600 hover:text-[#16a34a] hover:bg-emerald-50/80'
            }`}
          >
            <UserCheck className="w-4 h-4 shrink-0" />
            <span className="truncate">Citizen</span>
          </button>

          {/* Tab 2: Driver Portal */}
          <button
            type="button"
            onClick={() => setActivePortal('driver')}
            className={`py-2 sm:py-2.5 px-2 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              activePortal === 'driver'
                ? 'bg-[#2563eb] text-white shadow-md scale-[1.01]'
                : 'text-slate-600 hover:text-[#2563eb] hover:bg-blue-50/80'
            }`}
          >
            <Truck className="w-4 h-4 shrink-0" />
            <span className="truncate">Driver</span>
          </button>

          {/* Tab 3: Admin Portal */}
          <button
            type="button"
            onClick={() => setActivePortal('collector')}
            className={`py-2 sm:py-2.5 px-2 rounded-xl text-xs font-black transition-all flex items-center justify-center gap-1.5 cursor-pointer ${
              activePortal === 'collector'
                ? 'bg-[#ea580c] text-white shadow-md scale-[1.01]'
                : 'text-slate-600 hover:text-[#ea580c] hover:bg-orange-50/80'
            }`}
          >
            <ShoppingBag className="w-4 h-4 shrink-0" />
            <span className="truncate">Admin</span>
          </button>

        </div>

        {/* Sub-header Navigation Link */}
        <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 px-2 mt-2">
          <span>Select municipal role portal</span>
          <Link to="/signup" className="text-[#005C2B] hover:underline font-black flex items-center gap-1">
            <UserPlus className="w-3 h-3" />
            <span>Need an account? Create Your Account →</span>
          </Link>
        </div>

        {/* Evaluator Quick Demo Sandbox Banner */}
        <div className="mt-2 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200/80 flex items-center justify-between text-xs font-bold text-emerald-800">
          <span className="flex items-center gap-1.5">
            <span>✨</span>
            <span>Auditor or Council Evaluator?</span>
          </span>
          <Link to="/demo" className="text-emerald-700 hover:text-emerald-900 underline font-black">
            1-Click Instant Demo →
          </Link>
        </div>
      </div>

      {/* Single Active Portal Card View */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activePortal}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -15 }}
          transition={{ duration: 0.3 }}
          className="grid grid-cols-1 max-w-md sm:max-w-lg mx-auto"
        >
          {activePortal === 'citizen' && (
            <div className="w-full flex flex-col">
              <CitizenPortalLogin
                onSuccess={onSuccess}
                onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}
                onSwitchToSignup={() => navigate('/signup')}
              />
            </div>
          )}

          {activePortal === 'driver' && (
            <div className="w-full flex flex-col">
              <DriverPortalLogin
                onSuccess={onSuccess}
                onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}
              />
            </div>
          )}

          {activePortal === 'collector' && (
            <div className="w-full flex flex-col">
              <CollectorPortalLogin
                onSuccess={onSuccess}
                onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}
              />
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      {/* Forgot Password Modal */}
      <ForgotPasswordModal
        isOpen={isForgotPasswordOpen}
        onClose={() => setIsForgotPasswordOpen(false)}
        onBackToLogin={() => setIsForgotPasswordOpen(false)}
      />
    </div>
  );
};

export default ThreePortalLogins;
