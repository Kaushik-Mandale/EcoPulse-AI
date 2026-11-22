import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, Sparkles, Shield } from 'lucide-react';
import LoginForm from './LoginForm';
import SignupForm from './SignupForm';
import ForgotPasswordModal from './ForgotPasswordModal';

const AuthLayout = ({ initialMode = 'login', onSuccessNavigation }) => {
  const [activeTab, setActiveTab] = useState(initialMode); // 'login' | 'signup'
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false);
  const [activeRole, setActiveRole] = useState('citizen');

  useEffect(() => {
    setActiveTab(initialMode);
  }, [initialMode]);

  // Determine illustration asset based on selected role or mode
  const getRoleIllustration = () => {
    if (activeRole === 'driver') return '/driver.png';
    if (activeRole === 'collector') return '/admin.png';
    return '/complete-right.png';
  };

  return (
    <div className="relative min-h-screen w-full flex flex-col justify-between overflow-x-hidden bg-[#f4faf6] font-sans selection:bg-[#005C2B] selection:text-white">
      {/* Background Image (/background_1.png) */}
      <div
        className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-95 pointer-events-none"
        style={{ backgroundImage: `url('/background_1.png')` }}
      />

      {/* Soft Gradient Overlay */}
      <div className="absolute inset-0 z-0 bg-gradient-to-br from-white/90 via-white/75 to-emerald-50/60 pointer-events-none" />

      {/* Glowing Ambient Light Orbs */}
      <motion.div
        animate={{
          scale: [1, 1.15, 1],
          opacity: [0.3, 0.5, 0.3],
        }}
        transition={{ duration: 8, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute top-10 -left-20 w-96 h-96 bg-[#005C2B]/15 rounded-full blur-3xl pointer-events-none"
      />
      <motion.div
        animate={{
          scale: [1.15, 1, 1.15],
          opacity: [0.2, 0.4, 0.2],
        }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute bottom-10 -right-20 w-[500px] h-[500px] bg-sky-400/15 rounded-full blur-3xl pointer-events-none"
      />

      {/* Top Header */}
      <header className="relative z-20 w-full px-6 md:px-12 py-5 max-w-[1340px] mx-auto flex items-center justify-between">
        <a href="/" className="flex items-center gap-3 group">
          <div className="w-[42px] h-[42px] bg-[#005C2B] rounded-xl flex items-center justify-center text-white shadow-xs group-hover:scale-105 transition-transform">
            <svg className="w-6 h-6 fill-current" viewBox="0 0 24 24">
              <path d="M20 8h-3V4H3c-1.1 0-2 .9-2 2v11h2c0 1.66 1.34 3 3 3s3-1.34 3-3h6c0 1.66 1.34 3 3 3s3-1.34 3-3h2v-5l-3-4zM6 18.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm13.5-9l1.96 2.5H17V9.5h2.5zm-1.5 9c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
            </svg>
          </div>
          <div>
            <div className="text-[20px] font-black text-gray-900 tracking-tight leading-none">
              EcoPulse AI
            </div>
            <div className="text-[11px] font-semibold text-gray-500 tracking-wide mt-1">
              Smart Waste Management
            </div>
          </div>
        </a>

        <a
          href="/"
          className="inline-flex items-center gap-2 bg-white/90 backdrop-blur-md px-4 py-2 rounded-xl text-xs font-bold text-gray-700 border border-gray-200/80 shadow-2xs hover:bg-white hover:text-[#005C2B] hover:shadow-xs transition-all cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Landing Page</span>
        </a>
      </header>

      {/* Main Split Sliding Card Container */}
      <main className="relative z-20 flex-1 flex items-center justify-center p-4 sm:p-6 md:p-8">
        <div className="w-full max-w-5xl relative">
          
          {/* Main Card */}
          <div className="bg-white/85 backdrop-blur-2xl border border-white/90 rounded-[32px] shadow-[0_30px_70px_-15px_rgba(0,92,43,0.22),0_10px_30px_rgba(0,0,0,0.06)] overflow-hidden grid grid-cols-1 lg:grid-cols-12 min-h-[640px]">
            
            {/* ------------------------------------------------------------- */}
            {/* PANEL 1: FORM PANEL                                           */}
            {/* When Login: RIGHT side (lg:order-2)                           */}
            {/* When Signup: LEFT side (lg:order-1)                          */}
            {/* ------------------------------------------------------------- */}
            <motion.div
              layout
              transition={{ type: 'spring', damping: 28, stiffness: 220 }}
              className={`lg:col-span-7 p-6 sm:p-8 md:p-10 flex flex-col justify-between relative bg-white/90 ${
                activeTab === 'login' ? 'lg:order-2' : 'lg:order-1'
              }`}
            >
              {/* Top Tab Switcher */}
              <div className="mb-6 p-1 bg-gray-100/90 rounded-2xl flex items-center border border-gray-200/80 max-w-xs mx-auto lg:mx-0">
                <button
                  type="button"
                  onClick={() => setActiveTab('login')}
                  className={`relative flex-1 py-2 px-4 rounded-xl text-xs font-black transition-all cursor-pointer z-10 ${
                    activeTab === 'login' ? 'text-[#005C2B]' : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {activeTab === 'login' && (
                    <motion.div
                      layoutId="split-tab-pill"
                      className="absolute inset-0 bg-white rounded-xl shadow-xs border border-emerald-100"
                      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span className="relative z-10">Sign In</span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab('signup')}
                  className={`relative flex-1 py-2 px-4 rounded-xl text-xs font-black transition-all cursor-pointer z-10 ${
                    activeTab === 'signup' ? 'text-[#005C2B]' : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {activeTab === 'signup' && (
                    <motion.div
                      layoutId="split-tab-pill"
                      className="absolute inset-0 bg-white rounded-xl shadow-xs border border-emerald-100"
                      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span className="relative z-10">Create Account</span>
                </button>
              </div>

              {/* Form Content with Animation */}
              <AnimatePresence mode="wait">
                {activeTab === 'login' ? (
                  <motion.div
                    key="split-login-form"
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -20 }}
                    transition={{ duration: 0.25 }}
                  >
                    <LoginForm
                      onSwitchToSignup={() => setActiveTab('signup')}
                      onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}
                      onRoleChange={setActiveRole}
                      onSuccess={onSuccessNavigation}
                    />
                  </motion.div>
                ) : (
                  <motion.div
                    key="split-signup-form"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 20 }}
                    transition={{ duration: 0.25 }}
                  >
                    <SignupForm
                      onSwitchToLogin={() => setActiveTab('login')}
                      onRoleChange={setActiveRole}
                      onSuccess={onSuccessNavigation}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            {/* ------------------------------------------------------------- */}
            {/* PANEL 2: VISUAL & INFO PANEL                                  */}
            {/* When Login: LEFT side (lg:order-1)                            */}
            {/* When Signup: RIGHT side (lg:order-2)                           */}
            {/* ------------------------------------------------------------- */}
            <motion.div
              layout
              transition={{ type: 'spring', damping: 28, stiffness: 220 }}
              className={`lg:col-span-5 p-8 md:p-10 bg-gradient-to-br from-[#003816] via-[#005C2B] to-[#007a33] text-white flex flex-col justify-between relative overflow-hidden ${
                activeTab === 'login' ? 'lg:order-1' : 'lg:order-2'
              }`}
            >
              {/* Background Asset Overlay (/background_3.png) */}
              <div
                className="absolute inset-0 z-0 bg-no-repeat bg-cover bg-center opacity-30 mix-blend-overlay pointer-events-none"
                style={{ backgroundImage: `url('/background_3.png')` }}
              />

              {/* Ambient Glowing Orbs */}
              <div className="absolute -top-16 -left-16 w-48 h-48 bg-emerald-400/20 rounded-full blur-2xl pointer-events-none" />
              <div className="absolute -bottom-16 -right-16 w-48 h-48 bg-sky-400/20 rounded-full blur-2xl pointer-events-none" />

              <div className="relative z-10 space-y-6">
                {/* Top Badge */}
                <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-md px-3.5 py-1.5 rounded-full text-xs font-bold text-emerald-200 border border-white/15">
                  <Sparkles className="w-3.5 h-3.5 text-emerald-300" />
                  <span>{activeTab === 'login' ? 'Welcome Back' : 'Join EcoPulse AI'}</span>
                </div>

                {/* Info Heading */}
                <div>
                  <h3 className="text-2xl sm:text-3xl font-black leading-snug tracking-tight text-white">
                    {activeTab === 'login'
                      ? 'Citizen Reporting and Municipal Operations'
                      : 'Report Waste and Follow Complaint Updates'}
                  </h3>
                  <p className="text-xs sm:text-sm font-medium text-emerald-100/90 mt-2 leading-relaxed">
                    Connect citizens, drivers, and municipal teams through one platform.
                  </p>
                </div>

                {/* Feature Bullets */}
                <ul className="space-y-3 pt-2 text-xs font-semibold text-emerald-50">
                  <li className="flex items-center gap-2.5">
                    <div className="w-5 h-5 rounded-full bg-emerald-400/20 text-emerald-300 flex items-center justify-center font-bold text-[10px] shrink-0 border border-emerald-400/30">
                      ✓
                    </div>
                    <span>Web Reporting • Configured WhatsApp Workflows</span>
                  </li>
                  <li className="flex items-center gap-2.5">
                    <div className="w-5 h-5 rounded-full bg-emerald-400/20 text-emerald-300 flex items-center justify-center font-bold text-[10px] shrink-0 border border-emerald-400/30">
                      ✓
                    </div>
                    <span>Assigned Driver Tasks</span>
                  </li>
                  <li className="flex items-center gap-2.5">
                    <div className="w-5 h-5 rounded-full bg-emerald-400/20 text-emerald-300 flex items-center justify-center font-bold text-[10px] shrink-0 border border-emerald-400/30">
                      ✓
                    </div>
                    <span>Check Complaint Status</span>
                  </li>
                </ul>
              </div>

              {/* Main Center/Bottom Illustration Asset */}
              <div className="relative z-10 my-6 flex justify-center items-center">
                <motion.img
                  key={activeTab}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.3 }}
                  src={getRoleIllustration()}
                  alt="EcoPulse AI Smart Waste Illustration"
                  className="w-full max-w-[260px] h-auto object-contain drop-shadow-[0_15px_30px_rgba(0,0,0,0.35)]"
                />
              </div>

              {/* Platform summary */}
              <div className="relative z-10 pt-4 border-t border-emerald-700/50">
                <p className="text-[11px] font-medium text-emerald-100/80 italic leading-snug">
                  Citizen reports and municipal operations in one connected platform.
                </p>
              </div>
            </motion.div>

          </div>

        </div>
      </main>

      {/* Bottom Footer */}
      <footer className="relative z-20 w-full py-4 text-center text-xs font-semibold text-gray-500">
        © 2026 EcoPulse AI • Smart Waste Management Platform
      </footer>

      {/* Forgot Password Modal */}
      <ForgotPasswordModal
        isOpen={isForgotPasswordOpen}
        onClose={() => setIsForgotPasswordOpen(false)}
        onBackToLogin={() => setIsForgotPasswordOpen(false)}
      />
    </div>
  );
};

export default AuthLayout;
